from django.db import models

class Geofence(models.Model):
    """
    위험구역. 원형으로만 관리한다.
    center_x, center_y 는 이미지 기준 픽셀 좌표.
    radius 는 픽셀 단위.
    curl 로 center_x/center_y/radius 를 PATCH 하면
    프론트에서 CSS transition 으로 원이 부드럽게 이동/확산한다.
    """
    SEVERITY_CHOICES = [
        ('danger', '위험'),
        ('warning', '주의'),
        ('safe', '안전'),
    ]
 
    zone = models.ForeignKey(
        'facilities.Zone', on_delete=models.SET_NULL, null=True, blank=True, related_name='geofences'
    )
    floor = models.ForeignKey('facilities.Floor', on_delete=models.CASCADE, related_name='geofences')
    name = models.CharField(max_length=100)
    center_x = models.FloatField(help_text='원 중심 x (px)')
    center_y = models.FloatField(help_text='원 중심 y (px)')
    radius = models.FloatField(help_text='반지름 (px)')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='danger')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'geofences'
        verbose_name = '위험구역'
        verbose_name_plural = '위험구역 목록'
        app_label = 'facilities'  
 
    def __str__(self):
        return f'{self.name} ({self.severity})'
 




# class Geofence(models.Model):
#     class GeofenceType(models.TextChoices):
#         CIRCLE = "circle", "원형"
#         POLYGON = "polygon", "다각형"

#     class Severity(models.TextChoices):
#         LOW = "low", "낮음"
#         MEDIUM = "medium", "보통"
#         HIGH = "high", "높음"
#         CRITICAL = "critical", "위험"

#     zone = models.ForeignKey(
#         "facilities.Zone", on_delete=models.CASCADE, related_name="geofences"
#     )
#     geofence_type = models.CharField(max_length=20, choices=GeofenceType.choices)
#     radius_or_polygon = models.JSONField()
#     severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
#     is_active = models.BooleanField(default=True)

#     class Meta:
#         db_table = "geofences"
#         app_label = 'facilities'    

#     def __str__(self):
#         return f"Geofence [{self.severity}] - {self.zone.zone_name}"
