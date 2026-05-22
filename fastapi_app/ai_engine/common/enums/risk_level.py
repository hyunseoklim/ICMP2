"""
RiskLevel — 위험 등급 4단계 열거형.

본 enum은 다음 위치의 결과 dataclass에서 level 필드 값으로 사용된다:
    - common/modules/threshold.py의 ThresholdResult
    - common/modules/z_score.py의 ZScoreResult
    - common/modules/change_point.py의 ChangePointResult
    - gas/modules/isolation_forest.py의 IsolationForestResult
    - power/modules/isolation_forest.py의 IsolationForestResult
    - 통합 결과의 *최종 위험 등급*

값은 한글 문자열로 정의되어 *보고서·검증 보고서와 일관성*을 유지한다.
"""

from enum import Enum


class RiskLevel(Enum):
    """위험 등급 4단계.
    
    Members:
        NORMAL: 정상 — 임계 범위 내, 통계 이상 없음.
        CAUTION: 주의 — 주의 임계 초과 또는 SPIKE/변화 탐지.
        DANGER: 위험 — 위험 임계 초과, 즉시 대응 필요.
        UNKNOWN: 판정불가 — 결측 비율 초과, 윈도우 미충족, 모드 비활성 등.
    
    Examples:
        >>> RiskLevel.NORMAL.value
        '정상'
        >>> RiskLevel.DANGER.name
        'DANGER'
    """

    NORMAL = "정상"
    CAUTION = "주의"
    DANGER = "위험"
    UNKNOWN = "판정불가"
