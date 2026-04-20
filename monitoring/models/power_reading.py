from django.db import models


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
