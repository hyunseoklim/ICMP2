from rest_framework import serializers
from monitoring.models import ThresholdPolicy


class ThresholdPolicySerializer(serializers.ModelSerializer):

    class Meta:
        model  = ThresholdPolicy
        fields = "__all__"

    def validate(self, data):
        warning_min = data.get("warning_min")
        warning_max = data.get("warning_max")
        danger_min  = data.get("danger_min")
        danger_max  = data.get("danger_max")

        if warning_min is not None and warning_max is not None:
            if warning_min >= warning_max:
                raise serializers.ValidationError(
                    "warning_min은 warning_max보다 작아야 합니다."
                )

        if danger_min is not None and danger_max is not None:
            if danger_min >= danger_max:
                raise serializers.ValidationError(
                    "danger_min은 danger_max보다 작아야 합니다."
                )

        if warning_max is not None and danger_min is not None:
            if warning_max > danger_min:
                raise serializers.ValidationError(
                    "주의 범위(warning_max)는 위험 범위(danger_min)보다 작거나 같아야 합니다."
                )

        return data