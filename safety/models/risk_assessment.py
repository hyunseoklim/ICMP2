from django.db import models


class RiskAssessment(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = "low", "낮음"
        MEDIUM = "medium", "보통"
        HIGH = "high", "높음"

    class Status(models.TextChoices):
        DRAFT = "draft", "작성 중"
        ACTIVE = "active", "적용 중"
        ARCHIVED = "archived", "보관"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="risk_assessments"
    )
    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="risk_assessments"
    )
    title = models.CharField(max_length=200)
    hazard_type = models.CharField(max_length=100)
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices)
    action_plan = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        db_table = "risk_assessments"

    def __str__(self):
        return f"{self.title} [{self.risk_level}]"
