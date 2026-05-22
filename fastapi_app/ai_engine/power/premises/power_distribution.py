"""
power/premises/power_distribution — 전력 3차원 분포 정의.

본 모듈은 전력 3채널(voltage·current·power)의 평균·표준편차·상관·공분산을
정의하고, 작업 모드(WORKING/IDLE)별 분포 파라미터를 산출하는 함수 제공.

본 모듈이 정해주는 것:
    - 전력 3종 sensor_type 순서 (벡터 차원 정의)
    - 모드별 평균·표준편차
    - 채널 간 상관 (옴의 법칙 P = V × I 반영)
    - 모드별 평균 벡터 / 공분산 행렬 함수

활용처:
    - power/modules/isolation_forest.py: 학습 데이터 분포 정의
    - generator/power_generator/: 합성 데이터 샘플링

근거 (Phase 2 + 본 단위 추가 결정):
    - W.5 모드별 평균 (work.py 참조)
    - 전압-전류 상관 +0.3 (전압 변동의 부하 영향)
    - 전압-전력 상관 +0.6
    - 전류-전력 상관 +0.95 (P=V·I로 강한 상관)
"""

from __future__ import annotations

import numpy as np

from common.enums import WorkMode
from .work import POWER_MEANS_WORKING, POWER_MEANS_IDLE


# ============================================================================
# 전력 3종 sensor_type 순서 (벡터 차원 정의)
# ============================================================================

POWER_SENSOR_TYPES: list = ["voltage", "current", "power"]
"""전력 3종 sensor_type. 본 순서가 *벡터 차원의 정의*.

mean_vector(), covariance_matrix(), correlation_matrix()의 반환값은
본 리스트의 순서를 따른다.
"""

POWER_DIMENSION: int = 3
"""전력 차원 수. 항상 3 (B.2 전력 IF 3차원)."""


# ============================================================================
# 모드별 표준편차
# ============================================================================

POWER_STDS_WORKING: dict = {
    "voltage": 5.0,     # ±5V (전원 변동)
    "current": 0.5,     # ±0.5A (부하 변동)
    "power":   110.0,   # ±110W (V·I 연동 변동성)
}
"""WORKING 모드 표준편차."""

POWER_STDS_IDLE: dict = {
    "voltage": 5.0,
    "current": 0.1,
    "power":   22.0,
}
"""IDLE 모드 표준편차. 부하 작아서 절대 변동 작음."""


# ============================================================================
# 채널 간 상관 관계 (모드 무관)
# ============================================================================

POWER_CORRELATIONS: dict = {
    ("voltage", "current"): 0.1,   # V는 거의 일정 → I 영향 미미
    ("voltage", "power"):   0.3,   # V는 거의 일정 → P 영향 미미
    ("current", "power"):   0.95,  # P = V × I → V 일정이면 P ∝ I (강한 상관)
}
"""전력 채널 간 상관. 옴의 법칙 P = V × I 반영.

설계 근거 (Phase 4 작업 단위 12 검증 단계 보정):
    - V는 작업장 전원으로 *거의 일정* → I·P와 약한 상관만 가짐
    - I는 부하 변동에 따라 큰 변화 → P와 강한 상관 (V 일정이면 P ∝ I)

본 값들은 *양의 정부호 공분산 행렬*을 만족하도록 보정됨.
(원안 0.3/0.6/0.95는 행렬식 음수 → 다변량 분포 정의 불가)
"""


# ============================================================================
# 함수: 상관 행렬 생성
# ============================================================================

def correlation_matrix() -> np.ndarray:
    """전력 3채널 상관 행렬을 3×3 numpy 배열로 반환.
    
    Returns:
        np.ndarray (3, 3). 순서는 POWER_SENSOR_TYPES와 동일.
    """
    n = POWER_DIMENSION
    R = np.eye(n, dtype=float)
    idx = {st: i for i, st in enumerate(POWER_SENSOR_TYPES)}

    for (st1, st2), rho in POWER_CORRELATIONS.items():
        if st1 not in idx or st2 not in idx:
            raise ValueError(
                f"POWER_CORRELATIONS의 키 {(st1, st2)!r}는 "
                f"POWER_SENSOR_TYPES에 있어야 함"
            )
        i, j = idx[st1], idx[st2]
        R[i, j] = rho
        R[j, i] = rho

    return R


# ============================================================================
# 함수: 모드별 평균 벡터
# ============================================================================

def mean_vector(work_mode: WorkMode = WorkMode.WORKING) -> np.ndarray:
    """작업 모드별 전력 3차원 평균 벡터 반환.
    
    Args:
        work_mode: WorkMode.WORKING 또는 WorkMode.IDLE. 기본 WORKING.
    
    Returns:
        np.ndarray (3,). 순서는 POWER_SENSOR_TYPES.
    
    Examples:
        >>> mean_vector(WorkMode.WORKING)
        array([ 220.,   11., 2420.])
        >>> mean_vector(WorkMode.IDLE)
        array([220.,   1., 220.])
    """
    if work_mode == WorkMode.WORKING:
        means_dict = POWER_MEANS_WORKING
    elif work_mode == WorkMode.IDLE:
        means_dict = POWER_MEANS_IDLE
    else:
        raise ValueError(f"알 수 없는 work_mode: {work_mode!r}")

    return np.array(
        [means_dict[st] for st in POWER_SENSOR_TYPES],
        dtype=float,
    )


# ============================================================================
# 함수: 모드별 공분산 행렬
# ============================================================================

def covariance_matrix(work_mode: WorkMode = WorkMode.WORKING) -> np.ndarray:
    """전력 3차원 공분산 행렬 반환.
    
    공분산 행렬 = D @ R @ D
    (D는 표준편차 대각 행렬, R은 상관 행렬)
    
    Args:
        work_mode: 작업 모드. 모드별로 다른 표준편차 사용.
    
    Returns:
        np.ndarray (3, 3). 양의 정부호.
    """
    if work_mode == WorkMode.WORKING:
        stds_dict = POWER_STDS_WORKING
    elif work_mode == WorkMode.IDLE:
        stds_dict = POWER_STDS_IDLE
    else:
        raise ValueError(f"알 수 없는 work_mode: {work_mode!r}")

    R = correlation_matrix()
    std_array = np.array(
        [stds_dict[st] for st in POWER_SENSOR_TYPES],
        dtype=float,
    )
    D = np.diag(std_array)
    return D @ R @ D


# ============================================================================
# 함수: 분포 파라미터 일괄 조회
# ============================================================================

def get_distribution_params(
    work_mode: WorkMode = WorkMode.WORKING,
) -> dict:
    """작업 모드별 다변량 정규분포 파라미터를 dict로 반환.
    
    Args:
        work_mode: 작업 모드.
    
    Returns:
        dict — keys: "mean", "cov", "sensor_types".
    """
    return {
        "mean": mean_vector(work_mode),
        "cov": covariance_matrix(work_mode),
        "sensor_types": list(POWER_SENSOR_TYPES),
    }
