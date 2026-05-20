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

    comm_err = all(v is not None and float(v) == -1 for v in values.values())
    missing_count = sum(1 for v in values.values() if v is None)
    if comm_err:
        quality_flag = 'comm_err'
    elif missing_count == len(gas_fields):
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

    from monitoring.anomaly.window import push as window_push, _buffers, init_from_db as window_init
    window_push(device.device_uid, reading)
    # 서버 재시작 후 첫 수신 시 DB에서 버퍼를 채움 (최소 10개 미만이면 보충)
    if len(_buffers.get(device.device_uid, {}).get('co', [])) < 10:
        window_init(device.device_uid)

    from alerts.services import check_gas_thresholds
    check_gas_thresholds(device, reading)

    from monitoring.anomaly.zscore import analyze as zscore_analyze
    from alerts.services import trigger_anomaly_alarms
    zscore_results = zscore_analyze(device.device_uid, reading)
    trigger_anomaly_alarms(device, zscore_results)

    # STEP E: Change Point detection
    try:
        from monitoring.anomaly.changepoint import analyze as cp_analyze
        from alerts.services import trigger_changepoint_alarms
        cp_results = cp_analyze(device.device_uid, reading)
        if cp_results:
            trigger_changepoint_alarms(device, cp_results)
    except Exception as _e:
        pass

    # STEP F: Isolation Forest
    try:
        from monitoring.anomaly.isolation import analyze as iso_analyze
        from alerts.services import trigger_isolation_alarm
        iso_result = iso_analyze(device.device_uid, reading)
        if iso_result.get('is_anomaly'):
            trigger_isolation_alarm(device, iso_result)
    except Exception as _e:
        pass

    # STEP G: ARIMA 예측 — 백그라운드 스레드로 실행
    # Celery 워커는 별도 프로세스라 _latest 캐시를 공유 못 함.
    # daemon 스레드는 같은 프로세스 메모리를 공유하므로 get_latest()에서 읽힘.
    try:
        import threading
        import django.db

        _uid     = device.device_uid
        _reading = reading
        _device  = device

        def _arima_bg():
            try:
                from monitoring.anomaly.arima import analyze as arima_analyze
                from alerts.services import trigger_arima_alarms
                results = arima_analyze(_uid, _reading)
                if results:
                    trigger_arima_alarms(_device, results)
            finally:
                django.db.close_old_connections()

        threading.Thread(target=_arima_bg, daemon=True).start()
    except Exception as _e:
        pass

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

    # 전력 슬라이딩 윈도우 + ARIMA 예측 (백그라운드 스레드)
    if quality_flag == 'ok' and float(power_w) >= 0:
        rated = float(channel.rated_power_w or 1000)
        load_ratio = float(power_w) / rated * 100

        from monitoring.anomaly.power_window import push as pw_push
        pw_push(device_uid, channel_code, load_ratio)

        # Z-score 통계 이상탐지 (동기 — 빠름)
        try:
            from monitoring.anomaly.power_zscore import analyze as pz_analyze
            from alerts.services import check_power_zscore_alarms
            zs_result = pz_analyze(device_uid, channel_code, load_ratio)
            check_power_zscore_alarms(device, channel, zs_result)
        except Exception:
            pass

        # Change Point 탐지 (동기 — 빠름)
        try:
            from monitoring.anomaly.power_changepoint import analyze as pcp_analyze
            from alerts.services import trigger_power_changepoint_alarms
            cp_result = pcp_analyze(device_uid, channel_code, load_ratio)
            trigger_power_changepoint_alarms(device, channel, cp_result)
        except Exception:
            pass

        # ARIMA 예측 (백그라운드 스레드 — 느림)
        try:
            import threading
            import django.db

            _uid, _ch_code, _rated = device_uid, channel_code, rated

            def _power_arima_bg():
                try:
                    from monitoring.anomaly.power_arima import analyze as pa_analyze
                    pa_analyze(_uid, _ch_code, _rated)
                finally:
                    django.db.close_old_connections()

            threading.Thread(target=_power_arima_bg, daemon=True).start()
        except Exception:
            pass

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


