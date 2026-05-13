from django.db import models
from django.conf import settings


class DataRetentionPolicy(models.Model):

    DEVICE_TYPE = [
        ('gas',   '유해가스 센서'),
        ('power', '스마트 전력 시스템'),
        ('node',  '위치 노드'),
    ]

    DATA_CATEGORY = [
        ('raw',       '원천 로그'),
        ('event',     '이벤트 이력'),
        ('aggregate', '집계 이력'),
        ('location',  '위치 이력'),
    ]

    DELETE_SCHEDULE = [
        ('daily',        '매일'),
        ('monthly_1',    '매월 1일'),
        ('monthly_15',   '매월 15일'),
        ('monthly_last', '매월 말일'),
        ('quarterly',    '분기말'),
    ]

    device_type     = models.CharField(max_length=20, choices=DEVICE_TYPE)
    data_category   = models.CharField(max_length=20, choices=DATA_CATEGORY)
    origin_days     = models.PositiveIntegerField(help_text="원천 데이터 보관 기간(일)")
    history_days    = models.PositiveIntegerField(help_text="이력 데이터 보관 기간(일)")
    delete_schedule = models.CharField(max_length=20, choices=DELETE_SCHEDULE)
    is_active       = models.BooleanField(default=True)
    memo            = models.TextField(blank=True)
    manager         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='retention_policies',
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'data_retention_policies'
        ordering            = ['device_type', 'data_category']
        verbose_name        = '데이터 보관 주기'
        verbose_name_plural = '데이터 보관 주기 목록'

    def __str__(self):
        return f"{self.get_device_type_display()} / {self.get_data_category_display()}"

    @property
    def manager_name(self):
        if not self.manager:
            return '-'
        u = self.manager
        return getattr(u, 'name', None) or u.get_full_name() or u.username
