from rest_framework import serializers
from monitoring.models import InspectionLog, ActionLog
from django.utils import timezone


class InspectionLogSerializer(serializers.ModelSerializer):

    class Meta:
        model  = InspectionLog
        fields = "__all__"
        read_only_fields = ["created_at"]

    def validate(self, data):
        # 조치 필요일 때 예상 조치일 필수
        status               = data.get("status")
        expected_action_date = data.get("expected_action_date")

        if status == "action_required" and not expected_action_date:
            raise serializers.ValidationError(
                "조치 필요 상태일 때 예상 조치일은 필수입니다."
            )

        # 예상 조치일이 점검일보다 이전이면 안 됨
        inspection_date = data.get("inspection_date")
        if inspection_date and expected_action_date:
            if expected_action_date < inspection_date:
                raise serializers.ValidationError(
                    "예상 조치일은 점검일 이후여야 합니다."
                )

        return data


class ActionLogSerializer(serializers.ModelSerializer):

    class Meta:
        model  = ActionLog
        fields = "__all__"
        read_only_fields = ["created_at"]

    def validate_action_date(self, value):
        if value > timezone.now().date():
            raise serializers.ValidationError("조치 완료일은 오늘 이후일 수 없습니다.")
        return value