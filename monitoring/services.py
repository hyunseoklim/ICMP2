import uuid
from datetime import timedelta

from django.utils import timezone


# ══════════════════════════════════════════════════════════
# 전력 수신 처리 파이프라인 (HTTP 뷰 & Celery 공용) — Phase D M1-6
# ══════════════════════════════════════════════════════════

def process_power_ingest(device_uid: str, channel_code: str, payload: dict) -> None:
    """전력 센서 데이터 1건 처리. HTTP·Celery 공용.

    gas의 process_gas_ingest 대칭. 단 STEP F (IF)는 Phase D 결정 (a)
    비활성 — STEP G (ARIMA 예측)만 진입. STEP F 활성화 결정 시
    monitoring/ai/power_if.py docstring 참조.

    Args:
        device_uid: 'PWR-001' 등.
        channel_code: 'slave01' 등.
        payload: {'current_a', 'voltage_v', 'power_w', 'measured_at'?}

    Flow:
        1. PowerReading INSERT (FloatField — Phase C-5 마이그레이션)
        2. STEP B — check_power_thresholds (Django load_rate 즉시 알람)
        3. STEP G — forecast_power_task.delay (forecast 큐 위임)
    """
    from monitoring.models import Device, DeviceChannel, PowerReading, DropLog, DetectionResult
    from monitoring.collector import update_last_seen

    # ── ① 유효성 게이트 (장비/채널 — 무음 드롭 금지) ──
    device = Device.objects.filter(device_uid=device_uid).first()
    if not device:
        DropLog.objects.create(device_uid=device_uid or '', reason='device_not_found', raw_payload=dict(payload))
        return
    if not device.is_active or device.status != 'active':
        DropLog.objects.create(device_uid=device_uid, reason='inactive', raw_payload=dict(payload))
        return
    channel = DeviceChannel.objects.filter(device=device, channel_code=channel_code).first()
    if not channel:
        DropLog.objects.create(device_uid=device_uid, reason='channel_not_found', raw_payload=dict(payload))
        return
    if not channel.is_active or channel.status != 'active':
        DropLog.objects.create(device_uid=device_uid, reason='channel_inactive', raw_payload=dict(payload))
        return

    # event_id 계보 — 원천 부여 우선, 없으면 경계 발급(실장비 대비)
    event_id = payload.get('event_id') or uuid.uuid4()
    tick_id  = payload.get('tick_id')   # 보류

    current_a = payload.get('current_a', -1.0)
    voltage_v = payload.get('voltage_v', -1.0)
    power_w   = payload.get('power_w',   -1.0)

    # ② 값 검증 — 원천이 검증했으면 신뢰, 아니면 경계 검증
    if 'quality_flag' in payload:
        quality_flag = payload['quality_flag']
    else:
        fields = [current_a, voltage_v, power_w]
        if all(v in (-1, -1.0) for v in fields):
            quality_flag = 'comm_err'
        elif any(v in (-1, -1.0) for v in fields):
            quality_flag = 'partial'
        else:
            quality_flag = 'ok'

    ts_fallback = False
    measured_at_raw = payload.get('measured_at')
    if measured_at_raw:
        from django.utils.dateparse import parse_datetime
        from django.utils.timezone import make_aware, is_aware
        parsed = parse_datetime(str(measured_at_raw))
        if parsed is None:
            measured_at = timezone.now(); ts_fallback = True
        elif not is_aware(parsed):
            measured_at = make_aware(parsed)
        else:
            measured_at = parsed
    else:
        measured_at = timezone.now(); ts_fallback = True

    PowerReading.objects.create(
        device=device, channel=channel,
        current_a=current_a, voltage_v=voltage_v, power_w=power_w,
        measured_at=measured_at, quality_flag=quality_flag,
        event_id=event_id, tick_id=tick_id, ts_fallback=ts_fallback,
        raw_payload=dict(payload),
    )
    update_last_seen(device)

    # ── ③ 단계별 판정 + DetectionResult 계보 + 알람 ──
    Stage = DetectionResult.Stage
    detections = []

    # STEP B — 부하율 임계 판정
    from alerts.services import check_power_thresholds
    check_power_thresholds(device, channel, float(power_w))
    rated_w = float(channel.rated_power_w or 1000)
    if power_w and float(power_w) > 0 and rated_w > 0:
        load_rate = (float(power_w) / rated_w) * 100
        level = '위험' if load_rate >= 75 else ('주의' if load_rate >= 50 else '정상')
        detections.append(DetectionResult(
            event_id=event_id, gas_reading=None, device=device,
            sensor_type=channel_code, stage=Stage.THRESHOLD,
            level=level, score=round(load_rate, 2),
            detail={'power_w': float(power_w), 'rated_w': rated_w, 'load_rate': round(load_rate, 2)},
        ))

    if detections:
        DetectionResult.objects.bulk_create(detections)

    # STEP G — ARIMA 예측 (forecast 큐 위임 — gas D2 아키텍처). event_id 전파 → ARIMA 계보는 forecast 태스크가 적재
    from alerts.tasks import forecast_power_task
    fpayload = dict(payload)
    fpayload['event_id'] = str(event_id)
    forecast_power_task.delay(device_uid, channel_code, fpayload)


