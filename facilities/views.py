from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView


from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.views      import View
from .models import (
    Facility, Building, Floor, FloorGrid, IndexGrid,
    Zone,  Geofence, LocationNode, Worker, WorkerLocation, Equipment
   
)
from .serializers import (
    FacilitySerializer, BuildingSerializer, FloorSerializer,
    FloorGridSerializer,
    ZoneSerializer, LocationNodeSerializer,
    WorkerSerializer, WorkerLocationSerializer,
    GeofenceSerializer,
    WorkerLocationLatestSerializer, EquipmentSerializer
)
from .services.floor_grid_maker    import FloorGridService
from .repositories import IndexGridWriter, IndexGridReader



@login_required(login_url="login")
def worker_list(request):
    return render(request, "facilities/worker_list.html")

class DashboardTempleteView(TemplateView):
    template_name = 'dashboard.html'


def monitoring_view(request):
    """
    실시간 모니터링 메인 화면.
    사업장/건물/층 목록을 컨텍스트로 전달하여 셀렉트박스를 구성한다.
    """
    facilities = Facility.objects.filter(status='active').order_by('facility_name')
    context = {
        'facilities': facilities,
    }
    return render(request, 'map/map_monitoring.html', context)


class FacilityViewSet(viewsets.ModelViewSet):
    queryset = Facility.objects.all().order_by('facility_name')
    serializer_class = FacilitySerializer


class BuildingViewSet(viewsets.ModelViewSet):
    serializer_class = BuildingSerializer

    def get_queryset(self):
        qs = Building.objects.all()
        facility_id = self.request.query_params.get('facility_id')
        if facility_id:
            qs = qs.filter(facility_id=facility_id)
        return qs.order_by('building_name')


class FloorViewSet(viewsets.ModelViewSet):
    serializer_class = FloorSerializer

    def get_queryset(self):
        qs = Floor.objects.all()
        building_id = self.request.query_params.get('building_id')
        if building_id:
            qs = qs.filter(building_id=building_id)
        return qs.order_by('floor_no')

@method_decorator(csrf_exempt, name='dispatch')
class FloorGridSetupView(View):
    """
    Grid 생성 및 DB 저장.

    POST /facilities/floors/<floor_id>/setup/

    흐름:
        1. Floor 조회       → 없으면 404
        2. FloorGrid 조회   → 없으면 cell_size=1.0으로 생성
        3. 셀 목록 계산     → FloorGridService.generate_all_cells()
        4. DB 저장          → IndexGridWriter.bulk_create()
        5. 응답             → {"created": 셀 수}

    멱등성:
        이미 저장된 셀은 skip (ignore_conflicts=True)
        같은 floor_id로 중복 호출해도 안전
    """

    def post(self, request, floor_id):

        # 1. Floor 조회
        floor = get_object_or_404(Floor, id=floor_id)

        # 2. FloorGrid 조회 또는 생성
        #    floor.grid 없으면 RelatedObjectDoesNotExist 발생
        #    → get_or_create로 방어
        FloorGrid.objects.get_or_create(
            floor=floor,
            defaults={"cell_size": 1.0}
        )

        # 3. 셀 목록 계산
        service = FloorGridService(floor)
        cells   = service.generate_all_cells()

        # 4. DB 저장
        writer  = IndexGridWriter()
        writer.bulk_create(floor, cells)

        # 5. 응답
        return JsonResponse({"created": len(cells)})
    
class FloorGridViewSet(viewsets.ModelViewSet):
    """
    FloorGrid CRUD — cell_size 설정값 관리

    엔드포인트:
        GET    /api/floor-grids/?floor_id=<id>  — 격자 설정 조회
        POST   /api/floor-grids/                — 직접 생성 (관리자용)
        PATCH  /api/floor-grids/<id>/           — cell_size 수정
        DELETE /api/floor-grids/<id>/           — 삭제

    격자선 렌더링용 데이터:
        GET /api/floors/<id>/grid-data/ 사용 (floor_grid_data 함수)
    """
    serializer_class = FloorGridSerializer

    def get_queryset(self):
        qs = FloorGrid.objects.all()
        floor_id = self.request.query_params.get('floor_id')
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        return qs

