"""
work — 작업 시간 구조의 공통 부분 (가스·전력 무관).

본 모듈은 시스템 전제 조건서 차원 4(작업·작업자 가정)의 *공통 시간 구조*를 구현한다.
가스 전용 (W.2 작업 유형, W.4 작업자 호흡)은 gas/premises/work.py에 정의.
전력 전용 (W.5 작업 모드별 전력 사이클)은 power/premises/work.py에 정의.

본 모듈이 정해주는 것:
    - 작업 시간대 정의 (W.1)
    - 전이 구간 길이 (W.3)
    - 시간대 판정 함수 (determine_work_mode)
    - 전이 가중치 함수 (transition_weight)

timezone 정보는 호출자 책임. 본 모듈은 timestamp의 시·분만 추출하여 판정.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from devkit.core.enums import WorkMode


# ============================================================================
# W.1 작업 시간대
# ============================================================================

WORK_START_TIME: time = time(8, 0)
"""작업 시작 시각 (08:00). 결정 W.1."""

WORK_END_TIME: time = time(18, 0)
"""작업 종료 시각 (18:00). 결정 W.1."""


# ============================================================================
# W.3 전이 구간
# ============================================================================

TRANSITION_DURATION_MINUTES: int = 5
"""전이 구간 길이 (분). 결정 W.3.

WORKING ↔ IDLE 전환 시점 ±5분 동안 환경(가스 농도, 전력)이 선형 보간된다.
generator/core/transition.py에서 본 값을 참조하여 합성 데이터의 전이 구간을 생성.
"""


# ============================================================================
# 시간대 판정 함수
# ============================================================================

def determine_work_mode(timestamp: datetime) -> WorkMode:
    """주어진 시각의 작업 모드(WORKING/IDLE)를 반환한다.
    
    판정 규칙 (W.1):
        - WORK_START_TIME (08:00) ≤ 시각 < WORK_END_TIME (18:00) → WORKING
        - 그 외 → IDLE
    
    timezone 정보는 호출자 책임. 본 함수는 timestamp의 *시·분만* 추출하여 판정.
    naive datetime, timezone-aware datetime 둘 다 허용.
    
    Args:
        timestamp: 판정할 시각.
    
    Returns:
        WorkMode.WORKING 또는 WorkMode.IDLE.
    
    Examples:
        >>> from datetime import datetime
        >>> determine_work_mode(datetime(2026, 5, 19, 9, 0))   # 09:00
        <WorkMode.WORKING: '작업중'>
        >>> determine_work_mode(datetime(2026, 5, 19, 20, 0))  # 20:00
        <WorkMode.IDLE: '대기'>
        >>> determine_work_mode(datetime(2026, 5, 19, 18, 0))  # 18:00 (경계)
        <WorkMode.IDLE: '대기'>
    """
    current = timestamp.time()
    if WORK_START_TIME <= current < WORK_END_TIME:
        return WorkMode.WORKING
    return WorkMode.IDLE


def transition_weight(timestamp: datetime) -> float:
    """주어진 시각의 전이 가중치 (0.0~1.0)를 반환한다.
    
    가중치 정의:
        - 완전 IDLE 구간: 0.0
        - 완전 WORKING 구간: 1.0
        - WORKING 진입 (08:00 ~ 08:05): 0.0 → 1.0 선형 증가
        - WORKING 종료 (17:55 ~ 18:00): 1.0 → 0.0 선형 감소
    
    generator에서 환경 부드러운 전환(가스 농도·전력 점진 변화)에 사용.
    
    Args:
        timestamp: 판정할 시각.
    
    Returns:
        가중치 (0.0 ≤ x ≤ 1.0).
    
    Examples:
        >>> from datetime import datetime
        >>> transition_weight(datetime(2026, 5, 19, 9, 0))    # 완전 WORKING
        1.0
        >>> transition_weight(datetime(2026, 5, 19, 8, 0))    # 진입 시작
        0.0
        >>> transition_weight(datetime(2026, 5, 19, 8, 5))    # 진입 완료
        1.0
        >>> transition_weight(datetime(2026, 5, 19, 22, 0))   # 완전 IDLE
        0.0
        >>> # 진입 중간 (08:02 30초 = 2.5분 경과 / 5분)
        >>> transition_weight(datetime(2026, 5, 19, 8, 2, 30))
        0.5
    """
    current = timestamp.time()

    # IDLE 구간 (작업 외 시간)
    if current < WORK_START_TIME or current >= WORK_END_TIME:
        return 0.0

    transition = timedelta(minutes=TRANSITION_DURATION_MINUTES)

    # 진입 구간: WORK_START_TIME ~ WORK_START_TIME + 5분
    start_dt = datetime.combine(timestamp.date(), WORK_START_TIME)
    transition_end = (start_dt + transition).time()

    if WORK_START_TIME <= current < transition_end:
        # 경과 시간 비율 계산
        current_dt = datetime.combine(timestamp.date(), current)
        elapsed = (current_dt - start_dt).total_seconds()
        total = transition.total_seconds()
        return elapsed / total

    # 종료 구간: WORK_END_TIME - 5분 ~ WORK_END_TIME
    end_dt = datetime.combine(timestamp.date(), WORK_END_TIME)
    transition_start = (end_dt - transition).time()

    if transition_start <= current < WORK_END_TIME:
        current_dt = datetime.combine(timestamp.date(), current)
        remaining = (end_dt - current_dt).total_seconds()
        total = transition.total_seconds()
        return remaining / total

    # 완전 WORKING 구간 (전이 외 모든 작업 시간)
    return 1.0
