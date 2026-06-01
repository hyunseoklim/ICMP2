"""
generator/power_generator/scenario — 전력 시나리오 카드 데이터 생성.

지원 시나리오:
    - S-T-V: 전압 강하 (220 → 170V, 위험 저측)
    - S-T-I: 전류 급증 (11 → 35A)
    - S-C-Power: 부하 변화 (WORKING → IDLE 전환)
    - S-P-I: 전류 점진 증가 (ARIMA 사전 경고)
    - S-Ohm: 옴의 법칙 어긋남 (센서 오류 시뮬레이션)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np

from power.core.data_types import SensorBundle
from power.core.enums import WorkMode
from power.premises import (
    POWER_SENSOR_TYPES, POWER_RESOLUTION,
    get_distribution_params,
)
from devkit.generator.core.time_index import build_time_axis


def generate_scenario(
    scenario_id: str,
    n_samples: int = 200,
    start_time: Optional[datetime] = None,
    seed: int = 42,
    device_id: str = "power_1",
) -> list:
    """전력 시나리오 카드별 시계열 생성.
    
    Args:
        scenario_id: 'S-T-V', 'S-T-I', 'S-C-Power', 'S-P-I', 'S-Ohm' 중 하나.
        n_samples: 시계열 길이.
        start_time: 시작 시각.
        seed: 난수 시드.
        device_id: 장비 식별자.
    
    Returns:
        list[SensorBundle].
    """
    if start_time is None:
        start_time = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)

    rng = np.random.default_rng(seed)
    timestamps = build_time_axis(start_time, n_samples)

    if scenario_id == "S-T-V":
        samples = _scenario_voltage_drop(n_samples, rng)
    elif scenario_id == "S-T-I":
        samples = _scenario_current_spike(n_samples, rng)
    elif scenario_id == "S-C-Power":
        samples = _scenario_mode_change(n_samples, rng)
    elif scenario_id == "S-P-I":
        samples = _scenario_current_rising(n_samples, rng)
    elif scenario_id == "S-Ohm":
        samples = _scenario_ohm_violation(n_samples, rng)
    else:
        raise ValueError(
            f"지원하지 않는 시나리오: {scenario_id!r}. "
            f"지원 목록: ['S-T-V', 'S-T-I', 'S-C-Power', 'S-P-I', 'S-Ohm']"
        )

    # 양자화
    for i, st in enumerate(POWER_SENSOR_TYPES):
        res = POWER_RESOLUTION[st]
        samples[:, i] = np.round(samples[:, i] / res) * res

    # SensorBundle 변환
    bundles = []
    for t_idx, ts in enumerate(timestamps):
        values = {}
        flags = {}
        for i, st in enumerate(POWER_SENSOR_TYPES):
            v = float(samples[t_idx, i])
            values[st] = v
            flags[st] = True
        bundles.append(SensorBundle(
            timestamp=ts, device_id=device_id,
            values=values, is_valid_flags=flags,
        ))

    return bundles


# ============================================================================
# 시나리오별 시계열 생성기
# ============================================================================

def _normal_vi(n: int, rng: np.random.Generator) -> tuple:
    """WORKING 모드 정상 V·I 추출 (옴의 법칙 P=V*I 자동 적용)."""
    params = get_distribution_params(WorkMode.WORKING)
    mean = params["mean"]
    cov = params["cov"]
    v_idx = POWER_SENSOR_TYPES.index("voltage")
    i_idx = POWER_SENSOR_TYPES.index("current")

    vi_mean = np.array([mean[v_idx], mean[i_idx]])
    vi_cov = np.array([
        [cov[v_idx, v_idx], cov[v_idx, i_idx]],
        [cov[i_idx, v_idx], cov[i_idx, i_idx]],
    ])
    vi = rng.multivariate_normal(vi_mean, vi_cov, size=n)
    return vi[:, 0], vi[:, 1]


def _assemble(v: np.ndarray, i: np.ndarray, p: np.ndarray) -> np.ndarray:
    """V, I, P 1D 배열을 (n, 3) 형태로 결합 (POWER_SENSOR_TYPES 순서)."""
    n = len(v)
    samples = np.zeros((n, 3))
    samples[:, POWER_SENSOR_TYPES.index("voltage")] = v
    samples[:, POWER_SENSOR_TYPES.index("current")] = i
    samples[:, POWER_SENSOR_TYPES.index("power")] = p
    return samples


def _scenario_voltage_drop(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-T-V: 전압 220 → 170V 강하 (저측 위험).
    
    구간:
        [0, n//2): V 220 정상
        [n//2, n): V 220 → 170 점진
    """
    v, i = _normal_vi(n, rng)
    mid = n // 2
    # 후반 V 강하
    v[mid:] = np.linspace(220.0, 170.0, n - mid) + rng.normal(0, 5.0, n - mid)
    p = v * i + rng.normal(0, 0.01 * np.abs(v * i), size=n)
    return _assemble(v, i, p)


