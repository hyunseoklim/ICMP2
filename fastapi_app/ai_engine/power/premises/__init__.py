"""전력 도메인 전제 가정 — 분포·측정·작업 모드·옴의 법칙."""

from . import work
from . import measurement
from . import power_distribution
from . import ohm_law

from .work import (
    # ── deprecated (제거 예정 — see reports/MIGRATION.md) ──
    POWER_MEANS_WORKING,    # → working_means(rated_w) 사용
    # ── 기존 ──
    POWER_MEANS_IDLE,
    get_means,
)
from .measurement import (
    POWER_DEVICES,
    POWER_DEVICE_COUNT,
    POWER_RESOLUTION,
)
from .power_distribution import (
    POWER_SENSOR_TYPES,
    POWER_DIMENSION,
    # ── deprecated (제거 예정 — see reports/MIGRATION.md) ──
    POWER_STDS_WORKING,     # → working_stds(rated_w) 사용
    # ── 기존 ──
    POWER_STDS_IDLE,
    POWER_CORRELATIONS,
    correlation_matrix,
    mean_vector,
    covariance_matrix,
    get_distribution_params,
    # ── Phase B-2 신규 ──
    working_means,
    working_stds,
)
from .ohm_law import (
    expected_power,
    verify_ohm_law,
)

__all__ = [
    "work", "measurement", "power_distribution", "ohm_law",
    "POWER_MEANS_WORKING", "POWER_MEANS_IDLE", "get_means",
    "POWER_DEVICES", "POWER_DEVICE_COUNT", "POWER_RESOLUTION",
    "POWER_SENSOR_TYPES", "POWER_DIMENSION",
    "POWER_STDS_WORKING", "POWER_STDS_IDLE", "POWER_CORRELATIONS",
    "correlation_matrix", "mean_vector", "covariance_matrix",
    "get_distribution_params",
    "working_means", "working_stds",
    "expected_power", "verify_ohm_law",
]
