"""
generator/core/quantizer — 측정 분해능에 따른 양자화 (M.7).

본 모듈은 합성 데이터 생성 시 *센서별 분해능*에 맞춰 값을 양자화한다.

핵심 결정 (Phase 2 M.7):
    - 가스: GAS_RESOLUTION (예: CO 1.0, H2S 0.1, O3 0.001)
    - 전력: POWER_RESOLUTION (V·I 0.1, P 1.0)

활용처:
    - generator/gas_generator/normal_pool.py: 분포 추출 후 양자화
    - generator/power_generator/normal_pool.py: 옴의 법칙 적용 후 양자화
    - tests/generator/: 양자화 일관성 검증
"""

from __future__ import annotations

import numpy as np

from common.data_types import SensorBundle


def quantize_value(value: float, resolution: float) -> float:
    """단일 값을 분해능에 맞춰 양자화 (반올림).
    
    Args:
        value: 원본 값.
        resolution: 분해능 (예: 0.1, 1.0, 0.001).
    
    Returns:
        양자화된 값.
    
    Raises:
        ValueError: resolution이 0 이하.
    
    Examples:
        >>> quantize_value(5.73, 1.0)
        6.0
        >>> quantize_value(0.0157, 0.001)
        0.016
        >>> quantize_value(220.43, 0.1)
        220.4
    """
    if resolution <= 0:
        raise ValueError(f"resolution은 양수여야 함. 받은 값: {resolution}")
    return float(round(value / resolution) * resolution)


def quantize_array(
    values: np.ndarray,
    resolution: float,
) -> np.ndarray:
    """numpy 배열의 모든 값을 양자화. NaN은 그대로 유지.
    
    Args:
        values: 1D 또는 2D 배열.
        resolution: 분해능.
    
    Returns:
        양자화된 배열 (같은 모양).
    """
    if resolution <= 0:
        raise ValueError(f"resolution은 양수여야 함. 받은 값: {resolution}")
    # NaN 위치 보존
    nan_mask = np.isnan(values)
    result = np.round(values / resolution) * resolution
    result = np.where(nan_mask, np.nan, result)
    return result


def quantize_bundle(
    bundle: SensorBundle,
    resolution_map: dict,
) -> SensorBundle:
    """SensorBundle의 모든 값을 채널별 분해능으로 양자화.
    
    Args:
        bundle: 원본 SensorBundle.
        resolution_map: {sensor_type: resolution, ...}.
                        bundle.values의 키와 매칭. 없는 키는 그대로 둠.
    
    Returns:
        양자화된 SensorBundle (새 인스턴스).
    
    Examples:
        >>> from gas.premises import GAS_RESOLUTION
        >>> bundle = SensorBundle(...)
        >>> quantized = quantize_bundle(bundle, GAS_RESOLUTION)
    """
    new_values = {}
    for st, v in bundle.values.items():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            new_values[st] = v
        elif st in resolution_map:
            new_values[st] = quantize_value(v, resolution_map[st])
        else:
            new_values[st] = v

    return SensorBundle(
        timestamp=bundle.timestamp,
        device_id=bundle.device_id,
        values=new_values,
        is_valid_flags=dict(bundle.is_valid_flags),
    )
