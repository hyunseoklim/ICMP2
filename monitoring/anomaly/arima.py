"""
STEP G — ARIMA 시계열 예측 (단기 위험 예측)

슬라이딩 윈도우 데이터로 ARIMA 모델을 학습해
다음 N_FORECAST 스텝을 예측하고,
예측값이 임계치를 초과할 경우 PREDICTIVE_WARNING을 발령.

특성:
  - 가스별 단변량 예측 (각 gas 독립 모델)
  - statsmodels ARIMA(1,1,1) 고정 차수 (Auto-ARIMA 없이 단순화)
  - 성능 부담이 크므로 MIN_TRAIN_SAMPLES 충족 시에만 실행
  - 예측 결과는 캐시에 저장하고 API 응답용으로 제공
"""

from __future__ import annotations

import logging
from .window import get, GAS_FIELDS
from monitoring.services import DEFAULT_THRESHOLDS, O2_WARN  # noqa: E401

logger = logging.getLogger(__name__)

MIN_TRAIN_SAMPLES = 20   # 예측에 필요한 최소 샘플 수
N_FORECAST        = 5    # 앞으로 몇 스텝 예측 (분 단위)
ARIMA_ORDER       = (1, 1, 1)

_latest: dict[str, list[dict]] = {}
# 모든 가스의 예측값 (임계치 초과 여부와 무관하게 차트 표시용)
_latest_forecasts: dict[str, dict[str, list[float]]] = {}


def analyze(device_uid: str, reading) -> list[dict]:
    """
    GasReading 1건 수신 시 가스별 ARIMA 예측 수행.
    - _latest_forecasts: 모든 가스 예측값 저장 (차트용)
    - _latest: 임계치 초과 예측 가스만 저장 (경보용)
    """
    measured_at = reading.measured_at.isoformat() if reading.measured_at else None
    results = []
    forecasts: dict[str, list[float]] = {}

    for gas in GAS_FIELDS:
        values = get(device_uid, gas)
        if len(values) < MIN_TRAIN_SAMPLES:
            continue

        forecast = _forecast(values)
        if forecast is None:
            continue

        forecasts[gas] = [round(v, 4) for v in forecast]

        warn_th = _get_warn_threshold(gas)
        if warn_th is None:
            continue

        exceeds = [i for i, v in enumerate(forecast) if _exceeds(gas, v, warn_th)]
        if not exceeds:
            continue

        first_exceed_step = exceeds[0] + 1
        results.append({
            'device_uid':        device_uid,
            'metric':            gas,
            'forecast':          forecasts[gas],
            'warn_threshold':    warn_th,
            'first_exceed_step': first_exceed_step,
            'final_status':      'PREDICTIVE_WARNING',
            'measured_at':       measured_at,
        })

    _latest[device_uid] = results
    if forecasts:
        _latest_forecasts[device_uid] = forecasts
    return results


def _forecast(values: list[float]) -> list[float] | None:
    try:
        from statsmodels.tsa.arima.model import ARIMA
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model = ARIMA(values, order=ARIMA_ORDER)
            fit   = model.fit()
            pred  = fit.forecast(steps=N_FORECAST)
        return list(pred)
    except ImportError:
        logger.warning("statsmodels 미설치 — ARIMA 비활성화")
        return None
    except Exception as e:
        logger.debug("ARIMA 예측 실패: %s", e)
        return None


def _get_warn_threshold(gas: str) -> float | None:
    if gas == 'o2':
        return O2_WARN
    th = DEFAULT_THRESHOLDS.get(gas)
    if th is None:
        return None
    # DEFAULT_THRESHOLDS 값은 (warning_max, danger_max) 튜플
    return th[0]


def _exceeds(gas: str, value: float, threshold: float) -> bool:
    if gas == 'o2':
        return value < threshold
    return value >= threshold


def get_latest(device_uid: str) -> list[dict]:
    """임계치 초과 예측 결과 반환 (경보용)."""
    return _latest.get(device_uid, [])


def get_latest_forecasts(device_uid: str) -> dict[str, list[float]]:
    """모든 가스 예측값 반환 (차트 점선용)."""
    return _latest_forecasts.get(device_uid, {})
