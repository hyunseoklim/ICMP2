from django.contrib import admin
from facilities.models import (
    Facility,
    Building,
    Floor,
    FloorGrid,
    IndexGrid,
    Zone,
    Geofence,
    LocationNode,
    Worker,
    WorkerLocation,
    Equipment,
    SensorLocation,
)


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display  = ["facility_code", "facility_name", "status", "address", "created_at"]
    list_filter   = ["status"]
    search_fields = ["facility_code", "facility_name"]


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display  = ["facility", "building_code", "building_name", "created_at"]
    list_filter   = ["facility"]
    search_fields = ["building_code", "building_name"]


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display  = ["building", "floor_no", "floor_name", "width", "length", "plan_image"]
    list_filter   = ["building"]
    search_fields = ["floor_name"]


@admin.register(FloorGrid)
class FloorGridAdmin(admin.ModelAdmin):
    list_display = ["floor", "cell_size", "created_at"]


@admin.register(IndexGrid)
class IndexGridAdmin(admin.ModelAdmin):
    list_display = ["floor", "grid_index", "col", "row"]
    list_filter  = ["floor"]


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display  = ["floor", "zone_name", "zone_type", "status"]
    list_filter   = ["zone_type", "status"]
    search_fields = ["zone_name"]


@admin.register(Geofence)
class GeofenceAdmin(admin.ModelAdmin):
    list_display  = ["name", "floor", "geofence_type", "severity", "is_active"]
    list_filter   = ["severity", "geofence_type", "is_active"]
    search_fields = ["name"]


@admin.register(LocationNode)
class LocationNodeAdmin(admin.ModelAdmin):
    list_display  = ["node_code", "node_name", "floor", "x", "y", "z", "status"]
    list_filter   = ["status", "floor"]
    search_fields = ["node_code", "node_name"]


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display  = ["worker_no", "worker_name", "department", "current_state", "safety_status"]
    list_filter   = ["current_state", "safety_status", "department"]
    search_fields = ["worker_no", "worker_name"]


@admin.register(WorkerLocation)
class WorkerLocationAdmin(admin.ModelAdmin):
    list_display = ["worker", "floor", "x", "y", "safety_status", "measured_at"]
    list_filter  = ["safety_status", "floor"]


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display  = ["equipment_code", "equipment_name", "floor", "status", "is_placed"]
    list_filter   = ["status", "is_placed", "floor"]
    search_fields = ["equipment_code", "equipment_name"]


@admin.register(SensorLocation)
class SensorLocationAdmin(admin.ModelAdmin):
    list_display  = ["device_id", "device_name", "sensor_type", "floor", "x", "y", "is_active"]
    list_filter   = ["sensor_type", "is_active", "floor"]
    search_fields = ["device_name"]