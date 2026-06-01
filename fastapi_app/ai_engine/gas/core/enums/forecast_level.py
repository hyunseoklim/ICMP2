"""
forecast_level — 미래 위험 예측의 확신도 등급 열거형.

미래 위험 예측 서브시스템 재설계에 따라, 예측 결과는 *2축*으로 표현된다:

    - 심각도(severity): 예측이 *어느 임계*를 향하는가 — CAUTION / DANGER.
      별도 enum을 두지 않고, 결과 객체가 임계별 확신도를 각각 보유하여 표현한다
      (예: ForecastPolicyResult.caution_confidence / danger_confidence).
    - 확신도(confidence): 그 임계 도달을 *얼마나 확신*하는가 — ForecastConfidence.

RiskLevel과 분리한 이유:
    - RiskLevel은 *현재 시점*의 위험 등급.
    - ForecastConfidence는 *미래 예측 시점*의 도달 확신 등급.

값은 한글 문자열로 정의.
"""

from enum import Enum


class ForecastConfidence(Enum):
    """미래 위험 예측의 확신도 5단계.

    하나의 임계(주의 또는 위험)에 대해, 예측이 그 임계에 도달할 것이라는
    *확신의 강도*를 표현한다. 심각도(어느 임계인가)는 결과 객체가
    임계별로 본 등급을 각각 보유하여 표현한다.

    Members:
        NORMAL: 정상 — 예측 CI 상한 + 마진 < 임계 (해당 임계 미도달 예측).
        TENTATIVE: 잠정 — 예측 CI 상한 + 마진 ≥ 임계 (가능성 있음, 저확신).
        CONFIRMED_WARNING: 확정-경고 — 예측 평균 + 마진 ≥ 임계가 K회 연속이며
                           적합된 drift가 통계적으로 유의 (평균 예측상 도달, 중확신).
        CONFIRMED_STRONG: 확정-강 — 예측 CI 하한 ≥ 임계가 K회 연속
                          (보수적 하한까지 도달, 고확신).
        UNKNOWN: 판정불가 — 세그먼트 부족·결측·CP anchor 신뢰불가 등.

    주의: STRONG은 위험의 *심각도*가 아니라 *확신의 강함*을 뜻한다.
          심각도(CAUTION/DANGER)는 caution/danger 두 임계 축이 담당한다.

    Examples:
        >>> ForecastConfidence.CONFIRMED_WARNING.value
        '확정-경고'
        >>> ForecastConfidence.TENTATIVE.name
        'TENTATIVE'
    """

    NORMAL = "정상"
    TENTATIVE = "잠정"
    CONFIRMED_WARNING = "확정-경고"
    CONFIRMED_STRONG = "확정-강"
    UNKNOWN = "판정불가"
