from rest_framework import serializers
from .models import (
    Facility, Building, Floor, FloorGrid,
    Zone, LocationNode, Worker, WorkerLocation,
    Geofence, SensorDummy,
)


class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = '__all__'


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = '__all__'


class FloorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Floor
        fields = '__all__'


class FloorGridSerializer(serializers.ModelSerializer):
    class Meta:
        model = FloorGrid
        fields = '__all__'


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = '__all__'


class LocationNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationNode
        fields = '__all__'


class WorkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Worker
        fields = '__all__'


class WorkerLocationSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.worker_name', read_only=True)

    class Meta:
        model = WorkerLocation
        fields = '__all__'


class GeofenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Geofence
        fields = '__all__'


class SensorDummySerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorDummy
        fields = '__all__'


class WorkerLocationLatestSerializer(serializers.ModelSerializer):
    """
    프론트 시뮬레이션용 — 작업자별 최신 위치 1건씩 반환한다.
    """
    worker_name = serializers.CharField(source='worker.worker_name', read_only=True)
    worker_status = serializers.CharField(source='worker.status', read_only=True)

    class Meta:
        model = WorkerLocation
        fields = [
            'id', 'worker_id', 'worker_name', 'worker_status',
            'cell_no', 'x', 'y', 'z', 'measured_at',
        ]