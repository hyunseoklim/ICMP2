"""
boundary — 모듈 경계 정책.

본 모듈은 시스템 전제 조건서 차원 6(모듈 운영 경계)을 구현한다.

본 모듈이 정해주는 것:
    - 알람 통합 정책 (B.1, 자리표시자)
    - 모델 인스턴스 수 (B.2)
    - 재학습 정책 (B.3, 자리표시자)
    - 모듈 활성화 정책 (B.1 + W.1 결합)
    - is_module_active 판정 함수
"""

from __future__ import annotations

from power.core.enums import WorkMode


# ============================================================================
# B.1 알람 통합 정책 (자리표시자)
# ============================================================================

INTEGRATION_LOGIC_ENABLED: bool = True
"""모듈 결과 통합 알람 정책 활성화 여부. 결정 B.1.

미래 위험 예측 서브시스템 재설계로 *예측 경로 한정* 통합 로직이
도입되었다 — common/integration/ (CP·ARIMA·출력 정책을 파이프라인으로
결합, 2축 등급화·K-확인). 본 값은 그 범위에서 True.

전(全) 모듈을 결합하는 통합 알람(B.1 본래 범위)은 여전히 후속 과업.
"""


# ============================================================================
# B.2 모델 인스턴스 수
# ============================================================================

GAS_IF_MODEL_COUNT: int = 1
"""가스 IF 모델 인스턴스 수. 결정 B.2.

가스 9차원 다변량 IsolationForest 1개. 가스 장비 2대(gas_A, gas_B)는
*같은 모델*에서 판정 (장비 식별자는 입력 메타데이터로만 전달).
"""

POWER_IF_MODEL_COUNT: int = 1
"""전력 IF 모델 인스턴스 수. 결정 B.2.

전력 3차원(전압·전류·전력) 다변량 IsolationForest 1개.
"""

GAS_ARIMA_MODEL_COUNT: int = 0
"""가스 ARIMA frozen 모델 인스턴스 수. 결정 B.2 (재설계로 개정).

미래 위험 예측 서브시스템 재설계로 ARIMA는 frozen(1회 학습·저장) 구조를
폐기하고 predict 시점 CP-anchored 재적합으로 전환 — 영구 모델 인스턴스
없음(0). (구 값 18 = 9 가스 × 2 장비.)
"""

POWER_ARIMA_MODEL_COUNT: int = 0
"""전력 ARIMA frozen 모델 인스턴스 수. 결정 B.2 (재설계로 개정).

가스와 동일 — predict 시점 재적합, frozen 인스턴스 없음(0). (구 값 3.)
"""

TOTAL_MODEL_COUNT: int = 2
"""전체 frozen 학습 모델 수 = IF 2 + ARIMA 0 = 2개. 결정 B.2 (재설계로 개정).

ARIMA는 재설계로 frozen 모델을 갖지 않음 (구 값 23 = IF 2 + ARIMA 21)."""


# ============================================================================
# B.3 재학습 정책 (자리표시자)
# ============================================================================

RETRAINING_ENABLED: bool = False
"""동적 재학습 활성화 여부. 결정 B.3.

본 과업은 *단일 학습*만 수행. 학습된 23개 모델은 본 과업 동안 갱신 없음.

후속 과업 (Phase 5+)에서 *드리프트 탐지 → 재학습 트리거* 정책을 도입할 때
True로 전환.
"""


# ============================================================================
# 모듈 활성화 정책 (B.1 + W.1 결합)
# ============================================================================

MODULE_ACTIVE_MODES: dict = {
    "threshold":              [WorkMode.WORKING, WorkMode.IDLE],
    "z_score":                [WorkMode.WORKING, WorkMode.IDLE],
    "change_point_flow":      [WorkMode.WORKING, WorkMode.IDLE],
    "isolation_forest_gas":   [WorkMode.WORKING],
    "isolation_forest_power": [WorkMode.WORKING],
    "arima":                  [WorkMode.WORKING],
    "change_point_predict":   [WorkMode.WORKING],
}
"""모듈별 활성화되는 작업 모드 목록.

본 dict는 *어떤 모듈이 어떤 모드에서 호출되는지* 정해준다.
호출자는 is_module_active() 함수로 활성화 여부를 판정한 뒤 모듈 호출.

키 명명 규칙: Python 식별자형 (밑줄 구분).

설명:
    - threshold·z_score·change_point_flow는 *항상 활성*
      - 야간(IDLE) 누출 탐지, 24시간 모니터링 등에 사용
      - S-C3 야간 모드 13A 부하 탐지(change_point_flow)도 IDLE에서 동작
    - isolation_forest_gas/power, arima, change_point_predict는 *WORKING 전용*
      - 학습 데이터가 WORKING NORMAL 분포(T.3)이므로 IDLE에서 부정확
      - IDLE에서는 UNKNOWN 반환 또는 호출 자체를 건너뜀

근거: 결정 B.1 + W.1.
"""


def is_module_active(module_name: str, mode: WorkMode) -> bool:
    """주어진 모드에서 모듈이 활성화되는지 판정한다.
    
    Args:
        module_name: MODULE_ACTIVE_MODES의 키 중 하나.
                     예: "threshold", "isolation_forest_gas", "arima"
        mode: 현재 작업 모드 (WorkMode.WORKING 또는 WorkMode.IDLE).
    
    Returns:
        활성화되면 True, 아니면 False.
    
    Raises:
        KeyError: module_name이 MODULE_ACTIVE_MODES에 없을 때.
    
    Examples:
        >>> is_module_active("isolation_forest_gas", WorkMode.WORKING)
        True
        >>> is_module_active("isolation_forest_gas", WorkMode.IDLE)
        False
        >>> is_module_active("threshold", WorkMode.IDLE)
        True
    """
    if module_name not in MODULE_ACTIVE_MODES:
        raise KeyError(
            f"알 수 없는 모듈명: {module_name!r}. "
            f"허용된 모듈: {list(MODULE_ACTIVE_MODES.keys())}"
        )
    return mode in MODULE_ACTIVE_MODES[module_name]
