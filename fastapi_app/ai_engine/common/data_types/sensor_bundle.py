"""
SensorBundle — 한 시점·한 장비의 여러 센서 값을 묶은 자료 구조.

가스 장비는 9개 센서(CO, H2S, CO2, O2, NO2, SO2, O3, NH3, VOC)의 묶음을,
전력 장비는 3개 센서(voltage, current, power)의 묶음을 표현한다.
device_id로 가스/전력을 구분.

설계 원칙:
    - 단일 클래스로 가스·전력 모두 처리
    - DataPoint와의 양방향 변환 제공
    - IF 학습 입력용 벡터 변환 제공 (to_vector)
    - 결측 비율 계산 제공 (valid_ratio)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from .data_point import DataPoint


@dataclass
class SensorBundle:
    """한 시점·한 장비의 여러 센서 묶음.
    
    Attributes:
        timestamp: 묶음 시각 (모든 센서가 같은 시점).
        device_id: 장비 식별자 (예: "gas_A", "power_1").
        values: sensor_type → value 매핑.
                결측은 값이 None.
        is_valid_flags: sensor_type → is_valid 매핑.
    
    Examples:
        >>> from datetime import datetime, timezone
        >>> bundle = SensorBundle(
        ...     timestamp=datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc),
        ...     device_id="gas_A",
        ...     values={"co": 5.0, "h2s": 1.0, "co2": 450.0},
        ...     is_valid_flags={"co": True, "h2s": True, "co2": True},
        ... )
        >>> bundle.values["co"]
        5.0
    """

    timestamp: datetime
    device_id: str
    values: dict = field(default_factory=dict)
    is_valid_flags: dict = field(default_factory=dict)

    @classmethod
    def from_data_points(cls, points: list[DataPoint]) -> "SensorBundle":
        """DataPoint 리스트에서 SensorBundle을 생성한다.
        
        모든 DataPoint는 *같은 timestamp와 device_id*를 가져야 한다.
        
        Args:
            points: 같은 시점·장비의 DataPoint 리스트.
        
        Returns:
            생성된 SensorBundle 인스턴스.
        
        Raises:
            ValueError: points가 비어있거나 timestamp/device_id가 일치하지 않을 때.
        
        Examples:
            >>> from datetime import datetime, timezone
            >>> ts = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)
            >>> points = [
            ...     DataPoint(ts, "gas_A", "co", 5.0),
            ...     DataPoint(ts, "gas_A", "h2s", 1.0),
            ... ]
            >>> bundle = SensorBundle.from_data_points(points)
            >>> bundle.values["co"]
            5.0
            >>> bundle.values["h2s"]
            1.0
        """
        if not points:
            raise ValueError("points 리스트가 비어있음")

        first = points[0]
        timestamp = first.timestamp
        device_id = first.device_id

        # 모든 DataPoint의 timestamp/device_id 일치 확인
        for p in points[1:]:
            if p.timestamp != timestamp:
                raise ValueError(
                    f"timestamp 불일치: {p.timestamp} != {timestamp}"
                )
            if p.device_id != device_id:
                raise ValueError(
                    f"device_id 불일치: {p.device_id} != {device_id}"
                )

        values = {p.sensor_type: p.value for p in points}
        is_valid_flags = {p.sensor_type: p.is_valid for p in points}

        return cls(
            timestamp=timestamp,
            device_id=device_id,
            values=values,
            is_valid_flags=is_valid_flags,
        )

    def to_data_points(self) -> list[DataPoint]:
        """SensorBundle을 DataPoint 리스트로 분해한다.
        
        각 센서별로 DataPoint 1개를 생성. 호출자가 *센서별로 개별 처리*해야 할 때 사용.
        
        Returns:
            DataPoint 리스트. 센서 순서는 values dict의 삽입 순서.
        """
        return [
            DataPoint(
                timestamp=self.timestamp,
                device_id=self.device_id,
                sensor_type=sensor_type,
                value=value,
                is_valid=self.is_valid_flags.get(sensor_type, True),
            )
            for sensor_type, value in self.values.items()
        ]

    @classmethod
    def from_dict(cls, data: dict) -> "SensorBundle":
        """외부 dict에서 SensorBundle을 생성한다.
        
        FastAPI 수신 JSON 등 외부 데이터 변환의 진입점.
        
        Args:
            data: dict 형태의 외부 데이터.
                  필수 키: timestamp, device_id, values
                  선택 키: is_valid_flags (기본: 모든 센서 True)
        
        Returns:
            생성된 SensorBundle 인스턴스.
        
        Examples:
            >>> data = {
            ...     "timestamp": "2026-05-19T09:00:00+00:00",
            ...     "device_id": "gas_A",
            ...     "values": {"co": 5.0, "h2s": 1.0},
            ... }
            >>> bundle = SensorBundle.from_dict(data)
            >>> bundle.values["co"]
            5.0
        """
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif not isinstance(ts, datetime):
            raise ValueError(
                f"timestamp는 ISO 8601 문자열 또는 datetime이어야 함. "
                f"받은 타입: {type(ts).__name__}"
            )

        values = {}
        for sensor_type, value in data["values"].items():
            values[str(sensor_type)] = float(value) if value is not None else None

        is_valid_flags = data.get("is_valid_flags", {})
        # 누락된 sensor_type은 True로 기본 설정
        for sensor_type in values.keys():
            is_valid_flags.setdefault(sensor_type, True)

        return cls(
            timestamp=ts,
            device_id=str(data["device_id"]),
            values=values,
            is_valid_flags={k: bool(v) for k, v in is_valid_flags.items()},
        )

    def to_dict(self) -> dict:
        """SensorBundle을 dict로 직렬화한다.
        
        FastAPI 응답, JSON 파일 저장 등에 사용.
        
        Returns:
            dict 표현. JSON 직렬화 가능.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "values": dict(self.values),
            "is_valid_flags": dict(self.is_valid_flags),
        }

    def to_vector(self, sensor_types: list) -> np.ndarray:
        """지정된 sensor_type 순서에 따라 *N차원 벡터*로 변환한다.
        
        IF 학습 입력용. 가스 IF는 9차원, 전력 IF는 3차원으로 변환.
        결측(None)은 np.nan으로 변환되어 호출자가 별도 처리.
        
        Args:
            sensor_types: 벡터 차원 순서를 정의하는 sensor_type 리스트.
                          (예: ["co", "h2s", "co2", "o2", ...])
        
        Returns:
            np.ndarray (1D, 길이=len(sensor_types)).
            결측값은 np.nan.
        
        Examples:
            >>> bundle = SensorBundle(
            ...     timestamp=datetime.now(timezone.utc),
            ...     device_id="gas_A",
            ...     values={"co": 5.0, "h2s": 1.0, "co2": 450.0},
            ... )
            >>> vec = bundle.to_vector(["co", "h2s", "co2"])
            >>> vec.tolist()
            [5.0, 1.0, 450.0]
        """
        result = np.empty(len(sensor_types), dtype=float)
        for i, sensor_type in enumerate(sensor_types):
            value = self.values.get(sensor_type)
            result[i] = np.nan if value is None else float(value)
        return result

    def valid_ratio(self) -> float:
        """묶음 내 *유효 센서의 비율*을 반환한다.
        
        결측·무효 처리(M.6 결측 5% 정책)의 임계 비교에 사용.
        호출자가 본 반환값과 임계(예: 0.8)를 비교하여 UNKNOWN 판정 여부 결정.
        
        Returns:
            유효 비율 (0.0 ~ 1.0). 빈 묶음은 0.0.
        
        Examples:
            >>> bundle = SensorBundle(
            ...     timestamp=datetime.now(timezone.utc),
            ...     device_id="gas_A",
            ...     values={"co": 5.0, "h2s": None, "co2": 450.0},
            ...     is_valid_flags={"co": True, "h2s": False, "co2": True},
            ... )
            >>> bundle.valid_ratio()
            0.6666666666666666
        """
        if not self.values:
            return 0.0
        valid_count = sum(
            1 for sensor_type in self.values.keys()
            if self.is_valid_flags.get(sensor_type, True)
            and self.values[sensor_type] is not None
        )
        return valid_count / len(self.values)
