from django.contrib import admin
from monitoring.models import (
    Device,
    DeviceChannel,
    DeviceStatusLog,
    GasReading,
    PowerStatusReading,
    PowerReading,
    ThresholdPolicy,
    InspectionLog,
    ActionLog,
)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display  = ["device_uid", "device_name", "device_type", "status", "last_seen_at"]
    list_filter   = ["device_type", "status"]
    search_fields = ["device_uid", "device_name"]


@admin.register(DeviceChannel)
class DeviceChannelAdmin(admin.ModelAdmin):
    list_display = ["device", "channel_code", "channel_name", "is_active", "status"]
    list_filter  = ["status", "is_active"]


@admin.register(DeviceStatusLog)
class DeviceStatusLogAdmin(admin.ModelAdmin):
    list_display = ["device", "status_code", "occurred_at"]
    list_filter  = ["status_code"]


class ScenarioFilter(admin.SimpleListFilter):
    title = "시나리오 데이터"
    parameter_name = "scenario_data"

    def lookups(self, request, model_admin):
        return [
            ("all",    "시나리오 데이터만 (A-M)"),
            ("normal", "시나리오 A — 정상운영만"),
            ("real",   "실제 센서 데이터만"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "all":
            return queryset.filter(raw_payload__scenario_tag="scenario_generated")
        if self.value() == "normal":
            return queryset.filter(raw_payload__scenario="normal_operation")
        if self.value() == "real":
            return queryset.exclude(raw_payload__scenario_tag="scenario_generated")
        return queryset


@admin.register(GasReading)
class GasReadingAdmin(admin.ModelAdmin):
    list_display  = ["device", "co", "o2", "co2", "measured_at", "scenario_label"]
    list_filter   = ["device", ScenarioFilter]
    search_fields = ["device__device_uid"]

    @admin.display(description="시나리오")
    def scenario_label(self, obj):
        if isinstance(obj.raw_payload, dict):
            return obj.raw_payload.get("scenario", "-")
        return "-"


@admin.register(PowerStatusReading)
class PowerStatusReadingAdmin(admin.ModelAdmin):
    list_display = ["device", "channel", "status_value", "received_at"]


@admin.register(PowerReading)
class PowerReadingAdmin(admin.ModelAdmin):
    list_display = ["device", "channel", "current_a", "voltage_v", "power_w", "measured_at"]


@admin.register(ThresholdPolicy)
class ThresholdPolicyAdmin(admin.ModelAdmin):
    list_display = ["metric_code", "warning_min", "warning_max", "danger_min", "danger_max", "action_type", "is_active"]
    list_filter  = ["is_active", "action_type"]


@admin.register(InspectionLog)
class InspectionLogAdmin(admin.ModelAdmin):
    list_display  = ["device", "inspection_type", "inspection_date", "status", "inspector"]
    list_filter   = ["inspection_type", "status"]
    search_fields = ["device__device_uid"]


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ["inspection", "actor", "action_date"]