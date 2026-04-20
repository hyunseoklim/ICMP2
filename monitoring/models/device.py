from django.db import models


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
