"""
generator/core/time_index — 합성 시계열의 시간축 생성.

핵심 결정 (Phase 2):
    - M.4: 3초 간격 측정
    - T.1: 학습 풀 5000샘플 = 약 4.2시간
    - T.2: 평가 풀 2150샘플 = 약 1.8시간

활용처:
    - generator/gas_generator/normal_pool.py
    - generator/power_generator/normal_pool.py
    - generator/*/scenario.py: 시나리오 카드별 시간축
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from devkit.core.premises.measurement import MEASUREMENT_INTERVAL_SECONDS


def build_time_axis(
    start: datetime,
    n_steps: int,
    interval_seconds: Optional[float] = None,
) -> list:
    """일정 간격의 시간축을 생성.
    
    Args:
        start: 시작 시각 (datetime).
        n_steps: 시점 개수.
        interval_seconds: 간격(초). None이면 M.4 기본값(3.0).
    
    Returns:
        list[datetime] — [start, start+interval, ..., start+(n_steps-1)*interval]
    
    Raises:
        ValueError: n_steps < 1 또는 interval_seconds <= 0.
    
    Examples:
        >>> from datetime import datetime, timezone
        >>> ts = build_time_axis(datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc), n_steps=3)
        >>> len(ts)
        3
        >>> (ts[1] - ts[0]).total_seconds()
        3.0
    """
    if n_steps < 1:
        raise ValueError(f"n_steps는 1 이상. 받은 값: {n_steps}")

    interval = interval_seconds if interval_seconds is not None else MEASUREMENT_INTERVAL_SECONDS
    if interval <= 0:
        raise ValueError(f"interval_seconds는 양수여야 함. 받은 값: {interval}")

    return [start + timedelta(seconds=i * interval) for i in range(n_steps)]


def duration_for_steps(
    n_steps: int,
    interval_seconds: Optional[float] = None,
) -> timedelta:
    """시점 개수에 해당하는 총 시간 길이.
    
    Args:
        n_steps: 시점 개수.
        interval_seconds: 간격(초). None이면 M.4 기본값.
    
    Returns:
        timedelta.
    
    Examples:
        >>> duration_for_steps(5000)
        datetime.timedelta(seconds=15000)  # = 4.17시간
        >>> duration_for_steps(2150)
        datetime.timedelta(seconds=6450)   # = 1.79시간
    """
    interval = interval_seconds if interval_seconds is not None else MEASUREMENT_INTERVAL_SECONDS
    return timedelta(seconds=n_steps * interval)
