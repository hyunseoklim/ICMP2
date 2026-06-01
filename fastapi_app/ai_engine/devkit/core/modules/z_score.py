"""
z_score — Z-score 기반 통계적 이상(SPIKE) 탐지 모듈.

본 모듈은 *윈도우 내 평균·표준편차*만으로 현재 측정값의 이상 여부를 판정.
학습 없이 동작하며, ARIMA 잔차 등 *어떤 시계열에도 같은 알고리즘 재사용* 가능.

설계 원칙:
    - 윈도우 관리는 SlidingWindow에 위임 (책임 분리)
    - 호출자가 push 후 detect 호출 (현재 값이 윈도우에 포함된 상태)
    - 결측은 np.nanmean/np.nanstd로 자동 제외
    - SPIKE 탐지 시 CAUTION 반환 (위험은 Threshold·IF가 판정)

핵심 결정 (Phase 2):
    - 결정 F: 임계 z = 3.0 (3σ 규칙)
    - 결정 E-1: W30 = 30시점 윈도우 (90초)
    - M.6: 윈도우 유효 비율 < 0.8 → UNKNOWN

표준 사용 예:
    >>> from devkit.core.modules import SlidingWindow, ZScoreDetector
    >>> sw = SlidingWindow(window_size=30)
    >>> detector = ZScoreDetector(sw, z_threshold=3.0)
    >>> for point in stream:
    ...     sw.push(point)
    ...     result = detector.detect(point)
    ...     if result.is_spike:
    ...         print(f"SPIKE 탐지: z={result.z_score:.2f}")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from devkit.core.data_types import DataPoint
from devkit.core.enums import RiskLevel
from .sliding_window import SlidingWindow


# 기본값
_DEFAULT_Z_THRESHOLD: float = 3.0
_DEFAULT_MIN_VALID_RATIO: float = 0.8


# ============================================================================
# ZScoreResult — Z-score 판정 결과
# ============================================================================

@dataclass
class ZScoreResult:
    """Z-score 모듈의 판정 결과.
    
    Attributes:
        timestamp: 판정 대상 시각.
        device_id: 장비 식별자.
        sensor_type: 센서 종류.
        value: 측정값 (결측 시 None).
        z_score: 표준화 점수 (결측·미충족 시 None).
        mean: 윈도우 평균 (결측 제외, 계산 불가 시 None).
        std: 윈도우 표준편차 (n-1 분모, 계산 불가 시 None).
        level: 위험 등급 (NORMAL/CAUTION/UNKNOWN).
        is_spike: |z| >= 임계인지 (UNKNOWN 시 False).
        reason: 판정 사유 한글 문자열.
        window_size: 윈도우 크기 (N).
        valid_count: 윈도우 내 유효 데이터 수.
    """

    timestamp: datetime
    device_id: str
    sensor_type: str
    value: Optional[float]
    z_score: Optional[float]
    mean: Optional[float]
    std: Optional[float]
    level: RiskLevel
    is_spike: bool
    reason: str
    window_size: int
    valid_count: int

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict.
        
        NaN은 None으로 변환되어 JSON 호환.
        """
        def _safe(x):
            if x is None:
                return None
            if isinstance(x, float) and np.isnan(x):
                return None
            return x

        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "value": _safe(self.value),
            "z_score": _safe(self.z_score),
            "mean": _safe(self.mean),
            "std": _safe(self.std),
            "level": self.level.value,
            "is_spike": self.is_spike,
            "reason": self.reason,
            "window_size": self.window_size,
            "valid_count": self.valid_count,
        }


# ============================================================================
# ZScoreDetector — 본체 클래스
# ============================================================================

