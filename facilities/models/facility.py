from django.db import models


class Facility(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "운영 중"
        INACTIVE = "inactive", "운영 중지"

    facility_name = models.CharField(max_length=200)
    facility_code = models.CharField(max_length=50, unique=True)
    address = models.TextField(blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "facilities"
        verbose_name_plural = "facilities"

    def __str__(self):
        return f"{self.facility_name} ({self.facility_code})"
