from django.db import models


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
