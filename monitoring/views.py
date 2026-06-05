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
    ForecastSnapshotSerializer,
)
from monitoring.collector import update_last_seen
from alerts.models import ForecastSnapshot


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
    FastAPI 가짜 데이터 생성기 → Django DB 저장 (Redis 미사용 시 fallback)
    """
    device_uid = request.data.get('device_uid')
    if not Device.objects.filter(device_uid=device_uid).exists():
        return Response({'error': f'장비 없음: {device_uid}'}, status=404)

    from monitoring.services import process_gas_ingest
    process_gas_ingest(device_uid, dict(request.data))
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
def ingest_power(request):
    """POST /monitoring/api/power-readings/ — process_power_ingest 위임.

    Phase D M1-7 (2026-05-23): HTTP·Celery 공용 진입점으로 위임 (gas 패턴).
    PowerReading INSERT + STEP B (load_rate 알람) + STEP G (forecast 큐) 위임.
    """
    device_uid   = request.data.get('device_uid')
    channel_code = request.data.get('channel_code')

    if not Device.objects.filter(device_uid=device_uid).exists():
        return Response({'error': f'장비 없음: {device_uid}'}, status=404)
    if not DeviceChannel.objects.filter(
        device__device_uid=device_uid, channel_code=channel_code,
    ).exists():
        return Response({'error': f'채널 없음: {channel_code}'}, status=404)

    from monitoring.services import process_power_ingest
    process_power_ingest(device_uid, channel_code, dict(request.data))
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

    # 1:1 연결된 Device(loc) 의 last_seen_at 동기 갱신
    # — 노드 관리 페이지의 "마지막 데이터 수신" 표시 및 MISSING 알람 활성화의 기반
    if node.device_id:
        update_last_seen(node.device)

    return Response({'status': 'ok'})


# ── API ViewSets (DRF JSON 데이터) ─────────────────────────

# ── 'AI 예측' 탭 조회 상수·헬퍼 ────────────────────────────

FORECAST_PAST_POINTS = 60   # 'AI 예측' 차트에 표시할 과거 실측 개수
GAS_CHANNEL_CODES = ["co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"]

@api_view(['GET'])
@permission_classes([AllowAny])
def app_config(request):
    """GET /monitoring/api/app-config/ — 프론트엔드에 필요한 Django settings 값을 반환."""
    from django.conf import settings
    return Response({
        'DEFAULT_POWER_RATED_W': settings.DEFAULT_POWER_RATED_W,
    })


# Phase D M2-1 — 전력 'AI 예측' 탭의 sensor 순서 (PowerReading 컬럼명 매핑)
POWER_SENSOR_TYPES = ["voltage", "current", "power"]
_POWER_SENSOR_TO_FIELD = {
    "voltage": "voltage_v",
    "current": "current_a",
    "power":   "power_w",
}


def _median_interval(readings, default=60):
    """연속 측정 간격(초)의 중앙값 — ETA 스텝→분 환산용. 2개 미만이면 default."""
    if len(readings) < 2:
        return default
    deltas = sorted(
        (readings[i].measured_at - readings[i - 1].measured_at).total_seconds()
        for i in range(1, len(readings))
    )
    mid = deltas[len(deltas) // 2]
    return int(mid) if mid > 0 else default


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

    @action(detail=True, methods=["get"])
    def forecast(self, request, pk=None):
        """GET /api/devices/{id}/forecast/ - 'AI 예측' 탭용 채널별 예측 데이터.

        가스 9채널별로 (1) 과거 실측 시계열과 (2) ForecastSnapshot의 예측
        곡선·2축 등급을 결합해 반환한다. 예측 곡선은 STEP G(forecast worker)
        가 채운다 — 워밍업/예측불가 구간은 forecast_mean이 null.
        """
        device   = self.get_object()
        readings = list(
            GasReading.objects.filter(device=device)
            .order_by("-measured_at")[:FORECAST_PAST_POINTS]
        )
        readings.reverse()  # 과거 → 현재 순

        snapshots = {
            snap.sensor_type: snap
            for snap in ForecastSnapshot.objects.filter(device=device)
        }

        channels = []
        for ch in GAS_CHANNEL_CODES:
            snap = snapshots.get(ch)
            ch_data = (
                ForecastSnapshotSerializer(snap).data if snap is not None
                else {
                    "sensor_type": ch, "updated_at": None,
                    "headline_severity": None, "headline_confidence": "UNKNOWN",
                    "caution_confidence": "UNKNOWN", "danger_confidence": "UNKNOWN",
                    "caution_eta_step": None, "danger_eta_step": None,
                    "path": "unknown", "forecast_steps": 0, "reason": "예측 미생성",
                    "forecast_mean": None, "ci_lower": None, "ci_upper": None,
                }
            )
            ch_data["past"] = [
                {"t": r.measured_at.isoformat(), "v": getattr(r, ch, None)}
                for r in readings
            ]
            channels.append(ch_data)

        return Response({
            "device_uid":       device.device_uid,
            "interval_seconds": _median_interval(readings),
            "channels":         channels,
        })


class DeviceChannelViewSet(viewsets.ModelViewSet):
    """채널 CRUD API"""
    queryset         = DeviceChannel.objects.select_related("device").all()
    serializer_class = DeviceChannelSerializer
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ["device", "status", "is_active", "channel_code"]

    @action(detail=True, methods=["get"])
    def forecast(self, request, pk=None):
        """GET /api/channels/{id}/forecast/ — 전력 'AI 예측' 탭용 sensor별 예측.

        Phase D M2-1 (2026-05-23) — gas의 DeviceViewSet.forecast()와 동일 패턴,
        단 channel 단위로 분리 (power 데이터 모델 부합).

        전력 3 sensor(voltage·current·power)별로:
            (1) 과거 실측 시계열 (PowerReading의 voltage_v / current_a / power_w)
            (2) ForecastSnapshot의 예측 곡선·2축 등급 (channel별 row)
        을 결합해 반환한다. 예측 곡선은 STEP G(forecast worker)가 채운다 —
        워밍업/예측불가 구간은 forecast_mean이 null.
        """
        channel = self.get_object()
        device  = channel.device

        readings = list(
            PowerReading.objects.filter(device=device, channel=channel)
            .order_by("-measured_at")[:FORECAST_PAST_POINTS]
        )
        readings.reverse()  # 과거 → 현재 순

        snapshots = {
            snap.sensor_type: snap
            for snap in ForecastSnapshot.objects.filter(device=device, channel=channel)
        }

        sensors = []
        for sensor_type in POWER_SENSOR_TYPES:
            snap = snapshots.get(sensor_type)
            sensor_data = (
                ForecastSnapshotSerializer(snap).data if snap is not None
                else {
                    "sensor_type":         sensor_type,
                    "channel_code":        channel.channel_code,
                    "updated_at":          None,
                    "headline_severity":   None,
                    "headline_confidence": "UNKNOWN",
                    "caution_confidence":  "UNKNOWN",
                    "danger_confidence":   "UNKNOWN",
                    "caution_eta_step":    None,
                    "danger_eta_step":     None,
                    "path":                "unknown",
                    "forecast_steps":      0,
                    "reason":              "예측 미생성",
                    "forecast_mean":       None,
                    "ci_lower":            None,
                    "ci_upper":            None,
                }
            )
            field_name = _POWER_SENSOR_TO_FIELD[sensor_type]
            sensor_data["past"] = [
                {"t": r.measured_at.isoformat(), "v": getattr(r, field_name, None)}
                for r in readings
            ]
            sensors.append(sensor_data)

        return Response({
            "device_uid":       device.device_uid,
            "channel_code":     channel.channel_code,
            "channel_name":     channel.channel_name,
            "rated_power_w":    channel.rated_power_w,
            "interval_seconds": _median_interval(readings),
            "sensors":          sensors,
        })


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
