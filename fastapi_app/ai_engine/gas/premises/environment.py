"""
gas/premises/environment — 가스 도메인 환기 가정 (E.1).

본 모듈은 시스템 전제 조건서 E.1을 코드 상수·함수로 구현한다.
환기 강도 3단계와 환기 단계별 가스 평균 변화 배수를 정의.

본 모듈이 정해주는 것:
    - 환기 강도 3단계 (STRONG/NORMAL/WEAK)
    - 단계별 ACH (Air Changes per Hour) 값
    - 단계별 가스 평균 배수 (NORMAL을 1.0 기준)

활용처:
    - gas/premises/gas_distribution.py의 mean_vector(): 환기 단계별 평균 벡터
    - generator/gas_generator/: 시나리오 카드 데이터 생성 시 환기 단계 변경
    - generator/integrated_story/: U-2 환기 부족(WEAK) → U-7 STRONG 복귀 시퀀스

근거 (Phase 2 E.1):
    - 학습 분포는 NORMAL 100% (T.3)
    - WEAK·STRONG은 시나리오 검증에만 사용 (학습 대상 외)
"""

from __future__ import annotations

from enum import Enum


class VentilationLevel(Enum):
    """환기 강도 3단계.
    
    Members:
        STRONG: 강 — 강제 환기, 가스 농도 낮음 (ACH 12).
        NORMAL: 보통 — 일반 환기, 학습 분포의 기준 (ACH 6).
        WEAK: 약 — 환기 부족, 가스 농도 상승 (ACH 2).
    """

    STRONG = "강"
    NORMAL = "보통"
    WEAK = "약"


# ============================================================================
# 환기 강도 ACH (Air Changes per Hour)
# ============================================================================

VENTILATION_ACH: dict = {
    VentilationLevel.STRONG: 12,
    VentilationLevel.NORMAL: 6,
    VentilationLevel.WEAK: 2,
}
"""환기 단계별 ACH 값. 결정 E.1.

ACH는 *시간당 공기 교체 횟수*. 높을수록 환기가 강함.
"""


# ============================================================================
# 환기 단계별 가스 평균 배수
# ============================================================================

VENTILATION_MEAN_MULTIPLIER: dict = {
    VentilationLevel.STRONG: 0.5,
    VentilationLevel.NORMAL: 1.0,
    VentilationLevel.WEAK: 2.0,
}
"""환기 단계별 가스 평균 변화 배수 (NORMAL 기준).

본 배수는 *NORMAL 환기*의 가스 평균을 1.0으로 두었을 때 각 단계의 비율.
gas_distribution.py의 mean_vector(ventilation)이 이 배수를 곱하여
환기 단계별 9차원 평균 벡터를 반환.

예시:
    - STRONG: CO 평균 5.0 × 0.5 = 2.5 ppm
    - NORMAL: CO 평균 5.0 × 1.0 = 5.0 ppm (기준)
    - WEAK:   CO 평균 5.0 × 2.0 = 10.0 ppm

주의: O2는 *환기와 반대 방향* — 환기 강할수록 O2 농도 *증가*.
gas_distribution.py에서 O2만 별도 처리.
"""


# ============================================================================
# 산소 (O2)는 환기 방향 반대 — 별도 처리
# ============================================================================

VENTILATION_O2_MULTIPLIER: dict = {
    VentilationLevel.STRONG: 1.005,  # STRONG → O2 약간 높음 (외부 공기 유입)
    VentilationLevel.NORMAL: 1.0,
    VentilationLevel.WEAK: 0.95,     # WEAK → O2 약간 낮음 (실내 소비 누적)
}
"""산소(O2) 평균 배수. 다른 가스와 반대 방향.

환기가 강할수록 외부 공기 유입으로 O2 농도 *증가*,
환기 부족 시 작업자 소비로 O2 농도 *감소*.

값은 보수적으로 작게 설정 — O2 변동은 작지만 그래도 측정 가능 수준.
"""
