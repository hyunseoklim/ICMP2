from django.db import models


class Zone(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "운영 중"
        INACTIVE = "inactive", "비활성"

    floor = models.ForeignKey(
        "facilities.Floor", on_delete=models.CASCADE, related_name="zones"
    )
    zone_name = models.CharField(max_length=200)
    zone_type = models.CharField(max_length=50)
    polygon_data = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "zones"

    def __str__(self):
        return f"{self.floor.floor_name} - {self.zone_name}"
