from django.db import models


class DeviceChannel(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "활성"
        INACTIVE = "inactive", "비활성"

    device = models.ForeignKey(
        "monitoring.Device", on_delete=models.CASCADE, related_name="channels"
    )
    channel_no = models.PositiveIntegerField()
    channel_code = models.CharField(max_length=50)
    channel_name = models.CharField(max_length=100)
    channel_type = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "device_channels"
        unique_together = ("device", "channel_no")

    def __str__(self):
        return f"{self.device.device_name} CH{self.channel_no} {self.channel_name}"



class DeviceStatusLog(models.Model):
    device = models.ForeignKey(
        "monitoring.Device", on_delete=models.CASCADE, related_name="status_logs"
    )
    status_code = models.CharField(max_length=50)
    status_message = models.TextField(blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        db_table = "device_status_logs"
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.device.device_uid} [{self.status_code}] @ {self.occurred_at}"




class Device(models.Model):
    class DeviceType(models.TextChoices):
        GAS = "gas", "유해가스 센서"
        POWER = "power", "스마트 전력계"

    class Status(models.TextChoices):
        ACTIVE = "active", "정상"
        INACTIVE = "inactive", "비활성"
        FAULT = "fault", "장애"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="devices"
    )
    building = models.ForeignKey(
        "facilities.Building", on_delete=models.SET_NULL, null=True, blank=True, related_name="devices"
    )
    floor = models.ForeignKey(
        "facilities.Floor", on_delete=models.SET_NULL, null=True, blank=True, related_name="devices"
    )
    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="devices"
    )
    device_type = models.CharField(max_length=20, choices=DeviceType.choices)
    device_uid = models.CharField(max_length=100, unique=True)
    device_name = models.CharField(max_length=200)
    software_version = models.CharField(max_length=50, blank=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    installed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "devices"

    def __str__(self):
        return f"{self.device_name} ({self.device_uid})"




class GasReading(models.Model):
    device = models.ForeignKey(
        "monitoring.Device", on_delete=models.CASCADE, related_name="gas_readings"
    )
    co = models.FloatField(null=True, blank=True)
    h2s = models.FloatField(null=True, blank=True)
    co2 = models.FloatField(null=True, blank=True)
    o2 = models.FloatField(null=True, blank=True)
    no2 = models.FloatField(null=True, blank=True)
    so2 = models.FloatField(null=True, blank=True)
    o3 = models.FloatField(null=True, blank=True)
    nh3 = models.FloatField(null=True, blank=True)
    voc = models.FloatField(null=True, blank=True)
    measured_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gas_readings"
        ordering = ["-measured_at"]

    def __str__(self):
        return f"{self.device.device_uid} @ {self.measured_at}"




class PowerReading(models.Model):
    device = models.ForeignKey(
        "monitoring.Device", on_delete=models.CASCADE, related_name="power_readings"
    )
    channel = models.ForeignKey(
        "monitoring.DeviceChannel", on_delete=models.SET_NULL, null=True, blank=True, related_name="power_readings"
    )
    current_value = models.FloatField(null=True, blank=True)
    voltage_value = models.FloatField(null=True, blank=True)
    power_value = models.FloatField(null=True, blank=True)
    power_status = models.CharField(max_length=50, blank=True)
    measured_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "power_readings"
        ordering = ["-measured_at"]

    def __str__(self):
        return f"{self.device.device_uid} {self.power_value}W @ {self.measured_at}"



class ThresholdPolicy(models.Model):
    class ActionType(models.TextChoices):
        ALERT = "alert", "알림"
        SHUTDOWN = "shutdown", "장비 차단"

    metric_code = models.CharField(max_length=50, unique=True)
    normal_min = models.FloatField(null=True, blank=True)
    normal_max = models.FloatField(null=True, blank=True)
    warning_min = models.FloatField(null=True, blank=True)
    warning_max = models.FloatField(null=True, blank=True)
    danger_min = models.FloatField(null=True, blank=True)
    danger_max = models.FloatField(null=True, blank=True)
    action_type = models.CharField(max_length=20, choices=ActionType.choices, default=ActionType.ALERT)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "threshold_policies"

    def __str__(self):
        return f"{self.metric_code} [{self.action_type}]"