def floor_grid_data(request, floor_id):
    """
    GET /api/floors/<floor_id>/grid-data/

    IndexGrid DB 기반 격자 정보 반환.
    JS는 받은 값 그대로 렌더링만 수행. 연산 없음.

    Single Source of Truth: IndexGrid DB
    → JS 격자선, 각 앱 인덱스 모두 동일한 기준

    선행 조건:
        /floors/<floor_id>/setup/ 으로 IndexGrid 생성 완료 필요
        미생성 시 400 반환

    좌표계: meter (floor.width, floor.length 기준)
    Leaflet bounds: [[0, 0], [floor.length, floor.width]]

    반환:
    {
        "floor_id":  1,
        "width":     10,
        "length":    5,
        "cell_size": 1.0,
        "cols":      10,
        "rows":      5,
        "lines": {
            "vertical":   [{"x": 0,   "y1": 0, "y2": 5}, ...],
            "horizontal": [{"y": 0,   "x1": 0, "x2": 10}, ...]
        }
    }
    """
    floor = get_object_or_404(Floor, pk=floor_id)

    # IndexGrid DB 조회 — Single Source of Truth
    cells = IndexGridReader().get_full_grid(floor)
    if not cells:
        return JsonResponse(
            {"error": "IndexGrid 없음. /floors/{floor_id}/setup/ 먼저 호출 필요"},
            status=400
        )

    # cell_size 조회
    try:
        cell_size = float(floor.grid.cell_size)
    except Exception:
        cell_size = 1.0

    width  = float(floor.width)
    length = float(floor.length)

    # cols, rows: Floor 모델이 아닌 DB 실제값 기준
    cols = max(cell.col for cell in cells) + 1
    rows = max(cell.row for cell in cells) + 1

    return JsonResponse({
        "floor_id":  floor.id,
        "width":     width,
        "length":    length,
        "cell_size": cell_size,
        "cols":      cols,
        "rows":      rows,
        "floor_image": request.build_absolute_uri(floor.plan_image.url) if floor.plan_image else None,  # ← 추가
        "lines": {
            "vertical": [
                {"x": round(c * cell_size, 6), "y1": 0, "y2": length}
                for c in range(cols + 1)
            ],
            "horizontal": [
                {"y": round(r * cell_size, 6), "x1": 0, "x2": width}
                for r in range(rows + 1)
            ],
        }
    })
class ZoneViewSet(viewsets.ModelViewSet):
    """
    Zone CRUD.
    GET /api/zones/?floor_id=<id>  로 특정 층의 구역 목록을 조회한다.
    프론트에서 셀 드래그 완료 후 POST 로 저장한다.
    """
    serializer_class = ZoneSerializer

    def get_queryset(self):
        qs = Zone.objects.all()
        floor_id = self.request.query_params.get('floor_id')
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        return qs.order_by('zone_name')


class LocationNodeViewSet(viewsets.ModelViewSet):
    serializer_class = LocationNodeSerializer

    def get_queryset(self):
        qs = LocationNode.objects.all()
        zone_id = self.request.query_params.get('zone_id')
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs


class WorkerViewSet(viewsets.ModelViewSet):
    queryset = Worker.objects.all().order_by('worker_name')
    serializer_class = WorkerSerializer


