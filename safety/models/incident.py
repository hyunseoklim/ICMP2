from django.db import models


class Incident(models.Model):
    class Severity(models.TextChoices):
        LOW = "low", "낮음"
        MEDIUM = "medium", "보통"
        HIGH = "high", "높음"
        CRITICAL = "critical", "중대"

    class Status(models.TextChoices):
        OPEN = "open", "발생"
        INVESTIGATING = "investigating", "조사 중"
        CLOSED = "closed", "종료"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="incidents"
    )
    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents"
    )
    worker = models.ForeignKey(
        "facilities.Worker", on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents"
    )
    incident_type = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    occurred_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    class Meta:
        db_table = "incidents"
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"[{self.severity}] {self.title} ({self.status})"