class ZScoreDetector:
    """Z-score 기반 통계적 이상 탐지기.
    
    윈도우 관리는 SlidingWindow에 위임. 본 모듈은 *통계 계산과 판정*만 책임.
    
    호출 규약:
        1. 호출자가 SlidingWindow에 DataPoint를 push
        2. 호출자가 본 모듈의 detect() 호출
        3. 본 모듈이 윈도우 내 (현재 값 포함) 평균·표준편차로 z 계산
    
    Examples:
        >>> from devkit.core.modules import SlidingWindow, ZScoreDetector
        >>> from devkit.core.data_types import DataPoint
        >>> 
        >>> sw = SlidingWindow(window_size=30)
        >>> detector = ZScoreDetector(sw, z_threshold=3.0)
        >>> 
        >>> # 윈도우 채우기 (정상 데이터)
        >>> from datetime import datetime, timezone, timedelta
        >>> ts = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
        >>> for i in range(30):
        ...     p = DataPoint(ts + timedelta(seconds=i*3), "gas_A", "co", 5.0)
        ...     sw.push(p)
        ...     r = detector.detect(p)
        ...     # 모두 같은 값 → std=0 → NORMAL
    """

    def __init__(
        self,
        window: SlidingWindow,
        z_threshold: float = _DEFAULT_Z_THRESHOLD,
        min_valid_ratio: float = _DEFAULT_MIN_VALID_RATIO,
    ):
        """SlidingWindow와 임계값으로 초기화.
        
        Args:
            window: 윈도우 인스턴스. 호출자가 push로 데이터를 채워야 함.
            z_threshold: |z| 임계. 결정 F에 따라 기본 3.0.
            min_valid_ratio: 윈도우 내 최소 유효 비율. M.6에 따라 기본 0.8.
        
        Raises:
            ValueError: z_threshold ≤ 0 또는 min_valid_ratio가 [0, 1] 범위 외.
        """
        if z_threshold <= 0:
            raise ValueError(
                f"z_threshold는 양수여야 함. 받은 값: {z_threshold}"
            )
        if not 0.0 <= min_valid_ratio <= 1.0:
            raise ValueError(
                f"min_valid_ratio는 [0, 1] 범위. 받은 값: {min_valid_ratio}"
            )
        self._window = window
        self._z_threshold = z_threshold
        self._min_valid_ratio = min_valid_ratio

    @property
    def z_threshold(self) -> float:
        """Z-score 임계 (불변)."""
        return self._z_threshold

    @property
    def min_valid_ratio(self) -> float:
        """최소 유효 비율 (불변)."""
        return self._min_valid_ratio

    @property
    def window(self) -> SlidingWindow:
        """관리 중인 SlidingWindow."""
        return self._window

    # ------------------------------------------------------------------------
    # 외부 API
    # ------------------------------------------------------------------------

    def detect(self, point: DataPoint) -> ZScoreResult:
        """현재 DataPoint에 대한 Z-score 판정.
        
        본 호출 전에 호출자가 point를 SlidingWindow에 push 했어야 함.
        (또는 push 전에 호출하여 직전 윈도우 기준으로 판정 가능 — 호출자 정책)
        
        Args:
            point: 판정 대상 DataPoint.
        
        Returns:
            ZScoreResult — z 값, 평균, 표준편차, level, 사유.
        """
        # 케이스 1: 측정값 결측
        if point.value is None or not point.is_valid:
            return self._build_unknown(
                point,
                reason="결측" if point.value is None else "유효하지 않은 측정",
            )

        # 윈도우 상태 조회
        values = self._window.get_values(point.device_id, point.sensor_type)
        is_full = self._window.is_full(point.device_id, point.sensor_type)
        valid_ratio = self._window.valid_ratio(point.device_id, point.sensor_type)
        valid_count = int(np.sum(~np.isnan(values)))

        # 케이스 2: 윈도우 미충족
        if not is_full:
            return self._build_unknown(
                point,
                reason=f"윈도우 미충족 ({len(values)}/{self._window.window_size})",
                valid_count=valid_count,
            )

        # 케이스 3: 유효 비율 부족
        if valid_ratio < self._min_valid_ratio:
            return self._build_unknown(
                point,
                reason=f"유효 비율 부족 ({valid_ratio:.2f} < {self._min_valid_ratio})",
                valid_count=valid_count,
            )

        # 케이스 4: 정상 계산
        mean = float(np.nanmean(values))
        std = float(np.nanstd(values, ddof=1))

        # 케이스 5: std = 0 (모든 값 동일) → 변동 없음 → NORMAL
        if std == 0.0 or np.isnan(std):
            return ZScoreResult(
                timestamp=point.timestamp,
                device_id=point.device_id,
                sensor_type=point.sensor_type,
                value=point.value,
                z_score=0.0,
                mean=mean,
                std=std if not np.isnan(std) else None,
                level=RiskLevel.NORMAL,
                is_spike=False,
                reason="표준편차 0 (변동 없음)",
                window_size=self._window.window_size,
                valid_count=valid_count,
            )

        # z-score 계산
        z = (point.value - mean) / std
        is_spike = abs(z) >= self._z_threshold

        if is_spike:
            level = RiskLevel.CAUTION
            reason = f"SPIKE 탐지 (|z|={abs(z):.2f} >= {self._z_threshold})"
        else:
            level = RiskLevel.NORMAL
            reason = f"정상 범위 (|z|={abs(z):.2f} < {self._z_threshold})"

        return ZScoreResult(
            timestamp=point.timestamp,
            device_id=point.device_id,
            sensor_type=point.sensor_type,
            value=point.value,
            z_score=z,
            mean=mean,
            std=std,
            level=level,
            is_spike=is_spike,
            reason=reason,
            window_size=self._window.window_size,
            valid_count=valid_count,
        )

    def detect_value(
        self,
        device_id: str,
        sensor_type: str,
        current_value: float,
        timestamp: Optional[datetime] = None,
    ) -> ZScoreResult:
        """DataPoint 없이 값만으로 Z-score 판정.
        
        ARIMA 잔차에 Z-score 적용 등 *DataPoint 객체가 없는 경우* 사용.
        호출자가 미리 SlidingWindow에 잔차들을 push해 둔 상태여야 함.
        
        Args:
            device_id: 장비 식별자 (또는 잔차 식별자).
            sensor_type: 센서 종류 (또는 잔차 종류).
            current_value: 현재 값.
            timestamp: 결과의 timestamp. None이면 datetime.now() 사용.
        
        Returns:
            ZScoreResult.
        """
        if timestamp is None:
            timestamp = datetime.now()

        # 임시 DataPoint를 만들어 detect() 위임
        temp_point = DataPoint(
            timestamp=timestamp,
            device_id=device_id,
            sensor_type=sensor_type,
            value=current_value,
            is_valid=True,
        )
        return self.detect(temp_point)

    # ------------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------------

    def _build_unknown(
        self,
        point: DataPoint,
        reason: str,
        valid_count: int = 0,
    ) -> ZScoreResult:
        """UNKNOWN 결과를 생성."""
        return ZScoreResult(
            timestamp=point.timestamp,
            device_id=point.device_id,
            sensor_type=point.sensor_type,
            value=point.value,
            z_score=None,
            mean=None,
            std=None,
            level=RiskLevel.UNKNOWN,
            is_spike=False,
            reason=reason,
            window_size=self._window.window_size,
            valid_count=valid_count,
        )
