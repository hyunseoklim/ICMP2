from rest_framework import viewsets, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.views.generic import TemplateView
from django.utils import timezone

from monitoring.models import (
    Device,
    DeviceChannel,
    DeviceStatusLog,
    GasReading,
    PowerStatusReading,
    PowerReading,
    NodeReading,
    ThresholdPolicy,
    InspectionLog,
    ActionLog,
)
from monitoring.serializers import (
    DeviceSerializer,
    DeviceChannelSerializer,
    DeviceStatusLogSerializer,
    GasReadingSerializer,
    PowerStatusReadingSerializer,
    PowerReadingSerializer,
    ThresholdPolicySerializer,
    InspectionLogSerializer,
    ActionLogSerializer,
)
from monitoring.collector import update_last_seen


# ── Template Views (HTML 렌더링) ───────────────────────────

class MonitoringDashboardView(TemplateView):
    """실시간 모니터링 대시보드"""
    template_name = "monitoring/dashboard.html"


class GasSensorManageView(TemplateView):
    """유해가스 센서 관리 페이지"""
    template_name = "monitoring/gas_detail.html"


class PowerSystemManageView(TemplateView):
    """스마트 전력 시스템 관리 페이지"""
    template_name = "monitoring/power_detail.html"


# ── Ingest API (FastAPI → Django 데이터 수신) ──────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def ingest_gas(request):
    """
    POST /ingest/gas/
    FastAPI 가짜 데이터 생성기 → Django DB 저장
    """
    device_uid = request.data.get('device_uid')
    device = Device.objects.filter(device_uid=device_uid).first()
    if not device:
        return Response({'error': f'장비 없음: {device_uid}'}, status=404)

    raw = request.data
    gas_fields = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']
    values = {f: raw.get(f) for f in gas_fields}

    missing_count = sum(1 for v in values.values() if v is None)
    if missing_count == len(gas_fields):
        quality_flag = 'missing'
    elif missing_count > 0:
        quality_flag = 'partial'
    else:
        quality_flag = 'ok'

    measured_at_raw = raw.get('measured_at')
    if measured_at_raw:
        from django.utils.dateparse import parse_datetime
        measured_at = parse_datetime(measured_at_raw) or timezone.now()
    else:
        measured_at = timezone.now()

    reading = GasReading.objects.create(
        device=device,
        **values,
        measured_at=measured_at,
        quality_flag=quality_flag,
        raw_payload=dict(raw),
    )
    update_last_seen(device)

    from monitoring.anomaly.window import push as window_push
    window_push(device.device_uid, reading)

    from alerts.services import check_gas_thresholds
    check_gas_thresholds(device, reading)

    from monitoring.anomaly.zscore import analyze as zscore_analyze
    from alerts.services import trigger_anomaly_alarms
    zscore_results = zscore_analyze(device.device_uid, reading)
    trigger_anomaly_alarms(device, zscore_results)

    from monitoring.anomaly.changepoint import detect as cp_detect
    from alerts.services import trigger_changepoint_alarms
    cp_results = cp_detect(device.device_uid, reading)
    trigger_changepoint_alarms(device, cp_results)

    # ─── sensor WebSocket broadcast ───────────────────────
    try:
        from facilities.models import SensorLocation
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from monitoring.services import calc_danger_level

        sensor = SensorLocation.objects.filter(
            device_id = device.id,
            is_active = True,
        ).first()

        if sensor:
            level_kr = calc_danger_level(reading)
            status = {
                '위험': 'danger',
                '주의': 'warning',
                '정상': 'normal',
            }.get(level_kr, 'normal')

            payload = {
                'id':          sensor.id,
                'device_id':   device.id,
                'sensor_type': sensor.sensor_type,
                'x':           float(sensor.x),
                'y':           float(sensor.y),
                'device_name': sensor.device_name,
                'is_active':   sensor.is_active,
                'status':      status,
                'latest_value': {
                    'co':  reading.co,
                    'h2s': reading.h2s,
                    'co2': reading.co2,
                    'o2':  reading.o2,
                    'no2': reading.no2,
                    'so2': reading.so2,
                    'o3':  reading.o3,
                    'nh3': reading.nh3,
                    'voc': reading.voc,
                },
            }

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'floor_{sensor.floor_id}_sensor',
                {
                    'type':     'sensor.update',
                    'msg_type': 'delta',
                    'data':     [payload],
                },
            )
    except Exception as e:
        print(f'[sensor_ws] broadcast 실패: {e}')
    # ─── sensor WebSocket broadcast 끝 ────────────────────
        # ─── geofence 자동 생성/갱신/삭제 ───────────────────────
    # 가스 위험도(danger/warning/safe) 기반으로 geofence 자동 처리
    # safe: 기존 geofence 비활성화 / danger,warning: 생성 또는 갱신
    try:
        from facilities.services.geofence_service import update_geofence_from_gas
        update_geofence_from_gas(reading)
    except Exception as e:
        print(f'[geofence] 업데이트 실패: {e}')
    # ─── geofence 끝 ─────────────────────────────────────

    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
