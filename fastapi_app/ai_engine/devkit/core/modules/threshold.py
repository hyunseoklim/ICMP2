"""
threshold — 단일 측정값을 임계와 비교하여 NORMAL/CAUTION/DANGER로 판정하는 모듈.

본 모듈은 본 과업의 4개 비학습 모듈 중 가장 단순하지만 가장 자주 호출된다.
매 측정 시점(3초마다)마다 모든 채널에 대해 호출되어 즉시 위험 등급을 판정.

설계 원칙:
    - 상태 없음 (stateless): 임계치 표만 보관, 측정값을 기억하지 않음
    - fail-safe 판정 (결정 A): 임계 정보 부재 시 가장 보수적으로 UNKNOWN
    - 3가지 방향 지원: high(가스, 전류, 전력), low(O2), both(전압)
    - 경계값 포함 (>=, <=): 보수적

임계치 표 형식 (dict, yaml에서 그대로 로드 가능):
    {
        "co": {"direction": "high", "caution": 25.0, "danger": 200.0},
        "o2": {"direction": "low", "caution": 18.0, "danger": 16.0},
        "voltage": {
            "direction": "both",
            "caution_high": 240.0, "danger_high": 260.0,
            "caution_low": 200.0, "danger_low": 180.0,
        },
    }

표준 사용 예:
    >>> table = {"co": {"direction": "high", "caution": 25.0, "danger": 200.0}}
    >>> classifier = ThresholdClassifier(table)
    >>> result = classifier.classify(DataPoint(ts, "gas_A", "co", 30.0))
    >>> result.level
    <RiskLevel.CAUTION: '주의'>
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

from devkit.core.data_types import DataPoint
from devkit.core.enums import RiskLevel


# 허용되는 방향 값
_ALLOWED_DIRECTIONS = {"high", "low", "both"}


# ============================================================================
# ThresholdResult — 판정 결과
# ============================================================================

@dataclass
class ThresholdResult:
    """Threshold 모듈의 판정 결과.
    
    Attributes:
        timestamp: 판정 대상 시각 (입력 DataPoint의 timestamp).
        device_id: 장비 식별자.
        sensor_type: 센서 종류.
        value: 측정값 (결측 시 None).
        level: 위험 등급 (NORMAL/CAUTION/DANGER/UNKNOWN).
        threshold_caution: 사용된 주의 임계값 (참고용, None 가능).
                           "both" 방향의 경우 tuple (low, high).
        threshold_danger: 사용된 위험 임계값. "both" 방향은 tuple.
        direction: 적용된 방향 ("high", "low", "both", "" — 임계 없음).
        reason: 판정 사유 한글 문자열.
    """

    timestamp: datetime
    device_id: str
    sensor_type: str
    value: Optional[float]
    level: RiskLevel
    threshold_caution: Optional[Union[float, tuple]]
    threshold_danger: Optional[Union[float, tuple]]
    direction: str
    reason: str

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict.
        
        tuple 임계는 list로 변환되어 JSON 호환.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "value": self.value,
            "level": self.level.value,
            "threshold_caution": (
                list(self.threshold_caution)
                if isinstance(self.threshold_caution, tuple)
                else self.threshold_caution
            ),
            "threshold_danger": (
                list(self.threshold_danger)
                if isinstance(self.threshold_danger, tuple)
                else self.threshold_danger
            ),
            "direction": self.direction,
            "reason": self.reason,
        }


# ============================================================================
# ThresholdClassifier — 본체 클래스
# ============================================================================

class ThresholdClassifier:
    """임계치 표를 받아 측정값을 NORMAL/CAUTION/DANGER로 판정.
    
    임계치 표는 dict 형식. yaml 설정 파일에서 로드한 결과를 그대로 사용 가능.
    
    Examples:
        >>> table = {
        ...     "co": {"direction": "high", "caution": 25.0, "danger": 200.0},
        ...     "o2": {"direction": "low", "caution": 18.0, "danger": 16.0},
        ... }
        >>> classifier = ThresholdClassifier(table)
        >>> classifier.classify_value("co", 30.0)
        <RiskLevel.CAUTION: '주의'>
        >>> classifier.classify_value("o2", 15.0)
        <RiskLevel.DANGER: '위험'>
    """

    def __init__(self, threshold_table: dict):
        """임계치 표(dict)로 초기화.
        
        Args:
            threshold_table: sensor_type → 임계 정보 dict.
                각 항목의 필수 키: "direction"
                  - "high" 시: "caution", "danger"
                  - "low" 시: "caution", "danger"
                  - "both" 시: "caution_high", "danger_high",
                               "caution_low", "danger_low"
        
        Raises:
            ValueError: direction이 허용되지 않은 값일 때.
        """
        # direction 값 검증 (잘못된 표가 들어오면 초기화 시점에 발견)
        for sensor_type, info in threshold_table.items():
            direction = info.get("direction")
            if direction not in _ALLOWED_DIRECTIONS:
                raise ValueError(
                    f"sensor_type {sensor_type!r}의 direction이 잘못됨: "
                    f"{direction!r}. 허용 값: {_ALLOWED_DIRECTIONS}"
                )
        self._table = dict(threshold_table)

    # ------------------------------------------------------------------------
    # 외부 API
    # ------------------------------------------------------------------------

    def has_threshold(self, sensor_type: str) -> bool:
        """해당 sensor_type의 임계가 등록되어 있는지.
        
        Args:
            sensor_type: 센서 종류.
        
        Returns:
            등록되어 있으면 True.
        """
        return sensor_type in self._table

    def classify_value(self, sensor_type: str, value: float) -> RiskLevel:
        """값만으로 위험 등급을 판정.
        
        ARIMA 예측값을 Threshold와 비교할 때 등 *DataPoint 없이*
        값만으로 판정할 때 사용.
        
        Args:
            sensor_type: 센서 종류.
            value: 측정값.
        
        Returns:
            RiskLevel.NORMAL/CAUTION/DANGER, 또는 임계 미정의 시 UNKNOWN.
        
        Examples:
            >>> classifier.classify_value("co", 30.0)
            <RiskLevel.CAUTION: '주의'>
        """
        if sensor_type not in self._table:
            return RiskLevel.UNKNOWN
        info = self._table[sensor_type]
        return self._evaluate(info, value)

    def classify(self, point: DataPoint) -> ThresholdResult:
        """단일 DataPoint를 판정.
        
        결측·무효 측정·임계 미정의 등의 케이스를 모두 fail-safe로 처리.
        
        Args:
            point: 판정할 DataPoint.
        
        Returns:
            ThresholdResult — level과 사유, 임계 정보 포함.
        """
        # 케이스 1: 결측
        if point.value is None:
            return ThresholdResult(
                timestamp=point.timestamp,
                device_id=point.device_id,
                sensor_type=point.sensor_type,
                value=None,
                level=RiskLevel.UNKNOWN,
                threshold_caution=None,
                threshold_danger=None,
                direction="",
                reason="결측",
            )

        # 케이스 2: 유효하지 않은 측정
        if not point.is_valid:
            return ThresholdResult(
                timestamp=point.timestamp,
                device_id=point.device_id,
                sensor_type=point.sensor_type,
                value=point.value,
                level=RiskLevel.UNKNOWN,
                threshold_caution=None,
                threshold_danger=None,
                direction="",
                reason="유효하지 않은 측정",
            )

        # 케이스 3: 임계 정보 미정의
        if point.sensor_type not in self._table:
            return ThresholdResult(
                timestamp=point.timestamp,
                device_id=point.device_id,
                sensor_type=point.sensor_type,
                value=point.value,
                level=RiskLevel.UNKNOWN,
                threshold_caution=None,
                threshold_danger=None,
                direction="",
                reason="임계치 미정의",
            )

        # 케이스 4: 정상 판정
        info = self._table[point.sensor_type]
        level = self._evaluate(info, point.value)
        caution, danger = self._extract_thresholds(info)
        reason = self._build_reason(info["direction"], point.value, info, level)

        return ThresholdResult(
            timestamp=point.timestamp,
            device_id=point.device_id,
            sensor_type=point.sensor_type,
            value=point.value,
            level=level,
            threshold_caution=caution,
            threshold_danger=danger,
            direction=info["direction"],
            reason=reason,
        )

    # ------------------------------------------------------------------------
    # 내부 평가 로직
    # ------------------------------------------------------------------------

    def _evaluate(self, info: dict, value: float) -> RiskLevel:
        """방향에 따라 값을 평가하여 RiskLevel 반환.
        
        임계 정보 일부 누락 시 보수적으로 UNKNOWN.
        """
        direction = info["direction"]

        if direction == "high":
            caution = info.get("caution")
            danger = info.get("danger")
            if caution is None or danger is None:
                return RiskLevel.UNKNOWN
            # 경계값 포함 (>=)
            if value >= danger:
                return RiskLevel.DANGER
            if value >= caution:
                return RiskLevel.CAUTION
            return RiskLevel.NORMAL

        if direction == "low":
            caution = info.get("caution")
            danger = info.get("danger")
            if caution is None or danger is None:
                return RiskLevel.UNKNOWN
            # 경계값 포함 (<=)
            if value <= danger:
                return RiskLevel.DANGER
            if value <= caution:
                return RiskLevel.CAUTION
            return RiskLevel.NORMAL

        # direction == "both"
        c_high = info.get("caution_high")
        d_high = info.get("danger_high")
        c_low = info.get("caution_low")
        d_low = info.get("danger_low")
        if None in (c_high, d_high, c_low, d_low):
            return RiskLevel.UNKNOWN
        if value >= d_high or value <= d_low:
            return RiskLevel.DANGER
        if value >= c_high or value <= c_low:
            return RiskLevel.CAUTION
        return RiskLevel.NORMAL

    def _extract_thresholds(
        self, info: dict
    ) -> tuple:
        """임계 정보 dict에서 caution·danger 임계값을 추출하여 (caution, danger) 반환.
        
        - high/low: (caution, danger) — 각각 float
        - both: ((caution_low, caution_high), (danger_low, danger_high)) — 각각 tuple
        """
        direction = info["direction"]
        if direction in ("high", "low"):
            return info.get("caution"), info.get("danger")
        # both
        caution = (info.get("caution_low"), info.get("caution_high"))
        danger = (info.get("danger_low"), info.get("danger_high"))
        return caution, danger

    def _build_reason(
        self,
        direction: str,
        value: float,
        info: dict,
        level: RiskLevel,
    ) -> str:
        """판정 사유 한글 문자열 생성."""
        if level == RiskLevel.NORMAL:
            return "정상 범위"
        if level == RiskLevel.UNKNOWN:
            return "임계 정보 불충분"

        # CAUTION 또는 DANGER
        suffix = "주의 임계 초과" if level == RiskLevel.CAUTION else "위험 임계 초과"

        if direction == "high":
            return f"고측 {suffix}"
        if direction == "low":
            return f"저측 {suffix}"

        # both
        if level == RiskLevel.DANGER:
            if value >= info["danger_high"]:
                return f"고측 위험 임계 초과"
            return f"저측 위험 임계 초과"
        # CAUTION
        if value >= info["caution_high"]:
            return f"고측 주의 임계 초과"
        return f"저측 주의 임계 초과"
