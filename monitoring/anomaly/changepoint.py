"""
STEP E — Change Point Detection (이전 윈도우 vs 현재 윈도우 비교)

전체 슬라이딩 윈도우를 prev / curr 두 구간으로 나눠
평균 이동(mean_shift_score)과 분산 비율(std_ratio)을 계산.

판정 기준:
  mean_shift_score >= ALERT_THRESHOLD  → CHANGE_POINT_ALERT
  mean_shift_score >= WARN_THRESHOLD   → CHANGE_POINT_WARNING
  std_ratio        >= STD_RATIO_LIMIT  → CHANGE_POINT_VARIANCE (분산 급변)
  그 외                                → NORMAL
"""

import statistics
from .window import get, GAS_FIELDS

MIN_WINDOW   = 10   # 판단에 필요한 최소 총 샘플 수
WARN_THRESHOLD  = 2.0   # mean_shift_score 경보 기준
ALERT_THRESHOLD = 3.0   # mean_shift_score 위험 기준
STD_RATIO_LIMIT = 3.0   # std_ratio 급변 기준

_latest: dict[str, list[dict]] = {}


def analyze(device_uid: str, reading) -> list[dict]:
    """
    GasReading 1건에 대해 가스별 Change Point 분석 수행.
    반환: 변화 감지된 가스별 결과 dict 리스트 (NORMAL은 제외)
    """
    measured_at = reading.measured_at.isoformat() if reading.measured_at else None
    results = []

    for gas in GAS_FIELDS:
        current = getattr(reading, gas, None)
        if current is None:
            continue

        values = get(device_uid, gas)
        if len(values) < MIN_WINDOW:
            continue

        result = _detect(device_uid, gas, values, float(current), measured_at)
        if result and result['final_status'] != 'NORMAL':
            results.append(result)

    _latest[device_uid] = results
    return results


def _detect(device_uid: str, gas: str, values: list[float],
            current: float, measured_at) -> dict | None:
    half = len(values) // 2
    prev = values[:half]
    curr = values[half:]

    if len(prev) < 2 or len(curr) < 2:
        return None

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

    return {
        'device_uid':       device_uid,
        'metric':           gas,
        'value':            current,
        'prev_mean':        round(prev_mean, 4),
        'curr_mean':        round(curr_mean, 4),
        'prev_std':         round(prev_std, 4),
        'curr_std':         round(curr_std, 4),
        'mean_shift_score': round(mean_shift, 4),
        'std_ratio':        round(std_ratio, 4),
        'direction':        direction,
        'final_status':     status,
        'measured_at':      measured_at,
    }


def get_latest(device_uid: str) -> list[dict]:
    """가장 최근 Change Point 분석 결과 반환 (API 응답용)."""
    return _latest.get(device_uid, [])
