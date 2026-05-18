"""
STEP D — Z-score 기반 통계적 조기 이상탐지

판단 순서:
  1순위: 임계치 초과 → CRITICAL
  2순위: abs(z) >= 3   → ANOMALY_WARNING
  3순위: 정상           → NORMAL

O2는 감소 방향이 위험이므로 z <= -3 조건으로 별도 처리.
"""

import statistics
from .window import get, is_ready, GAS_FIELDS

MIN_SAMPLES = 10   # 최소 샘플 수 (미달 시 판단 보류)
Z_THRESHOLD = 3.0  # 이상 판정 기준

# 값이 낮아질수록 위험한 가스
DECREASING_DANGER = {'o2'}

# 최신 분석 결과 캐시 (device_uid → list[dict])
# API 응답용 — 서버 재시작 시 초기화됨
_latest: dict[str, list[dict]] = {}


def analyze(device_uid: str, reading) -> list[dict]:
    """
    GasReading 1건에 대해 가스별 Z-score 분석 수행.
    반환: 가스별 결과 dict 리스트 (판단 보류 항목은 제외)
    """
    from monitoring.services import check_threshold_exceeded

    exceeded = {e['gas']: e['level'] for e in check_threshold_exceeded(reading)}
    measured_at = reading.measured_at.isoformat() if reading.measured_at else None

    results = []

    for gas in GAS_FIELDS:
        current = getattr(reading, gas, None)
        if current is None:
            continue

        current = float(current)

        # 1순위: 임계치 초과
        if gas in exceeded:
            results.append(_make_result(
                device_uid=device_uid,
                gas=gas,
                current=current,
                mean=None,
                std=None,
                z=None,
                direction=None,
                threshold_status=exceeded[gas],
                stat_status='NORMAL',
                final_status='CRITICAL',
                measured_at=measured_at,
            ))
            continue

        # 샘플 부족 → 판단 보류
        if not is_ready(device_uid, gas, min_samples=MIN_SAMPLES):
            continue

        values = get(device_uid, gas)
        history = values[:-1] if len(values) > 1 else values
        if len(history) < 2:
            continue

        mean = statistics.mean(history)
        std  = statistics.stdev(history) + 1e-9  # 0 나누기 방지
        z    = (current - mean) / std

        direction = 'decrease' if z < 0 else 'increase'

        # 2순위: Z-score 이상 판정
        if gas in DECREASING_DANGER:
            anomaly = z <= -Z_THRESHOLD
        else:
            anomaly = abs(z) >= Z_THRESHOLD

        stat_status = 'ANOMALY_WARNING' if anomaly else 'NORMAL'

        results.append(_make_result(
            device_uid=device_uid,
            gas=gas,
            current=current,
            mean=round(mean, 4),
            std=round(std, 4),
            z=round(z, 4),
            direction=direction,
            threshold_status='normal',
            stat_status=stat_status,
            final_status=stat_status,
            measured_at=measured_at,
        ))

    _latest[device_uid] = results
    return results


def get_latest(device_uid: str) -> list[dict]:
    """가장 최근 분석 결과 반환 (API 응답용)."""
    return _latest.get(device_uid, [])


def _make_result(device_uid, gas, current, mean, std, z, direction,
                 threshold_status, stat_status, final_status, measured_at) -> dict:
    return {
        'device_uid':        device_uid,
        'metric':            gas,
        'value':             current,
        'mean':              mean,
        'std':               std,
        'z_score':           z,
        'direction':         direction,
        'threshold_status':  threshold_status,
        'stat_status':       stat_status,
        'final_status':      final_status,
        'measured_at':       measured_at,
    }
