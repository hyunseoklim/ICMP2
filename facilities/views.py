import json
import logging

from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.views      import View
from .models import (
    Facility, Building, Floor, FloorGrid, IndexGrid,
    Zone, Geofence, LocationNode, Worker, WorkerLocation, Equipment,
    SensorLocation
)
from safety.models import SafetyCheckSession

from .serializers import (
    FacilitySerializer, BuildingSerializer, FloorSerializer,
    FloorGridSerializer,
    ZoneSerializer, LocationNodeSerializer,
    WorkerSerializer, WorkerLocationSerializer,
    GeofenceSerializer,
    WorkerLocationLatestSerializer, EquipmentSerializer,
    SensorLocationSerializer
)
from .cache import INDEX_GRID_TTL, floor_grid_response_cache_key
from .services.floor_grid_maker    import FloorGridService, setup_index_grid_for_floor
from .repositories import IndexGridWriter, IndexGridReader



@login_required(login_url="login")
def worker_list(request):
   # on_duty 작업자만 표시 (현재 현장 출입자 기준)
    workers = Worker.objects.select_related('user', 'department').filter(current_state='on_duty').order_by('worker_name')
    today = timezone.localdate()

    today_sessions = {
        s.worker_id: s
        for s in SafetyCheckSession.objects.filter(check_date=today)
    }

    for worker in workers:
        worker.today_session = today_sessions.get(worker.pk)

    context = {
        'workers': workers,
        'worker_stats': {
            'total':   workers.count(),
            'checkin': workers.filter(current_state='on_duty').count(),
            'danger':  workers.filter(safety_status='danger').count(),
            'warning': workers.filter(safety_status='warning').count(),
            'safe':    workers.filter(safety_status='safe').count(),
        }
    }
    return render(request, "facilities/worker_list.html", context)

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
        floor = get_object_or_404(Floor, id=floor_id)
        count = setup_index_grid_for_floor(floor)
        # FloorGridSetupView는 Django View(=DRF APIView 아님) — DRF Response 반환 시
        # 렌더러 미설정으로 AssertionError. dev 변경을 흡수하되 이 줄만 JsonResponse 유지.
        return JsonResponse({"created": count})
    
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
    response_key = floor_grid_response_cache_key(floor_id)
    cached_body = cache.get(response_key)
    if cached_body is not None:
        return HttpResponse(cached_body, content_type="application/json")

    floor = get_object_or_404(Floor, pk=floor_id)

    grid = IndexGridReader().get_full_grid(floor)
    if grid["total"] == 0:
        return JsonResponse(
            {"error": f"IndexGrid 없음. /floors/{floor_id}/setup/ 먼저 호출 필요"},
            status=400,
        )

    try:
        cell_size = float(floor.grid.cell_size)
    except Exception:
        cell_size = 1.0

    width  = float(floor.width)
    length = float(floor.length)
    cols   = grid["cols"]
    rows   = grid["rows"]

    payload = {
        "floor_id":  floor.id,
        "width":     width,
        "length":    length,
        "cell_size": cell_size,
        "cols":      cols,
        "rows":      rows,
        "floor_image": request.build_absolute_uri(floor.plan_image.url) if floor.plan_image else None,
        "lines": {
            "vertical": [
                {"x": round(c * cell_size, 6), "y1": 0, "y2": length}
                for c in range(cols + 1)
            ],
            "horizontal": [
                {"y": round(r * cell_size, 6), "x1": 0, "x2": width}
                for r in range(rows + 1)
            ],
        },
    }

    body = json.dumps(payload)
    cache.set(response_key, body, INDEX_GRID_TTL)
    return HttpResponse(body, content_type="application/json")
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
        floor_id = self.request.query_params.get('floor_id')
        zone_id  = self.request.query_params.get('zone_id')
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs

    def perform_update(self, serializer):
        # T1-δ B1+C1+E3
        from core.services.change_log import capture_state, log_change
        before = capture_state(serializer.instance)
        instance = serializer.save()
        after = capture_state(instance)
        log_change(instance, before, after, 'update', self.request.user)

    def perform_destroy(self, instance):
        from core.services.change_log import capture_state, log_change
        before = capture_state(instance)
        log_change(instance, before, None, 'delete', self.request.user)
        instance.delete()

