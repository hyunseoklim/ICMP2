"""
power/premises/work — 전력 도메인 작업 모드별 사이클 (W.5).

본 모듈은 시스템 전제 조건서 W.5를 구현. 작업 모드(WORKING/IDLE)에 따른
전압·전류·전력 평균값과 그 사이의 전이 정의.

본 모듈이 정해주는 것:
    - WORKING 모드 평균 전력 (220V·11A·2,420W)
    - IDLE 모드 평균 전력 (220V·1A·220W)
    - 모드별 평균 dict 조회 함수

활용처:
    - power/premises/power_distribution.py: 모드별 평균 벡터 계산
    - generator/power_generator/: 작업 시간대(WORKING)와 야간(IDLE)의 전력 패턴 생성
    - generator/integrated_story/: 통합 스토리의 모드 전환 시점 전력 변화
"""

from __future__ import annotations

from common.enums import WorkMode


# ============================================================================
# W.5 작업 모드별 평균 전력
# ============================================================================

POWER_MEANS_WORKING: dict = {
    "voltage": 220.0,   # 표준 단상 전압 (V)
    "current": 11.0,    # 도장 작업 부하 (A)
    "power":   2420.0,  # = 220 × 11 (W, 옴의 법칙)
}
"""WORKING 모드 평균. 결정 W.5.

도장 작업(W.2)의 평균 부하. 옴의 법칙 P = V × I 만족.
"""

POWER_MEANS_IDLE: dict = {
    "voltage": 220.0,
    "current": 1.0,
    "power":   220.0,
}
"""IDLE 모드 평균. 결정 W.5.

대기 상태(작업 외 시간)의 최소 부하. 환기 시스템·조명 등.
"""


# ============================================================================
# 모드별 평균 조회 함수
# ============================================================================

def get_means(work_mode: WorkMode) -> dict:
    """작업 모드별 평균 dict 반환.
    
    Args:
        work_mode: WorkMode.WORKING 또는 WorkMode.IDLE.
    
    Returns:
        {"voltage": float, "current": float, "power": float}
    
    Raises:
        ValueError: 알 수 없는 work_mode.
    
    Examples:
        >>> get_means(WorkMode.WORKING)
        {'voltage': 220.0, 'current': 11.0, 'power': 2420.0}
        >>> get_means(WorkMode.IDLE)
        {'voltage': 220.0, 'current': 1.0, 'power': 220.0}
    """
    if work_mode == WorkMode.WORKING:
        return dict(POWER_MEANS_WORKING)
    if work_mode == WorkMode.IDLE:
        return dict(POWER_MEANS_IDLE)
    raise ValueError(f"알 수 없는 work_mode: {work_mode!r}")