# ══════════════════════════════════════════════════════════
# 가스 수신 처리 파이프라인 (HTTP 뷰 & Celery 공용)
# ══════════════════════════════════════════════════════════

GAS_FIELDS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']

# 물리적 sane-range (위반 = invalid 태깅, 버리지 않음)
GAS_VALID_RANGE = {
    'co': (0, 10000), 'h2s': (0, 1000), 'co2': (0, 50000),
    'o2':  (0, 30),   'no2': (0, 1000), 'so2': (0, 1000),
    'o3':  (0, 100),  'nh3': (0, 1000), 'voc': (0, 10000),
}


def _jsonable(d: dict) -> dict:
    """numpy/Decimal 등을 JSONField 저장 가능한 native 타입으로 정규화."""
    out = {}
    for k, v in d.items():
        if v is None or isinstance(v, (bool, str)):
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = float(v)
        else:
            out[k] = str(v)
    return out


def process_gas_ingest(device_uid: str, payload: dict) -> None:
    """
    가스 센서 데이터 1건 처리.
    HTTP ingest 뷰와 Celery Redis 소비자 양쪽에서 호출한다.

    payload 예시:
        {"device_uid": "GAS-001", "measured_at": "...", "co": 5.2, ...}
    """
    from monitoring.models import Device, GasReading, DropLog
    from monitoring.collector import update_last_seen

    # ── ① 유효성 게이트 (무음 드롭 금지 — 거부는 DropLog로 추적) ──
    device = Device.objects.filter(device_uid=device_uid).first()
    if not device:
        DropLog.objects.create(device_uid=device_uid or '', reason='device_not_found', raw_payload=dict(payload))
        return
    if not device.is_active or device.status != 'active':
        DropLog.objects.create(device_uid=device_uid, reason='inactive', raw_payload=dict(payload))
        return

    # event_id 계보 — 원천(FastAPI)이 부여했으면 사용, 없으면 ingest 경계 발급(실장비 대비)
    event_id = payload.get('event_id') or uuid.uuid4()
    tick_id  = payload.get('tick_id')   # 보류 — 교차 상관 필요 시 원천 부여(없으면 null)

    values = {f: payload.get(f) for f in GAS_FIELDS}
    # ② 값 검증 — 원천이 검증했으면 그 결과 신뢰, 아니면 경계에서 검증(실장비 fallback)
    if 'quality_flag' in payload:
        quality_flag = payload['quality_flag']
        violations = payload.get('violations', [])
    else:
        missing_count = sum(1 for v in values.values() if v is None)
        violations = [
            f for f, v in values.items()
            if v is not None and not (GAS_VALID_RANGE[f][0] <= float(v) <= GAS_VALID_RANGE[f][1])
        ]
        if violations:
            quality_flag = 'invalid'
        elif missing_count == len(GAS_FIELDS):
            quality_flag = 'missing'
        elif missing_count > 0:
            quality_flag = 'partial'
        else:
            quality_flag = 'ok'

    ts_fallback = False
    measured_at_raw = payload.get('measured_at')
    if measured_at_raw:
        from django.utils.dateparse import parse_datetime
        from django.utils.timezone import make_aware, is_aware
        parsed = parse_datetime(str(measured_at_raw))
        if parsed is None:
            measured_at = timezone.now(); ts_fallback = True
        elif not is_aware(parsed):
            measured_at = make_aware(parsed)
        else:
            measured_at = parsed
    else:
        measured_at = timezone.now(); ts_fallback = True

    raw = dict(payload)
    if violations:
        raw['_violations'] = violations
    reading = GasReading.objects.create(
        device=device,
        **values,
        measured_at=measured_at,
        quality_flag=quality_flag,
        event_id=event_id,
        tick_id=tick_id,
        ts_fallback=ts_fallback,
        raw_payload=raw,
    )
    update_last_seen(device)

    # ── ③ 단계별 판정 + 결과 영속(DetectionResult 계보) + 알람 ──
    from monitoring.models import DetectionResult
    Stage = DetectionResult.Stage
    detections: list = []

    # STEP C — Sliding Window 버퍼 갱신 (상태)
    from monitoring.anomaly.window import push as window_push
    window_push(device.device_uid, reading)

    # STEP B — 임계치 초과 판단
    from alerts.services import check_gas_thresholds
    check_gas_thresholds(device, reading)
    for e in check_threshold_exceeded(reading):
        detections.append(DetectionResult(
            event_id=event_id, gas_reading=reading, device=device,
            sensor_type=e.get('gas'), stage=Stage.THRESHOLD,
            level=str(e.get('level')), score=values.get(e.get('gas')), detail=_jsonable(e),
        ))

    # STEP D — Z-score 통계 이상 탐지
    from monitoring.anomaly.zscore import analyze as zscore_analyze
    from alerts.services import trigger_anomaly_alarms
    zscore_results = zscore_analyze(device.device_uid, reading)
    trigger_anomaly_alarms(device, zscore_results)
    for r in zscore_results:
        detections.append(DetectionResult(
            event_id=event_id, gas_reading=reading, device=device,
            sensor_type=r.get('metric'), stage=Stage.ZSCORE,
            level=str(r.get('final_status')), score=r.get('z_score'), detail=_jsonable(r),
        ))

    # STEP E — Change Point 탐지
    from monitoring.anomaly.changepoint import detect as cp_detect
    from alerts.services import trigger_changepoint_alarms
    cp_results = cp_detect(device.device_uid, reading)
    trigger_changepoint_alarms(device, cp_results)
    for r in cp_results:
        detections.append(DetectionResult(
            event_id=event_id, gas_reading=reading, device=device,
            sensor_type=r.get('metric'), stage=Stage.CHANGEPOINT,
            level=str(r.get('state') or 'NORMAL'), score=r.get('mean_shift_score'), detail=_jsonable(r),
        ))

    # STEP F — Isolation Forest 9채널 분포 이상 탐지 (AI 엔진)
    from monitoring.ai.gas_if import predict_gas_anomaly
    from alerts.services import trigger_if_anomaly_alarms
    if_result = predict_gas_anomaly(reading)
    trigger_if_anomaly_alarms(device, if_result)
    if if_result is not None:
        detections.append(DetectionResult(
            event_id=event_id, gas_reading=reading, device=device,
            sensor_type=None, stage=Stage.IF,
            level=if_result.level.name,
            score=getattr(if_result, 'mahalanobis_distance', None),
            detail={'is_anomaly': bool(getattr(if_result, 'is_anomaly', False)),
                    'reason': str(getattr(if_result, 'reason', ''))},
        ))

    if detections:
        DetectionResult.objects.bulk_create(detections)

    # STEP G — ARIMA 예측 (forecast 큐 위임). event_id 전파 → ARIMA 단계 계보는 forecast 태스크가 적재
    from alerts.tasks import forecast_gas_task
    fpayload = dict(payload)
    fpayload['event_id'] = str(event_id)
    forecast_gas_task.delay(device_uid, fpayload)

    # WebSocket 브로드캐스트
    try:
        from facilities.models import SensorLocation
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        sensor = SensorLocation.objects.filter(
            device_id=device.id, is_active=True
        ).first()

        if sensor:
            level_kr = calc_danger_level(reading)
            status = {'위험': 'danger', '주의': 'warning', '정상': 'normal'}.get(level_kr, 'normal')
            ws_payload = {
                'id': sensor.id,
                'device_id': device.id,
                'sensor_type': sensor.sensor_type,
                'x': float(sensor.x),
                'y': float(sensor.y),
                'device_name': sensor.device_name,
                'is_active': sensor.is_active,
                'status': status,
                'latest_value': {f: getattr(reading, f) for f in GAS_FIELDS},
            }
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'floor_{sensor.floor_id}_sensor',
                {'type': 'sensor.update', 'msg_type': 'delta', 'data': [ws_payload]},
            )
    except Exception as e:
        print(f'[sensor_ws] broadcast 실패: {e}')

    # Geofence 자동 갱신
    try:
        from facilities.services.geofence_service import update_geofence_from_gas
        update_geofence_from_gas(reading)
    except Exception as e:
        print(f'[geofence] 업데이트 실패: {e}')

