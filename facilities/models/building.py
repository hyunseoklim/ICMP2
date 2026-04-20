from django.db import models


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