class WorkerViewSet(viewsets.ModelViewSet):
    queryset = Worker.objects.all().order_by('worker_name')
    serializer_class = WorkerSerializer

    @action(detail=False, methods=['get'], url_path='safety-status')
    def safety_status(self, request):
        """
        GET /api/workers/safety-status/
        on_duty 작업자만 반환 + safety_status 포함
        """
        from django.utils import timezone
        from safety.models import SafetyCheckSession

        today = timezone.localdate()
        workers = Worker.objects.filter(current_state='on_duty').order_by('worker_name')

        result = []
        for w in workers:
            session = SafetyCheckSession.objects.filter(worker=w, check_date=today).first()
            result.append({
                'id':            w.id,
                'worker_name':   w.worker_name,
                'safety_status': w.safety_status,
                'safety_done':   session.checklist_completed if session else False,
            })
        return Response(result)

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
            from facilities.services.geofence_checker import sync_worker_status
            from monitoring.models import GasReading
            from facilities.services.geofence_service import update_geofence_from_gas

            # 1. 가스 센서 최신값 기반 Geofence 자동 갱신
            floor_id = request.query_params.get('floor_id')
            if floor_id:
                sensor_device_ids = SensorLocation.objects.filter(
                    floor_id=floor_id,
                    sensor_type='gas',
                    is_active=True,
                ).values_list('device_id', flat=True)

                for device_id in sensor_device_ids:
                    reading = GasReading.objects.filter(
                        device_id=device_id
                    ).order_by('-measured_at').first()
                    if reading:
                        try:
                            update_geofence_from_gas(reading)
                        except Exception as e:
                            logger.warning('[geofence_sync] device_id=%s 오류: %s', device_id, e)


            # 2. 현장 근무 중인 작업자 geofence 판단 (off_duty 제외)
            workers = Worker.objects.exclude(current_state='off_duty')
            result  = []

            for worker in workers:
                loc = worker.locations.order_by('-measured_at').first()
                if not loc:
                    continue
                if not loc.floor:
                    continue

                # 지오펜스 내부 판단 + Worker.current_state 업데이트
                worker_status = sync_worker_status(worker, loc)

                # x, y → grid_index
                service    = FloorGridService(loc.floor)
                grid_index = service.get_grid_index(loc.x, loc.y)
                if grid_index is None:
                    continue

                snap = service.get_snap_point(grid_index)

                data               = WorkerLocationLatestSerializer(loc).data
                data['grid_index'] = grid_index
                data['snap_x']     = snap['snap_x']
                data['snap_y']     = snap['snap_y']
                # worker_status를 판단 결과로 교체
                data['worker_status'] = worker_status

                result.append(data)

            return Response(result)

        # POST — curl 로 위치 주입
        worker_id = request.data.get('worker_id')
        if not worker_id:
            return Response(
                {'error': 'worker_id 필요'},
                status=status.HTTP_400_BAD_REQUEST
            )

        worker   = get_object_or_404(Worker, pk=worker_id)
        floor_id = request.data.get('floor_id')
        loc      = WorkerLocation.objects.create(
            worker   = worker,
            x        = request.data.get('x', 0),
            y        = request.data.get('y', 0),
            z        = request.data.get('z', 0),
            cell_no  = request.data.get('cell_no', ''),
            floor_id = floor_id,
            zone_id  = request.data.get('zone_id'),
        )

        # floor 에 연결된 WebSocket 클라이언트에 위치 broadcast
        if floor_id:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            from facilities.services.geofence_checker import sync_worker_status

            worker_status = sync_worker_status(worker, loc)

            service    = FloorGridService(loc.floor)
            grid_index = service.get_grid_index(loc.x, loc.y)
            snap       = service.get_snap_point(grid_index) if grid_index is not None else {'snap_x': loc.x, 'snap_y': loc.y}

            payload = {
                'worker_id':     worker.id,
                'worker_name':   worker.worker_name,
                'worker_status': worker_status,
                'x':             float(loc.x),
                'y':             float(loc.y),
                'snap_x':        snap['snap_x'],
                'snap_y':        snap['snap_y'],
                'grid_index':    grid_index,
                'measured_at':   loc.measured_at.isoformat(),
            }

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'floor_{floor_id}_worker',
                {'type': 'worker.update', 'msg_type': 'delta', 'data': [payload]},
            )

        return Response(
            WorkerLocationSerializer(loc).data,
            status=status.HTTP_201_CREATED
        )



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

    def perform_update(self, serializer):
        # T1-δ B1+C1+E3: 변경 이력 기록 (full snapshot before/after)
        from core.services.change_log import capture_state, log_change
        before = capture_state(serializer.instance)
        instance = serializer.save()
        after = capture_state(instance)
        log_change(instance, before, after, 'update', self.request.user)

    def perform_destroy(self, instance):
        from core.services.change_log import capture_state, log_change
        before = capture_state(instance)
        log_change(instance, before, None, 'delete', self.request.user)
        instance.delete()