# ──────────────────────────────────────────────────────────
# 가스 위험도 상수
# ──────────────────────────────────────────────────────────

# O2는 다른 가스와 반대로 수치가 낮을수록 위험 (정상: 18% 이상 / 주의: 16~18% / 위험: 16% 미만)
# 임계치 정의서에 정상 범위는 18-23.5인데 23.5인 경우 주의, 위험 구분해야 하는지 디코나이 측에서 답변 주실 예정
O2_WARN   = 18
O2_DANGER = 16
O2_HIGH = 23.5

# 위험도 문자열 비교를 위한 우선순위 매핑
# max() 함수에서 key로 사용 → 여러 가스 중 가장 높은 위험도 선택
LEVEL_PRIORITY = {"정상": 0, "주의": 1, "위험": 2}

# O2는 역방향 특성으로 별도 처리하므로 여기에 포함하지 않음
# DB에 ThresholdPolicy가 있으면 이 값 대신 DB 값 사용 (get_thresholds 참고)
DEFAULT_THRESHOLDS = {
    "co":  (25,   200  ),  # 일산화탄소 ppm
    "h2s": (10,   15   ),  # 황화수소 ppm
    "co2": (1000, 5000 ),  # 이산화탄소 ppm
    "no2": (3,    5    ),  # 이산화질소 ppm
    "so2": (2,    5    ),  # 이산화황 ppm
    "o3":  (0.06, 0.12 ),  # 오존 ppm
    "nh3": (25,   35   ),  # 암모니아 ppm
    "voc": (0.5,  1.0  ),  # 휘발성유기화합물 ppm
}


