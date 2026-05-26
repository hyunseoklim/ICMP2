"""
gas/thresholds/loader — 가스 9종 임계치 yaml 로드 및 검증.

본 모듈은 config/gas/threshold.yaml을 로드하여 ThresholdClassifier 호환
dict로 변환한다. 9종 가스 모두 정의되어 있는지, 형식이 올바른지 검증.

설계 원칙:
    - common/utils.load_config 재사용 (yaml 로딩 정책 일관)
    - 검증 실패 시 명확한 ValueError (어떤 가스의 어떤 항목이 잘못됐는지)
    - 기본 경로 자동 추정 (호출자가 경로 신경 안 씀)

표준 사용 예:
    >>> from gas.thresholds import load_gas_thresholds
    >>> from common.modules import ThresholdClassifier
    >>> 
    >>> table = load_gas_thresholds()
    >>> classifier = ThresholdClassifier(table)
    >>> # 이제 ThresholdClassifier는 가스 9종 모두 판정 가능
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from common.utils.config_loader import load_config, get_config_dir
from gas.premises.gas_distribution import GAS_SENSOR_TYPES


# 허용되는 direction 값
_ALLOWED_DIRECTIONS = {"high", "low", "both"}

# 기본 yaml 경로
def _default_path() -> Path:
    """기본 yaml 경로 — 호출 시점에 동적 계산 (ai_engine 루트 기준)."""
    return get_config_dir() / "gas" / "threshold.yaml"


# ============================================================================
# 외부 API
# ============================================================================

def load_gas_thresholds(
    config_path: Optional[Union[str, Path]] = None,
) -> dict:
    """가스 9종 임계치 yaml을 로드하여 ThresholdClassifier 호환 dict 반환.
    
    Args:
        config_path: yaml 파일 경로. None이면 기본 경로
                     (ai_engine/config/gas/threshold.yaml) 사용.
    
    Returns:
        {sensor_type: {direction, caution, danger, unit?, description?}, ...}
        ThresholdClassifier 생성자에 그대로 전달 가능.
    
    Raises:
        FileNotFoundError: yaml 파일이 없을 때.
        ValueError: 검증 실패 시 (9종 누락·잘못된 direction·임계 순서 위반 등).
    
    Examples:
        >>> table = load_gas_thresholds()
        >>> table["co"]["caution"]
        25.0
        >>> table["o2"]["direction"]
        'low'
    """
    path = Path(config_path) if config_path else _default_path()

    raw = load_config(path)

    if not isinstance(raw, dict):
        raise ValueError(
            f"가스 임계치 yaml은 최상위가 dict여야 함. 받은 타입: {type(raw).__name__}"
        )

    validate_gas_thresholds(raw)
    return raw


def validate_gas_thresholds(thresholds: dict) -> None:
    """가스 임계치 dict의 형식을 검증.
    
    검증 항목:
        1. 9종 (GAS_SENSOR_TYPES) 모두 정의되어 있는지
        2. 각 항목에 direction 키가 있고 "high"/"low"/"both" 중 하나인지
        3. high/low: caution, danger 키 존재 + 수치 타입
        4. high: caution < danger
        5. low: caution > danger (낮을수록 위험)
        6. both: caution_high < danger_high, caution_low > danger_low
    
    Args:
        thresholds: 검증할 dict.
    
    Raises:
        ValueError: 검증 실패 시. 메시지에 어떤 가스의 어떤 항목이
                    잘못됐는지 명시.
    """
    if not isinstance(thresholds, dict):
        raise ValueError(
            f"thresholds는 dict여야 함. 받은 타입: {type(thresholds).__name__}"
        )

    # 1. 9종 모두 존재 확인
    missing = [st for st in GAS_SENSOR_TYPES if st not in thresholds]
    if missing:
        raise ValueError(
            f"가스 9종 중 누락된 항목: {missing}. "
            f"필수 9종: {GAS_SENSOR_TYPES}"
        )

    # 2~6. 각 항목 검증
    for sensor_type in GAS_SENSOR_TYPES:
        info = thresholds[sensor_type]
        if not isinstance(info, dict):
            raise ValueError(
                f"{sensor_type!r}의 임계 정보는 dict여야 함. "
                f"받은 타입: {type(info).__name__}"
            )

        # direction 검증
        direction = info.get("direction")
        if direction not in _ALLOWED_DIRECTIONS:
            raise ValueError(
                f"{sensor_type!r}의 direction이 잘못됨: {direction!r}. "
                f"허용 값: {_ALLOWED_DIRECTIONS}"
            )

        # 방향별 임계 검증
        if direction in ("high", "low"):
            _validate_high_low(sensor_type, info, direction)
        else:  # both
            _validate_both(sensor_type, info)


# ============================================================================
# 내부 검증 헬퍼
# ============================================================================

def _validate_high_low(sensor_type: str, info: dict, direction: str) -> None:
    """direction == "high" 또는 "low" 항목 검증."""
    # caution, danger 키 존재
    for key in ("caution", "danger"):
        if key not in info:
            raise ValueError(
                f"{sensor_type!r}({direction})에 {key!r} 키가 없음"
            )
        if not isinstance(info[key], (int, float)):
            raise ValueError(
                f"{sensor_type!r}의 {key!r}는 수치여야 함. "
                f"받은 타입: {type(info[key]).__name__}"
            )

    caution = float(info["caution"])
    danger = float(info["danger"])

    # 임계 순서
    if direction == "high":
        if not (caution < danger):
            raise ValueError(
                f"{sensor_type!r}(high)의 임계 순서 위반: "
                f"caution({caution}) < danger({danger}) 이어야 함"
            )
    else:  # low
        if not (caution > danger):
            raise ValueError(
                f"{sensor_type!r}(low)의 임계 순서 위반: "
                f"caution({caution}) > danger({danger}) 이어야 함 "
                f"(낮을수록 위험)"
            )


def _validate_both(sensor_type: str, info: dict) -> None:
    """direction == "both" 항목 검증."""
    required = ("caution_high", "danger_high", "caution_low", "danger_low")
    for key in required:
        if key not in info:
            raise ValueError(
                f"{sensor_type!r}(both)에 {key!r} 키가 없음"
            )
        if not isinstance(info[key], (int, float)):
            raise ValueError(
                f"{sensor_type!r}의 {key!r}는 수치여야 함. "
                f"받은 타입: {type(info[key]).__name__}"
            )

    c_high = float(info["caution_high"])
    d_high = float(info["danger_high"])
    c_low = float(info["caution_low"])
    d_low = float(info["danger_low"])

    # 고측: caution_high < danger_high
    if not (c_high < d_high):
        raise ValueError(
            f"{sensor_type!r}(both)의 고측 임계 순서 위반: "
            f"caution_high({c_high}) < danger_high({d_high}) 이어야 함"
        )

    # 저측: caution_low > danger_low (낮을수록 위험)
    if not (c_low > d_low):
        raise ValueError(
            f"{sensor_type!r}(both)의 저측 임계 순서 위반: "
            f"caution_low({c_low}) > danger_low({d_low}) 이어야 함"
        )

    # 고측과 저측이 겹치지 않아야 함
    if not (c_low < c_high):
        raise ValueError(
            f"{sensor_type!r}(both)의 고저 임계 범위 겹침: "
            f"caution_low({c_low}) < caution_high({c_high}) 이어야 함"
        )
