from django.db import models


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
