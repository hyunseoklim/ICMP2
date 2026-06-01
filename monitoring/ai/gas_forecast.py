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

# 워커 시작 시 DB에서 재생할 채널당 최근 측정 개수 (ARIMA history_size 150 이상)
_BACKFILL_POINTS = 200

# forecast worker 단일 프로세스 전역 — 상주 인스턴스 + 처리 이력
_subsystem = None
_arima_recorder = None       # _RecordingARIMA — predict_channel 직후 곡선 회수용
_last_processed: dict = {}   # device_uid → 마지막 처리 measured_at (datetime)


class _RecordingARIMA:
    """ARIMA 예측기 위임 래퍼 — predict() 결과(ARIMAResult)를 기록한다.

    PredictionSubsystem은 predict_channel()마다 주입된 arima의 predict()를
    정확히 1회 호출한다(prediction_subsystem.py). 따라서 predict_channel()
    호출 직후 last_result를 읽으면 그 채널의 원시 예측 곡선
    (forecast_mean·ci_lower·ci_upper)을 얻을 수 있다 — 'AI 예측' 탭의
    점선 차트용.

    엔진(fastapi_app/ai_engine) 코드는 한 줄도 수정하지 않는다 — 검증된
    공개 계약인 `arima=` 의존성 주입 seam만 이용한다. predict()를 그대로
    위임하므로 등급·K-카운터·알람 동작은 바이트 동일하게 유지된다.
    """

    def __init__(self, inner):
        self._inner = inner
        self.last_result = None

    def predict(self, history, cp_anchor):
        result = self._inner.predict(history, cp_anchor)
        self.last_result = result
        return result


def _get_subsystem():
    """가스 예측 서브시스템을 1회 생성·캐시하여 반환."""
    global _subsystem, _arima_recorder
    if _subsystem is None:
        from gas.core.integration import PredictionSubsystem, ForecastPolicy
        from gas.modules import GasARIMAPredictor
        from gas.thresholds import load_gas_thresholds

        k = int(getattr(settings, 'FORECAST_K_CONFIRM', 18))
        _arima_recorder = _RecordingARIMA(GasARIMAPredictor())
        _subsystem = PredictionSubsystem(
            load_gas_thresholds(),
            arima=_arima_recorder,
            policy=ForecastPolicy(k_confirm=k),
        )
        logger.info("가스 예측 서브시스템 생성 완료 (K_CONFIRM=%d)", k)
        try:
            _backfill(_subsystem)
        except Exception as exc:
            logger.warning("백필 실패 — 콜드 상태로 시작(자연 워밍업): %s", exc)
    return _subsystem


def _backfill(subsystem) -> None:
    """워커 시작 시 DB의 최근 GasReading을 서브시스템에 재생해 즉시 워밍업.

    forecast 워커는 스트리밍 상태기 — 재시작 시 채널별 메모리 윈도우를
    잃는다. DB에 이미 쌓인 측정 이력을 push로 재생하면 라이브 reading을
    기다리지 않고 곧바로 예측 가능 상태가 된다(재시작 후 '예측 준비 중'
    공백 제거).

    비용 최소화: 측정 이력은 push로만 전량 재생(윈도우 워밍업 — 수 ms)
    하고, predict_channel은 채널당 1회만 호출해 초기 스냅샷을 저장한다
    (~수 초). K-카운터는 0에서 시작하므로 CONFIRMED 등급은 이후 라이브
    reading으로 재누적된다(곡선·차트는 즉시 정상).
    """
    from gas.core.data_types import DataPoint
    from monitoring.models import Device, GasReading
    from alerts.services import save_forecast_snapshots

    for device in Device.objects.filter(device_type='gas'):
        uid = device.device_uid
        readings = list(
            GasReading.objects.filter(device=device)
            .order_by('-measured_at')[:_BACKFILL_POINTS]
        )
        if not readings:
            continue
        readings.reverse()  # 과거 → 현재 순

        # 1) 측정 이력 push — 채널별 윈도우 워밍업
        for r in readings:
            for ch in GAS_CHANNELS:
                v = getattr(r, ch, None)
                subsystem.push(DataPoint(
                    timestamp=r.measured_at, device_id=uid, sensor_type=ch,
                    value=v, is_valid=(v is not None),
                ))

        # 2) 채널당 predict 1회 → 초기 스냅샷 저장
        results = []
        for ch in GAS_CHANNELS:
            _arima_recorder.last_result = None
            policy = subsystem.predict_channel(uid, ch)
            results.append((policy, _arima_recorder.last_result))
        save_forecast_snapshots(device, results)

        # 3) 마지막 처리 시각 기록 — 라이브 reading 중복처리 방지
        _last_processed[uid] = readings[-1].measured_at
        logger.info("백필 완료 — device=%s, %d readings 재생", uid, len(readings))


def _parse_ts(raw):
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime
    from django.utils.timezone import make_aware, is_aware
    if raw:
        ts = parse_datetime(str(raw))
        if ts is not None:
            return ts if is_aware(ts) else make_aware(ts)
    return timezone.now()


def run_forecast(device_uid: str, payload: dict):
    """가스 reading 1건을 예측 서브시스템에 투입하고 채널별 예측을 산출한다.

    Returns:
        list[tuple[ForecastPolicyResult, ARIMAResult|None]] — 9채널의
        (2축 등급 결과, 원시 예측 곡선). 곡선은 'AI 예측' 탭의 점선 차트용.
        중복·역순 reading이면 빈 리스트(idempotency 가드 — 상태 오염 방지).
    """
    measured_at = _parse_ts(payload.get('measured_at'))

    # 서브시스템 확보 — 최초 호출 시 DB 백필이 실행되어 _last_processed가 채워진다
    sub = _get_subsystem()

    # --- idempotency 가드 — 중복/역순/백필 포함분 reading은 통째로 skip ---
    last = _last_processed.get(device_uid)
    if last is not None and measured_at <= last:
        logger.debug("forecast skip (중복/역순/백필포함) — device=%s ts=%s", device_uid, measured_at)
        return []
    _last_processed[device_uid] = measured_at   # 처리 착수 기록 (재처리 차단)

    from gas.core.data_types import DataPoint

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
        _arima_recorder.last_result = None             # 직전 채널 곡선 잔존 방지
        policy_result = sub.predict_channel(device_uid, ch)
        results.append((policy_result, _arima_recorder.last_result))

    return results
