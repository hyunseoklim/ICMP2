"""
WorkMode — 작업 시간대 2단계 열거형.

본 enum은 다음 위치에서 사용된다:
    - common/premises/work.py의 시간대 판정 함수 반환값
    - common/premises/boundary.py의 MODULE_ACTIVE_MODES 키
    - generator/core/time_axis.py의 시간 구조 구성
    - gas·power 모듈의 활성화 정책 분기

본 과업은 시스템 전제 조건서 W.1에 따라 WORKING/IDLE 2단계를 사용한다.
전이 구간(W.3 5분)은 별도 모드가 아닌 generator 내부에서 선형 보간으로 처리.

값은 한글 문자열로 정의.
"""

from enum import Enum


class WorkMode(Enum):
    """작업 시간대 2단계.
    
    Members:
        WORKING: 작업중 — 08:00~18:00 (W.1).
                 모든 모듈 활성. 가스는 작업으로 인한 변동,
                 전력은 220V·11A·2,420W 평균(W.5 WORKING).
        IDLE: 대기 — 18:00~다음날 08:00.
              IF·ARIMA 비활성(B.1). Threshold·Z-score·CP 흐름은 활성.
              전력은 220V·1A·220W 평균(W.5 IDLE).
    
    Examples:
        >>> WorkMode.WORKING.value
        '작업중'
        >>> WorkMode.IDLE.name
        'IDLE'
    """

    WORKING = "작업중"
    IDLE = "대기"
