"""공통 전제 가정 — 환경·측정·시간·학습·경계."""

from . import environment
from . import measurement
from . import work
from . import training
from . import boundary

# 자주 사용되는 함수들을 직접 import 가능하게
from .work import determine_work_mode, transition_weight
from .boundary import is_module_active

__all__ = [
    # 서브 모듈
    "environment",
    "measurement",
    "work",
    "training",
    "boundary",
    # 함수
    "determine_work_mode",
    "transition_weight",
    "is_module_active",
]