class SensorLocationViewSet(viewsets.ModelViewSet):
    """
    센서 위치 CRUD.

    GET /api/sensor-locations/?floor_id=<id>
        → 해당 층의 활성 센서 위치 목록 반환
        → sensor.js 폴링 대상

    GET /api/sensor-locations/?floor_id=<id>&sensor_type=gas
        → 가스 센서만 필터링

    sensor.js가 참조하는 필드:
        id, device_id, sensor_type, x, y, device_name, is_active
    """
    serializer_class = SensorLocationSerializer

    def get_queryset(self):
        qs = SensorLocation.objects.all()
        floor_id    = self.request.query_params.get('floor_id')
        sensor_type = self.request.query_params.get('sensor_type')
        is_active   = self.request.query_params.get('is_active')

        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        if sensor_type:
            qs = qs.filter(sensor_type=sensor_type)
        if is_active is not None:
            qs = qs.filter(is_active=is_active in ['true', '1', 'True'])
        else:
            qs = qs.filter(is_active=True)  # 기본값: 활성 센서만

        return qs.order_by('sensor_type', 'id')

    def perform_update(self, serializer):
        # T1-δ B1+C1+E3
        from core.services.change_log import capture_state, log_change
        before = capture_state(serializer.instance)
        instance = serializer.save()
        after = capture_state(instance)
        log_change(instance, before, after, 'update', self.request.user)

    def perform_destroy(self, instance):
        from core.services.change_log import capture_state, log_change
        before = capture_state(instance)
        log_change(instance, before, None, 'delete', self.request.user)
        instance.delete()