# ──────────────────────────────────────────────────────────
# 전력 이상 판단 상수
# ──────────────────────────────────────────────────────────
# 2분 넘도록 데이터가 안 오면 수신 중단(STALE)으로 판단
# ※ 클라이언트 확인 후 조정 필요한 임시값
STALE_THRESHOLD = timedelta(minutes=2)


# ══════════════════════════════════════════════════════════
# 가스 위험도 로직
# ══════════════════════════════════════════════════════════

def get_thresholds(scope: str = '실시간 관제') -> dict:
    """
    임계치 정책 조회
    - scope 파라미터로 반영 범위 필터링
      · '실시간 관제' (기본값): 실시간 위험도 계산·차트 표시용
      · '알림'               : AlarmEvent 생성 판단용
      · scope='' 인 정책은 범위 미지정으로 간주 → 전체 적용 (폴백)
    - DB에 해당 scope 데이터 없으면 PDF 기본값(DEFAULT_THRESHOLDS) 사용
    - O2는 역방향 처리이므로 반환값에서 제외
    """
    from monitoring.models import ThresholdPolicy
    from django.db.models import Q

    policies = ThresholdPolicy.objects.filter(
        is_active=True,
    ).filter(
        Q(scope__contains=scope) | Q(scope='')  # scope 미지정 정책은 전체 적용
    )
    if not policies.exists():
        return DEFAULT_THRESHOLDS

    return {
        p.metric_code: (p.warning_max, p.danger_max)
        for p in policies
        if p.metric_code != "o2"       # O2는 별도 처리 (아래 calc_danger_level 참고)
        and p.warning_max is not None
        and p.danger_max  is not None
    }


