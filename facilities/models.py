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


class Building(models.Model):
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="buildings"
    )
    building_name = models.CharField(max_length=200)
    building_code = models.CharField(max_length=50)

    class Meta:
        db_table = "buildings"
        unique_together = ("facility", "building_code")

    def __str__(self):
        return f"{self.facility.facility_name} - {self.building_name}"


class Floor(models.Model):
    building = models.ForeignKey(
        "facilities.Building", on_delete=models.CASCADE, related_name="floors"
    )
    floor_name = models.CharField(max_length=100)
    floor_no = models.IntegerField()

    class Meta:
        db_table = "floors"
        unique_together = ("building", "floor_no")
        ordering = ["floor_no"]

    def __str__(self):
        return f"{self.building.building_name} {self.floor_name}"


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


class LocationNode(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "활성"
        INACTIVE = "inactive", "비활성"

    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.CASCADE, related_name="location_nodes"
    )
    node_name = models.CharField(max_length=200)
    node_code = models.CharField(max_length=50, unique=True)
    x = models.FloatField()
    y = models.FloatField()
    z = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "location_nodes"

    def __str__(self):
        return f"{self.node_name} ({self.node_code})"


class Worker(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "재직 중"
        INACTIVE = "inactive", "퇴직"

    user = models.OneToOneField(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="worker"
    )
    worker_no = models.CharField(max_length=50, unique=True)
    worker_name = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "workers"

    def __str__(self):
        return f"{self.worker_name} ({self.worker_no})"


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
