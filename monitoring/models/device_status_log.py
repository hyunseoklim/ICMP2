from django.db import models


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
