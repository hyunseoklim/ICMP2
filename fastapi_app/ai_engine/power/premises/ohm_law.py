"""
power/premises/ohm_law — 옴의 법칙 P = V × I 검증 함수.

본 모듈은 전압·전류·전력의 *물리적 일관성*을 확인하는 유틸리티 제공.

활용처:
    - generator/power_generator/: 합성 데이터 생성 시 P = V·I 보장
    - 운영 시 *센서 오류 탐지* (V·I는 정상이지만 P가 어긋남 등)
    - tests/power/: 학습 풀의 옴의 법칙 만족 여부 검증
"""

from __future__ import annotations


def expected_power(voltage: float, current: float) -> float:
    """V·I로부터 기대 전력 P를 계산.
    
    Args:
        voltage: 전압 (V).
        current: 전류 (A).
    
    Returns:
        기대 전력 P = V × I (W).
    
    Examples:
        >>> expected_power(220.0, 11.0)
        2420.0
        >>> expected_power(220.0, 1.0)
        220.0
    """
    return float(voltage) * float(current)


def verify_ohm_law(
    voltage: float,
    current: float,
    power: float,
    tolerance: float = 0.1,
) -> dict:
    """측정된 V·I·P가 옴의 법칙 P = V·I를 만족하는지 검증.
    
    Args:
        voltage: 측정 전압 (V).
        current: 측정 전류 (A).
        power: 측정 전력 (W).
        tolerance: 허용 상대 오차 (기본 0.1 = 10%).
                   |P_actual - P_expected| / P_expected ≤ tolerance 면 일관성 인정.
    
    Returns:
        dict:
            - expected_power: V·I로 계산한 기대 전력
            - actual_power: 입력된 측정 전력
            - residual: actual - expected
            - residual_ratio: |residual| / expected_power (expected_power=0 시 inf)
            - is_consistent: residual_ratio ≤ tolerance 면 True
    
    Examples:
        >>> r = verify_ohm_law(220.0, 11.0, 2420.0)
        >>> r["is_consistent"]
        True
        >>> r["residual"]
        0.0
        
        >>> r = verify_ohm_law(220.0, 11.0, 3000.0)
        >>> r["is_consistent"]  # 25% 오차 → 일관성 X
        False
    """
    expected = expected_power(voltage, current)
    actual = float(power)
    residual = actual - expected

    if expected == 0.0:
        # 기대 전력 0인데 측정 전력 있으면 불일치
        ratio = float("inf") if residual != 0.0 else 0.0
    else:
        ratio = abs(residual) / abs(expected)

    return {
        "expected_power": expected,
        "actual_power": actual,
        "residual": residual,
        "residual_ratio": ratio,
        "is_consistent": ratio <= tolerance,
    }
