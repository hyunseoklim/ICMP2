from django.db import models


class Zone(models.Model):
    """
    운영자가 meshgrid 위에서 셀 범위를 지정하여 구역 이름을 부여한다.
    cell_row_start/end, cell_col_start/end 로 직사각형 범위를 저장한다.
    """
    ZONE_TYPE_CHOICES = [
        ('work', '작업구역'),
        ('storage', '창고'),
        ('rest', '휴게구역'),
        ('utility', '설비구역'),
        ('passage', '통로'),
        ('etc', '기타'),
    ]
 
    floor = models.ForeignKey('facilities.Floor', on_delete=models.CASCADE, related_name='zones')
    zone_name = models.CharField(max_length=100)
    zone_type = models.CharField(max_length=20, choices=ZONE_TYPE_CHOICES, default='work')
    cell_row_start = models.PositiveIntegerField(default=0)
    cell_row_end = models.PositiveIntegerField(default=0)
    cell_col_start = models.PositiveIntegerField(default=0)
    cell_col_end = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, default='#378ADD', help_text='지도 표시 색상 hex')
    status = models.CharField(
        max_length=20,
        choices=[('active', '활성'), ('inactive', '비활성')],
        default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'zones'
        verbose_name = '구역'
        verbose_name_plural = '구역 목록'
        app_label = 'facilities'
 
    def __str__(self):
        return f'{self.floor} - {self.zone_name}'
    



# class Zone(models.Model):
#     class Status(models.TextChoices):
#         ACTIVE = "active", "운영 중"
#         INACTIVE = "inactive", "비활성"

#     floor = models.ForeignKey(
#         "facilities.Floor", on_delete=models.CASCADE, related_name="zones"
#     )
#     zone_name = models.CharField(max_length=200)
#     zone_type = models.CharField(max_length=50)
#     polygon_data = models.JSONField(null=True, blank=True)
#     status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

#     class Meta:
#         db_table = "zones"
#         app_label = 'facilities'
#     def __str__(self):
#         return f"{self.floor.floor_name} - {self.zone_name}"
