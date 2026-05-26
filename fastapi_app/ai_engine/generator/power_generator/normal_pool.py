"""
generator/power_generator/normal_pool — 전력 WORKING 학습 풀 생성.

핵심 결정 (Phase 2):
    - T.1: 학습 풀 5,000샘플
    - T.3: WORKING 모드 100% 학습
    - W.5: 220V·11A·2,420W (WORKING 평균) — 기존 경로 한정
    - M.7: 분해능 양자화 (V·I 0.1, P 1.0)
    - M.6: 5% 결측 주입

옴의 법칙 보장 (기존 경로):
    - V·I만 분포에서 추출
    - P = V × I × (1 + ε) (ε는 1% 측정 노이즈)
    - 학습 풀의 P가 V×I와 합리적으로 일치

Phase B-1 — 그룹별 학습 풀 생성을 위한 인프라:
    - sample_truncated() 함수 신설 — 다변량 truncated normal (rejection sampling).
      음수 + 정격 상한 초과 샘플을 거부하여 분포 모양 보존 (B-3).
    - generate_power_normal_pool() 시그니처 확장 — rated_w, mean, std, 임계.
    - mean/std 명시 시 신규 truncated 경로, 미명시 시 기존 경로 (회귀 호환).
    - 신규 경로의 옴의 법칙 통합은 B-2/C 진입 시 보강.

활용처:
    - 작업 단위 12 (power IF) 학습 입력
    - 작업 단위 12 (power ARIMA) 학습 입력
    - Phase C — 그룹별 IF 11개 모델 학습 입력
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

import numpy as np

from common.data_types import SensorBundle
from common.enums import WorkMode
from power.premises import (
    POWER_SENSOR_TYPES, POWER_RESOLUTION,
    POWER_DEVICES,
    correlation_matrix,
    working_means,
    working_stds,
)
from generator.core.time_index import build_time_axis
from generator.core.nan_injector import inject_nan


logger = logging.getLogger(__name__)


# 옴의 법칙 노이즈 비율 (측정 오차 시뮬레이션)
_DEFAULT_OHM_NOISE_RATIO: float = 0.01  # 1%

# Phase B-1 — truncated sampling 임계
_DEFAULT_STOP_REJECTION_RATIO: float = 0.05  # 5% 초과 시 stop & report
_DEFAULT_WARN_REJECTION_RATIO: float = 0.01  # 1% 초과 시 std 가정 재검토 alert
_DEFAULT_MAX_ATTEMPTS: int = 10              # rejection sampling 시 최대 시도 배수


class RejectionRateExceeded(RuntimeError):
    """학습 풀 생성 중 rejection ratio가 stop 임계를 초과했을 때 발생.

    원인 예시:
        - mean이 정격(rated_w) 상한에 너무 가까움 → 평균+4σ가 상한 초과
        - std가 너무 큼 → 분포 꼬리가 [lower, upper] 밖
        - lower/upper 범위가 분포에 비해 너무 좁음

    대응: mean/std 가정 재검토, 또는 stop_rejection_ratio를 그룹별로 완화.
    """
    pass


def _std_dict_to_cov(std: dict) -> np.ndarray:
    """std dict + 상관 행렬 → 공분산 행렬.

    cov = D · R · D, D는 std 대각행렬, R은 POWER_CORRELATIONS 기반 상관 행렬.
    """
    R = correlation_matrix()
    std_arr = np.array(
        [std["voltage"], std["current"], std["power"]],
        dtype=float,
    )
    D = np.diag(std_arr)
    return D @ R @ D


def sample_truncated(
    mean: dict,
    cov: np.ndarray,
    n: int,
    lower: dict,
    upper: dict,
    seed: Optional[int] = None,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
) -> Tuple[np.ndarray, int, int]:
    """다변량 truncated normal — rejection sampling.

    모든 차원이 [lower, upper] 범위 내인 샘플만 채택. Phase B-3의 음수·상한
    초과 제어용. 거부율 임계 검사는 호출자(generate_power_normal_pool 또는
    단위 테스트)가 수행한다.

    Args:
        mean: {"voltage": float, "current": float, "power": float}.
        cov:  3×3 공분산 행렬 (POWER_SENSOR_TYPES 순서).
        n:    채택 목표 샘플 수.
        lower: 차원별 하한 (포함). 예: {"voltage": 0, "current": 0, "power": 0}.
        upper: 차원별 상한 (포함).
        seed: 난수 시드. None이면 numpy 기본 RNG 사용.
        max_attempts: 총 시도 횟수 상한 배수. 총 시도 ≤ n × max_attempts.
                      초과 시 부족분 그대로 반환 (호출자가 부족 판단).

    Returns:
        (samples, n_dist_rejected, n_attempted)
            samples: shape (k, 3). k ≤ n — 채택된 샘플 (POWER_SENSOR_TYPES 순서).
            n_dist_rejected: *분포 거부* 샘플 수 — mask=False(범위 밖)만 카운트.
                             알고리즘 슬라이싱 손실(부족분 채우려 batch=100 생성 후
                             초과분 버림)은 거부 아님 → 별도 처리.
            n_attempted: 총 분포 추출 시도 수 (multivariate_normal 호출 합).
    """
    rng = np.random.default_rng(seed)
    mu = np.array(
        [mean["voltage"], mean["current"], mean["power"]],
        dtype=float,
    )
    lo = np.array(
        [lower["voltage"], lower["current"], lower["power"]],
        dtype=float,
    )
    hi = np.array(
        [upper["voltage"], upper["current"], upper["power"]],
        dtype=float,
    )

    accepted: list = []
    n_attempted = 0
    n_dist_rejected = 0  # 분포 거부만 카운트 (슬라이싱 손실과 분리)
    max_total = max(n * max_attempts, n + 100)
    while len(accepted) < n and n_attempted < max_total:
        batch_size = max(n - len(accepted), 100)
        batch = rng.multivariate_normal(mu, cov, size=batch_size)
        n_attempted += batch_size
        mask = np.all((batch >= lo) & (batch <= hi), axis=1)
        n_dist_rejected += int(np.sum(~mask))
        accepted.extend(batch[mask].tolist())

    accepted_arr = np.array(accepted[:n], dtype=float)
    return accepted_arr, n_dist_rejected, n_attempted


def _ohm_truncated(
    mean: dict,
    cov: np.ndarray,
    n: int,
    lower: dict,
    upper: dict,
    ohm_noise_ratio: float,
    seed: Optional[int] = None,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
) -> Tuple[np.ndarray, int, int]:
    """옴의 법칙 P = V × I 보장 + truncated sampling (B-2-3 통합).

    V, I만 2변량 분포에서 추출 → P = V × I + ε(1% 노이즈)로 계산 →
    V, I, P 모두 [lower, upper] 범위 내인 샘플만 채택.

    Args:
        mean: 3차원 평균 dict (POWER_SENSOR_TYPES 키).
        cov:  3×3 공분산 (POWER_SENSOR_TYPES 순서).
        n:    채택 목표 샘플 수.
        lower/upper: 차원별 하한/상한.
        ohm_noise_ratio: P = V·I × (1 + ε) 노이즈 비율.
        seed: 난수 시드.
        max_attempts: 최대 시도 배수.

    Returns:
        (samples, n_dist_rejected, n_attempted).
            samples: POWER_SENSOR_TYPES 순서로 정렬된 (k, 3) 배열.
            n_dist_rejected: *분포 거부*만 카운트 (mask=False). 슬라이싱 손실 분리.
            n_attempted: 총 분포 추출 시도 수.
    """
    rng = np.random.default_rng(seed)
    v_idx = POWER_SENSOR_TYPES.index("voltage")
    i_idx = POWER_SENSOR_TYPES.index("current")

    vi_mean = np.array([mean["voltage"], mean["current"]], dtype=float)
    vi_cov = np.array([
        [cov[v_idx, v_idx], cov[v_idx, i_idx]],
        [cov[i_idx, v_idx], cov[i_idx, i_idx]],
    ])

    lo = np.array(
        [lower["voltage"], lower["current"], lower["power"]],
        dtype=float,
    )
    hi = np.array(
        [upper["voltage"], upper["current"], upper["power"]],
        dtype=float,
    )

    accepted: list = []
    n_attempted = 0
    n_dist_rejected = 0  # 분포 거부만 카운트 (슬라이싱 손실과 분리)
    max_total = max(n * max_attempts, n + 100)
    while len(accepted) < n and n_attempted < max_total:
        batch_size = max(n - len(accepted), 100)
        vi_batch = rng.multivariate_normal(vi_mean, vi_cov, size=batch_size)
        n_attempted += batch_size
        v_batch = vi_batch[:, 0]
        i_batch = vi_batch[:, 1]
        p_expected = v_batch * i_batch
        p_noise = rng.normal(
            0, ohm_noise_ratio * np.abs(p_expected), size=batch_size,
        )
        p_batch = p_expected + p_noise
        # POWER_SENSOR_TYPES 순서대로 결합 (voltage, current, power)
        batch_3d = np.column_stack([v_batch, i_batch, p_batch])
        mask = np.all((batch_3d >= lo) & (batch_3d <= hi), axis=1)
        n_dist_rejected += int(np.sum(~mask))
        accepted.extend(batch_3d[mask].tolist())

    accepted_arr = np.array(accepted[:n], dtype=float)
    return accepted_arr, n_dist_rejected, n_attempted


def generate_power_normal_pool(
    n_samples: int = 5000,
    start_time: Optional[datetime] = None,
    seed: int = 42,
    missing_ratio: float = 0.05,
    work_mode: WorkMode = WorkMode.WORKING,
    enforce_ohm_law: bool = True,
    ohm_noise_ratio: float = _DEFAULT_OHM_NOISE_RATIO,
    apply_quantization: bool = True,
    apply_missing: bool = True,
    # ── Phase B-1 신규 인자 (B-2에서 working_means/working_stds로 호출) ──
    rated_w: int = 1000,
    mean: Optional[dict] = None,
    std: Optional[dict] = None,
    stop_rejection_ratio: float = _DEFAULT_STOP_REJECTION_RATIO,
    warn_rejection_ratio: float = _DEFAULT_WARN_REJECTION_RATIO,
) -> list:
    """전력 3차원 WORKING 학습 풀 생성.

    Phase B-2-3 통일 흐름 (의사코드 §2-2 채택):
        1. mean/std 미명시 → working_means(rated_w)/working_stds(rated_w) 보충
        2. cov = D · R · D (std 대각 × 상관 행렬)
        3. rated_w 기반 상한 적용 (V=270, A=rated/220×1.5, P=rated×1.0)
        4. enforce_ohm_law=True → _ohm_truncated (V·I 추출 + P=V·I+ε + 3D 검사)
           enforce_ohm_law=False → sample_truncated (V·I·P 직접 추출)
        5. rejection ratio 임계 검사 → stop/warn/info 로깅

    의도된 변경 (Phase B 핵심):
        무인자 호출도 fallback이 working_means(1000) = [220, 2.343, 515.4]로
        진입하므로 학습 풀 평균이 기존 [220, 11, 2420]에서 변경된다. 모델
        메타데이터 train_mean도 함께 바뀐다 — Phase C 재학습 전제.

    Args:
        n_samples: 시점 수. T.1 기본 5,000.
        start_time: 시작 시각.
        seed: 난수 시드.
        missing_ratio: 결측 비율 (M.6 기본 0.05).
        work_mode: 작업 모드. B-2-3 후 *deprecated* — 그룹별 분포가 모드를
                   대체. WorkMode.IDLE 호출 시 향후 working_means_idle 등으로
                   확장 필요 (현재 무시됨).
        enforce_ohm_law: True면 P = V × I 보장 (_ohm_truncated 경로).
        ohm_noise_ratio: P = V·I + ε 측정 노이즈 비율 (기본 0.01).
        apply_quantization: 분해능 양자화.
        apply_missing: 결측 주입.
        rated_w: 정격 전력(W). 상한 결정 + working_means/working_stds fallback.
        mean: {"voltage": V, "current": A, "power": W}. None이면 working_means.
        std:  {"voltage": V, "current": A, "power": W}. None이면 working_stds.
        stop_rejection_ratio: rejection 비율 stop 임계 (B-3).
        warn_rejection_ratio: rejection 비율 warn 임계 (B-3).

    Returns:
        list[SensorBundle] (실제 생성 수 ≤ n_samples, device_id='power_1').

    Raises:
        RejectionRateExceeded: rejection 비율이 stop 임계 초과.
    """
    if start_time is None:
        start_time = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)

    # work_mode는 B-2-3 후 deprecated (그룹별 분포가 모드를 대체).
    # 향후 working_means_idle 등 확장 시 본 변수 활용 예정.
    _ = work_mode

    # ── B-2-3: fallback — mean/std None이면 working_means/working_stds 보충 ──
    if mean is None:
        mean = working_means(rated_w)
    if std is None:
        std = working_stds(rated_w)

    cov = _std_dict_to_cov(std)
    lower = {"voltage": 0.0, "current": 0.0, "power": 0.0}
    upper = {
        "voltage": 270.0,
        "current": rated_w / 220.0 * 1.5,
        "power": float(rated_w),
    }

    if enforce_ohm_law:
        # 옴의 법칙 보장 + truncated — V·I 추출 → P=V·I+ε → V·I·P 모두 검사
        samples, n_dist_rejected, n_attempted = _ohm_truncated(
            mean=mean, cov=cov, n=n_samples,
            lower=lower, upper=upper,
            ohm_noise_ratio=ohm_noise_ratio, seed=seed,
        )
    else:
        # 옴의 법칙 미보장 — V·I·P 3차원 직접 truncated
        samples, n_dist_rejected, n_attempted = sample_truncated(
            mean=mean, cov=cov, n=n_samples,
            lower=lower, upper=upper, seed=seed,
        )

    # 분포 거부 비율 — 슬라이싱 손실 제외 (회계 분리, B-2-3 정정)
    ratio = (n_dist_rejected / n_attempted) if n_attempted > 0 else 0.0
    if ratio > stop_rejection_ratio:
        raise RejectionRateExceeded(
            f"학습 풀 생성 중단 — rated_w={rated_w}, "
            f"분포 거부={ratio:.1%} > stop={stop_rejection_ratio:.0%}. "
            f"mean/std 가정 또는 stop_rejection_ratio 재검토 필요."
        )
    elif ratio > warn_rejection_ratio:
        logger.warning(
            "rated_w=%s 분포 거부=%.1f%% — std/mean 가정 재검토 alert",
            rated_w, ratio * 100,
        )
    else:
        logger.info(
            "rated_w=%s 분포 거부=%.3f%% (채택=%d, 시도=%d)",
            rated_w, ratio * 100, len(samples), n_attempted,
        )

    if len(samples) < n_samples:
        logger.warning(
            "rated_w=%s 채택 부족 — 목표 %d, 실제 %d (max_attempts 도달)",
            rated_w, n_samples, len(samples),
        )

    n_actual = len(samples)

    # 분해능 양자화
    if apply_quantization:
        for i, st in enumerate(POWER_SENSOR_TYPES):
            res = POWER_RESOLUTION[st]
            samples[:, i] = np.round(samples[:, i] / res) * res

    # 결측 주입
    if apply_missing and missing_ratio > 0:
        samples, _ = inject_nan(samples, missing_ratio, seed=seed + 1)

    # 시간축
    timestamps = build_time_axis(start_time, n_actual)

    # SensorBundle 변환
    bundles = []
    for t_idx, ts in enumerate(timestamps):
        values = {}
        flags = {}
        for i, st in enumerate(POWER_SENSOR_TYPES):
            v = samples[t_idx, i]
            is_nan = np.isnan(v)
            values[st] = None if is_nan else float(v)
            flags[st] = not is_nan
        bundles.append(SensorBundle(
            timestamp=ts, device_id="power_1",
            values=values, is_valid_flags=flags,
        ))

    return bundles
