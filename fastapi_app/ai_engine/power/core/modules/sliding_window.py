"""
sliding_window — 채널별 최근 N개 측정값을 관리하는 슬라이딩 윈도우 모듈.

본 모듈은 본 과업의 4개 비학습 모듈 중 가장 기반이 되는 부품으로,
다른 시계열 모듈(Z-score, Change Point, ARIMA)의 입력을 공급한다.

설계 원칙:
    - 채널 식별: (device_id, sensor_type) 튜플
    - 자료 구조: collections.deque(maxlen=N) — 자동으로 오래된 값 제거
    - 결측 보관: None·is_valid=False도 그대로 deque에 유지
    - 호출자 책임: timestamp 순서 검증, 유효 비율 임계 판단

윈도우 크기 (결정 E-1):
    - W30 = 30시점 = 90초 → Z-score 모듈용
    - W40 = 40시점 = 120초 → Change Point 흐름 탐지용
    - W60 = 60시점 = 180초 → ARIMA, Change Point 예측 검증용

표준 사용 예:
    >>> window = SlidingWindow(window_size=30)
    >>> for point in incoming_stream:
    ...     window.push(point)
    >>> if window.is_full("gas_A", "co"):
    ...     values = window.get_values("gas_A", "co")
    ...     # numpy 연산 (np.nanmean 등) 가능
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from power.core.data_types import DataPoint


# 채널 키 타입 별칭
ChannelKey = tuple[str, str]  # (device_id, sensor_type)


# ============================================================================
# SlidingWindowSnapshot — 윈도우 상태 스냅샷
# ============================================================================

@dataclass
class SlidingWindowSnapshot:
    """특정 채널의 윈도우 스냅샷.
    
    호출자가 윈도우 상태를 한 번에 받고 싶을 때 사용.
    
    Attributes:
        device_id: 장비 식별자.
        sensor_type: 센서 종류.
        points: 현재 보관 중인 DataPoint 리스트 (오래된 순).
        is_full: 윈도우가 가득 찼는지 (length == window_size).
        valid_ratio: 윈도우 내 유효 값 비율 (0.0 ~ 1.0).
        window_size: 윈도우 크기 (N).
    """

    device_id: str
    sensor_type: str
    points: list
    is_full: bool
    valid_ratio: float
    window_size: int

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict 반환."""
        return {
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "points": [p.to_dict() for p in self.points],
            "is_full": self.is_full,
            "valid_ratio": self.valid_ratio,
            "window_size": self.window_size,
        }

    def values_array(self) -> np.ndarray:
        """윈도우 내 값만 추출한 1D numpy 배열.
        
        결측(None)은 np.nan으로 변환됨. numpy의 nan-aware 함수
        (np.nanmean, np.nanstd 등)와 직접 호환.
        
        Returns:
            np.ndarray (1D, dtype=float, 길이=len(points)).
        """
        result = np.empty(len(self.points), dtype=float)
        for i, p in enumerate(self.points):
            result[i] = np.nan if p.value is None else float(p.value)
        return result

    def is_usable(self, min_valid_ratio: float = 0.8) -> bool:
        """판정 가능한 상태인지 확인.
        
        가득 찬 윈도우 + 유효 비율 충족 시에만 True.
        
        Args:
            min_valid_ratio: 최소 유효 비율 (기본 0.8, M.6 결측 5% 정책).
        
        Returns:
            판정 가능하면 True.
        """
        return self.is_full and self.valid_ratio >= min_valid_ratio


# ============================================================================
# SlidingWindow — 슬라이딩 윈도우 본체
# ============================================================================

