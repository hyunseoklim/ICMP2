"""
CPPurpose — Change Point 모듈의 사용 목적 2단계 열거형.

본 enum은 다음 위치에서 사용된다:
    - common/modules/change_point.py의 ChangePointDetector 생성자 인자
    - tests/integration의 통합 스토리 검증 (FLOW와 PREDICT 두 인스턴스 호출)

본 과업의 Change Point 모듈은 *두 용도*로 호출된다:
    1. FLOW_DETECTION: 시계열 흐름 변화 탐지 (W40 윈도우, S-C1·C2·C3 시나리오)
    2. PREDICT_VALIDATION: ARIMA 예측 교차 검증 (W60 윈도우, S-P1·P2·P3 시나리오)

같은 ChangePointDetector 클래스가 본 enum 값에 따라
*윈도우 크기와 min_size 등 동작 파라미터를 분기*한다 (결정 G-2 참조).

값은 한글 문자열로 정의.
"""

from enum import Enum


class CPPurpose(Enum):
    """Change Point 사용 목적 2단계.
    
    Members:
        FLOW_DETECTION: 흐름 탐지 — W40 윈도우, min_size=10.
                        S-C1 (VOC 점진 상승), S-C2 (O2 점진 하락),
                        S-C3 (야간 모드 13A 부하) 시나리오 검증.
        PREDICT_VALIDATION: 예측 검증 — W60 윈도우, min_size=15.
                            ARIMA 예측이 잡은 변화 시점을 교차 검증.
                            S-P1·P2·P3 시나리오 검증.
    
    Examples:
        >>> CPPurpose.FLOW_DETECTION.value
        '흐름 탐지'
        >>> CPPurpose.PREDICT_VALIDATION.name
        'PREDICT_VALIDATION'
    """

    FLOW_DETECTION = "흐름 탐지"
    PREDICT_VALIDATION = "예측 검증"
