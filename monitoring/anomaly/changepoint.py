"""
STEP E — 상태 변화 감지 (Change Point Detection)

이전 구간(prev W개) vs 최근 구간(curr W개) 비교:
  mean_shift_score = |curr_mean - prev_mean| / (prev_std + 1e-9)
  std_ratio        = (curr_std + 1e-9) / (prev_std + 1e-9)

판단 기준 (하나라도 해당하면 변화 감지):
  mean_shift_score >= 3.0
  std_ratio >= 3.0
  std_ratio <= 1/3.0

상태 머신 (device_uid × gas):
  STABLE → SHIFT  : CHANGE_POINT 이벤트
  SHIFT  → STABLE : BACK_TO_STABLE 이벤트
"""

import numpy as np
from .window import get, WINDOW_SIZE, BUFFER_SIZE

# Change Point 적용 항목 (초기 추천 5개)
CP_GAS_FIELDS = ['co', 'co2', 'h2s', 'o2', 'voc']

MEAN_SHIFT_THRESHOLD = 3.0
STD_RATIO_HIGH       = 3.0
STD_RATIO_LOW        = 1 / 3.0

# 상태 머신: device_uid → gas → 'STABLE' | 'SHIFT'
_state: dict[str, dict[str, str]] = {}

# 최신 결과 캐시 (API 응답용)
_latest: dict[str, list[dict]] = {}


def _ensure_state(device_uid: str) -> None:
    if device_uid not in _state:
        _state[device_uid] = {gas: 'STABLE' for gas in CP_GAS_FIELDS}


def detect(device_uid: str, reading) -> list[dict]:
    """
    GasReading 1건에 대해 Change Point 탐지 수행.
    반환: 가스별 결과 dict 리스트 (데이터 부족 항목은 제외)
    """
    _ensure_state(device_uid)
    measured_at = reading.measured_at.isoformat() if reading.measured_at else None

    results = []

    for gas in CP_GAS_FIELDS:
        # 2W개 전체 가져오기
        values = get(device_uid, gas, n=BUFFER_SIZE)
        if len(values) < BUFFER_SIZE:
            continue  # 데이터 부족 → 판단 보류

        prev = np.array(values[:WINDOW_SIZE], dtype=float)   # 이전 구간
        curr = np.array(values[WINDOW_SIZE:], dtype=float)   # 최근 구간

        prev_mean = float(np.mean(prev))
        prev_std  = float(np.std(prev))
        curr_mean = float(np.mean(curr))
        curr_std  = float(np.std(curr))

        mean_shift_score = abs(curr_mean - prev_mean) / (prev_std + 1e-9)
        std_ratio        = (curr_std + 1e-9) / (prev_std + 1e-9)

        is_change = (
            mean_shift_score >= MEAN_SHIFT_THRESHOLD
            or std_ratio >= STD_RATIO_HIGH
            or std_ratio <= STD_RATIO_LOW
        )

        prev_state = _state[device_uid][gas]

        # 상태 전환 감지
        if is_change and prev_state == 'STABLE':
            _state[device_uid][gas] = 'SHIFT'
            event = 'CHANGE_POINT'
        elif not is_change and prev_state == 'SHIFT':
            _state[device_uid][gas] = 'STABLE'
            event = 'BACK_TO_STABLE'
        else:
            event = None

        results.append({
            'device_uid':        device_uid,
            'metric':            gas,
            'prev_mean':         round(prev_mean, 4),
            'prev_std':          round(prev_std, 4),
            'curr_mean':         round(curr_mean, 4),
            'curr_std':          round(curr_std, 4),
            'mean_shift_score':  round(mean_shift_score, 4),
            'std_ratio':         round(std_ratio, 4),
            'is_change':         is_change,
            'state':             _state[device_uid][gas],
            'event':             event,   # 'CHANGE_POINT' | 'BACK_TO_STABLE' | None
            'measured_at':       measured_at,
        })

    _latest[device_uid] = results
    return results


def get_latest(device_uid: str) -> list[dict]:
    """가장 최근 Change Point 분석 결과 반환 (API 응답용)."""
    return _latest.get(device_uid, [])
