"""
change_point — ruptures.Pelt 기반 시계열 변화점 탐지 모듈.

본 모듈은 시계열의 *통계적 구조 변화 시점*을 탐지한다. 두 가지 용도로
같은 클래스를 호출하며, CPPurpose enum으로 구분.

용도별 차이:
    - FLOW_DETECTION (W40): 흐름 변화 탐지 (S-C1·C2·C3 시나리오)
      → min_size=10, 모든 변화점 탐지·보고
    - PREDICT_VALIDATION (W60): ARIMA 예측 교차 검증 (S-P1·P2·P3)
      → min_size=15, 변화점 탐지·보고 (시점 비교는 호출자 책임)

핵심 결정 (Phase 2):
    - 결정 G-1: BIC 페널티 (log(n) * variance)
    - 결정 G-2: min_size = 윈도우 크기의 25%
    - 결정 G-3: ruptures.Pelt, l2 비용 모델
    - 결정 E-1: FLOW W40 / PREDICT W60
    - M.6: 유효 비율 < 0.8 → UNKNOWN
    - 결측 처리: 유효 비율 0.8 이상이면 선형 보간 후 Pelt 입력

표준 사용 예:
    >>> from common.enums import CPPurpose
    >>> from common.modules import SlidingWindow, ChangePointDetector
    >>> 
    >>> sw_flow = SlidingWindow(window_size=40)
    >>> cp_flow = ChangePointDetector(sw_flow, purpose=CPPurpose.FLOW_DETECTION)
    >>> 
    >>> # 호출자가 윈도우에 push 후
    >>> for point in stream:
    ...     sw_flow.push(point)
    >>> 
    >>> # 변화점 탐지
    >>> result = cp_flow.detect("gas_A", "voc")
    >>> if result.has_change_point:
    ...     print(f"변화점: {result.breakpoints}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import ruptures as rpt

from common.enums import CPPurpose, RiskLevel
from .sliding_window import SlidingWindow


# 기본값 (결정 G-1, G-2)
_DEFAULT_MIN_SIZE_RATIO: float = 0.25
_DEFAULT_SIGNIFICANCE_LEVEL: float = 0.05
_DEFAULT_MIN_VALID_RATIO: float = 0.8
_DEFAULT_COST_MODEL: str = "l2"

# 예측 anchor API 기본값 (예측 서브시스템 재설계)
_DEFAULT_MAGNITUDE_GATE: float = 50.0    # C3 보정값 (전이 카탈로그 sweep)
_DEFAULT_CONTAMINATION_BLOCK: int = 8    # 잠정값, C3 미보정


# ============================================================================
# ChangePointResult — 변화점 판정 결과
# ============================================================================

@dataclass
class ChangePointResult:
    """Change Point 모듈의 판정 결과.
    
    Attributes:
        timestamp: 판정 시각 (윈도우 내 가장 최근 timestamp).
        device_id: 장비 식별자.
        sensor_type: 센서 종류.
        purpose: 사용 목적 (FLOW_DETECTION / PREDICT_VALIDATION).
        breakpoints: 윈도우 내 변화점 인덱스 목록.
                     ruptures.Pelt 출력에서 마지막 값(=윈도우 길이)는 제외.
                     예: [12, 25] → 인덱스 12와 25에서 변화점 탐지.
        has_change_point: 변화점이 1개 이상이면 True.
        level: 위험 등급 (CAUTION 변화점 있음 / NORMAL 없음 / UNKNOWN).
        reason: 판정 사유 한글 문자열.
        window_size: 윈도우 크기 (N).
        min_size: 사용된 min_size 값 (N * min_size_ratio).
        valid_count: 윈도우 내 유효 데이터 수.
        penalty: 사용된 BIC 페널티 값 (참고용, UNKNOWN 시 None).
    """

    timestamp: datetime
    device_id: str
    sensor_type: str
    purpose: CPPurpose
    breakpoints: list
    has_change_point: bool
    level: RiskLevel
    reason: str
    window_size: int
    min_size: int
    valid_count: int
    penalty: Optional[float] = None

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "purpose": self.purpose.value,
            "breakpoints": list(self.breakpoints),
            "has_change_point": self.has_change_point,
            "level": self.level.value,
            "reason": self.reason,
            "window_size": self.window_size,
            "min_size": self.min_size,
            "valid_count": self.valid_count,
            "penalty": self.penalty,
        }


# ============================================================================
# CPAnchorResult — 예측 서브시스템용 anchor 산출 결과
# ============================================================================

@dataclass
class CPAnchorResult:
    """예측 서브시스템용 Change Point 산출 — anchor·contamination·trigger.

    ChangePointResult(흐름 변화 탐지용)와 별개로, ARIMA 예측의
    *구간 기준점*을 제공하기 위한 결과.

    Attributes:
        timestamp: 판정 시각 (윈도우 최근 timestamp).
        device_id: 장비 식별자.
        sensor_type: 센서 종류.
        anchor_index: ARIMA 구간 시작 윈도우 인덱스 — 가장 최근의
                      magnitude-gated 변화점. None이면 최근 변화 없음
                      (구간 = 윈도우 전체).
        segment_length: anchor 이후 가용 시점 수 (anchor~윈도우 끝).
        contamination: 윈도우 내에 anchor로 아직 배제되지 않은 계단·스파이크
                       오염이 있는지 (CP 탐지지연 사각지대).
        trigger: 이번 호출에서 변화가 새로 시작됐는지 (contamination 상승 엣지).
        breakpoints: Pelt가 탐지한 전체 변화점 (참고).
        gated_breakpoints: magnitude_gate 이상 점프인 변화점 (참고).
        magnitude_gate: 사용된 점프 크기 임계.
        window_size: 윈도우 크기.
        reason: 판정 사유 한글 문자열.
    """

    timestamp: datetime
    device_id: str
    sensor_type: str
    anchor_index: Optional[int]
    segment_length: int
    contamination: bool
    trigger: bool
    breakpoints: list
    gated_breakpoints: list
    magnitude_gate: float
    window_size: int
    reason: str

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "anchor_index": self.anchor_index,
            "segment_length": self.segment_length,
            "contamination": self.contamination,
            "trigger": self.trigger,
            "breakpoints": list(self.breakpoints),
            "gated_breakpoints": list(self.gated_breakpoints),
            "magnitude_gate": self.magnitude_gate,
            "window_size": self.window_size,
            "reason": self.reason,
        }


# ============================================================================
# ChangePointDetector — 본체 클래스
# ============================================================================

class ChangePointDetector:
    """ruptures.Pelt 기반 시계열 변화점 탐지기.
    
    윈도우 관리는 SlidingWindow에 위임. 본 모듈은 *Pelt 호출과 판정*만 책임.
    
    호출 규약:
        1. 호출자가 SlidingWindow에 DataPoint를 push
        2. 호출자가 본 모듈의 detect(device_id, sensor_type) 호출
        3. 본 모듈이 윈도우 내 시계열을 Pelt에 입력하여 변화점 탐지
    
    Examples:
        >>> from common.enums import CPPurpose
        >>> sw = SlidingWindow(window_size=40)
        >>> detector = ChangePointDetector(sw, purpose=CPPurpose.FLOW_DETECTION)
        >>> # 윈도우 채우기 (생략)
        >>> result = detector.detect("gas_A", "voc")
    """

    def __init__(
        self,
        window: SlidingWindow,
        purpose: CPPurpose,
        min_size_ratio: float = _DEFAULT_MIN_SIZE_RATIO,
        significance_level: float = _DEFAULT_SIGNIFICANCE_LEVEL,
        min_valid_ratio: float = _DEFAULT_MIN_VALID_RATIO,
        cost_model: str = _DEFAULT_COST_MODEL,
        magnitude_gate: float = _DEFAULT_MAGNITUDE_GATE,
        contamination_block: int = _DEFAULT_CONTAMINATION_BLOCK,
    ):
        """SlidingWindow + 사용 목적으로 초기화.
        
        Args:
            window: 윈도우 인스턴스 (FLOW: W40, PREDICT: W60 권장).
            purpose: 사용 목적 (CPPurpose enum).
            min_size_ratio: min_size 비율. 기본 0.25 (결정 G-2).
                            min_size = int(window_size * min_size_ratio).
            significance_level: 유의수준 (참고용, 결정 G-1 기본 0.05).
            min_valid_ratio: 윈도우 내 최소 유효 비율. M.6 기본 0.8.
            cost_model: ruptures 비용 모델. 기본 "l2" (결정 G-3).
        
        Raises:
            ValueError: 파라미터 범위 위반.
        """
        if not isinstance(purpose, CPPurpose):
            raise ValueError(
                f"purpose는 CPPurpose enum이어야 함. 받은 타입: {type(purpose).__name__}"
            )
        if not 0.0 < min_size_ratio <= 0.5:
            raise ValueError(
                f"min_size_ratio는 (0, 0.5] 범위. 받은 값: {min_size_ratio}"
            )
        if not 0.0 < significance_level < 1.0:
            raise ValueError(
                f"significance_level은 (0, 1) 범위. 받은 값: {significance_level}"
            )
        if not 0.0 <= min_valid_ratio <= 1.0:
            raise ValueError(
                f"min_valid_ratio는 [0, 1] 범위. 받은 값: {min_valid_ratio}"
            )

        self._window = window
        self._purpose = purpose
        self._min_size_ratio = min_size_ratio
        self._significance_level = significance_level
        self._min_valid_ratio = min_valid_ratio
        self._cost_model = cost_model
        self._magnitude_gate = float(magnitude_gate)
        self._contamination_block = int(contamination_block)

        # min_size 계산 (결정 G-2)
        self._min_size = max(1, int(window.window_size * min_size_ratio))

        # anchor_status() trigger(상승 엣지) 판정용 채널별 상태
        self._last_contamination: dict = {}

    @property
    def purpose(self) -> CPPurpose:
        """사용 목적 (불변)."""
        return self._purpose

    @property
    def min_size(self) -> int:
        """계산된 min_size 값."""
        return self._min_size

    @property
    def window(self) -> SlidingWindow:
        """관리 중인 SlidingWindow."""
        return self._window

    # ------------------------------------------------------------------------
    # 외부 API
    # ------------------------------------------------------------------------

    def detect(self, device_id: str, sensor_type: str) -> ChangePointResult:
        """현재 윈도우 내 변화점 탐지.
        
        Args:
            device_id: 장비 식별자.
            sensor_type: 센서 종류.
        
        Returns:
            ChangePointResult — 변화점 인덱스 목록과 등급.
        """
        # 윈도우 상태 조회
        points = self._window.get(device_id, sensor_type)
        is_full = self._window.is_full(device_id, sensor_type)
        valid_ratio = self._window.valid_ratio(device_id, sensor_type)
        values = self._window.get_values(device_id, sensor_type)
        valid_count = int(np.sum(~np.isnan(values)))

        # 가장 최근 timestamp (없으면 현재 시각)
        if points:
            last_ts = points[-1].timestamp
        else:
            last_ts = datetime.now(timezone.utc)

        # 케이스 1: 윈도우 미충족
        if not is_full:
            return self._build_unknown(
                last_ts, device_id, sensor_type,
                reason=f"윈도우 미충족 ({len(points)}/{self._window.window_size})",
                valid_count=valid_count,
            )

        # 케이스 2: 유효 비율 부족
        if valid_ratio < self._min_valid_ratio:
            return self._build_unknown(
                last_ts, device_id, sensor_type,
                reason=f"유효 비율 부족 ({valid_ratio:.2f} < {self._min_valid_ratio})",
                valid_count=valid_count,
            )

        # 케이스 3: 결측 보간 후 Pelt 입력
        signal = self._interpolate_nan(values)
        if signal is None:
            return self._build_unknown(
                last_ts, device_id, sensor_type,
                reason="신호 변환 실패 (전부 결측)",
                valid_count=valid_count,
            )

        # 케이스 4: 분산이 0이면 변화점 없음
        variance = float(np.var(signal))
        if variance == 0.0:
            return ChangePointResult(
                timestamp=last_ts,
                device_id=device_id,
                sensor_type=sensor_type,
                purpose=self._purpose,
                breakpoints=[],
                has_change_point=False,
                level=RiskLevel.NORMAL,
                reason="분산 0 (변동 없음)",
                window_size=self._window.window_size,
                min_size=self._min_size,
                valid_count=valid_count,
                penalty=0.0,
            )

        # 케이스 5: Pelt 호출
        try:
            penalty = float(np.log(len(signal)) * variance)
            algo = rpt.Pelt(model=self._cost_model, min_size=self._min_size, jump=1)
            algo.fit(signal)
            raw_breakpoints = algo.predict(pen=penalty)
        except Exception as e:
            return self._build_unknown(
                last_ts, device_id, sensor_type,
                reason=f"Pelt 알고리즘 오류: {e}",
                valid_count=valid_count,
            )

        # ruptures의 마지막 값은 항상 신호 끝점 (= len(signal)) → 제외
        breakpoints = [int(bp) for bp in raw_breakpoints if bp < len(signal)]

        has_cp = len(breakpoints) > 0

        if has_cp:
            level = RiskLevel.CAUTION
            reason = f"변화점 {len(breakpoints)}개 탐지: {breakpoints}"
        else:
            level = RiskLevel.NORMAL
            reason = "변화점 없음"

        return ChangePointResult(
            timestamp=last_ts,
            device_id=device_id,
            sensor_type=sensor_type,
            purpose=self._purpose,
            breakpoints=breakpoints,
            has_change_point=has_cp,
            level=level,
            reason=reason,
            window_size=self._window.window_size,
            min_size=self._min_size,
            valid_count=valid_count,
            penalty=penalty,
        )

    # ------------------------------------------------------------------------
    # 예측 anchor API (예측 서브시스템용 — detect()와 별개·가산)
    # ------------------------------------------------------------------------

    def anchor_status(self, device_id: str, sensor_type: str) -> CPAnchorResult:
        """ARIMA 예측 구간을 위한 anchor·contamination·trigger 산출.

        detect()(흐름 변화 탐지)와 *별개*의 산출이다. 같은 SlidingWindow를
        사용하되, magnitude-gated 변화점에서 *예측 구간의 기준점(anchor)* 을
        뽑고, CP 탐지지연 사각지대를 contamination flag로, 변화 개시를
        trigger로 보고한다.

        Args:
            device_id: 장비 식별자.
            sensor_type: 센서 종류.

        Returns:
            CPAnchorResult — anchor_index·contamination·trigger 등.
        """
        key = (device_id, sensor_type)
        points = self._window.get(device_id, sensor_type)
        values = self._window.get_values(device_id, sensor_type)
        n = len(values)
        last_ts = points[-1].timestamp if points else datetime.now(timezone.utc)
        win_size = self._window.window_size

        anchor_index: Optional[int] = None
        breakpoints: list = []
        gated: list = []

        # 1. Pelt 변화점 + magnitude 게이팅
        signal = self._interpolate_nan(values) if n > 0 else None
        if (signal is not None and n >= 2 * self._min_size
                and float(np.var(signal)) > 0.0):
            try:
                penalty = float(np.log(len(signal)) * np.var(signal))
                algo = rpt.Pelt(model=self._cost_model, min_size=self._min_size, jump=1)
                algo.fit(signal)
                raw = algo.predict(pen=penalty)
                breakpoints = [int(b) for b in raw if 0 < b < len(signal)]
            except Exception:
                breakpoints = []
            bounds = [0] + breakpoints + [len(signal)]
            for i in range(1, len(bounds) - 1):
                b = bounds[i]
                before = signal[bounds[i - 1]:b]
                after = signal[b:bounds[i + 1]]
                if len(before) and len(after):
                    jump = abs(float(np.mean(after)) - float(np.mean(before)))
                    if jump >= self._magnitude_gate:
                        gated.append(b)
            if gated:
                anchor_index = gated[-1]

        # 2. contamination — 최근 블록 평균 이동 (CP 탐지지연 사각지대)
        contamination = False
        blk = self._contamination_block
        if n >= 2 * blk:
            recent = values[n - blk:]
            prev = values[n - 2 * blk:n - blk]
            recent = recent[~np.isnan(recent)]
            prev = prev[~np.isnan(prev)]
            if len(recent) and len(prev):
                contamination = (
                    abs(float(np.mean(recent)) - float(np.mean(prev)))
                    >= self._magnitude_gate
                )

        # 3. trigger — contamination 상승 엣지 (변화 개시)
        trigger = contamination and not self._last_contamination.get(key, False)
        self._last_contamination[key] = contamination

        segment_length = n if anchor_index is None else (n - anchor_index)
        reason = (
            "anchor 없음 (최근 magnitude 변화점 미검출)"
            if anchor_index is None
            else f"anchor=idx{anchor_index}, 구간 {segment_length}시점"
        )
        return CPAnchorResult(
            timestamp=last_ts,
            device_id=device_id,
            sensor_type=sensor_type,
            anchor_index=anchor_index,
            segment_length=segment_length,
            contamination=contamination,
            trigger=trigger,
            breakpoints=breakpoints,
            gated_breakpoints=gated,
            magnitude_gate=self._magnitude_gate,
            window_size=win_size,
            reason=reason,
        )

    # ------------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------------

    def _interpolate_nan(self, values: np.ndarray) -> Optional[np.ndarray]:
        """NaN을 선형 보간한 1D 배열 반환.
        
        ruptures.Pelt는 NaN을 입력으로 받지 못하므로 보간 필요.
        전부 NaN이면 None 반환.
        
        Args:
            values: 1D numpy 배열 (NaN 포함 가능).
        
        Returns:
            보간된 배열 또는 None.
        """
        if np.all(np.isnan(values)):
            return None

        nan_mask = np.isnan(values)
        if not nan_mask.any():
            # NaN 없음 → 그대로 반환 (float 타입 보장)
            return values.astype(float)

        # 선형 보간
        x = np.arange(len(values))
        valid_indices = x[~nan_mask]
        valid_values = values[~nan_mask]
        result = np.interp(x, valid_indices, valid_values)
        return result.astype(float)

    def _build_unknown(
        self,
        timestamp: datetime,
        device_id: str,
        sensor_type: str,
        reason: str,
        valid_count: int = 0,
    ) -> ChangePointResult:
        """UNKNOWN 결과를 생성."""
        return ChangePointResult(
            timestamp=timestamp,
            device_id=device_id,
            sensor_type=sensor_type,
            purpose=self._purpose,
            breakpoints=[],
            has_change_point=False,
            level=RiskLevel.UNKNOWN,
            reason=reason,
            window_size=self._window.window_size,
            min_size=self._min_size,
            valid_count=valid_count,
            penalty=None,
        )
