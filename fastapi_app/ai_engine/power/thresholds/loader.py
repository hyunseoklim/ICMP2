"""
power/thresholds/loader — 전력 3채널 임계치 yaml 로드 및 검증.

본 모듈은 config/power/threshold.yaml을 로드하여 ThresholdClassifier 호환
dict로 변환. gas/thresholds/loader.py와 *대칭 구조*.

설계 원칙:
    - common/utils.load_config 재사용
    - 검증 실패 시 명확한 ValueError
    - 기본 경로 자동 추정

표준 사용 예:
    >>> from power.thresholds import load_power_thresholds
    >>> from power.core.modules import ThresholdClassifier
    >>> 
    >>> table = load_power_thresholds()
    >>> classifier = ThresholdClassifier(table)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from power.core.utils.config_loader import load_config, get_config_dir
from power.premises.power_distribution import POWER_SENSOR_TYPES


_ALLOWED_DIRECTIONS = {"high", "low", "both"}


def _default_path() -> Path:
    return get_config_dir() / "threshold.yaml"


def load_power_thresholds(
    config_path: Optional[Union[str, Path]] = None,
) -> dict:
    """전력 3채널 임계치 yaml을 로드하여 ThresholdClassifier 호환 dict 반환.
    
    Args:
        config_path: yaml 파일 경로. None이면 기본 경로
                     (ai_engine/config/power/threshold.yaml) 사용.
    
    Returns:
        {sensor_type: {direction, caution/danger or 4-tuple, ...}, ...}
    
    Raises:
        FileNotFoundError: yaml 파일 없음.
        ValueError: 검증 실패.
    
    Examples:
        >>> table = load_power_thresholds()
        >>> table["voltage"]["direction"]
        'both'
        >>> table["current"]["caution"]
        20.0
    """
    path = Path(config_path) if config_path else _default_path()
    raw = load_config(path)

    if not isinstance(raw, dict):
        raise ValueError(
            f"전력 임계치 yaml은 최상위가 dict여야 함. 받은 타입: {type(raw).__name__}"
        )

    validate_power_thresholds(raw)
    return raw


def validate_power_thresholds(thresholds: dict) -> None:
    """전력 임계치 dict의 형식을 검증.
    
    검증 항목:
        1. POWER_SENSOR_TYPES 3종 모두 정의
        2. direction이 "high"/"low"/"both" 중 하나
        3. high/low: caution, danger 키 존재 + 임계 순서
        4. both: caution_high < danger_high, caution_low > danger_low
    
    Raises:
        ValueError: 검증 실패.
    """
    if not isinstance(thresholds, dict):
        raise ValueError(
            f"thresholds는 dict여야 함. 받은 타입: {type(thresholds).__name__}"
        )

    missing = [st for st in POWER_SENSOR_TYPES if st not in thresholds]
    if missing:
        raise ValueError(
            f"전력 3종 중 누락된 항목: {missing}. "
            f"필수 3종: {POWER_SENSOR_TYPES}"
        )

    for sensor_type in POWER_SENSOR_TYPES:
        info = thresholds[sensor_type]
        if not isinstance(info, dict):
            raise ValueError(
                f"{sensor_type!r}의 임계 정보는 dict여야 함. "
                f"받은 타입: {type(info).__name__}"
            )

        direction = info.get("direction")
        if direction not in _ALLOWED_DIRECTIONS:
            raise ValueError(
                f"{sensor_type!r}의 direction이 잘못됨: {direction!r}. "
                f"허용 값: {_ALLOWED_DIRECTIONS}"
            )

        if direction in ("high", "low"):
            _validate_high_low(sensor_type, info, direction)
        else:
            _validate_both(sensor_type, info)


def _validate_high_low(sensor_type: str, info: dict, direction: str) -> None:
    for key in ("caution", "danger"):
        if key not in info:
            raise ValueError(f"{sensor_type!r}({direction})에 {key!r} 키 없음")
        if not isinstance(info[key], (int, float)):
            raise ValueError(
                f"{sensor_type!r}의 {key!r}는 수치여야 함. "
                f"받은 타입: {type(info[key]).__name__}"
            )

    caution = float(info["caution"])
    danger = float(info["danger"])

    if direction == "high":
        if not (caution < danger):
            raise ValueError(
                f"{sensor_type!r}(high)의 임계 순서 위반: "
                f"caution({caution}) < danger({danger}) 이어야 함"
            )
    else:
        if not (caution > danger):
            raise ValueError(
                f"{sensor_type!r}(low)의 임계 순서 위반: "
                f"caution({caution}) > danger({danger}) 이어야 함"
            )


def _validate_both(sensor_type: str, info: dict) -> None:
    required = ("caution_high", "danger_high", "caution_low", "danger_low")
    for key in required:
        if key not in info:
            raise ValueError(f"{sensor_type!r}(both)에 {key!r} 키 없음")
        if not isinstance(info[key], (int, float)):
            raise ValueError(
                f"{sensor_type!r}의 {key!r}는 수치여야 함. "
                f"받은 타입: {type(info[key]).__name__}"
            )

    c_high = float(info["caution_high"])
    d_high = float(info["danger_high"])
    c_low = float(info["caution_low"])
    d_low = float(info["danger_low"])

    if not (c_high < d_high):
        raise ValueError(
            f"{sensor_type!r}(both)의 고측 순서 위반: "
            f"caution_high({c_high}) < danger_high({d_high})"
        )
    if not (c_low > d_low):
        raise ValueError(
            f"{sensor_type!r}(both)의 저측 순서 위반: "
            f"caution_low({c_low}) > danger_low({d_low})"
        )
    if not (c_low < c_high):
        raise ValueError(
            f"{sensor_type!r}(both)의 고저 범위 겹침: "
            f"caution_low({c_low}) < caution_high({c_high})"
        )
