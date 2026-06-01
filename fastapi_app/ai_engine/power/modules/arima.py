"""
power/modules/arima — 전력 채널 ARIMA 미래값 예측 모듈.

gas/modules/arima.py와 *구조 동일*. 차이점은 클래스명(PowerARIMAPredictor)뿐.
재설계된 ARIMA 예측기는 도메인 비의존 — 단변량 수치 시계열을 예측한다.

미래 위험 예측 서브시스템 재설계에 따른 *예측기* 컴포넌트.
기존의 "1회 학습·freeze·apply" 구조를 폐기하고 다음으로 전환한다:

    - predict 시점에 CP-anchored 구간을 *재적합*하여 추세를 추정.
    - 점예측(forecast_mean)과 신뢰구간(CI)을 산출 — 불확실성을 정직하게 표현.
    - 등급화(ForecastConfidence)·K-확인은 통합 레이어(출력 정책)가 담당.
      본 모듈은 *순수 예측기* — 임계값을 알지 못한다.

핵심 설계:
    - frozen 모델(fit/save/load/joblib) 폐기 — predict 시점 재적합 (stateless).
    - 차수: ARIMA(0,1,1) + drift (결정 J 개정 — d=1 유지, drift 항 추가).
    - 구간: CP anchor 이후 [min_segment, max_segment].
    - 정규 / degraded 2경로 (B3): contamination 시 robust drift 보조 예측.
    - P3 slope-aware gate: 구간이 min_segment 미만이어도 기울기가 가파르면
      (구간 ≥ degraded_min_segment) degraded 경로로 조기 예측 — 급변(임박
      위험)을 UNKNOWN으로 누락하지 않음. 결과는 출력 정책에서 최대 TENTATIVE.
    - drift 유의성(drift_tstat) 산출 — 출력 정책의 CONFIRMED_WARNING 가드용.

역할 분리: 본 모듈은 CP를 내부 호출하지 않는다. CP 산출물(CPAnchorResult)을
predict()의 인자로 받는다.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from power.core.modules.change_point import CPAnchorResult


# ============================================================================
# 기본 결정값 (재설계 — 잠정값, C3 도메인 보정 대상)
# ============================================================================

_DEFAULT_ORDER: tuple = (0, 1, 1)             # 결정 J 개정: d=1 + drift
_DEFAULT_TREND: str = "t"                     # drift(추세) 항
_DEFAULT_FORECAST_STEPS: int = 60             # 예측 수평 H (결정 K, 잠정)
_DEFAULT_MIN_SEGMENT: int = 45                # 재적합 최소 구간 길이
_DEFAULT_MAX_SEGMENT: int = 90                # 재적합 최대 구간 길이 — C3 보정값
_DEFAULT_SEGMENT_HORIZON_RATIO: float = 1.0   # 구간 ≥ ratio × 수평
_DEFAULT_MIN_VALID_RATIO: float = 0.8         # M.6 — 구간 내 최소 유효 비율
_DEFAULT_DEGRADED_MIN_SEGMENT: int = 20       # P3 — slope-aware degraded 최소 구간
_DEFAULT_SLOPE_GATE: float = 1.0              # P3 — slope-aware 게이트 (스텝당, 잠정)


# ============================================================================
# ARIMAResult — 단일 채널 원시 예측 결과
# ============================================================================

@dataclass
class ARIMAResult:
    """전력 ARIMA 모듈의 단일 채널 *원시 예측* 결과.

    gas/modules/arima.py의 ARIMAResult와 구조 동일. 원시 예측 +
    신뢰성 메타데이터만 담는다. 2축 확신도 등급·K-확인은
    통합 레이어(출력 정책)가 본 결과를 입력받아 산출한다.

    Attributes:
        timestamp: 예측 시점.
        device_id: 장비 식별자.
        sensor_type: 센서 종류.
        path: 예측 경로 — 'normal' / 'degraded' / 'unknown'.
        forecast_mean: H시점 점예측 리스트. 'unknown'이면 빈 리스트.
        ci_lower: H시점 95% 신뢰구간 하한 (raw). 'unknown'이면 빈 리스트.
        ci_upper: H시점 95% 신뢰구간 상한 (raw). 'unknown'이면 빈 리스트.
        forecast_steps: 예측 수평 H.
        drift: 적합된 drift 계수 (normal=추세계수 / degraded=median 차분 / unknown=None).
        drift_tstat: |drift| / SE(drift) — drift 통계 유의성 (normal만; 그 외 None).
        segment_length: 재적합에 사용된 CP-anchored 구간 길이.
        anchor_index: 사용된 CP anchor 인덱스 (참고용).
        order: ARIMA 차수.
        reason: 판정 사유 한글 문자열.
    """

    timestamp: datetime
    device_id: str
    sensor_type: str
    path: str
    forecast_mean: list
    ci_lower: list
    ci_upper: list
    forecast_steps: int
    drift: Optional[float]
    drift_tstat: Optional[float]
    segment_length: int
    anchor_index: Optional[int]
    order: tuple
    reason: str

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict. NaN/Inf는 None으로 안전 변환."""
        def _safe(x):
            if x is None:
                return None
            if isinstance(x, float) and not np.isfinite(x):
                return None
            return x

        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "path": self.path,
            "forecast_mean": [_safe(v) for v in self.forecast_mean],
            "ci_lower": [_safe(v) for v in self.ci_lower],
            "ci_upper": [_safe(v) for v in self.ci_upper],
            "forecast_steps": self.forecast_steps,
            "drift": _safe(self.drift),
            "drift_tstat": _safe(self.drift_tstat),
            "segment_length": self.segment_length,
            "anchor_index": self.anchor_index,
            "order": list(self.order),
            "reason": self.reason,
        }


