from django.db import models


class SensorDummy(models.Model):
    """
    curl 로 주입하는 센서 더미 데이터.
    monitoring 앱이 생기기 전까지 facilities 에서 임시로 관리한다.
    """
    SENSOR_TYPE_CHOICES = [
        ('gas', '유해가스'),
        ('power', '스마트전력'),
        ('location', '위치센서'),
    ]
    STATUS_CHOICES = [
        ('normal', '정상'),
        ('warning', '주의'),
        ('danger', '위험'),
        ('offline', '오프라인'),
    ]
 
    device_id = models.CharField(max_length=50, unique=True)
    device_name = models.CharField(max_length=100)
    sensor_type = models.CharField(max_length=20, choices=SENSOR_TYPE_CHOICES, default='gas')
    floor = models.ForeignKey('facilities.Floor', on_delete=models.SET_NULL, null=True, blank=True)
    zone = models.ForeignKey('facilities.Zone', on_delete=models.SET_NULL, null=True, blank=True)
    x = models.FloatField(default=0, help_text='이미지 기준 x (px)')
    y = models.FloatField(default=0, help_text='이미지 기준 y (px)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='normal')
    latest_value = models.JSONField(default=dict, blank=True, help_text='최근 측정값 JSON')
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'sensor_dummy'
        verbose_name = '센서 더미'
        verbose_name_plural = '센서 더미 목록'
 
    def __str__(self):
        return f'{self.device_id} ({self.sensor_type})'
 