def ingest_power(request):
    """
    POST /ingest/power/
    FastAPI 가짜 데이터 생성기 → Django DB 저장
    """
    device_uid   = request.data.get('device_uid')
    channel_code = request.data.get('channel_code')

    device = Device.objects.filter(device_uid=device_uid).first()
    if not device:
        return Response({'error': f'장비 없음: {device_uid}'}, status=404)

    channel = DeviceChannel.objects.filter(
        device=device, channel_code=channel_code
    ).first()
    if not channel:
        return Response({'error': f'채널 없음: {channel_code}'}, status=404)

    raw = request.data
    measured_at_raw = raw.get('measured_at')
    if measured_at_raw:
        from django.utils.dateparse import parse_datetime
        power_measured_at = parse_datetime(measured_at_raw) or timezone.now()
    else:
        power_measured_at = timezone.now()

    current_a = raw.get('current_a', -1)
    voltage_v = raw.get('voltage_v', -1)
    power_w   = raw.get('power_w',   -1)

    power_fields = [current_a, voltage_v, power_w]
    if all(v == -1 for v in power_fields):
        quality_flag = 'comm_err'
    elif any(v == -1 for v in power_fields):
        quality_flag = 'partial'
    else:
        quality_flag = 'ok'

    PowerReading.objects.create(
        device=device,
        channel=channel,
        current_a=current_a,
        voltage_v=voltage_v,
        power_w=power_w,
        measured_at=power_measured_at,
        quality_flag=quality_flag,
        raw_payload=dict(raw),
    )
    update_last_seen(device)

    from alerts.services import check_power_thresholds
    check_power_thresholds(device, channel, float(request.data.get('power_w', 0)))

    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
def ingest_node(request):
    """
    POST /monitoring/api/node-readings/
    FastAPI 노드 수신 시뮬레이션 → Django DB 저장
    """
    from facilities.models import LocationNode

    node_code = request.data.get('node_code')
    node = LocationNode.objects.filter(node_code=node_code).first()
    if not node:
        return Response({'error': f'노드 없음: {node_code}'}, status=404)

    NodeReading.objects.create(
        node=node,
        x=request.data.get('x'),
        y=request.data.get('y'),
        received_at=timezone.now(),
    )
    return Response({'status': 'ok'})


# ── API ViewSets (DRF JSON 데이터) ─────────────────────────

