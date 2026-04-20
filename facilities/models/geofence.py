from django.db import models


class Geofence(models.Model):
    class GeofenceType(models.TextChoices):
        CIRCLE = "circle", "원형"
        POLYGON = "polygon", "다각형"

    class Severity(models.TextChoices):
        LOW = "low", "낮음"
        MEDIUM = "medium", "보통"
        HIGH = "high", "높음"
        CRITICAL = "critical", "위험"

    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.CASCADE, related_name="geofences"
    )
    geofence_type = models.CharField(max_length=20, choices=GeofenceType.choices)
    radius_or_polygon = models.JSONField()
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "geofences"

    def __str__(self):
        return f"Geofence [{self.severity}] - {self.zone.zone_name}"
