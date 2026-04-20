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