# ── AI 상태 API ───────────────────────────────────────────

@api_view(['GET'])
def ai_gas_status(request):
    """
    GET /monitoring/api/ai-status/
    메모리에 캐시된 각 장비별 최신 AI 분석 결과 반환.
    FastAPI가 데이터를 보내는 즉시 갱신되므로 폴링에 적합.
    """
    from monitoring.anomaly.zscore import get_latest as zs_latest
    from monitoring.anomaly.changepoint import get_latest as cp_latest
    from monitoring.anomaly.isolation import get_latest as iso_latest
    from monitoring.anomaly.arima import get_latest as arima_latest, get_latest_forecasts as arima_forecasts

    devices = Device.objects.filter(device_type='gas', is_active=True).values(
        'id', 'device_uid', 'device_name', 'status', 'last_seen_at'
    )

    _STATUS_PRIORITY = (
        'CHANGE_POINT_ALERT', 'ISOLATION_ANOMALY', 'CRITICAL',
        'ANOMALY_WARNING', 'PREDICTIVE_WARNING',
        'CHANGE_POINT_WARNING', 'CHANGE_POINT_VARIANCE',
        'NORMAL', 'INSUFFICIENT_DATA',
    )

    def _worst(items):
        statuses = {r.get('final_status', 'NORMAL') for r in (items if isinstance(items, list) else [items])}
        for s in _STATUS_PRIORITY:
            if s in statuses:
                return s
        return 'NORMAL'

    result = []
    for d in devices:
        uid = d['device_uid']
        zs   = zs_latest(uid)
        cp   = cp_latest(uid)
        iso  = iso_latest(uid)
        ar   = arima_latest(uid)
        ar_fc = arima_forecasts(uid)

        result.append({
            'device_uid':   uid,
            'device_name':  d['device_name'],
            'status':       d['status'],
            'last_seen_at': d['last_seen_at'].isoformat() if d['last_seen_at'] else None,
            'zscore': {
                'status':    _worst(zs),
                'anomalies': [r for r in zs if r['final_status'] not in ('NORMAL',)],
            },
            'changepoint': {
                'status':  _worst(cp),
                'details': cp,
            },
            'isolation': {
                'status':   iso.get('final_status', 'NORMAL') if iso else 'NORMAL',
                'score':    iso.get('score') if iso else None,
                'is_anomaly': iso.get('is_anomaly', False) if iso else False,
            },
            'arima': {
                'status':      _worst(ar),
                'predictions': ar,
                'forecasts':   ar_fc,  # gas → [v1,v2,v3,v4,v5] 전체 예측값 (차트용)
            },
        })

    return Response({
        'updated_at': timezone.now().isoformat(),
        'devices':    result,
    })


@api_view(['GET'])
def power_history(request):
    """
    GET /monitoring/api/power-history/?device_id={id}&limit={n}
    채널별 최근 N개 전력 측정값 반환 (시계열 AI 예측 차트용)
    """
    device_id = request.query_params.get('device_id')
    limit = min(int(request.query_params.get('limit', 30)), 100)

    if not device_id:
        return Response({'error': 'device_id required'}, status=400)

    channels = DeviceChannel.objects.filter(device_id=device_id, is_active=True)
    result = {}

    for ch in channels:
        readings = list(
            PowerReading.objects
            .filter(channel=ch, quality_flag='ok', power_w__gte=0)
            .order_by('-measured_at')[:limit]
        )
        readings.reverse()
        rated = ch.rated_power_w or 1000
        result[ch.channel_code] = {
            'channel_name': ch.channel_name or ch.channel_code,
            'rated_w':      rated,
            'readings': [
                {
                    'power_w':    r.power_w,
                    'load_ratio': round(r.power_w / rated * 100, 1),
                    'measured_at': r.measured_at.isoformat(),
                }
                for r in readings
            ],
        }

    return Response(result)