def calc_danger_level(reading) -> str:
    """
    GasReading 인스턴스를 받아 전체 위험도 반환
    반환값: '위험' / '주의' / '정상'

    - 여러 가스가 동시에 임계치 초과하면 가장 높은 위험도 반환
      ex) co=주의, h2s=위험 → '위험' 반환
    - O2는 낮을수록 위험한 역방향이므로 먼저 별도 체크
    - O2 > 23.5% 는 기준 미정이므로 임시 주의 처리
    """
    thresholds = get_thresholds()
    level = "정상"

    # O2 먼저 체크 (역방향: 수치가 낮을수록 위험)
    if reading.o2 is not None:
        if reading.o2 < O2_DANGER:
            level = "위험"
        elif reading.o2 < O2_WARN:
            level = max(level, "주의", key=lambda x: LEVEL_PRIORITY[x])
        elif reading.o2 > O2_HIGH:
            # 23.5% 초과: 기준 미정, 임시 주의 처리 (디코나이 확인 필요)
            level = max(level, "주의", key=lambda x: LEVEL_PRIORITY[x])

    # 나머지 가스 체크 (높을수록 위험)
    for gas, (warn, danger) in thresholds.items():
        if gas == "o2":
            continue

        value = getattr(reading, gas, None)
        if value is None:
            continue

        if value >= danger:
            level = "위험"
        elif value >= warn:
            level = max(level, "주의", key=lambda x: LEVEL_PRIORITY[x])

    return level


def check_threshold_exceeded(reading, scope: str = '실시간 관제') -> list:
    """
    임계치 초과한 가스 목록 반환
    alerts 앱에서 AlarmEvent 생성할 때 어떤 가스가 초과했는지 확인용

    scope 파라미터:
      - '실시간 관제' (기본값): 실시간 위험도 계산용
      - '알림'               : 알람 이벤트 생성 판단용 (alerts/services.py에서 호출)

    반환 예시:
    [
        {"gas": "co",  "value": 250.0, "level": "위험"},
        {"gas": "o2",  "value": 15.0,  "level": "위험"},
        {"gas": "h2s", "value": 12.0,  "level": "주의"},
    ]
    """
    exceeded = []

    if reading.o2 is not None:
        if reading.o2 < O2_DANGER:
            exceeded.append({"gas": "o2", "value": reading.o2, "level": "위험"})
        elif reading.o2 < O2_WARN:
            exceeded.append({"gas": "o2", "value": reading.o2, "level": "주의"})
        elif reading.o2 > O2_HIGH:
            # 23.5% 초과: 기준 미정, 임시 주의 처리 (디코나이 확인 후 수정 예정)
            exceeded.append({"gas": "o2", "value": reading.o2, "level": "주의"})

    thresholds = get_thresholds(scope)

    for gas, (warn, danger) in thresholds.items():
        if gas == "o2":
            continue

        value = getattr(reading, gas, None)
        if value is None:
            continue

        if value >= danger:
            exceeded.append({"gas": gas, "value": value, "level": "위험"})
        elif value >= warn:
            exceeded.append({"gas": gas, "value": value, "level": "주의"})

    return exceeded


