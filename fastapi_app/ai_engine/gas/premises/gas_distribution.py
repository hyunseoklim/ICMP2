"""
gas/premises/gas_distribution — 가스 9종 분포 정의 (E.2).

본 모듈은 시스템 전제 조건서 E.2를 코드 상수·함수로 구현한다.
가스 9종의 평균·표준편차와 상관 행렬을 정의하고,
환기 단계별 평균 벡터 + 공분산 행렬을 산출하는 함수 제공.

본 모듈이 정해주는 것:
    - 가스 9종 sensor_type 리스트 (순서 고정 — 벡터 차원 정의)
    - NORMAL 환기 기준 평균·표준편차
    - 가스 간 상관 관계 (비대각 항)
    - 환기 단계별 평균 벡터 / 공분산 행렬 함수

활용처:
    - gas/modules/isolation_forest.py: 학습 데이터 다변량 정규분포 정의
    - generator/gas_generator/: 합성 데이터 샘플링 시 분포 정의
    - tests/gas/: 결과 검증 시 정답 분포

근거 (Phase 2 E.2):
    - O2 ↔ CO2: -0.3 (호흡 작용)
    - CO ↔ VOC: +0.4 (동일 연소원)
    - CO ↔ NO2: +0.3 (동일 연소원)
    - 기타: 0 (독립)
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .environment import VentilationLevel, VENTILATION_MEAN_MULTIPLIER, VENTILATION_O2_MULTIPLIER


# ============================================================================
# 가스 9종 sensor_type 순서 (벡터 차원 정의)
# ============================================================================

GAS_SENSOR_TYPES: list = [
    "co",   # 일산화탄소
    "h2s",  # 황화수소
    "co2",  # 이산화탄소
    "o2",   # 산소
    "no2",  # 이산화질소
    "so2",  # 이산화황
    "o3",   # 오존
    "nh3",  # 암모니아
    "voc",  # 휘발성 유기화합물
]
"""가스 9종 sensor_type. 본 순서가 *벡터 차원의 정의*.

mean_vector(), covariance_matrix(), correlation_matrix()의 반환값은
본 리스트의 순서를 따른다. SensorBundle.to_vector(GAS_SENSOR_TYPES)로
9차원 벡터 변환 시에도 본 순서 사용.
"""

GAS_DIMENSION: int = 9
"""가스 차원 수. 항상 9 (B.2 가스 IF 9차원)."""


# ============================================================================
# NORMAL 환기 평균·표준편차
# ============================================================================

GAS_MEANS_NORMAL: dict = {
    "co":  5.0,
    "h2s": 1.0,
    "co2": 450.0,
    "o2":  20.9,
    "no2": 0.1,
    "so2": 0.1,
    "o3":  0.02,
    "nh3": 5.0,
    "voc": 50.0,
}
"""NORMAL 환기 기준 가스 평균. 결정 E.2.

단위: 모두 ppm (O2는 %vol).
환기 단계 변경 시 environment.VENTILATION_MEAN_MULTIPLIER 배수 적용.
"""

GAS_STDS: dict = {
    "co":  1.5,
    "h2s": 0.3,
    "co2": 50.0,
    "o2":  0.3,
    "no2": 0.05,
    "so2": 0.05,
    "o3":  0.01,
    "nh3": 1.5,
    "voc": 15.0,
}
"""가스 9종 표준편차. 결정 E.2.

환기 단계 변경에 *무관*하게 일정한 변동성 가정.
(평균만 환기 단계별로 변동, 표준편차·상관은 일정)
"""


# ============================================================================
# 가스 간 상관 관계 (비대각 항만)
# ============================================================================

GAS_CORRELATIONS: dict = {
    ("o2", "co2"): -0.3,
    ("co", "voc"): +0.4,
    ("co", "no2"): +0.3,
}
"""가스 간 상관 관계. 결정 E.2.

키는 (sensor_type1, sensor_type2) 튜플. 본 dict에 없는 쌍은 *상관 0* (독립).
대칭 처리는 correlation_matrix() 함수가 자동 수행 — (a,b)와 (b,a) 동일하게 적용.

근거:
    - O2 ↔ CO2 = -0.3: 호흡 작용 (CO2 증가 시 O2 감소)
    - CO ↔ VOC = +0.4: 동일 연소원 (도장 작업 휘발성)
    - CO ↔ NO2 = +0.3: 동일 연소원