def _scenario_current_spike(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-T-I: 전류 급증 11 → 35A.
    
    구간:
        [0, n//2): I 11 정상
        [n//2, n): I 35 급증 위험
    """
    v, i = _normal_vi(n, rng)
    mid = n // 2
    i[mid:] = 35.0 + rng.normal(0, 1.0, n - mid)
    p = v * i + rng.normal(0, 0.01 * np.abs(v * i), size=n)
    return _assemble(v, i, p)


def _scenario_mode_change(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-C-Power: WORKING → IDLE 전환 (Change Point).
    
    구간:
        [0, n//2): WORKING (V=220, I=11)
        [n//2, n): IDLE (V=220, I=1)
    """
    n_half = n // 2
    # 전반 WORKING
    v_w, i_w = _normal_vi(n_half, rng)
    # 후반 IDLE
    idle_params = get_distribution_params(WorkMode.IDLE)
    v_idx = POWER_SENSOR_TYPES.index("voltage")
    i_idx = POWER_SENSOR_TYPES.index("current")
    vi_idle_mean = np.array([idle_params["mean"][v_idx], idle_params["mean"][i_idx]])
    vi_idle_cov = np.array([
        [idle_params["cov"][v_idx, v_idx], idle_params["cov"][v_idx, i_idx]],
        [idle_params["cov"][i_idx, v_idx], idle_params["cov"][i_idx, i_idx]],
    ])
    vi_idle = rng.multivariate_normal(vi_idle_mean, vi_idle_cov, size=n - n_half)

    v = np.concatenate([v_w, vi_idle[:, 0]])
    i = np.concatenate([i_w, vi_idle[:, 1]])
    p = v * i + rng.normal(0, 0.01 * np.abs(v * i), size=n)
    return _assemble(v, i, p)


def _scenario_current_rising(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-P-I: 전류 점진 증가 (ARIMA 사전 경고).
    
    18 → 25A 점진 (caution 20 도달 후 위험 미만)
    """
    v, _ = _normal_vi(n, rng)
    i = np.linspace(18.0, 25.0, n) + rng.normal(0, 0.5, n)
    p = v * i + rng.normal(0, 0.01 * np.abs(v * i), size=n)
    return _assemble(v, i, p)


def _scenario_ohm_violation(n: int, rng: np.random.Generator) -> np.ndarray:
    """S-Ohm: 옴의 법칙 어긋남 (센서 오류).
    
    V·I는 정상, P만 비정상 (예: P 측정 센서 고장).
    """
    v, i = _normal_vi(n, rng)
    # P를 V*I의 70% 정도로 잘못 측정 (P 센서 캘리브레이션 오류 시뮬레이션)
    p = v * i * 0.7 + rng.normal(0, 50.0, size=n)
    return _assemble(v, i, p)
