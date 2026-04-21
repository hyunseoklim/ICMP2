from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Facility, Building, Floor, FloorGrid,
    Zone, LocationNode, Worker, WorkerLocation,
    Geofence, SensorDummy,
)
from .serializers import (
    FacilitySerializer, BuildingSerializer, FloorSerializer, FloorGridSerializer,
    ZoneSerializer, LocationNodeSerializer, WorkerSerializer, WorkerLocationSerializer,
    GeofenceSerializer, SensorDummySerializer, WorkerLocationLatestSerializer,
)


# ─── 템플릿 뷰 ───────────────────────────────────────────────

def monitoring_view(request):
    """
    실시간 모니터링 메인 화면.
    사업장/건물/층 목록을 컨텍스트로 전달하여 셀렉트박스를 구성한다.
    """
    facilities = Facility.objects.filter(status='active').order_by('facility_name')
    context = {
        'facilities': facilities,
    }
    return render(request, 'test/monitoring.html', context)


# ─── DRF ViewSet ─────────────────────────────────────────────

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


class FloorGridViewSet(viewsets.ModelViewSet):
    """
    FloorGrid CRUD.
    GET /api/floor-grids/?floor_id=<id>  로 특정 층의 격자 설정을 조회한다.
    운영자가 cell_width / cell_height 를 변경하면 프론트에서 격자를 재렌더링한다.
    """
    serializer_class = FloorGridSerializer

    def get_queryset(self):
        qs = FloorGrid.objects.all()
        floor_id = self.request.query_params.get('floor_id')
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        return qs


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
            workers = Worker.objects.filter(status='on_duty')
            result = []
            for worker in workers:
                loc = worker.locations.order_by('-measured_at').first()
                if loc:
                    result.append(WorkerLocationLatestSerializer(loc).data)
            return Response(result)

        # POST — curl 로 위치 주입
        worker_id = request.data.get('worker_id')
        if not worker_id:
            return Response({'error': 'worker_id 필요'}, status=status.HTTP_400_BAD_REQUEST)

        worker = get_object_or_404(Worker, pk=worker_id)
        loc = WorkerLocation.objects.create(
            worker=worker,
            x=request.data.get('x', 0),
            y=request.data.get('y', 0),
            z=request.data.get('z', 0),
            cell_no=request.data.get('cell_no', ''),
            floor_id=request.data.get('floor_id'),
            zone_id=request.data.get('zone_id'),
        )
        return Response(WorkerLocationSerializer(loc).data, status=status.HTTP_201_CREATED)


class GeofenceViewSet(viewsets.ModelViewSet):
    """
    Geofence CRUD.
    PATCH /api/geofences/<id>/  로 center_x / center_y / radius 를 업데이트하면
    프론트에서 CSS transition 으로 원이 부드럽게 이동/확산한다.

    curl 예시:
    curl -X PATCH http://localhost:8000/api/geofences/1/ \\
         -H "Content-Type: application/json" \\
         -d '{"center_x": 280, "center_y": 210, "radius": 75}'
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


class SensorDummyViewSet(viewsets.ModelViewSet):
    """
    센서 더미 데이터 CRUD.

    curl 주입 예시:
    curl -X POST http://localhost:8000/api/sensors/ \\
         -H "Content-Type: application/json" \\
         -d '{"device_id":"G2","device_name":"G2 유해가스 센서",
              "sensor_type":"gas","x":400,"y":130,
              "status":"danger","latest_value":{"co":32,"o2":18.1}}'

    curl -X PATCH http://localhost:8000/api/sensors/1/ \\
         -H "Content-Type: application/json" \\
         -d '{"status":"warning","latest_value":{"co":15,"o2":19.5}}'
    """
    serializer_class = SensorDummySerializer

    def get_queryset(self):
        qs = SensorDummy.objects.all()
        floor_id = self.request.query_params.get('floor_id')
        sensor_type = self.request.query_params.get('sensor_type')
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        if sensor_type:
            qs = qs.filter(sensor_type=sensor_type)
        return qs.order_by('device_id')