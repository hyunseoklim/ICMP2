"""
common/integration/prediction_subsystem — 미래 위험 예측 서브시스템 오케스트레이터.

CP(anchor_status) → ARIMA(predict) → 출력 정책(ForecastPolicy.grade)을 엮는
예측 서브시스템의 *진입점*.

역할 분리: CP·ARIMA·출력 정책은 독립 컴포넌트이며, 본 오케스트레이터가
파이프라인으로 연결한다.

의존성 주입: ARIMA 예측기는 *주입*받는다. common 레이어가 gas/power 모듈에
역의존하지 않도록, 호출자가 GasARIMAPredictor() 등을 생성하여 전달한다
(재설계된 ARIMA 예측기는 도메인 비의존이라 가스·전력 공용 가능).

표준 사용 예:
    >>> from gas.modules import GasARIMAPredictor
    >>> from gas.thresholds import load_gas_thresholds
    >>> sub = PredictionSubsystem(load_gas_thresholds(), arima=GasARIMAPredictor())
    >>> for point in stream:
    ...     sub.push(point)
    ...     result = sub.predict_channel(point.device_id, point.sensor_type)
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from devkit.core.enums import CPPurpose, RiskLevel
from devkit.core.modules import SlidingWindow, ChangePointDetector, ThresholdClassifier

from .forecast_policy import ForecastPolicy, ForecastPolicyResult


# 기본값 (재설계 — 잠정값, C3 도메인 보정 대상)
_DEFAULT_CP_WINDOW: int = 60          # CP 윈도우 (W60)
_DEFAULT_HISTORY_SIZE: int = 150      # ARIMA history 버퍼 (≥ max_segment)


class PredictionSubsystem:
    """예측 서브시스템 오케스트레이터 — CP → ARIMA → 출력 정책.

    채널별 측정 스트림(DataPoint)을 받아 2축 등급 예측
    (ForecastPolicyResult)을 산출한다.

    하나의 인스턴스가 여러 채널을 동시에 관리한다(SlidingWindow가
    채널별로 분리 관리). 임계 방향이 다른 도메인은 별도 인스턴스 권장
    (가스용 / 전력용).
    """

    def __init__(
        self,
        threshold_table: dict,
        arima,
        *,
        cp_window: int = _DEFAULT_CP_WINDOW,
        history_size: int = _DEFAULT_HISTORY_SIZE,
        policy: Optional[ForecastPolicy] = None,
    ):
        """오케스트레이터 초기화.

        Args:
            threshold_table: {sensor_type: {direction, caution, danger, ...}}.
                             ThresholdClassifier 호환 dict 그대로 사용 가능.
            arima: ARIMA 예측기 — predict(history, cp_anchor) 인터페이스 제공.
                   주입 필수 (common→gas/power 역의존 회피).
            cp_window: CP 윈도우 크기.
            history_size: ARIMA history 버퍼 크기 (ARIMA max_segment 이상 권장).
            policy: ForecastPolicy 인스턴스. None이면 기본값으로 생성.

        Raises:
            ValueError: arima 미주입 또는 윈도우 크기 위반.
        """
        if arima is None:
            raise ValueError("arima 예측기를 주입해야 함 (predict 인터페이스 제공)")
        if history_size < cp_window:
            raise ValueError(
                f"history_size({history_size})는 cp_window({cp_window}) 이상이어야 함"
            )

        self._table = dict(threshold_table)
        self._classifier = ThresholdClassifier(threshold_table)  # B1 — 현재 탐지
        self._cp_window = SlidingWindow(cp_window)
        self._history = SlidingWindow(history_size)
        self._cp = ChangePointDetector(
            self._cp_window, purpose=CPPurpose.PREDICT_VALIDATION
        )
        self._arima = arima
        self._policy = policy if policy is not None else ForecastPolicy()

    @property
    def policy(self) -> ForecastPolicy:
        """내부 ForecastPolicy (K 카운터 상태 보유)."""
        return self._policy

    def push(self, point) -> None:
        """측정 DataPoint를 CP·history 윈도우에 투입.

        Args:
            point: DataPoint. CP 윈도우와 ARIMA history 버퍼 모두에 추가된다.
        """
        self._cp_window.push(point)
        self._history.push(point)

    def predict_channel(self, device_id: str, sensor_type: str) -> ForecastPolicyResult:
        """채널의 2축 등급 예측 — CP → ARIMA → 출력 정책 파이프라인.

        Args:
            device_id: 장비 식별자.
            sensor_type: 센서 종류.

        Returns:
            ForecastPolicyResult — 2축 최종 등급.
        """
        # 1. CP — anchor / contamination / trigger
        cp_anchor = self._cp.anchor_status(device_id, sensor_type)

        # 2. ARIMA — CP-anchored 구간 재적합 → 원시 예측
        history = self._history.get_values(device_id, sensor_type)
        arima_result = self._arima.predict(history, cp_anchor)

        # 3. B1 — 현재 측정값의 Threshold 등급 (교차모듈 보강 증거)
        present_level = RiskLevel.UNKNOWN
        if len(history) and np.isfinite(history[-1]):
            present_level = self._classifier.classify_value(
                sensor_type, float(history[-1])
            )

        # 4. 출력 정책 — 2축 등급화 + K-확인 + B1 교차확인
        info = self._table.get(sensor_type, {})
        return self._policy.grade(
            arima_result,
            caution=info.get("caution"),
            danger=info.get("danger"),
            direction=info.get("direction", "high"),
            present_level=present_level,
        )
