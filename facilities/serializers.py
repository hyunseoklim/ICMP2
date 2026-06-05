from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .models import (
    Facility, Building, Floor, FloorGrid,
    Zone, LocationNode, Worker, WorkerLocation,
    Geofence, Equipment, SensorLocation)

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

class EquipmentSerializer(serializers.ModelSerializer):
    # 명세 3 Z2: unique 충돌 시 한국어 메시지
    equipment_code = serializers.CharField(
        max_length=20,
        validators=[
            UniqueValidator(
                queryset=Equipment.objects.all(),
                message='이미 등록된 설비 코드입니다.',
            )
        ],
    )

    class Meta:
        model = Equipment
        fields = [
            'id',
            'floor',
            'zone',
            'equipment_code',
            'equipment_name',
            'width',
            'height',
            'center_x',
            'center_y',
            'rotation',
            'status',
            'is_placed',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        # T1-γ: is_placed=True ⇒ floor/center_x/center_y/width/height 모두 비-null 필수.
        # PATCH 시 일부 필드만 들어오면 기존 instance 값으로 보강해서 검사.
        instance = self.instance
        get = lambda f: attrs[f] if f in attrs else getattr(instance, f, None)
        is_placed = get('is_placed')
        if is_placed:
            required = ['floor', 'center_x', 'center_y', 'width', 'height']
            missing = [f for f in required if get(f) is None]
            if missing:
                raise serializers.ValidationError({
                    f: '배치 완료 상태에서는 비-null 값이 필요합니다.' for f in missing
                })
        return attrs


class FloorGridSerializer(serializers.ModelSerializer):
    """
    FloorGrid 조회/응답용 Serializer.
 
    lines 필드 포함:
        JS(map_grid.js)가 이 값을 받아 렌더링만 수행.
        lines 가 빈 배열이면 JS의 _drawGridFallback 이 동작함.
 
    cols / rows 는 읽기 전용:
        service.py가 계산하여 저장하므로 외부에서 직접 수정하지 않음.
    """
    # cols = serializers.IntegerField(read_only=True)
    # rows = serializers.IntegerField(read_only=True)
 
    class Meta:
        model  = FloorGrid
        fields = [
            'id',
            'floor',
            'cell_size',
            'created_at',
            'updated_at',
        ]
 


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = '__all__'


class GeofenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Geofence
        fields = '__all__'


class LocationNodeSerializer(serializers.ModelSerializer):
    # 명세 3 Z2: unique 충돌 시 한국어 메시지
    node_code = serializers.CharField(
        max_length=50,
        validators=[
            UniqueValidator(
                queryset=LocationNode.objects.all(),
                message='이미 등록된 노드 코드입니다.',
            )
        ],
    )

    class Meta:
        model = LocationNode
        fields = [
            'id',
            'floor',
            'zone',
            'node_name',
            'node_code',     # T1-α Z1: API 응답에 노출 (frontend 매핑용)
            'x',
            'y',
            'status',
            'is_placed',     # T1-α X3
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        # T1-α W1: is_placed=True ⇒ floor/x/y 모두 비-null 필수.
        # PATCH 시 일부 필드만 들어오면 기존 instance 값으로 보강해서 검사.
        instance = self.instance
        get = lambda f: attrs[f] if f in attrs else getattr(instance, f, None)
        is_placed = get('is_placed')
        if is_placed:
            required = ['floor', 'x', 'y']
            missing = [f for f in required if get(f) is None]
            if missing:
                raise serializers.ValidationError({
                    f: '배치 완료 상태에서는 비-null 값이 필요합니다.' for f in missing
                })
        return attrs

class WorkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Worker
        fields = '__all__'


class WorkerLocationSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.worker_name', read_only=True)

    class Meta:
        model = WorkerLocation
        fields = '__all__'



class WorkerLocationLatestSerializer(serializers.ModelSerializer):
    """
    프론트 시뮬레이션용 — 작업자별 최신 위치 1건씩 반환한다.
    """
    worker_name = serializers.CharField(source='worker.worker_name', read_only=True)
    worker_status = serializers.CharField(source='worker.safety_status', read_only=True)

    class Meta:
        model = WorkerLocation
        fields = [
            'id', 'worker_id', 'worker_name', 'worker_status',
            'cell_no', 'x', 'y', 'z', 'measured_at',
        ]

class SensorLocationSerializer(serializers.ModelSerializer):
    """
    센서 위치 조회용 Serializer.
    sensor.js가 참조하는 필드:
      id, device_id, sensor_type, x, y, device_name, status(→is_active), floor
    JS의 sensor.status 참조를 위해 monitoring API와 별도로
    is_active를 status 형태로 노출하지 않음.
    상태(normal/warning/danger)는 monitoring 앱이 담당.
    """
    class Meta:
        model = SensorLocation
        fields = [
            'id',
            'device_id',
            'floor',
            'sensor_type',
            'x',
            'y',
            'device_name',
            'is_active',
            'is_placed',     # T1-β Q1
            'created_at',
            'updated_at',
        ]

    def validate(self, attrs):
        # T1-β W1: is_placed=True ⇒ floor/x/y 모두 비-null 필수.
        instance = self.instance
        get = lambda f: attrs[f] if f in attrs else getattr(instance, f, None)
        is_placed = get('is_placed')
        if is_placed:
            required = ['floor', 'x', 'y']
            missing = [f for f in required if get(f) is None]
            if missing:
                raise serializers.ValidationError({
                    f: '배치 완료 상태에서는 비-null 값이 필요합니다.' for f in missing
                })
        return attrs
        read_only_fields = ['created_at', 'updated_at']