@api_view(['GET'])
def gas_history(request):
    """
    GET /monitoring/api/gas-history/?device_id={id}&limit={n}
    최근 N개 가스 측정값 반환 (시계열 AI 예측 차트용, 시간순 정렬)
    """
    device_id = request.query_params.get('device_id')
    limit = min(int(request.query_params.get('limit', 30)), 100)

    if not device_id:
        return Response({'error': 'device_id required'}, status=400)

    readings = list(
        GasReading.objects
        .filter(device_id=device_id, quality_flag='ok')
        .order_by('-measured_at')[:limit]
    )
    readings.reverse()
    serializer = GasReadingSerializer(readings, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def ai_power_status(request):
    """
    GET /monitoring/api/ai-power-status/
    전력 장비별 채널 과부하 분석 (룰 기반).
    최근 수신된 채널별 PowerReading에서 rated_power_w 대비 사용률 계산.
    """
    from monitoring.models import PowerReading, DeviceChannel
    from datetime import timedelta

    stale_cutoff = timezone.now() - timedelta(minutes=30)  # 30분 이내면 유효
    devices = Device.objects.filter(device_type='power', is_active=True)

    result = []
    for device in devices:
        channels = DeviceChannel.objects.filter(device=device, is_active=True)

        ch_stats = []
        total_power = 0
        overload_count = 0

        for ch in channels:
            # 시간 제한 없이 가장 최신 값 조회 (단, 30분 초과면 stale 표시)
            r = (
                PowerReading.objects
                .filter(channel=ch, power_w__gte=0)
                .order_by('-measured_at')
                .first()
            )
            if not r:
                continue
            is_stale = r.measured_at < stale_cutoff

            rated   = ch.rated_power_w or 1000
            ratio   = round(r.power_w / rated * 100, 1)
            total_power += r.power_w

            if ratio >= 100:
                ch_status = 'DANGER'
                overload_count += 1
            elif ratio >= 80:
                ch_status = 'WARNING'
            else:
                ch_status = 'NORMAL'

            from monitoring.anomaly.power_arima       import get_latest as pa_latest
            from monitoring.anomaly.power_zscore      import get_latest as pz_latest
            from monitoring.anomaly.power_changepoint import get_latest as pcp_latest
            arima  = pa_latest(device.device_uid, ch.channel_code)
            zscore = pz_latest(device.device_uid, ch.channel_code)
            cp     = pcp_latest(device.device_uid, ch.channel_code)

            ch_stats.append({
                'channel_code': ch.channel_code,
                'channel_name': ch.channel_name or ch.channel_code,
                'power_w':      r.power_w,
                'rated_w':      rated,
                'ratio':        ratio,
                'status':       ch_status,
                'is_stale':     is_stale,
                'zscore': {
                    'final_status': zscore['final_status'] if zscore else 'NORMAL',
                    'z_score':      zscore['z_score']      if zscore else None,
                    'mean':         zscore['mean']         if zscore else None,
                },
                'arima': {
                    'forecast':   arima['forecast']   if arima else None,
                    'eta_warn':   arima['eta_warn']   if arima else None,
                    'eta_danger': arima['eta_danger'] if arima else None,
                    'max_load':   arima['max_load']   if arima else None,
                },
                'changepoint': {
                    'final_status':     cp['final_status']     if cp else 'NORMAL',
                    'mean_shift_score': cp['mean_shift_score'] if cp else None,
                    'std_ratio':        cp['std_ratio']        if cp else None,
                    'direction':        cp['direction']        if cp else None,
                },
            })

        if overload_count > 0:
            dev_status = 'DANGER'
        elif any(c['status'] == 'WARNING' for c in ch_stats):
            dev_status = 'WARNING'
        elif ch_stats:
            dev_status = 'NORMAL'
        else:
            dev_status = 'NO_DATA'

        result.append({
            'device_uid':    device.device_uid,
            'device_name':   device.device_name,
            'status':        dev_status,
            'total_power_w': total_power,
            'overload_count': overload_count,
            'channel_count':  len(ch_stats),
            'channels':      sorted(ch_stats, key=lambda x: x['ratio'], reverse=True)[:5],
        })

    return Response({
        'updated_at': timezone.now().isoformat(),
        'devices':    result,
    })

