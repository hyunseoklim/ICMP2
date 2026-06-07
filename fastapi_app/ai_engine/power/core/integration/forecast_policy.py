"""
common/integration/forecast_policy — 미래 위험 예측의 출력 정책 (등급화).

미래 위험 예측 서브시스템의 *통합 레이어* 컴포넌트. ARIMA의 원시 예측
(ARIMAResult)을 받아 2축 등급(심각도 × 확신도)을 산출한다.

본 모듈이 담당하는 것:
    - 2축 등급화: 임계(주의·위험)마다 ForecastConfidence 산출.
    - K-연속 확인: CONFIRMED_WARNING / CONFIRMED_STRONG 승격.
    - drift 유의성 가드: CONFIRMED_WARNING은 drift_tstat ≥ τ 일 때만.
    - degraded 상한(B3): degraded 경로는 최대 TENTATIVE.
    - 모델형태 보정 마진 m = margin_ratio × 임계 (임계 상대 — 채널 스케일
      무관): 등급화에 effective CI(= CI ± m) 사용.
    - B1 교차모듈 확인: 현재 탐지(Threshold) 등급을 보강 *증거*로만 부착.
      예측 등급은 불변(안전 목적상 보수적 유지) — corroborated 플래그로 반영.

등급 수식 (임계 T, 마진 m = margin_ratio × T, direction='high'):
    - NORMAL            : CI_upper + m < T
    - TENTATIVE         : CI_upper + m ≥ T
    - CONFIRMED_WARNING : (mean + m ≥ T) AND (drift_tstat ≥ τ), K회 연속
    - CONFIRMED_STRONG  : CI_lower ≥ T, K회 연속

본 모듈은 *상태 보유* — 채널·임계축별 K 카운터를 유지한다.

주의: 본 골격은 direction='high' 채널만 등급화한다.
      'low'(O2)·'both'(전압)는 UNKNOWN + 사유 반환 (후속 일반화 대상).

파라미터(margin_ratio·τ·K·β)는 잠정값 — C3 도메인 보정 대상.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from power.core.enums import ForecastConfidence, RiskLevel


# ============================================================================
# 기본 파라미터 (재설계 — 잠정값, C3 도메인 보정 대상)
# ============================================================================

_DEFAULT_MARGIN_RATIO: float = 0.2             # 모델형태 보정 마진 비율 (m = ratio×임계)
_DEFAULT_DRIFT_TAU: float = 2.0                # drift 유의성 임계 τ
_DEFAULT_K_CONFIRM: int = 18                   # K-연속 확인 횟수
_DEFAULT_DEGRADED_CI_WIDTH_RATIO: float = 0.5  # degraded CI 폭 한계 β

# 확신도 순위 (headline 산정용)
_CONF_RANK = {
    ForecastConfidence.NORMAL: 0,
    ForecastConfidence.UNKNOWN: 0,
    ForecastConfidence.TENTATIVE: 1,
    ForecastConfidence.CONFIRMED_WARNING: 2,
    ForecastConfidence.CONFIRMED_STRONG: 3,
}


# ============================================================================
# ForecastPolicyResult — 단일 채널 2축 최종 등급 결과
# ============================================================================

@dataclass
class ForecastPolicyResult:
    """출력 정책의 단일 채널 2축 최종 등급 결과.

    Attributes:
        timestamp: 판정 시점.
        device_id: 장비 식별자.
        sensor_type: 센서 종류.
        caution_confidence: 주의 임계 도달 확신도 (ForecastConfidence).
        danger_confidence: 위험 임계 도달 확신도.
        headline_severity: 'danger'/'caution'/None — 비-NORMAL 확신도를 가진
                           최고 심각도 (운영 표시용 요약).
        headline_confidence: headline_severity 축의 확신도. 사전경고 없으면
                             NORMAL, 판정불가면 UNKNOWN.
        caution_eta_step: mean+m이 주의 임계를 처음 넘는 예측 스텝 h
                          (1~H, 없으면 None) — Lead 산정용.
        danger_eta_step: 위험 임계에 대한 동일 값.
        path: ARIMA 예측 경로 ('normal'/'degraded'/'unknown') — 추적용.
        forecast_steps: 예측 수평 H.
        present_level: B1 — 현재 측정값의 Threshold 등급 (교차모듈 증거).
        corroborated: B1 — 현재 탐지가 예측을 보강하는가. 현재 등급이
                      CAUTION·DANGER이고 예측 headline이 위험 등급일 때 True.
        reason: 판정 사유 한글 문자열.
    """

    timestamp: datetime
    device_id: str
    sensor_type: str
    caution_confidence: ForecastConfidence
    danger_confidence: ForecastConfidence
    headline_severity: Optional[str]
    headline_confidence: ForecastConfidence
    caution_eta_step: Optional[int]
    danger_eta_step: Optional[int]
    path: str
    forecast_steps: int
    present_level: RiskLevel
    corroborated: bool
    reason: str
    forecast_mean: Optional[list] = None   # ARIMA 점예측 곡선(그래프용). path='unknown'이면 None
    ci_lower: Optional[list] = None        # 95% CI 하한
    ci_upper: Optional[list] = None        # 95% CI 상한

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "caution_confidence": self.caution_confidence.value,
            "danger_confidence": self.danger_confidence.value,
            "headline_severity": self.headline_severity,
            "headline_confidence": self.headline_confidence.value,
            "caution_eta_step": self.caution_eta_step,
            "danger_eta_step": self.danger_eta_step,
            "path": self.path,
            "forecast_steps": self.forecast_steps,
            "present_level": self.present_level.value,
            "corroborated": self.corroborated,
            "reason": self.reason,
        }


# ============================================================================
# ForecastPolicy — 2축 등급화 + K-확인 (상태 보유)
# ============================================================================

class ForecastPolicy:
    """ARIMAResult → 2축 등급(ForecastPolicyResult) 산출.

    채널·임계축별 K 카운터를 유지하는 *상태 객체*. 매 시점 grade()를
    호출하면 K-연속 확인이 누적된다.
    """

    def __init__(
        self,
        margin_ratio: float = _DEFAULT_MARGIN_RATIO,
        drift_tau: float = _DEFAULT_DRIFT_TAU,
        k_confirm: int = _DEFAULT_K_CONFIRM,
        degraded_ci_width_ratio: float = _DEFAULT_DEGRADED_CI_WIDTH_RATIO,
    ):
        """설정으로 초기화.

        Args:
            margin_ratio: 모델형태 보정 마진 비율. 축별 effective 마진
                          m = margin_ratio × 임계 — 채널 스케일 무관.
            drift_tau: CONFIRMED_WARNING의 drift 유의성 임계 τ.
            k_confirm: CONFIRMED 승격에 필요한 연속 확인 횟수 K.
            degraded_ci_width_ratio: degraded 경로 CI 폭 한계 비율 β
                                     (CI 폭 > β·임계 → 해당 축 UNKNOWN).

        Raises:
            ValueError: 파라미터 범위 위반.
        """
        if margin_ratio < 0:
            raise ValueError(f"margin_ratio는 0 이상. 받은 값: {margin_ratio}")
        if drift_tau < 0:
            raise ValueError(f"drift_tau는 0 이상. 받은 값: {drift_tau}")
        if k_confirm < 1:
            raise ValueError(f"k_confirm은 1 이상. 받은 값: {k_confirm}")
        if degraded_ci_width_ratio <= 0:
            raise ValueError(
                f"degraded_ci_width_ratio는 양수. 받은 값: {degraded_ci_width_ratio}"
            )

        self._margin_ratio = float(margin_ratio)
        self._tau = float(drift_tau)
        self._k = int(k_confirm)
        self._beta = float(degraded_ci_width_ratio)

        # 채널·임계축별 K 카운터 — 키: (device_id, sensor_type, 'caution'|'danger')
        self._warn_streak: dict = {}
        self._strong_streak: dict = {}

    @property
    def k_confirm(self) -> int:
        """K-연속 확인 횟수."""
        return self._k

    def reset(self) -> None:
        """모든 K 카운터 상태 초기화."""
        self._warn_streak.clear()
        self._strong_streak.clear()

    # ------------------------------------------------------------------------
    # 외부 API
    # ------------------------------------------------------------------------

    def grade(
        self,
        arima_result,
        caution: Optional[float],
        danger: Optional[float],
        direction: str = "high",
        present_level: RiskLevel = RiskLevel.UNKNOWN,
    ) -> ForecastPolicyResult:
        """ARIMAResult를 2축 등급으로 산출.

        Args:
            arima_result: ARIMA 모듈의 ARIMAResult (원시 예측).
            caution: 주의 임계값.
            danger: 위험 임계값.
            direction: 임계 방향 ('high'만 등급화, 그 외 UNKNOWN — 후속).
            present_level: B1 — 현재 측정값의 Threshold 등급. 예측 등급은
                           바꾸지 않고 corroborated 산출에만 쓰인다.

        Returns:
            ForecastPolicyResult — 2축 최종 등급 + B1 교차모듈 증거.
        """
        ar = arima_result
        ck = (ar.device_id, ar.sensor_type, "caution")
        dk = (ar.device_id, ar.sensor_type, "danger")

        # 등급화 불가 — direction 미지원 / 임계 미정의 / ARIMA unknown
        if direction != "high":
            self._reset(ck)
            self._reset(dk)
            return self._build(
                ar, ForecastConfidence.UNKNOWN, ForecastConfidence.UNKNOWN,
                None, None,
                f"direction '{direction}' 등급화 미구현 (후속 일반화 대상)",
                present_level,
            )
        if caution is None or danger is None:
            self._reset(ck)
            self._reset(dk)
            return self._build(
                ar, ForecastConfidence.UNKNOWN, ForecastConfidence.UNKNOWN,
                None, None, "임계(주의·위험) 미정의", present_level,
            )
        if ar.path == "unknown":
            self._reset(ck)
            self._reset(dk)
            return self._build(
                ar, ForecastConfidence.UNKNOWN, ForecastConfidence.UNKNOWN,
                None, None, f"ARIMA 예측 불가: {ar.reason}", present_level,
            )

        c_conf, c_eta = self._grade_axis(ck, ar, float(caution))
        d_conf, d_eta = self._grade_axis(dk, ar, float(danger))
        reason = f"{ar.path} 경로 — 주의:{c_conf.value} / 위험:{d_conf.value}"
        return self._build(ar, c_conf, d_conf, c_eta, d_eta, reason, present_level)

    # ------------------------------------------------------------------------
    # 내부 — 축별 등급화
    # ------------------------------------------------------------------------

    def _grade_axis(self, key, ar, threshold: float):
        """단일 임계축의 ForecastConfidence + eta 산출."""
        m = self._margin_ratio * threshold  # 임계 상대 마진 — 채널 스케일 무관
        mean = ar.forecast_mean
        lo = ar.ci_lower
        hi = ar.ci_upper

        # eta — mean+m이 임계를 처음 넘는 예측 스텝 (1-indexed)
        eta = next((h + 1 for h, x in enumerate(mean) if (x + m) >= threshold), None)
        any_tentative = any((u + m) >= threshold for u in hi)

        # degraded 경로 (B3) — CI 폭 과대 시 UNKNOWN, 그 외 최대 TENTATIVE
        if ar.path == "degraded":
            self._reset(key)
            width = max((u - l) for l, u in zip(lo, hi)) if lo else 0.0
            if width > self._beta * threshold:
                return ForecastConfidence.UNKNOWN, None
            conf = (ForecastConfidence.TENTATIVE if any_tentative
                    else ForecastConfidence.NORMAL)
            return conf, eta

        # 정규 경로 — K-연속 확인
        warn_cond = (
            any((x + m) >= threshold for x in mean)
            and ar.drift_tstat is not None
            and ar.drift_tstat >= self._tau
        )
        strong_cond = any(l >= threshold for l in lo)

        self._warn_streak[key] = (
            self._warn_streak.get(key, 0) + 1 if warn_cond else 0
        )
        self._strong_streak[key] = (
            self._strong_streak.get(key, 0) + 1 if strong_cond else 0
        )

        if self._strong_streak[key] >= self._k:
            conf = ForecastConfidence.CONFIRMED_STRONG
        elif self._warn_streak[key] >= self._k:
            conf = ForecastConfidence.CONFIRMED_WARNING
        elif any_tentative:
            conf = ForecastConfidence.TENTATIVE
        else:
            conf = ForecastConfidence.NORMAL
        return conf, eta

    def _reset(self, key) -> None:
        """단일 키의 K 카운터 초기화."""
        self._warn_streak[key] = 0
        self._strong_streak[key] = 0

    @staticmethod
    def _headline(c_conf: ForecastConfidence, d_conf: ForecastConfidence):
        """비-NORMAL 확신도를 가진 최고 심각도와 그 확신도 산출."""
        if _CONF_RANK[d_conf] > 0:
            return "danger", d_conf
        if _CONF_RANK[c_conf] > 0:
            return "caution", c_conf
        if ForecastConfidence.UNKNOWN in (c_conf, d_conf):
            return None, ForecastConfidence.UNKNOWN
        return None, ForecastConfidence.NORMAL

    def _build(self, ar, c_conf, d_conf, c_eta, d_eta, reason,
               present_level) -> ForecastPolicyResult:
        """ForecastPolicyResult 조립 + B1 교차모듈 증거 산출.

        B1: 예측 등급은 바꾸지 않는다. 현재 탐지(present_level)가 예측을
        보강하는지를 corroborated 플래그로만 표시한다 (보강 증거 only).
        """
        hs, hc = self._headline(c_conf, d_conf)
        corroborated = (
            present_level in (RiskLevel.CAUTION, RiskLevel.DANGER)
            and _CONF_RANK[hc] >= 1
        )
        if corroborated:
            reason = f"{reason} · 현재 {present_level.value} — 추세 보강"
        return ForecastPolicyResult(
            timestamp=ar.timestamp,
            device_id=ar.device_id,
            sensor_type=ar.sensor_type,
            caution_confidence=c_conf,
            danger_confidence=d_conf,
            headline_severity=hs,
            headline_confidence=hc,
            caution_eta_step=c_eta,
            danger_eta_step=d_eta,
            path=ar.path,
            forecast_steps=ar.forecast_steps,
            present_level=present_level,
            corroborated=corroborated,
            reason=reason,
            forecast_mean=ar.forecast_mean,
            ci_lower=ar.ci_lower,
            ci_upper=ar.ci_upper,
        )
