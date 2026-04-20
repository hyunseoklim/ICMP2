from django.db import models


class WorkerLocation(models.Model):
    worker = models.ForeignKey(
        "facilities.Worker", on_delete=models.CASCADE, related_name="locations"
    )
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="worker_locations"
    )
    building = models.ForeignKey(
        "facilities.Building", on_delete=models.SET_NULL, null=True, blank=True, related_name="worker_locations"
    )
    floor = models.ForeignKey(
        "facilities.Floor", on_delete=models.SET_NULL, null=True, blank=True, related_name="worker_locations"
    )
    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="worker_locations"
    )
    x = models.FloatField(null=True, blank=True)
    y = models.FloatField(null=True, blank=True)
    z = models.FloatField(null=True, blank=True)
    measured_at = models.DateTimeField()

    class Meta:
        db_table = "worker_locations"
        ordering = ["-measured_at"]

    def __str__(self):
        return f"{self.worker.worker_name} @ {self.measured_at}"
