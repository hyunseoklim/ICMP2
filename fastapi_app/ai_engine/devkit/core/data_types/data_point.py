"""
DataPoint — 한 시점·한 센서의 단일 측정값을 표현하는 자료 구조.

본 모듈은 본 과업의 모든 영역(common, gas, power, generator, tests)에서
*센서 측정값을 표현하는 기본 단위*로 사용된다.

설계 원칙:
    - 외부 프레임워크 의존 없음 (Django·FastAPI 무관)
    - 외부 dict와의 변환 함수 분리 (from_dict, to_dict)
    - JSON 직렬화 친화성 (FastAPI 응답 호환)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DataPoint:
    """한 시점의 한 센서 값.
    
    Attributes:
        timestamp: 측정 시각 (timezone-aware datetime 권장).
        device_id: 장비 식별자 (예: "gas_A", "gas_B", "power_1").
        sensor_type: 센서 종류 (예: "co", "h2s", "voltage", "current").
        value: 측정값. None은 결측(M.6)을 의미.
        is_valid: 유효 여부. 결측·통신 오류·범위 외 등은 False.
                  value=None과 자동 연동되지 않음 — 호출자가 명시적으로 설정.
    
    Examples:
        >>> from datetime import datetime, timezone
        >>> point = DataPoint(
        ...     timestamp=datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc),
        ...     device_id="gas_A",
        ...     sensor_type="co",
        ...     value=5.0,
        ...     is_valid=True,
        ... )
        >>> point.value
        5.0
        >>> point.is_valid
        True
    """

    timestamp: datetime
    device_id: str
    sensor_type: str
    value: Optional[float] = None
    is_valid: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "DataPoint":
        """외부 dict에서 DataPoint를 생성한다.
        
        FastAPI 수신 JSON, Django ORM 변환 결과, 외부 API 응답 등
        *모든 외부 데이터 소스*에서 DataPoint로 변환하는 진입점.
        
        Args:
            data: dict 형태의 외부 데이터.
                  필수 키: timestamp, device_id, sensor_type
                  선택 키: value (기본 None), is_valid (기본 True)
                  timestamp는 ISO 8601 문자열 또는 datetime 객체 허용.
        
        Returns:
            생성된 DataPoint 인스턴스.
        
        Raises:
            KeyError: 필수 키 누락 시.
            ValueError: timestamp 변환 실패 시.
        
        Examples:
            >>> data = {
            ...     "timestamp": "2026-05-19T09:00:00+00:00",
            ...     "device_id": "gas_A",
            ...     "sensor_type": "co",
            ...     "value": 5.0,
            ... }
            >>> point = DataPoint.from_dict(data)
            >>> point.device_id
            'gas_A'
        """
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif not isinstance(ts, datetime):
            raise ValueError(
                f"timestamp는 ISO 8601 문자열 또는 datetime이어야 함. "
                f"받은 타입: {type(ts).__name__}"
            )

        value = data.get("value")
        if value is not None:
            value = float(value)

        return cls(
            timestamp=ts,
            device_id=str(data["device_id"]),
            sensor_type=str(data["sensor_type"]),
            value=value,
            is_valid=bool(data.get("is_valid", True)),
        )

    def to_dict(self) -> dict:
        """DataPoint를 dict로 직렬화한다.
        
        FastAPI 응답, JSON 파일 저장, 로그 출력 등에 사용.
        datetime은 ISO 8601 문자열로 변환된다.
        
        Returns:
            dict 표현. JSON 직렬화 가능.
        
        Examples:
            >>> from datetime import datetime, timezone
            >>> point = DataPoint(
            ...     timestamp=datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc),
            ...     device_id="gas_A",
            ...     sensor_type="co",
            ...     value=5.0,
            ... )
            >>> d = point.to_dict()
            >>> d["device_id"]
            'gas_A'
            >>> d["timestamp"]
            '2026-05-19T09:00:00+00:00'
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "value": self.value,
            "is_valid": self.is_valid,
        }
