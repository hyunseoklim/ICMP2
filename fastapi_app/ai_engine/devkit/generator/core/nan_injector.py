"""
generator/core/nan_injector — 합성 데이터에 결측 주입 (M.6).

핵심 결정 (Phase 2 M.6):
    - 결측 비율: 정상 5%
    - 분포: 균일 무작위 (시간·채널 차등 없음)

활용처:
    - generator/gas_generator/normal_pool.py: 5% 결측 주입
    - generator/power_generator/normal_pool.py: 5% 결측 주입
    - tests/generator/: 결측 비율 검증
"""

from __future__ import annotations

import numpy as np
from typing import Optional


def inject_nan(
    samples: np.ndarray,
    missing_ratio: float = 0.05,
    seed: Optional[int] = None,
) -> tuple:
    """배열에 균일 무작위 결측 주입.
    
    Args:
        samples: 1D 또는 2D numpy 배열. 양자화 이후 호출 권장.
        missing_ratio: 결측 비율 (0.0 ~ 1.0). 기본 0.05 (M.6).
        seed: 재현성을 위한 난수 시드. None이면 무작위.
    
    Returns:
        (samples_with_nan, nan_mask) 튜플:
            - samples_with_nan: NaN이 주입된 배열 (원본 비파괴, 새 인스턴스)
            - nan_mask: NaN 위치 (True=결측)
    
    Raises:
        ValueError: missing_ratio가 [0, 1] 범위 외.
    
    Examples:
        >>> import numpy as np
        >>> X = np.random.normal(0, 1, (1000, 9))
        >>> X_nan, mask = inject_nan(X, missing_ratio=0.05, seed=42)
        >>> abs(mask.sum() / mask.size - 0.05) < 0.01  # 실제 5%에 근접
        True
    """
    if not 0.0 <= missing_ratio <= 1.0:
        raise ValueError(
            f"missing_ratio는 [0, 1] 범위. 받은 값: {missing_ratio}"
        )

    rng = np.random.default_rng(seed)

    # 결측 마스크 생성 (균일 무작위)
    nan_mask = rng.random(samples.shape) < missing_ratio

    # 원본 비파괴 — 새 배열 생성
    result = samples.astype(float, copy=True)
    result[nan_mask] = np.nan

    return result, nan_mask


def inject_nan_per_channel(
    samples: np.ndarray,
    missing_ratios: list,
    seed: Optional[int] = None,
) -> tuple:
    """채널별 다른 결측 비율 주입 (확장 기능).
    
    Args:
        samples: 2D 배열 (n_samples, n_channels).
        missing_ratios: 각 채널의 결측 비율 리스트.
        seed: 난수 시드.
    
    Returns:
        (samples_with_nan, nan_mask).
    
    Raises:
        ValueError: missing_ratios 길이가 채널 수와 다름.
    """
    if samples.ndim != 2:
        raise ValueError(f"samples는 2D 배열이어야 함. shape: {samples.shape}")

    n_samples, n_channels = samples.shape
    if len(missing_ratios) != n_channels:
        raise ValueError(
            f"missing_ratios 길이 ({len(missing_ratios)})가 "
            f"채널 수 ({n_channels})와 다름"
        )

    rng = np.random.default_rng(seed)
    nan_mask = np.zeros_like(samples, dtype=bool)

    for ch_idx, ratio in enumerate(missing_ratios):
        if not 0.0 <= ratio <= 1.0:
            raise ValueError(f"채널 {ch_idx} ratio가 [0, 1] 범위 외: {ratio}")
        nan_mask[:, ch_idx] = rng.random(n_samples) < ratio

    result = samples.astype(float, copy=True)
    result[nan_mask] = np.nan

    return result, nan_mask
