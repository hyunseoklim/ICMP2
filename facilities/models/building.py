from django.db import models


class Building(models.Model):
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="buildings"
    )
    building_name = models.CharField(max_length=200)
    building_code = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "buildings"
        verbose_name = '건물'
        verbose_name_plural = '건물 목록'
        unique_together = ("facility", "building_code")
        app_label = 'facilities'

    def __str__(self):
        return f"{self.facility.facility_name} - {self.building_name}"
