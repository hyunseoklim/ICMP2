from rest_framework import serializers
from monitoring.models import Device, DeviceChannel, DeviceStatusLog


class DeviceSerializer(serializers.ModelSerializer):

    class Meta:
        model  = Device
        fields = "__all__"

    def validate_port(self, value):
        if value is not None and not (1 <= value <= 65535):
            raise serializers.ValidationError("포트 번호는 1~65535 사이여야 합니다.")
        return value

    def validate_device_uid(self, value):
        instance = self.instance
        qs = Device.objects.filter(device_uid=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("이미 등록된 장비 ID입니다.")
        return value


class DeviceChannelSerializer(serializers.ModelSerializer):

    class Meta:
        model  = DeviceChannel
        fields = "__all__"


class DeviceStatusLogSerializer(serializers.ModelSerializer):

    class Meta:
        model  = DeviceStatusLog
        fields = "__all__"
        read_only_fields = ["occurred_at"]