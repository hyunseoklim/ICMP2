"""
STEP G — ARIMA 예측 서브시스템 (AI 사전 경고) — power 채널 어댑터.

fastapi_app/ai_engine 의 PredictionSubsystem(CP → ARIMA → 출력 정책)을
ICMP2 전력 파이프라인에 연결한다. STEP B/F가 *현재* 이상을 탐지한다면
STEP G는 추세를 분석해 임계 도달 *이전*에 미리 경보한다.

Phase D M1-4 (2026-05-23) — gas_forecast.py 패턴 미러:
    - 단일 PredictionSubsystem 인스턴스 (worker 프로세스 전역)
    - power의 (device_uid, channel_code) 시계열 단위를 *device_id 합성키*로 인코딩
      (예: device_id="PWR-001/slave01", sensor_type="voltage"|"current"|"power")
    - PredictionSubsystem.predict_channel(device_id, sensor_type)이 두 키로
      시계열 분리하므로 channel별 독립 윈도우 보존

상태 모델 (gas D2 아키텍처 미러):
    - forecast 전용 큐를 단일 동시성(--concurrency=1) worker가 소비.
      PredictionSubsystem 인스턴스를 모듈 전역에 1개 두면 채널별 윈도우·
      K-카운터·CP 상태가 단일 프로세스 메모리에 자연 보존된다.
    - worker 재시작 시 상태 유실 → 워밍업 재개 (수용 비용).

idempotency (재시도·재전달 안전):
    - push()/predict_channel()은 상태 변경이라 같은 reading을 두 번 처리하면
      상태가 오염된다. (device_uid, channel_code)별 마지막 처리 measured_at를
      기록하고, 그 이하 timestamp는 통째로 건너뛴다.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# 전력 3채널 — power_distribution.POWER_SENSOR_TYPES 와 동일
POWER_SENSOR_TYPES = ['voltage', 'current', 'power']

# 워커 시작 시 DB에서 재생할 채널당 최근 측정 개수 (ARIMA history_size 150 이상)
_BACKFILL_POINTS = 200

# forecast worker 단일 프로세스 전역 — 상주 인스턴스 + 처리 이력
_subsystem = None
_arima_recorder = None       # _RecordingARIMA — predict_channel 직후 곡선 회수용
_last_processed: dict = {}   # (device_uid, channel_code) → 마지막 처리 measured_at


class _RecordingARIMA:
    """ARIMA 예측기 위임 래퍼 — predict() 결과(ARIMAResult)를 기록.

    gas_forecast._RecordingARIMA 패턴 그대로. PredictionSubsystem은
    predict_channel()마다 주입된 arima의 predict()를 정확히 1회 호출하므로
    호출 직후 last_result로 채널 곡선 (forecast_mean·ci_lower·ci_upper)을 회수.
    """

    def __init__(self, inner):
        self._inner = inner
        self.last_result = None

    def predict(self, history, cp_anchor):
        result = self._inner.predict(history, cp_anchor)
        self.last_result = result
        return result


def _series_key(device_uid: str, channel_code: str) -> str:
    """PredictionSubsystem용 시계열 키 — channel을 device_id에 합성.

    "PWR-001/slave01" 형식. PredictionSubsystem이 (device_id, sensor_type) 두
    문자열로 시계열을 분리 — channel을 device_id에 합성해 channel별 독립 윈도우.
    """
    return f"{device_uid}/{channel_code}"


def _get_subsystem():
    """전력 예측 서브시스템을 1회 생성·캐시하여 반환."""
    global _subsystem, _arima_recorder
    if _subsystem is None:
        from common.integration import PredictionSubsystem, ForecastPolicy
        from power.modules import PowerARIMAPredictor
        from power.thresholds import load_power_thresholds

        k = int(getattr(settings, 'FORECAST_K_CONFIRM', 18))
        _arima_recorder = _RecordingARIMA(PowerARIMAPredictor())
        _subsystem = PredictionSubsystem(
            load_power_thresholds(),
            arima=_arima_recorder,
            policy=ForecastPolicy(k_confirm=k),
        )
        logger.info("전력 예측 서브시스템 생성 완료 (K_CONFIRM=%d)", k)
        try:
            _backfill(_subsystem)
        except Exception as exc:
            logger.warning("전력 백필 실패 — 콜드 상태로 시작(자연 워밍업): %s", exc)
    return _subsystem


def _backfill(subsystem) -> None:
    """워커 시작 시 DB의 최근 PowerReading을 서브시스템에 재생해 즉시 워밍업.

    gas_forecast._backfill 패턴 미러. 단 power는 (device, channel) 단위라
    채널별로 push + 초기 predict 1회 호출.
    """
    from common.data_types import DataPoint
    from monitoring.models import Device, DeviceChannel, PowerReading
    from alerts.services import save_forecast_snapshots

    for device in Device.objects.filter(device_type='power'):
        uid = device.device_uid
        for channel in DeviceChannel.objects.filter(device=device, is_active=True):
            ch_code = channel.channel_code
            series_key = _series_key(uid, ch_code)

            readings = list(
                PowerReading.objects.filter(device=device, channel=channel)
                .order_by('-measured_at')[:_BACKFILL_POINTS]
            )
            if not readings:
                continue
            readings.reverse()  # 과거 → 현재 순

            # 1) 측정 이력 push — 3 sensor_type 각각 윈도우 워밍업
            for r in readings:
                for st, val in [
                    ('voltage', r.voltage_v),
                    ('current', r.current_a),
                    ('power',   r.power_w),
                ]:
                    is_valid = val != -1.0 and val != -1
                    subsystem.push(DataPoint(
                        timestamp=r.measured_at,
                        device_id=series_key,
                        sensor_type=st,
                        value=float(val) if is_valid else None,
                        is_valid=is_valid,
                    ))

            # 2) 채널당 predict 3회 (sensor별) → 초기 스냅샷 저장
            results = []
            for st in POWER_SENSOR_TYPES:
                _arima_recorder.last_result = None
                policy = subsystem.predict_channel(series_key, st)
                results.append((policy, _arima_recorder.last_result))
            save_forecast_snapshots(device, results, channel=channel)

            # 3) 마지막 처리 시각 기록 — 라이브 reading 중복 처리 방지
            _last_processed[(uid, ch_code)] = readings[-1].measured_at
            logger.info(
                "power 백필 완료 — device=%s ch=%s, %d readings 재생",
                uid, ch_code, len(readings),
            )


def _parse_ts(raw):
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime
    if raw:
        ts = parse_datetime(str(raw))
        if ts is not None:
            return ts
    return timezone.now()


def run_forecast(device_uid: str, channel_code: str, payload: dict):
    """전력 reading 1건을 예측 서브시스템에 투입하고 sensor별 예측을 산출한다.

    Returns:
        list[tuple[ForecastPolicyResult, ARIMAResult|None]] — 3 sensor의
        (2축 등급, 원시 예측 곡선). 곡선은 'AI 예측' 탭 점선 차트용.
        중복·역순 reading이면 빈 리스트 (idempotency 가드 — 상태 오염 방지).
    """
    measured_at = _parse_ts(payload.get('measured_at'))
    series_key = _series_key(device_uid, channel_code)

    # 서브시스템 확보 — 최초 호출 시 DB 백필 실행
    sub = _get_subsystem()

    # idempotency 가드 — 중복/역순/백필 포함분 reading은 통째로 skip
    last = _last_processed.get((device_uid, channel_code))
    if last is not None and measured_at <= last:
        logger.debug(
            "power forecast skip (중복/역순/백필포함) — device=%s ch=%s ts=%s",
            device_uid, channel_code, measured_at,
        )
        return []
    _last_processed[(device_uid, channel_code)] = measured_at

    from common.data_types import DataPoint

    results = []
    for st, key in [
        ('voltage', 'voltage_v'),
        ('current', 'current_a'),
        ('power',   'power_w'),
    ]:
        v = payload.get(key)
        is_valid = v is not None and v != -1.0 and v != -1
        point = DataPoint(
            timestamp=measured_at,
            device_id=series_key,
            sensor_type=st,
            value=float(v) if is_valid else None,
            is_valid=is_valid,
        )
        sub.push(point)
        _arima_recorder.last_result = None
        policy_result = sub.predict_channel(series_key, st)
        results.append((policy_result, _arima_recorder.last_result))

    return results