class WorkerLocationViewSet(viewsets.ModelViewSet):
    """
    WorkerLocation CRUD + 시뮬레이션용 더미 엔드포인트.

    GET  /api/worker-locations/dummy/
         → 작업자별 최신 위치 1건씩 반환 (프론트 setInterval 폴링 대상)

    POST /api/worker-locations/dummy/
         → 특정 작업자의 위치를 직접 업데이트한다 (curl 주입 테스트용)
         Body: { "worker_id": 1, "x": 200, "y": 300, "cell_no": "3-5" }
    """
    serializer_class = WorkerLocationSerializer

    def get_queryset(self):
        qs = WorkerLocation.objects.select_related('worker')
        floor_id = self.request.query_params.get('floor_id')
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        return qs.order_by('-measured_at')

    @action(detail=False, methods=['get', 'post'], url_path='dummy')
    def dummy(self, request):
        if request.method == 'GET':
            workers = Worker.objects.filter(current_state='on_duty')
            result  = []

            for worker in workers:
                loc = worker.locations.order_by('-measured_at').first()
                if not loc:
                    continue

                # floor 없으면 snap 변환 불가 → skip
                if not loc.floor:
                    continue

                # x, y → grid_index
                service    = FloorGridService(loc.floor)
                grid_index = service.get_grid_index(loc.x, loc.y)

                # 유효하지 않은 좌표 → skip
                if grid_index is None:
                    continue

                # grid_index → snap_x, snap_y
                snap = service.get_snap_point(grid_index)

                # 기존 직렬화 + snap, grid_index 추가
                data               = WorkerLocationLatestSerializer(loc).data
                data['grid_index'] = grid_index
                data['snap_x']     = snap['snap_x']
                data['snap_y']     = snap['snap_y']

                result.append(data)

            return Response(result)

        # POST — curl 로 위치 주입
        worker_id = request.data.get('worker_id')
        if not worker_id:
            return Response(
                {'error': 'worker_id 필요'},
                status=status.HTTP_400_BAD_REQUEST
            )

        worker = get_object_or_404(Worker, pk=worker_id)
        loc    = WorkerLocation.objects.create(
            worker   = worker,
            x        = request.data.get('x', 0),
            y        = request.data.get('y', 0),
            z        = request.data.get('z', 0),
            cell_no  = request.data.get('cell_no', ''),
            floor_id = request.data.get('floor_id'),
            zone_id  = request.data.get('zone_id'),
        )
        return Response(
            WorkerLocationSerializer(loc).data,
            status=status.HTTP_201_CREATED
        )

class GeofenceViewSet(viewsets.ModelViewSet):
    """
    Geofence CRUD.
    PATCH /api/geofences/<id>/  로 center_x / center_y / radius 를 업데이트하면
    프론트에서 CSS transition 으로 원이 부드럽게 이동/확산한다.
    """
    serializer_class = GeofenceSerializer

    def get_queryset(self):
        qs = Geofence.objects.all()
        floor_id = self.request.query_params.get('floor_id')
        is_active = self.request.query_params.get('is_active')
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active in ['true', '1', 'True'])
        return qs.order_by('-severity')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def worker_safety_status(request):
    """
    GET /facilities/api/workers/safety-status/
    현재 근무 중인 전체 작업자 + 오늘 안전확인 완료 여부 반환
    """
    from safety.models import SafetyCheckSession
    from django.utils import timezone

    today = timezone.localdate()
    workers = Worker.objects.filter(current_state='on_duty').order_by('worker_name')

    result = []
    for w in workers:
        session = SafetyCheckSession.objects.filter(worker=w, check_date=today).first()
        result.append({
            'id':          w.id,
            'worker_name': w.worker_name,
            'safety_done': session.checklist_completed if session else False,
        })
    return Response(result)


class EquipmentViewSet(viewsets.ModelViewSet):
    serializer_class = EquipmentSerializer

    def get_queryset(self):
        qs = Equipment.objects.all()
        
        floor_id   = self.request.query_params.get('floor_id')
        zone_id    = self.request.query_params.get('zone_id')
        is_placed  = self.request.query_params.get('is_placed')
        status     = self.request.query_params.get('status')

        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if is_placed is not None:
            qs = qs.filter(is_placed=is_placed in ['true', '1', 'True'])
        if status:
            qs = qs.filter(status=status)

        return qs.order_by('equipment_code')


