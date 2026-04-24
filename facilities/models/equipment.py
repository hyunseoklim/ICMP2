from django.db import models


class Equipment(models.Model):
    """
    공장 내 물리적 설비
    ex) 냉각 설비 2호, 컴프레셔 B-02
    스마트 전력 시스템의 '연결 설비' 드롭다운에서 사용
    """

    class Status(models.TextChoices):
        ACTIVE   = "active",   "운영 중"
        INACTIVE = "inactive", "운영 중지"

    facility     = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.CASCADE,
        related_name="equipments"
    )
    name         = models.CharField(max_length=200, help_text="설비명 ex) 냉각 설비 2호")
    code         = models.CharField(max_length=50, unique=True, help_text="설비 코드 ex) B-02")
    equipment_type = models.CharField(max_length=100, blank=True, help_text="설비 종류 ex) 냉각기, 컴프레셔")
    status       = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    note         = models.TextField(blank=True, help_text="비고")

    class Meta:
        db_table            = "equipments"
        verbose_name        = "설비"
        verbose_name_plural = "설비 목록"

    def __str__(self):
        return f"{self.name} ({self.code})"