class SlidingWindow:
    """채널별 최근 N개 DataPoint를 deque로 관리한다.
    
    하나의 SlidingWindow 인스턴스는 *여러 채널*의 윈도우를 동시에 관리.
    채널은 (device_id, sensor_type) 튜플로 식별되며, 첫 push 시 자동 생성.
    
    Attributes:
        window_size: 윈도우 크기 (시점 수).
    
    Examples:
        >>> from datetime import datetime, timezone
        >>> from power.core.data_types import DataPoint
        >>> 
        >>> window = SlidingWindow(window_size=3)
        >>> ts = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
        >>> window.push(DataPoint(ts, "gas_A", "co", 5.0))
        >>> window.push(DataPoint(ts, "gas_A", "co", 6.0))
        >>> window.push(DataPoint(ts, "gas_A", "co", 7.0))
        >>> window.is_full("gas_A", "co")
        True
        >>> values = window.get_values("gas_A", "co")
        >>> values.tolist()
        [5.0, 6.0, 7.0]
    """

    def __init__(self, window_size: int):
        """윈도우 크기 N으로 초기화.
        
        Args:
            window_size: 보관할 시점 수. 결정 E-1에 따라 30/40/60 중 선택.
        
        Raises:
            ValueError: window_size가 1 미만일 때.
        """
        if window_size < 1:
            raise ValueError(
                f"window_size는 1 이상이어야 함. 받은 값: {window_size}"
            )
        self._window_size = window_size
        self._channels: dict = {}  # (device_id, sensor_type) → deque[DataPoint]

    @property
    def window_size(self) -> int:
        """윈도우 크기 (불변)."""
        return self._window_size

    # ------------------------------------------------------------------------
    # 추가 (push)
    # ------------------------------------------------------------------------

    def push(self, point: DataPoint) -> None:
        """DataPoint 하나를 해당 채널 윈도우에 추가.
        
        채널이 처음 등장하면 자동으로 deque 생성. 윈도우가 가득 찼으면
        가장 오래된 항목이 자동 제거됨 (deque의 maxlen 동작).
        
        timestamp 순서는 검증하지 않음 (호출자 책임).
        결측(value=None, is_valid=False)도 그대로 추가됨.
        
        Args:
            point: 추가할 DataPoint.
        """
        key = (point.device_id, point.sensor_type)
        if key not in self._channels:
            self._channels[key] = deque(maxlen=self._window_size)
        self._channels[key].append(point)

    def push_many(self, points: list) -> None:
        """여러 DataPoint를 순서대로 추가.
        
        Args:
            points: DataPoint 리스트 (순서 보존됨).
        """
        for point in points:
            self.push(point)

    # ------------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------------

    def get(self, device_id: str, sensor_type: str) -> list:
        """채널의 현재 윈도우 내용을 list로 반환.
        
        deque의 스냅샷이므로 반환된 리스트를 변경해도 윈도우는 영향 없음.
        
        Args:
            device_id: 장비 식별자.
            sensor_type: 센서 종류.
        
        Returns:
            DataPoint 리스트 (오래된 순). 채널이 없으면 빈 리스트.
        """
        key = (device_id, sensor_type)
        if key not in self._channels:
            return []
        return list(self._channels[key])

    def get_values(self, device_id: str, sensor_type: str) -> np.ndarray:
        """채널 값만 추출한 1D numpy 배열.
        
        결측(value=None)은 np.nan으로 변환됨. numpy의 nan-aware 함수
        (np.nanmean, np.nanstd 등)와 직접 호환.
        
        Args:
            device_id: 장비 식별자.
            sensor_type: 센서 종류.
        
        Returns:
            np.ndarray (1D, dtype=float). 채널이 없으면 길이 0.
        """
        points = self.get(device_id, sensor_type)
        result = np.empty(len(points), dtype=float)
        for i, p in enumerate(points):
            result[i] = np.nan if p.value is None else float(p.value)
        return result

    def get_snapshot(self, device_id: str, sensor_type: str) -> SlidingWindowSnapshot:
        """채널의 *상세 스냅샷*을 반환.
        
        is_full, valid_ratio, points를 한 번에 묶어서 받기.
        
        Args:
            device_id: 장비 식별자.
            sensor_type: 센서 종류.
        
        Returns:
            SlidingWindowSnapshot 인스턴스. 채널이 없으면
            빈 points 리스트와 valid_ratio=0.0의 스냅샷.
        """
        return SlidingWindowSnapshot(
            device_id=device_id,
            sensor_type=sensor_type,
            points=self.get(device_id, sensor_type),
            is_full=self.is_full(device_id, sensor_type),
            valid_ratio=self.valid_ratio(device_id, sensor_type),
            window_size=self._window_size,
        )

    # ------------------------------------------------------------------------
    # 상태 확인
    # ------------------------------------------------------------------------

    def is_full(self, device_id: str, sensor_type: str) -> bool:
        """윈도우가 가득 찼는지 (length == window_size).
        
        Args:
            device_id: 장비 식별자.
            sensor_type: 센서 종류.
        
        Returns:
            가득 찼으면 True. 채널이 없거나 미충족이면 False.
        """
        key = (device_id, sensor_type)
        if key not in self._channels:
            return False
        return len(self._channels[key]) == self._window_size

    def valid_ratio(self, device_id: str, sensor_type: str) -> float:
        """윈도우 내 *유효 값의 비율* (0.0 ~ 1.0).
        
        유효 정의: value is not None AND is_valid == True.
        
        호출자는 이 값과 임계(M.6: 0.8)를 비교하여
        판정 가능 여부 결정. UNKNOWN 판정 정책에 사용.
        
        Args:
            device_id: 장비 식별자.
            sensor_type: 센서 종류.
        
        Returns:
            유효 비율. 빈 채널은 0.0.
        """
        key = (device_id, sensor_type)
        if key not in self._channels:
            return 0.0
        q = self._channels[key]
        if not q:
            return 0.0
        valid_count = sum(
            1 for p in q
            if p.value is not None and p.is_valid
        )
        return valid_count / len(q)

    def channel_count(self) -> int:
        """현재 보관 중인 채널 수.
        
        Returns:
            (device_id, sensor_type) 쌍의 수.
        """
        return len(self._channels)

    def channels(self) -> list:
        """현재 보관 중인 채널 키 목록.
        
        Returns:
            [(device_id, sensor_type), ...] 리스트.
        """
        return list(self._channels.keys())

    # ------------------------------------------------------------------------
    # 초기화
    # ------------------------------------------------------------------------

    def clear(
        self,
        device_id: Optional[str] = None,
        sensor_type: Optional[str] = None,
    ) -> None:
        """채널 또는 전체 윈도우 초기화.
        
        Args:
            device_id: 장비 식별자. None이면 전체 초기화.
            sensor_type: 센서 종류. device_id와 함께 지정 시 해당 채널만.
        
        Raises:
            ValueError: device_id만 주고 sensor_type 누락(또는 반대) 시.
        
        Examples:
            >>> window.clear()                    # 전체 초기화
            >>> window.clear("gas_A", "co")       # 특정 채널만
        """
        # 둘 다 None → 전체 초기화
        if device_id is None and sensor_type is None:
            self._channels.clear()
            return

        # 둘 중 하나만 None → 오류
        if device_id is None or sensor_type is None:
            raise ValueError(
                "device_id와 sensor_type는 함께 지정해야 함 "
                "(또는 둘 다 None으로 전체 초기화)"
            )

        # 특정 채널만 초기화
        key = (device_id, sensor_type)
        if key in self._channels:
            del self._channels[key]
