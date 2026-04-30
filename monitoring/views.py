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

    reading = GasReading.objects.create(
        device=device,
        co=request.data.get('co', 0),
        h2s=request.data.get('h2s', 0),
        co2=request.data.get('co2', 0),
        o2=request.data.get('o2', 0),
        no2=request.data.get('no2', 0),
        so2=request.data.get('so2', 0),
        o3=request.data.get('o3', 0),
        nh3=request.data.get('nh3', 0),
        voc=request.data.get('voc', 0),
        measured_at=timezone.now(),
    )
    update_last_seen(device)

    from alerts.services import check_gas_thresholds
    check_gas_thresholds(device, reading)

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

    PowerReading.objects.create(
        device=device,
        channel=channel,
        current_a=request.data.get('current_a', 0),
        voltage_v=request.data.get('voltage_v', 0),
        power_w=request.data.get('power_w', 0),
        measured_at=timezone.now(),
    )
    update_last_seen(device)

    from alerts.services import check_power_thresholds
    check_power_thresholds(device, channel, float(request.data.get('power_w', 0)))

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
        readings = PowerReading.objects.filter(device=device).order_by('-measured_at')
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
