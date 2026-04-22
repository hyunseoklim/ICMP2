from rest_framework import serializers
from monitoring.models import GasReading

GAS_FIELDS = ["co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"]


class GasReadingSerializer(serializers.ModelSerializer):

    class Meta:
        model  = GasReading
        fields = "__all__"
        read_only_fields = ["received_at"]

    def validate(self, data):
        # 음수 체크 (O2는 0 이상, 나머지는 0 이상)
        for field in GAS_FIELDS:
            value = data.get(field)
            if value is not None and value < 0:
                raise serializers.ValidationError(
                    {field: f"{field} 값은 0 이상이어야 합니다."}
                )
        return data