class GeofenceViewSet(viewsets.ModelViewSet):
    """
    Geofence CRUD.
    PATCH /api/geofences/<id>/  로 center_x / center_y / radius 를 업데이트하면
    프론트에서 CSS transition 으로 원이 부드럽게 이동/확산한다.
    """
    serializer_class = GeofenceSerializer

    def get_queryset(self):
        qs = Geofence.objects.all()
        floor_id  = self.request.query_params.get('floor_id')
        is_active = self.request.query_params.get('is_active')
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active in ['true', '1', 'True'])
        return qs.order_by('-severity')

    def list(self, request, *args, **kwargs):
        floor_id = request.query_params.get('floor_id')
        if floor_id:
            self._sync_gas_geofences(floor_id)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        # T1-δ B1+C1+E3: create 도 기록 (Geofence 만 — frontend 가 직접 생성)
        from core.services.change_log import capture_state, log_change
        geofence = serializer.save()
        after = capture_state(geofence)
        log_change(geofence, None, after, 'create', self.request.user)
        self._broadcast(geofence, 'delta')

    def perform_update(self, serializer):
        from core.services.change_log import capture_state, log_change
        before = capture_state(serializer.instance)
        geofence = serializer.save()
        after = capture_state(geofence)
        log_change(geofence, before, after, 'update', self.request.user)
        self._broadcast(geofence, 'delta')

    def perform_destroy(self, instance):
        # soft-delete (is_active=False) — 사용자 의도는 delete 로 기록
        from core.services.change_log import capture_state, log_change
        before = capture_state(instance)
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        after = capture_state(instance)
        log_change(instance, before, after, 'delete', self.request.user)
        self._broadcast(instance, 'delta')

    def _broadcast(self, geofence, msg_type):
        from facilities.services.geofence_service import _broadcast_geofence
        _broadcast_geofence(geofence, msg_type)

    def _sync_gas_geofences(self, floor_id):
        from monitoring.models import GasReading
        from facilities.services.geofence_service import update_geofence_from_gas

        sensor_device_ids = SensorLocation.objects.filter(
            floor_id=floor_id,
            sensor_type='gas',
            is_active=True,
        ).values_list('device_id', flat=True)

        for device_id in sensor_device_ids:
            reading = GasReading.objects.filter(
                device_id=device_id
            ).order_by('-measured_at').first()

            if reading:
                try:
                    update_geofence_from_gas(reading)
                except Exception as e:
                    logger.warning('[geofence_sync] device_id=%s 오류: %s', device_id, e)


# ─────────────────────────────────────────────────────────────────────
# T1-ε: map editor bulk-save endpoint
# POST /facilities/api/map-editor/bulk-save/
# body: { equipment: {<pk>: {...}}, locationNode: {...}, sensor: {...}, geofence: {...} }
# B2 per-item: 객체별 독립 처리, 일부 실패 허용
# ChangeLog: 성공 row 만 기록 (T1-δ 와 일관)
# ─────────────────────────────────────────────────────────────────────
_BULK_CONFIG = {
    'equipment':    (Equipment,      EquipmentSerializer),
    'locationNode': (LocationNode,   LocationNodeSerializer),
    'sensor':       (SensorLocation, SensorLocationSerializer),
    'geofence':     (Geofence,       GeofenceSerializer),
}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_map_editor_save(request):
    """
    T1-ε: 지도 편집기의 일괄 저장 endpoint.
    per-item try/except — 일부 실패해도 나머지는 저장.
    """
    from core.services.change_log import capture_state, log_change

    payload = request.data or {}
    success_count = 0
    errors = []

    for category, (Model, Serializer) in _BULK_CONFIG.items():
        items = (payload.get(category) or {}).get('update') or payload.get(category) or {}
        # 양쪽 형식 지원: {<pk>: data} 또는 {update: {<pk>: data}}
        if not isinstance(items, dict):
            continue
        for pk, data in items.items():
            try:
                instance = Model.objects.get(pk=pk)
            except Model.DoesNotExist:
                errors.append({'type': category, 'pk': pk, 'errors': {'detail': 'Not found'}})
                continue
            serializer = Serializer(instance, data=data, partial=True)
            if not serializer.is_valid():
                errors.append({'type': category, 'pk': pk, 'errors': serializer.errors})
                continue
            try:
                before = capture_state(instance)
                instance = serializer.save()
                after = capture_state(instance)
                log_change(instance, before, after, 'update', request.user)
                success_count += 1
            except Exception as e:
                errors.append({'type': category, 'pk': pk, 'errors': {'detail': str(e)}})

    return Response({
        'success': success_count,
        'failed':  len(errors),
        'errors':  errors,
    }, status=status.HTTP_200_OK)