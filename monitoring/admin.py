from django.contrib import admin
from monitoring.models import (
    Device,
    DeviceChannel,
    DeviceStatusLog,
    GasReading,
    PowerStatusReading,
    CurrentReading,
    VoltageReading,
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
    list_display = ["device", "channel_code", "status"]
    list_filter  = ["status"]


@admin.register(DeviceStatusLog)
class DeviceStatusLogAdmin(admin.ModelAdmin):
    list_display = ["device", "status_code", "occurred_at"]
    list_filter  = ["status_code"]


@admin.register(GasReading)
class GasReadingAdmin(admin.ModelAdmin):
    list_display  = ["device", "co", "o2", "co2", "measured_at"]
    list_filter   = ["device"]
    search_fields = ["device__device_uid"]


@admin.register(PowerReading)
class PowerReadingAdmin(admin.ModelAdmin):
    list_display = ["device", "channel", "value", "measured_at"]


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