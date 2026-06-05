from rest_framework import serializers
from django.utils import timezone

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
from monitoring.constants import GAS_FIELDS
from monitoring.services import calc_danger_level, check_threshold_exceeded, calc_power_channel_level
from alerts.models import ForecastSnapshot

# ── Device ────────────────────────────────────────────────

class DeviceSerializer(serializers.ModelSerializer):

    class Meta:
        model  = Device
        fields = "__all__"

    def validate_port(self, value):
        """포트 번호 범위 검증 (1~65535)"""
        if value is not None and not (1 <= value <= 65535):
            raise serializers.ValidationError("포트 번호는 1~65535 사이여야 합니다.")
        return value

    def validate_device_uid(self, value):
        """장비 UID 중복 검증 (수정 시 자기 자신 제외)"""
        instance = self.instance
        qs = Device.objects.filter(device_uid=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("이미 등록된 장비 ID입니다.")
        return value


# ── DeviceChannel ──────────────────────────────────────────

class DeviceChannelSerializer(serializers.ModelSerializer):

    class Meta:
        model  = DeviceChannel
        fields = "__all__"


# ── DeviceStatusLog ────────────────────────────────────────

class DeviceStatusLogSerializer(serializers.ModelSerializer):

    class Meta:
        model            = DeviceStatusLog
        fields           = "__all__"
        read_only_fields = ["occurred_at"]


# ── GasReading ─────────────────────────────────────────────



class GasReadingSerializer(serializers.ModelSerializer):
    danger_level = serializers.SerializerMethodField()
    gas_levels   = serializers.SerializerMethodField()

    def get_danger_level(self, obj):          # ← 이게 빠져있었음
        return calc_danger_level(obj)

    def get_gas_levels(self, obj):
        exceeded = check_threshold_exceeded(obj)
        levels = {gas: 'normal' for gas in GAS_FIELDS}
        for item in exceeded:
            levels[item['gas']] = 'danger' if item['level'] == '위험' else 'warning'
        return levels

    class Meta:
        model            = GasReading
        fields           = "__all__"
        read_only_fields = ["received_at"]

    def validate(self, data):
        for field in GAS_FIELDS:
            value = data.get(field)
            if value is not None and value < 0:
                raise serializers.ValidationError(
                    {field: f"{field} 값은 0 이상이어야 합니다."}
                )
        return data


# ── PowerStatusReading ─────────────────────────────────────

class PowerStatusReadingSerializer(serializers.ModelSerializer):

    class Meta:
        model            = PowerStatusReading
        fields           = "__all__"
        read_only_fields = ["received_at"]


# ── PowerReading ───────────────────────────────────────────

class PowerReadingSerializer(serializers.ModelSerializer):
    channel_name        = serializers.CharField(source="channel.channel_name", read_only=True)
    channel_code        = serializers.CharField(source="channel.channel_code", read_only=True)
    channel_rated_power = serializers.IntegerField(source="channel.rated_power_w", read_only=True)
    level               = serializers.SerializerMethodField()

    def get_level(self, obj):
        return calc_power_channel_level(obj)

    class Meta:
        model            = PowerReading
        fields           = "__all__"
        read_only_fields = ["received_at"]

    def validate(self, data):
        for field in ["current_a", "voltage_v", "power_w"]:
            value = data.get(field)
            if value is not None and value < -1:
                raise serializers.ValidationError(
                    {field: f"{field} 값은 -1(통신불능) 또는 0 이상이어야 합니다."}
                )
        return data


# ── ThresholdPolicy ────────────────────────────────────────

class ThresholdPolicySerializer(serializers.ModelSerializer):

    class Meta:
        model  = ThresholdPolicy
        fields = "__all__"

    def validate(self, data):
        """임계치 범위 논리 검증"""
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


# ── InspectionLog ──────────────────────────────────────────

class InspectionLogSerializer(serializers.ModelSerializer):

    class Meta:
        model            = InspectionLog
        fields           = "__all__"
        read_only_fields = ["created_at"]

    def validate(self, data):
        """점검 상태 및 날짜 검증"""
        status               = data.get("status")
        expected_action_date = data.get("expected_action_date")
        inspection_date      = data.get("inspection_date")

        # 조치 필요 상태면 예상 조치일 필수
        if status == "action_required" and not expected_action_date:
            raise serializers.ValidationError(
                "조치 필요 상태일 때 예상 조치일은 필수입니다."
            )

        # 예상 조치일은 점검일 이후여야 함
        if inspection_date and expected_action_date:
            if expected_action_date < inspection_date:
                raise serializers.ValidationError(
                    "예상 조치일은 점검일 이후여야 합니다."
                )

        return data


# ── ActionLog ──────────────────────────────────────────────

class ActionLogSerializer(serializers.ModelSerializer):

    class Meta:
        model            = ActionLog
        fields           = "__all__"
        read_only_fields = ["created_at"]

    def validate_action_date(self, value):
        """조치 완료일은 미래일 수 없음"""
        if value > timezone.now().date():
            raise serializers.ValidationError(
                "조치 완료일은 오늘 이후일 수 없습니다."
            )
        return value


# ── ForecastSnapshot (AI 예측) ─────────────────────────────

class ForecastSnapshotSerializer(serializers.ModelSerializer):
    """STEP G — 채널별 최신 AI 예측 스냅샷 직렬화 ('AI 예측' 탭용).

    2축 등급(확신도·ETA)과 예측 곡선(forecast_mean·ci_*)을 함께 노출한다.

    Phase D M1-3 (2026-05-23) — power 채널 지원: channel_code 노출 (gas는 null).
    """

    channel_code = serializers.CharField(source="channel.channel_code", read_only=True, allow_null=True)

    class Meta:
        model  = ForecastSnapshot
        fields = [
            "sensor_type", "channel_code", "updated_at",
            "headline_severity", "headline_confidence",
            "caution_confidence", "danger_confidence",
            "caution_eta_step", "danger_eta_step",
            "path", "forecast_steps", "reason",
            "forecast_mean", "ci_lower", "ci_upper",
        ]