"""
generator/power_generator/normal_pool — 전력 WORKING 학습 풀 생성.

핵심 결정 (Phase 2):
    - T.1: 학습 풀 5,000샘플
    - T.3: WORKING 모드 100% 학습
    - W.5: 220V·11A·2,420W (WORKING 평균)
    - M.7: 분해능 양자화 (V·I 0.1, P 1.0)
    - M.6: 5% 결측 주입

옴의 법칙 보장:
    - V·I만 분포에서 추출
    - P = V × I × (1 + ε) (ε는 1% 측정 노이즈)
    - 학습 풀의 P가 V×I와 합리적으로 일치

활용처:
    - 작업 단위 12 (power IF) 학습 입력
    - 작업 단위 12 (power ARIMA) 학습 입력
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np

from common.data_types import SensorBundle
from common.enums import WorkMode
from power.premises import (
    POWER_SENSOR_TYPES, POWER_RESOLUTION,
    POWER_DEVICES,
    get_distribution_params,
)
from generator.core.time_index import build_time_axis
from generator.core.nan_injector import inject_nan


# 옴의 법칙 노이즈 비율 (측정 오차 시뮬레이션)
_DEFAULT_OHM_NOISE_RATIO: float = 0.01  # 1%


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
) -> list:
    """전력 3차원 WORKING 학습 풀 생성.
    
    Args:
        n_samples: 시점 수. T.1 기본 5,000.
        start_time: 시작 시각.
        seed: 난수 시드.
        missing_ratio: 결측 비율 (M.6 기본 0.05).
        work_mode: 작업 모드. T.3에 따라 기본 WORKING.
        enforce_ohm_law: True면 P = V × I 보장.
        ohm_noise_ratio: P 측정 노이즈 비율 (기본 0.01).
        apply_quantization: 분해능 양자화.
        apply_missing: 결측 주입.
    
    Returns:
        list[SensorBundle] (n_samples 개, device_id='power_1').
    """
    if start_time is None:
        start_time = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)

    rng = np.random.default_rng(seed)

    # 1. 분포 파라미터
    params = get_distribution_params(work_mode)
    mean = params["mean"]  # [V, I, P]
    cov = params["cov"]    # 3×3

    v_idx = POWER_SENSOR_TYPES.index("voltage")
    i_idx = POWER_SENSOR_TYPES.index("current")
    p_idx = POWER_SENSOR_TYPES.index("power")

    if enforce_ohm_law:
        # 2-A. V·I만 2차원 분포에서 추출
        vi_mean = np.array([mean[v_idx], mean[i_idx]])
        vi_cov = np.array([
            [cov[v_idx, v_idx], cov[v_idx, i_idx]],
            [cov[i_idx, v_idx], cov[i_idx, i_idx]],
        ])
        vi_samples = rng.multivariate_normal(vi_mean, vi_cov, size=n_samples)

        # 3-A. P = V × I + ε (1% 측정 노이즈)
        v_samples = vi_samples[:, 0]
        i_samples = vi_samples[:, 1]
        p_expected = v_samples * i_samples
        p_noise = rng.normal(0, ohm_noise_ratio * np.abs(p_expected), size=n_samples)
        p_samples = p_expected + p_noise

        # samples[:, [V, I, P]] 형태로 결합
        samples = np.column_stack([
            np.zeros(n_samples), np.zeros(n_samples), np.zeros(n_samples)
        ])
        samples[:, v_idx] = v_samples
        samples[:, i_idx] = i_samples
        samples[:, p_idx] = p_samples
    else:
        # 2-B. V·I·P 모두 3차원 분포에서 추출
        samples = rng.multivariate_normal(mean, cov, size=n_samples)

    # 4. 분해능 양자화
    if apply_quantization:
        for i, st in enumerate(POWER_SENSOR_TYPES):
            res = POWER_RESOLUTION[st]
            samples[:, i] = np.round(samples[:, i] / res) * res

    # 5. 결측 주입
    if apply_missing and missing_ratio > 0:
        samples, _ = inject_nan(samples, missing_ratio, seed=seed + 1)

    # 6. 시간축
    timestamps = build_time_axis(start_time, n_samples)

    # 7. SensorBundle 변환
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
