"""
STEP G — ARIMA 예측 서브시스템 (AI 사전 경고).

fastapi_app/ai_engine 의 PredictionSubsystem(CP → ARIMA → 출력 정책)을
ICMP2 가스 파이프라인에 연결한다. STEP B~F가 *현재* 이상을 탐지한다면
STEP G는 추세를 분석해 임계 도달 *이전*에 미리 경보한다.

상태 모델 (아키텍처 D2):
- 본 모듈은 forecast 전용 큐를 단일 동시성(--concurrency=1) worker가
  소비하는 전제로 설계됐다. PredictionSubsystem 인스턴스를 모듈 전역에
  1개 두면 채널별 윈도우(60·150점)·K-카운터·CP `_last_contamination`
  상태가 그 단일 프로세스 메모리에 자연 보존된다 → 상태 외부화 불필요.
- worker 재시작 시 상태 유실 → 워밍업 재개 (수용 비용).

idempotency (재시도·재전달 안전):
- push()/predict_channel()은 윈도우·K-카운터를 변경하는 상태 연산이라
  같은 reading을 두 번 처리하면 상태가 오염된다. device_uid별 마지막
  처리 measured_at를 기록하고, 그 이하 timestamp는 통째로 건너뛴다.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# 엔진 가스 9채널 — gas_distribution.GAS_SENSOR_TYPES 와 동일
GAS_CHANNELS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']

# forecast worker 단일 프로세스 전역 — 상주 인스턴스 + 처리 이력
_subsystem = None
_last_processed: dict = {}   # device_uid → 마지막 처리 measured_at (datetime)


def _get_subsystem():
    """가스 예측 서브시스템을 1회 생성·캐시하여 반환."""
    global _subsystem
    if _subsystem is None:
        from common.integration import PredictionSubsystem, ForecastPolicy
        from gas.modules import GasARIMAPredictor
        from gas.thresholds import load_gas_thresholds

        k = int(getattr(settings, 'FORECAST_K_CONFIRM', 18))
        _subsystem = PredictionSubsystem(
            load_gas_thresholds(),
            arima=GasARIMAPredictor(),
            policy=ForecastPolicy(k_confirm=k),
        )
        logger.info("가스 예측 서브시스템 생성 완료 (K_CONFIRM=%d)", k)
    return _subsystem


def _parse_ts(raw):
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime
    if raw:
        ts = parse_datetime(str(raw))
        if ts is not None:
            return ts
    return timezone.now()


def run_forecast(device_uid: str, payload: dict):
    """가스 reading 1건을 예측 서브시스템에 투입하고 채널별 예측을 산출한다.

    Returns:
        list[ForecastPolicyResult] — 9채널 예측. 중복·역순 reading이면
        빈 리스트(idempotency 가드 — 상태 오염 방지).
    """
    measured_at = _parse_ts(payload.get('measured_at'))

    # --- idempotency 가드 — 중복/역순 reading은 통째로 skip ---
    last = _last_processed.get(device_uid)
    if last is not None and measured_at <= last:
        logger.debug("forecast skip (중복/역순) — device=%s ts=%s", device_uid, measured_at)
        return []
    _last_processed[device_uid] = measured_at   # 처리 착수 기록 (재처리 차단)

    from common.data_types import DataPoint

    sub = _get_subsystem()
    results = []
    for ch in GAS_CHANNELS:
        v = payload.get(ch)
        point = DataPoint(
            timestamp=measured_at,
            device_id=device_uid,
            sensor_type=ch,
            value=v,
            is_valid=(v is not None),
        )
        sub.push(point)
        results.append(sub.predict_channel(device_uid, ch))

    return results
