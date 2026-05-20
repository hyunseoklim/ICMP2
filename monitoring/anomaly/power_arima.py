"""
전력 채널별 ARIMA 시계열 예측

채널별 부하율(load_ratio %) 데이터로 ARIMA(1,1,1)을 학습해
다음 N_FORECAST 스텝을 예측하고,
예측값이 위험 임계치(WARN=50%, DANGER=75%)를 초과할 경우
위험 도달 예상 시간을 반환.
"""

from __future__ import annotations

import logging
from .power_window import get, is_ready

logger = logging.getLogger(__name__)

N_FORECAST  = 12   # 앞으로 12분 예측
ARIMA_ORDER = (1, 1, 1)
WARN_LOAD   = 50.0
DANGER_LOAD = 75.0

# 채널별 최신 예측 캐시
# _latest[(device_uid, channel_code)] = {'forecast': [...], 'eta_warn': N, 'eta_danger': N, 'max_12h': v}
_latest: dict[tuple, dict] = {}


def analyze(device_uid: str, channel_code: str, rated_w: float) -> dict | None:
    """
    채널 1개에 대해 ARIMA 예측 수행.
    반환: {'forecast': [...], 'eta_warn': int|None, 'eta_danger': int|None, 'max_load': float}
    샘플 부족 시 None 반환.
    """
    if not is_ready(device_uid, channel_code):
        return None

    values = get(device_uid, channel_code)
    forecast = _forecast(values)
    if forecast is None:
        return None

    forecast = [round(v, 2) for v in forecast]

    eta_warn   = _eta(forecast, WARN_LOAD)
    eta_danger = _eta(forecast, DANGER_LOAD)
    max_load   = round(max(forecast), 2) if forecast else None

    result = {
        'forecast':   forecast,
        'eta_warn':   eta_warn,
        'eta_danger': eta_danger,
        'max_load':   max_load,
    }
    _latest[(device_uid, channel_code)] = result
    return result


def _forecast(values: list[float]) -> list[float] | None:
    try:
        from statsmodels.tsa.arima.model import ARIMA
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model = ARIMA(values, order=ARIMA_ORDER)
            fit   = model.fit()
            pred  = fit.forecast(steps=N_FORECAST)
        return [max(0.0, min(150.0, float(v))) for v in pred]
    except ImportError:
        logger.warning("statsmodels 미설치 — 전력 ARIMA 비활성화")
        return None
    except Exception as e:
        logger.debug("전력 ARIMA 예측 실패 (%s): %s", channel_code, e)
        return None


def _eta(forecast: list[float], threshold: float) -> int | None:
    """예측값이 threshold를 처음 초과하는 스텝(분) 반환. 없으면 None."""
    for i, v in enumerate(forecast):
        if v >= threshold:
            return i + 1
    return None


def get_latest(device_uid: str, channel_code: str) -> dict | None:
    """채널의 최신 ARIMA 예측 결과 반환."""
    return _latest.get((device_uid, channel_code))
