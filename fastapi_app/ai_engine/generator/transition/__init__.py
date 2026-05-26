"""generator/transition — 파라미터화 전이 시나리오 (B2·C3 보정용).

미래 위험 예측 서브시스템의 운영점 보정을 위해, 형태·전개속도를
파라미터로 받는 단일 채널 전이 시계열 생성기를 제공한다.
"""

from .parametric import generate_transition, SPEED_PRESETS
from .catalog import (
    TRANSITION_CATALOG, build_catalog_scenario,
    STORY_TRANSITION_MAP, get_story_transition,
)

__all__ = [
    "generate_transition",
    "SPEED_PRESETS",
    "TRANSITION_CATALOG",
    "build_catalog_scenario",
    "STORY_TRANSITION_MAP",
    "get_story_transition",
]
