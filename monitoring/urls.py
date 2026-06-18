from django.urls import path, include
from rest_framework.routers import DefaultRouter

from monitoring.views import (
    # Template Views
    MonitoringDashboardView,
    GasSensorManageView,
    PowerSystemManageView,
    # API ViewSets
    DeviceViewSet,
    DeviceChannelViewSet,
    DeviceStatusLogViewSet,
    GasReadingViewSet,
    PowerStatusReadingViewSet,
    PowerReadingViewSet,
    ThresholdPolicyViewSet,
    InspectionLogViewSet,
    ActionLogViewSet,
    # API Functions
    app_config,
    story_purge,
)

# ── API Router ─────────────────────────────────────────────
router = DefaultRouter()
router.register("devices",               DeviceViewSet,              basename="device")
router.register("channels",              DeviceChannelViewSet,       basename="channel")
router.register("device-status-logs",    DeviceStatusLogViewSet,     basename="device-status-log")
router.register("gas-readings",          GasReadingViewSet,          basename="gas-reading")
router.register("power-status-readings", PowerStatusReadingViewSet,  basename="power-status-reading")
router.register("power-readings",        PowerReadingViewSet,        basename="power-reading")
router.register("threshold-policies",    ThresholdPolicyViewSet,     basename="threshold-policy")
router.register("inspections",           InspectionLogViewSet,       basename="inspection")
router.register("actions",               ActionLogViewSet,           basename="action")

# ── URL Patterns ───────────────────────────────────────────
urlpatterns = [
    # 페이지 URL
    path("",        MonitoringDashboardView.as_view(), name="monitoring_dashboard"),
    path("gas/",    GasSensorManageView.as_view(),     name="monitoring_gas"),
    path("power/",  PowerSystemManageView.as_view(),   name="monitoring_power"),

    # API URL
    path("api/", include(router.urls)),
    path("api/app-config/", app_config, name="app-config"),
    path("api/story/purge/", story_purge, name="story-purge"),
]