# ============================================================================
# PowerARIMAPredictor — 본체 클래스
# ============================================================================

class PowerARIMAPredictor:
    """전력 채널 ARIMA 예측기 — predict 시점 CP-anchored 재적합.

    GasARIMAPredictor와 구조 동일. 학습 상태가 없다(stateless).
    설정만 보관하고, predict() 호출마다 주어진 history의 CP-anchored
    구간에 ARIMA를 재적합하여 예측한다.
    """

    def __init__(
        self,
        order: tuple = _DEFAULT_ORDER,
        trend: str = _DEFAULT_TREND,
        forecast_steps: int = _DEFAULT_FORECAST_STEPS,
        min_segment: int = _DEFAULT_MIN_SEGMENT,
        max_segment: int = _DEFAULT_MAX_SEGMENT,
        segment_horizon_ratio: float = _DEFAULT_SEGMENT_HORIZON_RATIO,
        min_valid_ratio: float = _DEFAULT_MIN_VALID_RATIO,
        degraded_min_segment: int = _DEFAULT_DEGRADED_MIN_SEGMENT,
        slope_gate: float = _DEFAULT_SLOPE_GATE,
    ):
        """설정으로 초기화. 학습 없음.

        Args:
            order: ARIMA 차수 (p, d, q). 결정 J 개정 기본 (0, 1, 1).
            trend: 추세 항. 't'면 drift 포함.
            forecast_steps: 예측 수평 H. 결정 K 기본 60.
            min_segment: 재적합 최소 구간 길이. 미달 시 P3 slope-aware gate.
            max_segment: 재적합 최대 구간 길이 (상한).
            segment_horizon_ratio: 구간 ≥ ratio × 수평 이어야 함. 미달 시 UNKNOWN.
            min_valid_ratio: 구간 내 최소 유효(비결측) 비율. 미달 시 UNKNOWN.
            degraded_min_segment: P3 — slope-aware degraded 경로 최소 구간.
                                  미달 시 UNKNOWN (어느 경로도 불가).
            slope_gate: P3 — slope-aware 게이트. 구간이 min_segment 미만일 때
                        robust slope ≥ slope_gate 이면 degraded 조기 예측 허용.

        Raises:
            ValueError: 파라미터 범위 위반.
        """
        if len(order) != 3:
            raise ValueError(f"order는 3-튜플 (p, d, q). 받은 값: {order}")
        if forecast_steps < 1:
            raise ValueError(f"forecast_steps는 1 이상. 받은 값: {forecast_steps}")
        if min_segment < 2:
            raise ValueError(f"min_segment는 2 이상. 받은 값: {min_segment}")
        if max_segment < min_segment:
            raise ValueError(
                f"max_segment({max_segment})는 min_segment({min_segment}) 이상이어야 함"
            )
        if not 0.0 <= min_valid_ratio <= 1.0:
            raise ValueError(f"min_valid_ratio는 [0, 1] 범위. 받은 값: {min_valid_ratio}")
        if degraded_min_segment < 6:
            raise ValueError(
                f"degraded_min_segment는 6 이상 (degraded는 차분 ≥5 필요). "
                f"받은 값: {degraded_min_segment}"
            )
        if degraded_min_segment > min_segment:
            raise ValueError(
                f"degraded_min_segment({degraded_min_segment})는 "
                f"min_segment({min_segment}) 이하여야 함"
            )
        if slope_gate < 0:
            raise ValueError(f"slope_gate는 0 이상. 받은 값: {slope_gate}")

        self._order = tuple(order)
        self._trend = str(trend)
        self._forecast_steps = int(forecast_steps)
        self._min_segment = int(min_segment)
        self._max_segment = int(max_segment)
        self._segment_horizon_ratio = float(segment_horizon_ratio)
        self._min_valid_ratio = float(min_valid_ratio)
        self._degraded_min_segment = int(degraded_min_segment)
        self._slope_gate = float(slope_gate)

    @property
    def order(self) -> tuple:
        """ARIMA 차수 (p, d, q)."""
        return self._order

    @property
    def forecast_steps(self) -> int:
        """예측 수평 H."""
        return self._forecast_steps

    # ------------------------------------------------------------------------
    # 예측
    # ------------------------------------------------------------------------

    def predict(self, history, cp_anchor: CPAnchorResult) -> ARIMAResult:
        """단일 채널 미래값 예측 — CP-anchored 구간 재적합.

        Args:
            history: 최근 측정값 시퀀스 (시간순). 길이 ≥ max_segment 권장.
                     None·결측은 NaN으로 포함 가능 (구간 내 선형 보간).
            cp_anchor: 같은 채널의 CPAnchorResult — anchor·contamination 제공.

        Returns:
            ARIMAResult — 원시 예측(점·CI) + 신뢰성 메타데이터.
        """
        now = datetime.now()
        device_id = cp_anchor.device_id
        sensor_type = cp_anchor.sensor_type
        H = self._forecast_steps

        arr = np.asarray(list(history), dtype=float)
        total = len(arr)

        # 1. 구간 길이 결정
        if cp_anchor.anchor_index is None:
            seg_len = min(total, self._max_segment)
        else:
            seg_len = min(cp_anchor.segment_length, self._max_segment, total)

        # 2. 절대 하한 — degraded 경로조차 불가능한 길이 (P3 게이트의 최소 전제)
        if seg_len < self._degraded_min_segment:
            return self._unknown(
                now, device_id, sensor_type, seg_len, cp_anchor.anchor_index,
                f"구간 부족 ({seg_len} < degraded_min {self._degraded_min_segment})",
            )

        # 3. 구간 추출 + 무결성 검증 (정규·degraded 공통 — 경로 분기보다 선행)
        segment = arr[total - seg_len:]
        if np.isinf(segment).any():
            return self._unknown(
                now, device_id, sensor_type, seg_len, cp_anchor.anchor_index,
                "구간에 Inf 포함",
            )
        nan_mask = np.isnan(segment)
        valid_ratio = 1.0 - (nan_mask.sum() / seg_len)
        if valid_ratio < self._min_valid_ratio:
            return self._unknown(
                now, device_id, sensor_type, seg_len, cp_anchor.anchor_index,
                f"유효 비율 부족 ({valid_ratio:.2f} < {self._min_valid_ratio})",
            )
        if nan_mask.any():  # M.6 — 선형 보간
            idx = np.arange(seg_len)
            segment = np.interp(idx, idx[~nan_mask], segment[~nan_mask])

        # 4. P3 slope-aware gate — 구간이 정규 적합 최소(min_segment)에 못 미칠 때
        #    기울기가 가파르면(임박 위험) degraded 경로로 조기 예측을 허용,
        #    완만하면 데이터 축적 대기(UNKNOWN). degraded 결과는 출력 정책에서
        #    최대 TENTATIVE로 상한된다 — 단구간 저증거를 반영.
        if seg_len < self._min_segment:
            slope = self._robust_slope(segment)
            if slope is None:
                return self._unknown(
                    now, device_id, sensor_type, seg_len, cp_anchor.anchor_index,
                    "단구간 — robust slope 추정 실패",
                )
            if slope < self._slope_gate:
                return self._unknown(
                    now, device_id, sensor_type, seg_len, cp_anchor.anchor_index,
                    f"단구간 — 기울기 완만 (slope {slope:.3f} < gate "
                    f"{self._slope_gate}), 데이터 축적 대기",
                )
            return self._degraded_forecast(
                now, device_id, sensor_type, segment, cp_anchor.anchor_index,
                reason=(f"degraded 경로 (P3 slope-aware) — 단구간 {seg_len}시점, "
                        f"가파른 상승(slope {slope:.3f}) robust 외삽"),
            )

        # 5. 정규 길이 구간 — 수평 대비 충분성 확인
        if seg_len < self._segment_horizon_ratio * H:
            return self._unknown(
                now, device_id, sensor_type, seg_len, cp_anchor.anchor_index,
                f"수평 대비 구간 부족 ({seg_len} < {self._segment_horizon_ratio}×{H})",
            )

        # 6. 경로 분기 (B3) — contamination 시 degraded
        if cp_anchor.contamination:
            return self._degraded_forecast(
                now, device_id, sensor_type, segment, cp_anchor.anchor_index,
            )
        return self._normal_forecast(
            now, device_id, sensor_type, segment, cp_anchor.anchor_index,
        )

    # ------------------------------------------------------------------------
    # 내부 — 정규 / degraded 경로
    # ------------------------------------------------------------------------

    def _normal_forecast(self, now, device_id, sensor_type, segment, anchor_index):
        """정규 경로 — ARIMA 재적합 + 신뢰구간 산출."""
        from statsmodels.tsa.arima.model import ARIMA

        H = self._forecast_steps
        seg_len = len(segment)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = ARIMA(segment, order=self._order, trend=self._trend).fit()
                fc = res.get_forecast(H)
                mean = np.asarray(fc.predicted_mean, dtype=float)
                ci = np.asarray(fc.conf_int(alpha=0.05), dtype=float)
            lower = ci[:, 0]
            upper = ci[:, 1]
            drift, drift_tstat = self._extract_drift(res)
        except Exception as e:
            return self._unknown(
                now, device_id, sensor_type, seg_len, anchor_index,
                f"ARIMA 적합 실패: {type(e).__name__}",
            )

        if not (np.all(np.isfinite(mean))
                and np.all(np.isfinite(lower))
                and np.all(np.isfinite(upper))):
            return self._unknown(
                now, device_id, sensor_type, seg_len, anchor_index,
                "예측에 NaN/Inf 발생",
            )

        return ARIMAResult(
            timestamp=now, device_id=device_id, sensor_type=sensor_type,
            path="normal",
            forecast_mean=[float(v) for v in mean],
            ci_lower=[float(v) for v in lower],
            ci_upper=[float(v) for v in upper],
            forecast_steps=H,
            drift=drift, drift_tstat=drift_tstat,
            segment_length=seg_len, anchor_index=anchor_index,
            order=self._order,
            reason=f"정규 경로 — 구간 {seg_len}시점 재적합",
        )

    def _degraded_forecast(self, now, device_id, sensor_type, segment, anchor_index,
                           reason="degraded 경로 — contamination 감지, "
                                  "robust drift 보조 예측"):
        """degraded 경로 — robust drift 보조 예측 (B3 / P3).

        median 1차 차분으로 추세를 견고하게 추정한다. 두 진입점:
          - B3: contamination(계단·스파이크 오염) 감지 시.
          - P3: 구간이 min_segment 미만이나 기울기가 가파를 때 (slope-aware).
        본 경로 결과는 출력 정책에서 최대 TENTATIVE로 상한된다.

        Args:
            reason: ARIMAResult에 기록할 판정 사유 (진입점별로 구분).
        """
        H = self._forecast_steps
        seg_len = len(segment)
        diffs = np.diff(segment)
        if len(diffs) < 5:
            return self._unknown(
                now, device_id, sensor_type, seg_len, anchor_index,
                "robust drift 추정 실패 (구간 부족)",
            )

        drift = float(np.median(diffs))
        last = float(segment[-1])
        steps = np.arange(1, H + 1, dtype=float)
        mean = last + drift * steps

        # robust 잔차 spread (MAD 기반) → 수평에 따라 확장하는 신뢰구간
        x = np.arange(seg_len, dtype=float)
        fitted = last + drift * (x - (seg_len - 1))
        resid = segment - fitted
        mad = float(np.median(np.abs(resid - np.median(resid))))
        sigma = 1.4826 * mad
        half = 1.96 * sigma * np.sqrt(steps)
        lower = mean - half
        upper = mean + half

        if not np.all(np.isfinite(mean)):
            return self._unknown(
                now, device_id, sensor_type, seg_len, anchor_index,
                "degraded 예측에 NaN/Inf 발생",
            )

        return ARIMAResult(
            timestamp=now, device_id=device_id, sensor_type=sensor_type,
            path="degraded",
            forecast_mean=[float(v) for v in mean],
            ci_lower=[float(v) for v in lower],
            ci_upper=[float(v) for v in upper],
            forecast_steps=H,
            drift=drift, drift_tstat=None,
            segment_length=seg_len, anchor_index=anchor_index,
            order=self._order,
            reason=reason,
        )

    # ------------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------------

    @staticmethod
    def _robust_slope(segment) -> Optional[float]:
        """구간의 robust 기울기 — median 1차 차분 (P3 slope-aware gate용).

        degraded 경로가 외삽에 쓰는 drift와 동일 정의 — 게이트 판정과
        실제 예측이 자기일관적이다.

        Returns:
            스텝당 robust slope. 추정 불가(길이 부족·비유한) 시 None.
        """
        if len(segment) < 2:
            return None
        slope = float(np.median(np.diff(segment)))
        return slope if np.isfinite(slope) else None

    @staticmethod
    def _extract_drift(res) -> tuple:
        """statsmodels 적합 결과에서 drift 계수·t값(|drift|/SE) 추출.

        trend='t'의 시간추세 항(statsmodels 명명 'x1')을 사용. 실패 시 (None, None).
        """
        try:
            params = res.params
            tvalues = res.tvalues
            try:
                drift = float(params["x1"])
                tstat = float(tvalues["x1"])
            except (KeyError, TypeError, IndexError):
                drift = float(np.asarray(params)[0])
                tstat = float(np.asarray(tvalues)[0])
            drift = drift if np.isfinite(drift) else None
            tstat = abs(tstat) if np.isfinite(tstat) else None
            return drift, tstat
        except Exception:
            return None, None

    def _unknown(self, now, device_id, sensor_type, seg_len, anchor_index, reason):
        """UNKNOWN(path='unknown') 결과 생성."""
        return ARIMAResult(
            timestamp=now, device_id=device_id, sensor_type=sensor_type,
            path="unknown",
            forecast_mean=[], ci_lower=[], ci_upper=[],
            forecast_steps=self._forecast_steps,
            drift=None, drift_tstat=None,
            segment_length=seg_len, anchor_index=anchor_index,
            order=self._order,
            reason=reason,
        )
