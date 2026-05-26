"""
generator/gas_generator/scenario — 가스 시나리오 카드 데이터 생성.

본 모듈은 보고서 5.2.3의 시나리오 카드별 *합성 시계열*을 생성한다.

지원 시나리오:
    - S-T1: CO 점진 상승 (정상→주의→위험)
    - S-T2: O2 점진 하락 (역방향)
    - S-T3: H2S 급격 상승
    - S-C1: CO 흐름 변화 (Change Point)
    - S-P1: VOC 점진 증가 (ARIMA 사전 경고)

활용처:
    - Phase 4 통합 검증 시나리오 입력
    - 학습된 모델의 *판정 정확도* 평가
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np

from common.data_types import SensorBundle
from gas.premises import (
    GAS_SENSOR_TYPES, GAS_RESOLUTION, GAS_MEANS_NORMAL,
    VentilationLevel, get_distribution_params,
)
from generator.core.time_index import build_time_axis


def generate_scenario(
    scenario_id: str,
    n_samples: int = 200,
    start_time: Optional[datetime] = None,
    seed: int = 42,
    device_id: str = "gas_A",
) -> list:
    """시나리오 카드별 가스 시계열 생성.
    
    Args:
        scenario_id: 'S-T1', 'S-T2', 'S-T3', 'S-C1', 'S-P1' 중 하나.
        n_samples: 시계열 길이.
        start_time: 시작 시각.
        seed: 난수 시드.
        device_id: 장비 식별자.
    
    Returns:
        list[SensorBundle].
    
    Raises:
        ValueError: 지원하지 않는 scenario_id.
    
    Examples:
        >>> bundles = generate_scenario('S-T1', n_samples=200)
        >>> len(bundles)
        200
    """
    if start_time is None:
        start_time = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)

    rng = np.random.default_rng(seed)
    timestamps = build_time_axis(start_time, n_samples)

    if scenario_id == "S-T1":
        samples = _scenario_T1_co_rising(n_samples, rng)
    elif scenario_id == "S-T2":
        samples = _scenario_T2_o2_falling(n_samples, rng)
    elif scenario_id == "S-T3":
        samples = _scenario_T3_h2s_spike(n_samples, rng)
    elif scenario_id == "S-C1":
        samples = _scenario_C1_co_change(n_samples, rng)
    elif scenario_id == "S-P1":
        samples = _scenario_P1_voc_rising(n_samples, rng)
    else:
        raise ValueError(
            f"지원하지 않는 시나리오: {scenario_id!r}. "
            f"지원 목록: ['S-T1', 'S-T2', 'S-T3', 'S-C1', 'S-P1']"
        )

    # 분해능 양자화
    for i, st in enumerate(GAS_SENSOR_TYPES):
        res = GAS_RESOLUTION[st]
        samples[:, i] = np.round(samples[:, i] / res) * res

    # SensorBundle 변환
    bundles = []
    for t_idx, ts in enumerate(timestamps):
        values = {}
        flags = {}
        for i, st in enumerate(GAS_SENSOR_TYPES):
            v = float(samples[t_idx, i])
            values[st] = v
            flags[st] = True
        bundles.append(SensorBundle(
            timestamp=ts, device_id=device_id,
            values=values, is_valid_flags=flags,
        ))

    return bundles


# ============================================================================
# 시나리오별 시계열 생성기 (내부)
# ============================================================================

def _baseline(n: int, rng: np.random.Generator) -> np.ndarray:
    """NORMAL 환기 분포 기준 정상 시계열 (n, 9) 생성."""
    params = get_distribution_params(VentilationLevel.NORMAL)
    return rng.multivariate_normal(params["mean"], params["cov"], size=n)


def _scenario_T1_co_rising(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-T1: CO 점진 상승.
    
    구간 (n=200 기준):
        [0, 60): CO 정상 (5 ppm)
        [60, 120): CO 주의 (5 → 100 ppm 점진)
        [120, 200): CO 위험 (100 → 250 ppm 점진)
    """
    samples = _baseline(n, rng)
    co_idx = GAS_SENSOR_TYPES.index("co")

    p1, p2 = int(n * 0.3), int(n * 0.6)
    # [0, p1): 정상 (기본값 유지)
    # [p1, p2): 5 → 100 ppm
    samples[p1:p2, co_idx] = np.linspace(5.0, 100.0, p2 - p1) + rng.normal(0, 1.5, p2 - p1)
    # [p2, n): 100 → 250 ppm
    samples[p2:, co_idx] = np.linspace(100.0, 250.0, n - p2) + rng.normal(0, 1.5, n - p2)
    return samples


def _scenario_T2_o2_falling(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-T2: O2 점진 하락 (역방향).
    
    구간:
        [0, 60): O2 정상 (20.9 %)
        [60, 120): O2 주의 (20.9 → 17 %)
        [120, 200): O2 위험 (17 → 14 %)
    """
    samples = _baseline(n, rng)
    o2_idx = GAS_SENSOR_TYPES.index("o2")

    p1, p2 = int(n * 0.3), int(n * 0.6)
    samples[p1:p2, o2_idx] = np.linspace(20.9, 17.0, p2 - p1) + rng.normal(0, 0.3, p2 - p1)
    samples[p2:, o2_idx] = np.linspace(17.0, 14.0, n - p2) + rng.normal(0, 0.3, n - p2)
    return samples


def _scenario_T3_h2s_spike(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-T3: H2S 급격 상승.
    
    구간:
        [0, 100): H2S 정상 (1 ppm)
        [100, 110): 급격 상승 (1 → 20 ppm, 위험)
        [110, n): 위험 수준 유지
    """
    samples = _baseline(n, rng)
    h2s_idx = GAS_SENSOR_TYPES.index("h2s")

    p1 = int(n * 0.5)
    p2 = p1 + 10
    samples[p1:p2, h2s_idx] = np.linspace(1.0, 20.0, p2 - p1) + rng.normal(0, 0.5, p2 - p1)
    samples[p2:, h2s_idx] = 20.0 + rng.normal(0, 0.5, n - p2)
    return samples


def _scenario_C1_co_change(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-C1: CO 흐름 변화 (Change Point 탐지용).
    
    구간:
        [0, n//2): CO 평균 5 (정상)
        [n//2, n): CO 평균 15 (주의 진입 직전, 흐름 변화)
    """
    samples = _baseline(n, rng)
    co_idx = GAS_SENSOR_TYPES.index("co")

    mid = n // 2
    samples[:mid, co_idx] = 5.0 + rng.normal(0, 1.5, mid)
    samples[mid:, co_idx] = 15.0 + rng.normal(0, 1.5, n - mid)
    return samples


def _scenario_P1_voc_rising(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-P1: VOC 점진 증가 (ARIMA 사전 경고 검증용).
    
    구간 전체: VOC 50 → 250 ppm 점진 (주의 임계 200 도달)
    """
    samples = _baseline(n, rng)
    voc_idx = GAS_SENSOR_TYPES.index("voc")

    samples[:, voc_idx] = np.linspace(50.0, 250.0, n) + rng.normal(0, 15.0, n)
    return samples
