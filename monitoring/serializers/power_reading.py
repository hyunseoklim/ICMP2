from rest_framework import serializers
from monitoring.models import (
    PowerStatusReading,
    CurrentReading,
    VoltageReading,
    PowerReading,
)


class PowerStatusReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PowerStatusReading
        fields = "__all__"
        read_only_fields = ["received_at"]


class CurrentReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CurrentReading
        fields = "__all__"
        read_only_fields = ["received_at"]

    def validate_value(self, value):
        if value < -1:
            raise serializers.ValidationError("값은 -1(통신불능) 또는 0 이상이어야 합니다.")
        return value


class VoltageReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VoltageReading
        fields = "__all__"
        read_only_fields = ["received_at"]

    def validate_value(self, value):
        if value < -1:
            raise serializers.ValidationError("값은 -1(통신불능) 또는 0 이상이어야 합니다.")
        return value


class PowerReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PowerReading
        fields = "__all__"
        read_only_fields = ["received_at"]

    def validate_value(self, value):
        if value < -1:
            raise serializers.ValidationError("값은 -1(통신불능) 또는 0 이상이어야 합니다.")
        return value