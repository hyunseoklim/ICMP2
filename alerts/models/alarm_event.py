from django.db import models


class AlarmEvent(models.Model):
    class Severity(models.TextChoices):
        LOW = "low", "낮음"
        MEDIUM = "medium", "보통"
        HIGH = "high", "높음"
        CRITICAL = "critical", "위험"

    class EventType(models.TextChoices):
        GAS = "gas", "유해가스"
        POWER = "power", "전력"
        LOCATION = "location", "위치"
        DEVICE = "device", "장비 상태"

    class EventStatus(models.TextChoices):
        OPEN = "open", "발생"
        ACKNOWLEDGED = "acknowledged", "확인"
        CLOSED = "closed", "종료"

    rule = models.ForeignKey(
        "alerts.AlarmRule", on_delete=models.CASCADE, related_name="events"
    )
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="alarm_events"
    )
    device = models.ForeignKey(
        "monitoring.Device", on_delete=models.SET_NULL, null=True, blank=True, related_name="alarm_events"
    )
    channel = models.ForeignKey(
        "monitoring.DeviceChannel", on_delete=models.SET_NULL, null=True, blank=True, related_name="alarm_events"
    )
    worker = models.ForeignKey(
        "facilities.Worker", on_delete=models.SET_NULL, null=True, blank=True, related_name="alarm_events"
    )
    severity = models.CharField(max_length=20, choices=Severity.choices)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    event_status = models.CharField(max_length=20, choices=EventStatus.choices, default=EventStatus.OPEN)
    occurred_at = models.DateTimeField()
    acknowledged_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="acknowledged_events"
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "alarm_events"
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"[{self.severity}] {self.title} ({self.event_status})"
