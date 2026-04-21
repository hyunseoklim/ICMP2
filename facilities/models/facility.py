from django.db import models


class Facility(models.Model):
    facility_name = models.CharField(max_length=100)
    facility_code = models.CharField(max_length=50, unique=True)
    address = models.CharField(max_length=255, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('active', '운영중'), ('inactive', '비운영'), ('maintenance', '점검중')],
        default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'facilities'
        verbose_name = '사업장'
        verbose_name_plural = '사업장 목록'
        app_label = 'facilities'
 
    def __str__(self):
        return self.facility_name
 
# class Facility(models.Model):
#     class Status(models.TextChoices):
#         ACTIVE = "active", "운영 중"
#         INACTIVE = "inactive", "운영 중지"

#     facility_name = models.CharField(max_length=200)
#     facility_code = models.CharField(max_length=50, unique=True)
#     address = models.TextField(blank=True)
#     lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
#     lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
#     status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

#     class Meta:
#         db_table = "facilities"
#         verbose_name_plural = "facilities"
#         app_label = 'facilities'

#     def __str__(self):
#         return f"{self.facility_name} ({self.facility_code})"
