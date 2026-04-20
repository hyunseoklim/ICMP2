from django.db import models


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
