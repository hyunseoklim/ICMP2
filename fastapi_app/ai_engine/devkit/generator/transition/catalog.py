"""
generator/transition/catalog — 대표 전이 시나리오 카탈로그.

보고서·검증 카드의 *기준 시나리오*. parametric.generate_transition의
명명된 고정 구성 모음 — {speed}×{shape} 그리드 + step/spike.

파라미터화 생성기(parametric)가 B2·C3 sweep용 연속 knob이라면,
본 카탈로그는 문서·테스트가 참조하는 고정 대표 케이스다.

⚠ 전개속도는 검증용 더미 가정값 (parametric 모듈 참조).
"""

from __future__ import annotations

import numpy as np

from .parametric import generate_transition, SPEED_PRESETS


# 표준 기준값 (VOC류 — baseline 50, caution 200)
_BASELINE: float = 50.0
_THRESHOLD: float = 200.0
_ONSET: int = 120
_NOISE_STD: float = 12.0
_NOISE_PHI: float = 0.95
_POST_BUFFER: int = 200   # 임계 도달 후 관측 여유 스텝


def _ramp_entry(shape: str, speed: str) -> dict:
    """전개형(linear/accelerating/saturation) 카탈로그 항목."""
    n_steps = _ONSET + SPEED_PRESETS[speed] + _POST_BUFFER
    return {
        "shape": shape, "speed": speed,
        "baseline": _BASELINE, "threshold": _THRESHOLD,
        "onset_step": _ONSET, "n_steps": n_steps,
        "noise_std": _NOISE_STD, "noise_phi": _NOISE_PHI,
    }


def _abrupt_entry(shape: str) -> dict:
    """급변형(step/spike) 카탈로그 항목 — speed 무관."""
    return {
        "shape": shape,
        "baseline": _BASELINE, "threshold": _THRESHOLD,
        "onset_step": _ONSET, "n_steps": 400,
        "noise_std": _NOISE_STD, "noise_phi": _NOISE_PHI,
    }


def _build_catalog() -> dict:
    cat: dict = {}
    for speed in ("slow", "medium", "fast"):
        for shape in ("linear", "accelerating", "saturation"):
            cat[f"{speed}-{shape}"] = _ramp_entry(shape, speed)
    cat["step"] = _abrupt_entry("step")
    cat["spike"] = _abrupt_entry("spike")
    return cat


TRANSITION_CATALOG: dict = _build_catalog()
"""대표 전이 시나리오 11종.

{slow,medium,fast} × {linear,accelerating,saturation} = 9 + step + spike.
각 값은 generate_transition() 호출 kwargs dict.
"""


# ============================================================================
# 통합 스토리 ↔ 카탈로그 매핑 (Step 3-3 — 경량 문서화)
# ============================================================================
#
# 24시간 통합 스토리(generator/integrated_story/story_24h.py)의 이상 사건이
# 어떤 대표 전이 형태에 대응하는지 *문서화*한다. story_24h.py를 재배선하지
# 않는 보조 검증용 참조 매핑 — 통합 스토리의 정성적 사건을 본 카탈로그의
# 정량적 전이 형태로 번역해, 예측 서브시스템 검증의 추적성을 제공한다.
#
# 스토리 사건 U.1~U.10 중 anomaly_type != "none"인 4건만 전이를 가진다.
# 나머지 6건(U.1·U.3·U.5·U.6·U.7·U.10)은 작업모드·환기 변경일 뿐
# 단일 채널 전이가 아니므로 매핑 대상이 아니다.

STORY_TRANSITION_MAP: dict = {
    "U.2": {
        "anomaly_type": "ventilation_weak",
        "catalog": "slow-linear",
        "direction": "high",
        "rationale": (
            "환기 약화로 가스 농도가 느리게 선형 상승. 부분 상승(CAUTION "
            "수준)으로 임계 완전 도달 전 회복 — 느린 배경 크리프의 대표형."
        ),
    },
    "U.4": {
        "anomaly_type": "voc_rising",
        "catalog": "medium-linear",
        "direction": "high",
        "rationale": (
            "도장 작업 집중으로 VOC 점진 상승 — 예측 서브시스템의 대표 "
            "사전경고 케이스. 대표 매핑이며 실제 스토리 전개는 더 길다."
        ),
    },
    "U.8": {
        "anomaly_type": "h2s_leak",
        "catalog": "step",
        "direction": "high",
        "rationale": (
            "H2S 누출 사고 — 급격한 계단형 임계 초과. 예측보다 즉시 탐지 "
            "영역이며, 예측기는 계단 직후 오탐을 내지 않아야 한다."
        ),
    },
    "U.9": {
        "anomaly_type": "h2s_recovery",
        "catalog": None,
        "direction": "low",
        "rationale": (
            "이상→정상 회복(하강). 본 카탈로그는 상승 전이만 다루므로 "
            "대응 항목 없음. 예측기는 direction='high'에서 UNKNOWN 처리."
        ),
    },
}
"""통합 스토리 이상 사건 ↔ 카탈로그 대표 전이 매핑.

키는 story_24h.py STORY_EVENTS의 event_id. 값은 dict:
    anomaly_type: 스토리 사건의 이상 코드.
    catalog: 대응 TRANSITION_CATALOG 키 (없으면 None).
    direction: 전이 방향 ('high' 상승 / 'low' 하강).
    rationale: 매핑 근거 (한글).
"""


def get_story_transition(event_id: str) -> dict:
    """스토리 사건 event_id의 카탈로그 매핑을 반환.

    Args:
        event_id: STORY_EVENTS의 사건 ID (예: 'U.4').

    Returns:
        STORY_TRANSITION_MAP의 매핑 dict.

    Raises:
        KeyError: 전이 매핑이 없는 사건 (anomaly_type='none' 사건 포함).
    """
    return STORY_TRANSITION_MAP[event_id]


def build_catalog_scenario(name: str, seed: int = 42, **overrides) -> np.ndarray:
    """카탈로그 시나리오를 시계열로 생성.

    Args:
        name: TRANSITION_CATALOG의 키 (예: 'medium-linear', 'step').
        seed: 난수 시드.
        **overrides: 카탈로그 기본 구성을 덮어쓸 generate_transition 인자.

    Returns:
        np.ndarray (1D) — 전이 시계열.

    Raises:
        ValueError: 알 수 없는 name.
    """
    if name not in TRANSITION_CATALOG:
        raise ValueError(
            f"알 수 없는 카탈로그 시나리오: {name!r}. "
            f"가능: {sorted(TRANSITION_CATALOG)}"
        )
    cfg = {**TRANSITION_CATALOG[name], **overrides, "seed": seed}
    return generate_transition(**cfg)