# ══════════════════════════════════════════════════════════
# 전력 이상 판단 로직
# ══════════════════════════════════════════════════════════

def is_stale(ts) -> bool:
    """
    마지막 수신 시각 기준 stale(수신 중단) 여부
    현재 시각 - 마지막 수신 시각 > STALE_THRESHOLD(2분) 이면 True
    """
    return timezone.now() - ts > STALE_THRESHOLD


def get_channel_status(reading) -> str:
    """
    단일 채널의 상태 반환 (통합 PowerReading 기준)

    판단 우선순위:
    1. STALE        - 데이터 없거나 2분 초과
    2. COMM_ERROR   - 전류/전압/전력 모두 -1 (완전 통신불능)
    3. PARTIAL_ERROR - 일부만 -1 (부분 데이터 오류)
    4. NORMAL       - 모두 정상
    """
    if not reading or is_stale(reading.measured_at):
        return "STALE"

    values = [reading.current_a, reading.voltage_v, reading.power_w]

    # 전류/전압/전력 전부 -1 → 채널 통신 완전 불능
    if all(v == -1 for v in values):
        return "COMM_ERROR"

    # 일부만 -1 → 데이터 오류 (완전 통신불능과 구분하기 위해 별도 상태)
    if any(v == -1 for v in values):
        return "PARTIAL_ERROR"

    return "NORMAL"


def is_channel_on(channel) -> bool:
    """
    채널 ON/OFF 여부
    PowerStatusReading 기준: ON=255, OFF=0
    - 데이터 없으면 False
    - 마지막 상태 수신 후 2분 초과(stale)면 신뢰 불가 → False
    """
    from monitoring.models import PowerStatusReading

    # 가장 최근 ON/OFF 상태 조회
    status = PowerStatusReading.objects.filter(
        channel=channel
    ).order_by("-received_at").first()

    if not status:
        return False

    # ON/OFF 상태 데이터도 오래됐으면 신뢰 불가
    if is_stale(status.received_at):
        return False

    return status.status_value == 255  # 255=ON, 0=OFF


def get_channel_summary(device_uid: str) -> list:
    """
    특정 전력 장비의 채널별 최신 상태 요약
    대시보드/alerts 앱에서 전체 채널 상태를 한번에 확인할 때 사용

    반환 예시:
    [
        {
            "channel":          "slave01",   # 채널 코드
            "is_on":            True,        # ON/OFF 스위치 상태
            "status":           "NORMAL",    # NORMAL/COMM_ERROR/PARTIAL_ERROR/STALE
            "is_comm_error":    False,       # 통신 완전 불능 여부
            "is_partial_error": False,       # 일부 데이터 오류 여부
            "is_stale":         False,       # 수신 중단 여부
            "current_a":        30,          # 전류 (A), None이면 데이터 없음
            "voltage_v":        220,         # 전압 (V)
            "power_w":          6600,        # 전력 (W)
        },
    ]
    """
    from monitoring.models import DeviceChannel, PowerReading

    # 해당 장비의 모든 채널 조회
    channels = DeviceChannel.objects.filter(device__device_uid=device_uid)
    result   = []

    for channel in channels:
        # 채널별 가장 최근 측정값 조회
        reading = PowerReading.objects.filter(
            channel=channel
        ).order_by("-measured_at").first()

        status = get_channel_status(reading)

        result.append({
            "channel":          channel.channel_code,
            "is_on":            is_channel_on(channel),
            "status":           status,
            # 편의 플래그: alerts 앱에서 조건 분기할 때 status 문자열 직접 비교 안 해도 됨
            "is_comm_error":    status == "COMM_ERROR",
            "is_partial_error": status == "PARTIAL_ERROR",
            "is_stale":         status == "STALE",
            "current_a":        reading.current_a if reading else None,
            "voltage_v":        reading.voltage_v if reading else None,
            "power_w":          reading.power_w   if reading else None,
        })

    return result