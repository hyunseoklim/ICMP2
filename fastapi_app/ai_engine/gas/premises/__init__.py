"""가스 도메인 전제 가정 — 환기·분포·장비·작업자."""

from . import environment
from . import gas_distribution
from . import measurement
from . import work

# 자주 사용되는 항목을 직접 import 가능하게
from .environment import (
    VentilationLevel,
    VENTILATION_ACH,
    VENTILATION_MEAN_MULTIPLIER,
    VENTILATION_O2_MULTIPLIER,
)
from .gas_distribution import (
    GAS_SENSOR_TYPES,
    GAS_DIMENSION,
    GAS_MEANS_NORMAL,
    GAS_STDS,
    GAS_CORRELATIONS,
    correlation_matrix,
    mean_vector,
    covariance_matrix,
    get_distribution_params,
)
from .measurement import (
    GAS_DEVICES,
    GAS_DEVICE_COUNT,
    INTER_DEVICE_GAS_CORRELATION,
    GAS_RESOLUTION,
)
from .work import (
    WORK_TYPE,
    WORKER_COUNT,
    WORKER_CO2_PRODUCTION_PPM_PER_HOUR,
    WORKER_O2_CONSUMPTION_PPM_PER_HOUR,
)

__all__ = [
    # 서브 모듈
    "environment", "gas_distribution", "measurement", "work",
    # 환기
    "VentilationLevel", "VENTILATION_ACH",
    "VENTILATION_MEAN_MULTIPLIER", "VENTILATION_O2_MULTIPLIER",
    # 분포
    "GAS_SENSOR_TYPES", "GAS_DIMENSION",
    "GAS_MEANS_NORMAL", "GAS_STDS", "GAS_CORRELATIONS",
    "correlation_matrix", "mean_vector", "covariance_matrix",
    "get_distribution_params",
    # 측정
    "GAS_DEVICES", "GAS_DEVICE_COUNT",
    "INTER_DEVICE_GAS_CORRELATION", "GAS_RESOLUTION",
    # 작업
    "WORK_TYPE", "WORKER_COUNT",
    "WORKER_CO2_PRODUCTION_PPM_PER_HOUR",
    "WORKER_O2_CONSUMPTION_PPM_PER_HOUR",
]