class DeviceViewSet(viewsets.ModelViewSet):
    """
    장비 CRUD API
    - list:   GET  /api/devices/
    - create: POST /api/devices/
    - retrieve: GET /api/devices/{id}/
    - update: PUT  /api/devices/{id}/
    - destroy: DELETE /api/devices/{id}/
    """
    queryset         = Device.objects.select_related(
        "facility", "building", "floor", "zone", "department", "manager"
    ).all()
    serializer_class = DeviceSerializer
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["device_type", "status", "is_active"]
    search_fields    = ["device_uid", "device_name"]
    ordering_fields  = ["last_seen_at", "device_name"]

    @action(detail=True, methods=["get"])
    def channels(self, request, pk=None):
        """GET /api/devices/{id}/channels/ - 해당 장비의 채널 목록"""
        device     = self.get_object()
        channels   = DeviceChannel.objects.filter(device=device)
        serializer = DeviceChannelSerializer(channels, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def latest_gas(self, request, pk=None):
        """GET /api/devices/{id}/latest_gas/ - 해당 장비의 최신 가스 측정값"""
        device   = self.get_object()
        reading  = GasReading.objects.filter(device=device).order_by('-measured_at').first()
        if not reading:
            return Response({"detail": "측정값 없음"}, status=404)
        serializer = GasReadingSerializer(reading)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def latest_power(self, request, pk=None):
        """GET /api/devices/{id}/latest_power/ - 해당 장비의 채널별 최신 전력값"""
        device   = self.get_object()
        readings = PowerReading.objects.filter(device=device).select_related("channel").order_by('-measured_at')[:200]

        # 채널별 최신값만
        latest = {}
        for r in readings:
            code = r.channel.channel_code
            if code not in latest:
                latest[code] = r
        serializer = PowerReadingSerializer(latest.values(), many=True)
        return Response(serializer.data)
    
    # @action(detail=True, methods=["get"])
    # def latest_power(self, request, pk=None):
    #     """GET /api/devices/{id}/latest_power/ - 해당 장비의 채널별 최신 전력값"""
    #     device = self.get_object()
        
    #     # [수정] DB 단에서 채널별로 가장 최신의 데이터 1개씩만 쿼리해 옵니다. (PostgreSQL 전용)
    #     # 만약 SQLite나 MySQL을 쓴다면 방식이 달라져야 함!!
    #     latest_readings = PowerReading.objects.filter(device=device) \
    #         .select_related("channel") \
    #         .order_by("channel", "-measured_at") \
    #         .distinct("channel")
            
    #     serializer = PowerReadingSerializer(latest_readings, many=True)
    #     return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def status_logs(self, request, pk=None):
        """GET /api/devices/{id}/status_logs/ - 해당 장비의 상태 이력"""
        device     = self.get_object()
        logs       = DeviceStatusLog.objects.filter(device=device)
        serializer = DeviceStatusLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def inspections(self, request, pk=None):
        """GET /api/devices/{id}/inspections/ - 해당 장비의 점검 이력"""
        device     = self.get_object()
        logs       = InspectionLog.objects.filter(device=device)
        serializer = InspectionLogSerializer(logs, many=True)
        return Response(serializer.data)


class DeviceChannelViewSet(viewsets.ModelViewSet):
    """채널 CRUD API"""
    queryset         = DeviceChannel.objects.select_related("device").all()
    serializer_class = DeviceChannelSerializer
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ["device", "status", "is_active", "channel_code"]


class DeviceStatusLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    장비 상태 이력 API (읽기 전용)
    상태 이력은 시스템이 자동 생성, 직접 수정 불가
    """
    queryset         = DeviceStatusLog.objects.select_related("device").all()
    serializer_class = DeviceStatusLogSerializer
    filter_backends  = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["device", "status_code"]
    ordering_fields  = ["occurred_at"]


class GasReadingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    가스 측정값 API (읽기 전용)
    측정값은 FastAPI가 저장, 직접 수정 불가
    """
    queryset         = GasReading.objects.select_related("device").all()
    serializer_class = GasReadingSerializer
    filter_backends  = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["device"]
    ordering_fields  = ["measured_at"]


class PowerStatusReadingViewSet(viewsets.ReadOnlyModelViewSet):
    """전력 ON/OFF 상태 API (읽기 전용)"""
    queryset         = PowerStatusReading.objects.select_related("device", "channel").all()
    serializer_class = PowerStatusReadingSerializer
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ["device", "channel"]


class PowerReadingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    전력 측정값 API (읽기 전용)
    측정값은 FastAPI가 저장, 직접 수정 불가
    """
    queryset         = PowerReading.objects.select_related("device", "channel").all()
    serializer_class = PowerReadingSerializer
    filter_backends  = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["device", "channel"]
    ordering_fields  = ["measured_at"]


class ThresholdPolicyViewSet(viewsets.ModelViewSet):
    """임계치 정책 CRUD API"""
    queryset         = ThresholdPolicy.objects.all()
    serializer_class = ThresholdPolicySerializer
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ["is_active", "action_type"]


class InspectionLogViewSet(viewsets.ModelViewSet):
    """점검 이력 CRUD API"""
    queryset         = InspectionLog.objects.select_related(
        "device", "inspector"
    ).all()
    serializer_class = InspectionLogSerializer
    filter_backends  = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["device", "inspection_type", "status"]
    ordering_fields  = ["inspection_date"]

    @action(detail=True, methods=["get"])
    def action_log(self, request, pk=None):
        """GET /api/inspections/{id}/action_log/ - 해당 점검의 조치 이력"""
        inspection = self.get_object()
        try:
            log        = inspection.action
            serializer = ActionLogSerializer(log)
            return Response(serializer.data)
        except ActionLog.DoesNotExist:
            return Response({"detail": "조치 이력 없음"}, status=404)


class ActionLogViewSet(viewsets.ModelViewSet):
    """조치 이력 CRUD API"""
    queryset         = ActionLog.objects.select_related(
        "inspection", "actor"
    ).all()
    serializer_class = ActionLogSerializer
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ["inspection"]
