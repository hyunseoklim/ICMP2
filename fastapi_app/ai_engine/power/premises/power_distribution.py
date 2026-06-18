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

    Phase B-2-8 — WORKING은 working_means(1000) 대표값 사용 (Phase B 분포 정렬).
    IDLE은 기존 POWER_MEANS_IDLE dict 유지 (그룹별 IDLE 분포 미정의).
    호출처(scenario.py, story_24h.py)는 rated_w 인자를 받지 않으므로 대표값
    채택. rated_w별 분포 필요 시 working_means(rated_w) 직접 호출 권장.

    Args:
        work_mode: WorkMode.WORKING 또는 WorkMode.IDLE. 기본 WORKING.

    Returns:
        np.ndarray (3,). 순서는 POWER_SENSOR_TYPES.

    Examples:
        >>> mean_vector(WorkMode.WORKING)   # B-2-8 후 변경됨
        array([220.   ,   1.663, 365.9  ])
        >>> mean_vector(WorkMode.IDLE)
        array([220.,   1., 220.])
    """
    if work_mode == WorkMode.WORKING:
        means_dict = working_means(1000)
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

    Phase B-2-8 — WORKING은 working_stds(1000) 대표값 사용. IDLE은 기존 dict.
    공분산 행렬 = D @ R @ D (D는 표준편차 대각 행렬, R은 상관 행렬)

    Args:
        work_mode: 작업 모드. 모드별로 다른 표준편차 사용.

    Returns:
        np.ndarray (3, 3). 양의 정부호.
    """
    if work_mode == WorkMode.WORKING:
        stds_dict = working_stds(1000)
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


# ============================================================================
# Phase B-2 — 그룹별 학습 풀 분포 (정격 그룹화)
# ============================================================================
#
# 그룹별 학습 풀 평균 — Phase B-2 *재산정* (2026-05).
#
# 산정 기준: **부하율(power_w / rated_w) < 50% 필터 후 그룹별 실측 평균**.
#
# 50% 기준 채택 이유:
#     1. Django alerts/services.py가 부하율 50% 이상을 주의(WARNING) 알람으로
#        정의. 학습 풀 = 알람 미발생 영역의 *정상 운영* 분포.
#     2. 필터 후 mean/rated ≈ 0.36~0.45 → 결정 ① "rated × 0.4 정상 평균" 정합.
#     3. 비필터 평균(자료 ①, mean/rated 0.5~0.92)은 알람 영역 30.2% 포함이
#        끌어올린 결과로 학습 풀 정의와 불일치 (B-2-3 회귀 16.7% 거부율로 감지).
#
# 산정 정책:
#     - 저전력 (50/100/200W) + 300/400W: 정상 운영 데이터 0건 또는 부족
#         · (가) 통일 공식 fallback — rated × 0.4
#         · 300W/400W는 평시 알람 영역 운영 (Finding-7) — 도메인 확인 필요
#     - 500~1000W: 필터 후 실측 평균 (n=11~44건)
#     - voltage: 절대값 220V (전 그룹 동일 분포 — 자료 ①)
#     - current: power / 220 *역산값*. 실측 current는 IntegerField 반올림으로
#       15~26% 저평가됨 (Finding-3 정량 증거). 220V 가정이 깨지면 재산정 필요.
#     - std: working_stds()에서 평균 × 0.25 통일 공식 (실측 5~22%보다 보수적).
#     - 1000W 그룹: 필터 후 채널 A/B 평균 차이 23W (그룹 평균 365.9W의 6%) →
#       Finding-5 자연 해결. 단일 학습 풀로 충분.
#
# 호환성 (B-2-3 normal_pool.py fallback 교체 후):
#     기존 train_power_models.py 무인자 호출 = rated_w=1000 기본값 fallback
#     → working_means(1000) = [220, 1.663, 365.9] → train_mean 변경됨 (의도).
#     Phase C 재학습 전제.
# ============================================================================

_GROUP_MEANS_WORKING: dict = {
    # ── (가) 통일 공식 (rated × 0.4) — 정상 운영 데이터 부족 ──
    50:   {"voltage": 220.0, "current": 0.091, "power":  20.0},  # 정상 0건
    100:  {"voltage": 220.0, "current": 0.182, "power":  40.0},  # 정상 0건
    200:  {"voltage": 220.0, "current": 0.364, "power":  80.0},  # 정상 0건
    300:  {"voltage": 220.0, "current": 0.545, "power": 120.0},  # 정상 0건 (Finding-7)
    400:  {"voltage": 220.0, "current": 0.727, "power": 160.0},  # 정상 0건 (Finding-7)
    # ── 필터 후 실측 평균 (부하율 < 50% — 정상 운영 분포) ──
    500:  {"voltage": 220.0, "current": 1.017, "power": 223.8},  # n=11, mean/rated=0.448
    600:  {"voltage": 220.0, "current": 1.160, "power": 255.2},  # n=20, mean/rated=0.425
    700:  {"voltage": 220.0, "current": 1.244, "power": 273.6},  # n=32, mean/rated=0.391
    800:  {"voltage": 220.0, "current": 1.319, "power": 290.3},  # n=29, mean/rated=0.363
    900:  {"voltage": 220.0, "current": 1.513, "power": 332.8},  # n=35, mean/rated=0.370
    1000: {"voltage": 220.0, "current": 1.663, "power": 365.9},  # n=44, mean/rated=0.366
}


def working_means(rated_w: int) -> dict:
    """그룹별 학습 풀 WORKING 평균 — 결정 ① (정격=정상 운영 상한) 기반.

    Phase B-2 산정 (실측 35~45% 패턴):
        - 저전력 (50/100/200W): (가) 통일 공식 — rated × 0.4
        - 중·고전력 (300~1000W): (다) 하이브리드 — power 실측, current P/220 역산
        - 미정의 rated_w: (가) 통일 공식 fallback

    Args:
        rated_w: 정격 전력(W).

    Returns:
        {"voltage": 220.0, "current": float, "power": float}.

    Examples:
        >>> working_means(50)
        {'voltage': 220.0, 'current': 0.091, 'power': 20.0}
        >>> working_means(1000)
        {'voltage': 220.0, 'current': 2.343, 'power': 515.4}
    """
    if rated_w in _GROUP_MEANS_WORKING:
        return dict(_GROUP_MEANS_WORKING[rated_w])
    # fallback: (가) 통일 공식
    mean_p = rated_w * 0.4
    return {"voltage": 220.0, "current": mean_p / 220.0, "power": mean_p}


def working_stds(rated_w: int) -> dict:
    """그룹별 학습 풀 WORKING 표준편차 — 평균 × 0.25 통일 공식.

    DB 실측 std 신뢰도 낮아 (Finding-3 정수 반올림 영향) 통일 공식 채택.
    voltage는 그룹 무관 절대값 5.0V.

    Args:
        rated_w: 정격 전력(W).

    Returns:
        {"voltage": 5.0, "current": float, "power": float}.
    """
    m = working_means(rated_w)
    return {
        "voltage": 5.0,
        "current": m["current"] * 0.25,
        "power":   m["power"] * 0.25,
    }
