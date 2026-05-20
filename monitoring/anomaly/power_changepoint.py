"""
STEP E (전력) — Change Point Detection

채널별 부하율(load_ratio %)의 슬라이딩 윈도우를 prev/curr 두 구간으로 나눠
평균 이동(mean_shift_score)과 분산 비율(std_ratio)을 계산.

판정 기준:
  mean_shift_score >= ALERT_THRESHOLD  → CHANGE_POINT_ALERT
  mean_shift_score >= WARN_THRESHOLD   → CHANGE_POINT_WARNING
  std_ratio        >= STD_RATIO_LIMIT  → CHANGE_POINT_VARIANCE
  그 외                                → NORMAL
"""

import statistics
from .power_window import get

MIN_WINDOW      = 10
WARN_THRESHOLD  = 2.0
ALERT_THRESHOLD = 3.0
STD_RATIO_LIMIT = 3.0

# (device_uid, channel_code) → dict
_latest: dict[tuple, dict] = {}


def analyze(device_uid: str, channel_code: str, load_ratio: float) -> dict:
    """
    채널 1개의 부하율에 대해 Change Point 분석 수행.
    반환: 분석 결과 dict
    """
    values = get(device_uid, channel_code)
    if len(values) < MIN_WINDOW:
        result = _make_result(device_uid, channel_code, load_ratio,
                              None, None, None, None, None, None, 'NORMAL')
        _latest[(device_uid, channel_code)] = result
        return result

    half      = len(values) // 2
    prev      = values[:half]
    curr      = values[half:]

    if len(prev) < 2 or len(curr) < 2:
        result = _make_result(device_uid, channel_code, load_ratio,
                              None, None, None, None, None, None, 'NORMAL')
        _latest[(device_uid, channel_code)] = result
        return result

    prev_mean = statistics.mean(prev)
    curr_mean = statistics.mean(curr)
    prev_std  = statistics.stdev(prev) + 1e-9
    curr_std  = statistics.stdev(curr) + 1e-9

    mean_shift = abs(curr_mean - prev_mean) / prev_std
    std_ratio  = max(prev_std, curr_std) / min(prev_std, curr_std)

    if mean_shift >= ALERT_THRESHOLD:
        status = 'CHANGE_POINT_ALERT'
    elif mean_shift >= WARN_THRESHOLD:
        status = 'CHANGE_POINT_WARNING'
    elif std_ratio >= STD_RATIO_LIMIT:
        status = 'CHANGE_POINT_VARIANCE'
    else:
        status = 'NORMAL'

    direction = 'increase' if curr_mean > prev_mean else 'decrease'

    result = _make_result(device_uid, channel_code, load_ratio,
                          round(prev_mean, 4), round(curr_mean, 4),
                          round(prev_std, 4),  round(curr_std, 4),
                          round(mean_shift, 4), round(std_ratio, 4),
                          status, direction)
    _latest[(device_uid, channel_code)] = result
    return result


def get_latest(device_uid: str, channel_code: str) -> dict | None:
    """채널의 최신 Change Point 분석 결과 반환."""
    return _latest.get((device_uid, channel_code))


def _make_result(device_uid, channel_code, load_ratio,
                 prev_mean, curr_mean, prev_std, curr_std,
                 mean_shift, std_ratio, status, direction='increase') -> dict:
    return {
        'device_uid':       device_uid,
        'channel_code':     channel_code,
        'metric':           'load_ratio',
        'value':            load_ratio,
        'prev_mean':        prev_mean,
        'curr_mean':        curr_mean,
        'prev_std':         prev_std,
        'curr_std':         curr_std,
        'mean_shift_score': mean_shift,
        'std_ratio':        std_ratio,
        'direction':        direction,
        'final_status':     status,
    }