"""


# ============================================================================
# 함수: 상관 행렬 생성
# ============================================================================

def correlation_matrix() -> np.ndarray:
    """가스 9종 상관 행렬을 9×9 numpy 배열로 반환.
    
    GAS_CORRELATIONS dict에서 비대각 항만 가져와 대칭 행렬 구성.
    대각은 모두 1.0. dict에 없는 쌍은 0.0.
    
    Returns:
        np.ndarray (9, 9). 행/열 순서는 GAS_SENSOR_TYPES와 동일.
    
    Examples:
        >>> R = correlation_matrix()
        >>> R.shape
        (9, 9)
        >>> # CO(0) ↔ VOC(8) 위치
        >>> R[0, 8]
        0.4
    """
    n = GAS_DIMENSION
    R = np.eye(n, dtype=float)

    # sensor_type → 인덱스 매핑
    idx = {st: i for i, st in enumerate(GAS_SENSOR_TYPES)}

    for (st1, st2), rho in GAS_CORRELATIONS.items():
        if st1 not in idx or st2 not in idx:
            raise ValueError(
                f"GAS_CORRELATIONS의 키 {(st1, st2)!r}는 "
                f"GAS_SENSOR_TYPES에 있어야 함"
            )
        i, j = idx[st1], idx[st2]
        R[i, j] = rho
        R[j, i] = rho

    return R


# ============================================================================
# 함수: 환기 단계별 평균 벡터
# ============================================================================

def mean_vector(
    ventilation: VentilationLevel = VentilationLevel.NORMAL,
) -> np.ndarray:
    """환기 단계에 따른 가스 9차원 평균 벡터 반환.
    
    NORMAL 환기 기준 평균(GAS_MEANS_NORMAL)에 환기 단계별 배수 적용.
    O2는 다른 가스와 반대 방향이므로 별도 배수 사용.
    
    Args:
        ventilation: 환기 단계. 기본 NORMAL.
    
    Returns:
        np.ndarray (9,). 순서는 GAS_SENSOR_TYPES와 동일.
    
    Examples:
        >>> v_normal = mean_vector(VentilationLevel.NORMAL)
        >>> v_normal[0]  # CO
        5.0
        >>> v_weak = mean_vector(VentilationLevel.WEAK)
        >>> v_weak[0]    # CO × 2.0 (환기 부족)
        10.0
        >>> v_weak[3]    # O2 × 0.95 (환기 부족 시 약간 감소)
        19.855
    """
    general_mul = VENTILATION_MEAN_MULTIPLIER[ventilation]
    o2_mul = VENTILATION_O2_MULTIPLIER[ventilation]

    result = np.empty(GAS_DIMENSION, dtype=float)
    for i, st in enumerate(GAS_SENSOR_TYPES):
        base_mean = GAS_MEANS_NORMAL[st]
        if st == "o2":
            result[i] = base_mean * o2_mul
        else:
            result[i] = base_mean * general_mul

    return result


# ============================================================================
# 함수: 환기 단계별 공분산 행렬
# ============================================================================

def covariance_matrix(
    ventilation: VentilationLevel = VentilationLevel.NORMAL,
) -> np.ndarray:
    """가스 9종 공분산 행렬 반환.
    
    공분산 행렬 = D @ R @ D
    (D는 표준편차 대각 행렬, R은 상관 행렬)
    
    표준편차·상관은 환기 단계와 *무관*하게 일정.
    환기 단계 인자는 *시그니처 일관성*과 후속 확장(환기별 변동성 변경)을 위해 유지.
    
    Args:
        ventilation: 환기 단계 (본 모듈에서는 사용 안 함, 시그니처 일관성).
    
    Returns:
        np.ndarray (9, 9). 양의 정부호.
    
    Examples:
        >>> C = covariance_matrix()
        >>> C.shape
        (9, 9)
        >>> # 대각: 분산 = 표준편차^2
        >>> C[0, 0]  # CO 분산 = 1.5^2 = 2.25
        2.25
    """
    R = correlation_matrix()
    std_array = np.array(
        [GAS_STDS[st] for st in GAS_SENSOR_TYPES],
        dtype=float,
    )
    D = np.diag(std_array)
    C = D @ R @ D
    return C


# ============================================================================
# 함수: 분포 파라미터 일괄 조회
# ============================================================================

def get_distribution_params(
    ventilation: VentilationLevel = VentilationLevel.NORMAL,
) -> dict:
    """환기 단계별 다변량 정규분포 파라미터를 dict로 반환.
    
    Args:
        ventilation: 환기 단계.
    
    Returns:
        dict — keys: "mean", "cov", "sensor_types".
    
    Examples:
        >>> params = get_distribution_params(VentilationLevel.NORMAL)
        >>> params["mean"].shape
        (9,)
        >>> params["cov"].shape
        (9, 9)
        >>> # numpy 다변량 샘플링 직접 호출 가능
        >>> samples = np.random.multivariate_normal(
        ...     params["mean"], params["cov"], size=100
        ... )
    """
    return {
        "mean": mean_vector(ventilation),
        "cov": covariance_matrix(ventilation),
        "sensor_types": list(GAS_SENSOR_TYPES),
    }
