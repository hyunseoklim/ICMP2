"""
전력 채널별 Z-score 통계 기반 조기 이상탐지

판단 순서:
  1순위: 부하율 임계치 초과 (>=75% DANGER, >=50% WARNING) → CRITICAL
  2순위: abs(z) >= 3 → ANOMALY_WARNING
  3순위: 정상 → NORMAL

부하율은 높아질수록 위험이므로 단방향(increase)만 체크.
"""

import statistics
from .power_window import get, is_ready

MIN_SAMPLES = 10
Z_THRESHOLD = 3.0

WARN_LOAD   = 50.0
DANGER_LOAD = 75.0

# 채널별 최신 분석 결과 캐시
# _latest[(device_uid, channel_code)] = dict
_latest: dict[tuple, dict] = {}


def analyze(device_uid: str, channel_code: str, load_ratio: float) -> dict:
    """
    채널 1개의 부하율에 대해 Z-score 분석 수행.
    반환: 분석 결과 dict
    """
    # 1순위: 임계치 초과
    if load_ratio >= DANGER_LOAD:
        result = _make_result(device_uid, channel_code, load_ratio,
                              mean=None, std=None, z=None,
                              threshold_status='danger',
                              stat_status='NORMAL',
                              final_status='CRITICAL')
        _latest[(device_uid, channel_code)] = result
        return result

    if load_ratio >= WARN_LOAD:
        result = _make_result(device_uid, channel_code, load_ratio,
                              mean=None, std=None, z=None,
                              threshold_status='warning',
                              stat_status='NORMAL',
                              final_status='CRITICAL')
        _latest[(device_uid, channel_code)] = result
        return result

    # 샘플 부족 → 판단 보류
    if not is_ready(device_uid, channel_code):
        return _make_result(device_uid, channel_code, load_ratio,
                            mean=None, std=None, z=None,
                            threshold_status='normal',
                            stat_status='INSUFFICIENT_DATA',
                            final_status='INSUFFICIENT_DATA')

    values = get(device_uid, channel_code)
    history = values[:-1] if len(values) > 1 else values
    if len(history) < 2:
        return _make_result(device_uid, channel_code, load_ratio,
                            mean=None, std=None, z=None,
                            threshold_status='normal',
                            stat_status='INSUFFICIENT_DATA',
                            final_status='INSUFFICIENT_DATA')

    mean = statistics.mean(history)
    std  = statistics.stdev(history) + 1e-9
    z    = (load_ratio - mean) / std

    # 2순위: Z-score 이상 (부하율은 높아지는 방향만 위험)
    anomaly = z >= Z_THRESHOLD
    stat_status  = 'ANOMALY_WARNING' if anomaly else 'NORMAL'
    final_status = stat_status

    result = _make_result(device_uid, channel_code, load_ratio,
                          mean=round(mean, 4), std=round(std, 4), z=round(z, 4),
                          threshold_status='normal',
                          stat_status=stat_status,
                          final_status=final_status)
    _latest[(device_uid, channel_code)] = result
    return result


def get_latest(device_uid: str, channel_code: str) -> dict | None:
    """채널의 최신 Z-score 분석 결과 반환 (API 응답용)."""
    return _latest.get((device_uid, channel_code))


def _make_result(device_uid, channel_code, load_ratio,
                 mean, std, z, threshold_status, stat_status, final_status) -> dict:
    return {
        'device_uid':       device_uid,
        'channel_code':     channel_code,
        'metric':           'load_ratio',
        'value':            load_ratio,
        'mean':             mean,
        'std':              std,
        'z_score':          z,
        'direction':        'increase',
        'threshold_status': threshold_status,
        'stat_status':      stat_status,
        'final_status':     final_status,
    }
