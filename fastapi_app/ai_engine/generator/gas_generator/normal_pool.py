"""
generator/gas_generator/normal_pool — 가스 NORMAL 환기 학습 풀 생성.

본 모듈은 Phase 4 검증의 *가스 학습 풀 5000샘플*을 생성한다.

핵심 결정 (Phase 2):
    - T.1: 학습 풀 5,000샘플
    - T.3: NORMAL 환기 100% 학습 분포
    - M.7: 9가스 분해능 양자화
    - M.6: 5% 결측 주입
    - M.2: 두 장비(gas_A, gas_B) 간 상관 ρ = 0.78

생성 프로세스:
    1. 9차원 다변량 정규분포 추출 (n_samples)
    2. 장비 별로 측정 — gas_A·gas_B 간 잔차 결합으로 상관 0.78 적용
    3. M.7 분해능 양자화
    4. M.6 결측 5% 주입
    5. SensorBundle 시퀀스 반환

활용처:
    - 작업 단위 10 (gas IF) 학습 입력
    - 작업 단위 11 (gas ARIMA) 학습 입력
    - tests/gas/: 학습 풀 통계 검증
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

from common.data_types import SensorBundle
from gas.premises import (
    GAS_SENSOR_TYPES, GAS_RESOLUTION,
    GAS_DEVICES, INTER_DEVICE_GAS_CORRELATION,
    VentilationLevel, get_distribution_params,
)
from generator.core.quantizer import quantize_value
from generator.core.time_index import build_time_axis
from generator.core.nan_injector import inject_nan


def generate_gas_normal_pool(
    n_samples: int = 5000,
    start_time: Optional[datetime] = None,
    seed: int = 42,
    missing_ratio: float = 0.05,
    ventilation: VentilationLevel = VentilationLevel.NORMAL,
    apply_quantization: bool = True,
    apply_missing: bool = True,
) -> list:
    """가스 9차원 학습 풀 생성 (gas_A, gas_B 모두 포함).
    
    Args:
        n_samples: 시점 수 (각 장비별 동일). T.1 기본 5,000.
        start_time: 시작 시각. None이면 2026-05-19 09:00 UTC.
        seed: 난수 시드 (재현성).
        missing_ratio: 결측 비율 (M.6 기본 0.05).
        ventilation: 환기 단계. T.3에 따라 기본 NORMAL.
        apply_quantization: 분해능 양자화 적용 여부.
        apply_missing: 결측 주입 여부.
    
    Returns:
        list[SensorBundle]:
            n_samples × 2장비 = 2 * n_samples 개 SensorBundle.
            시간 순서: [t0/gas_A, t0/gas_B, t1/gas_A, t1/gas_B, ...]
    
    Examples:
        >>> bundles = generate_gas_normal_pool(n_samples=100)
        >>> len(bundles)
        200
        >>> bundles[0].device_id
        'gas_A'
        >>> bundles[1].device_id
        'gas_B'
    """
    if start_time is None:
        from datetime import timezone
        start_time = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)

    rng = np.random.default_rng(seed)

    # 1. 환기 단계 분포 파라미터
    params = get_distribution_params(ventilation)
    mean = params["mean"]
    cov = params["cov"]

    # 2. 9차원 *공통 분포*에서 n_samples 추출 — "참값"으로 간주
    truth = rng.multivariate_normal(mean, cov, size=n_samples)

    # 3. 장비별 잔차 결합으로 상관 0.78 적용
    # gas_A = truth + noise_A
    # gas_B = truth + noise_B (noise_A, noise_B는 독립)
    # → Corr(gas_A, gas_B) = Var(truth) / (Var(truth) + Var(noise))
    #
    # 목표 상관 ρ = 0.78이면:
    # ρ = σ²_truth / (σ²_truth + σ²_noise)
    # σ²_noise = σ²_truth × (1 - ρ) / ρ
    #
    # 즉, noise std = truth std × √((1 - ρ) / ρ)
    rho = INTER_DEVICE_GAS_CORRELATION
    noise_scale = np.sqrt((1.0 - rho) / rho)

    # 각 가스의 std로 노이즈 스케일링
    gas_stds = np.array([
        np.sqrt(cov[i, i]) for i in range(len(GAS_SENSOR_TYPES))
    ])
    noise_std = gas_stds * noise_scale

    noise_A = rng.normal(0, noise_std, size=(n_samples, len(GAS_SENSOR_TYPES)))
    noise_B = rng.normal(0, noise_std, size=(n_samples, len(GAS_SENSOR_TYPES)))

    samples_A = truth + noise_A
    samples_B = truth + noise_B

    # 4. 분해능 양자화
    if apply_quantization:
        for i, st in enumerate(GAS_SENSOR_TYPES):
            res = GAS_RESOLUTION[st]
            samples_A[:, i] = np.round(samples_A[:, i] / res) * res
            samples_B[:, i] = np.round(samples_B[:, i] / res) * res

    # 5. 결측 주입
    if apply_missing and missing_ratio > 0:
        samples_A, _ = inject_nan(samples_A, missing_ratio, seed=seed + 1)
        samples_B, _ = inject_nan(samples_B, missing_ratio, seed=seed + 2)

    # 6. 시간축 생성
    timestamps = build_time_axis(start_time, n_samples)

    # 7. SensorBundle 변환
    bundles = []
    for t_idx, ts in enumerate(timestamps):
        # gas_A
        values_A = {}
        flags_A = {}
        for i, st in enumerate(GAS_SENSOR_TYPES):
            v = samples_A[t_idx, i]
            is_nan = np.isnan(v)
            values_A[st] = None if is_nan else float(v)
            flags_A[st] = not is_nan
        bundles.append(SensorBundle(
            timestamp=ts, device_id="gas_A",
            values=values_A, is_valid_flags=flags_A,
        ))

        # gas_B
        values_B = {}
        flags_B = {}
        for i, st in enumerate(GAS_SENSOR_TYPES):
            v = samples_B[t_idx, i]
            is_nan = np.isnan(v)
            values_B[st] = None if is_nan else float(v)
            flags_B[st] = not is_nan
        bundles.append(SensorBundle(
            timestamp=ts, device_id="gas_B",
            values=values_B, is_valid_flags=flags_B,
        ))

    return bundles


def split_pool_by_device(
    bundles: list,
) -> tuple:
    """장비별로 SensorBundle 리스트 분할.
    
    Args:
        bundles: generate_gas_normal_pool()의 출력.
    
    Returns:
        (bundles_A, bundles_B) 튜플.
    """
    bundles_A = [b for b in bundles if b.device_id == "gas_A"]
    bundles_B = [b for b in bundles if b.device_id == "gas_B"]
    return bundles_A, bundles_B
