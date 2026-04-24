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



class AlarmRule(models.Model):
    class RuleType(models.TextChoices):
        THRESHOLD = "threshold", "임계치 초과"
        MISSING = "missing", "데이터 누락"
        STATUS = "status", "장비 상태"

    class ActionType(models.TextChoices):
        NOTIFY = "notify", "알림"
        SHUTDOWN = "shutdown", "장비 차단"

    rule_name = models.CharField(max_length=200)
    rule_type = models.CharField(max_length=20, choices=RuleType.choices)
    metric_code = models.CharField(max_length=50)
    condition_operator = models.CharField(max_length=10)
    warning_value = models.FloatField(null=True, blank=True)
    danger_value = models.FloatField(null=True, blank=True)
    action_type = models.CharField(max_length=20, choices=ActionType.choices, default=ActionType.NOTIFY)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "alarm_rules"

    def __str__(self):
        return f"{self.rule_name} ({self.rule_type})"



class EventHistory(models.Model):
    alarm_event = models.ForeignKey(
        "alerts.AlarmEvent", on_delete=models.CASCADE, related_name="histories"
    )
    action_type = models.CharField(max_length=50)
    action_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_histories"
    )
    action_note = models.TextField(blank=True)
    action_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_histories"
        ordering = ["-action_at"]
        verbose_name_plural = "event histories"

    def __str__(self):
        return f"Event {self.alarm_event_id} [{self.action_type}] @ {self.action_at}"



class NotificationTemplate(models.Model):
    class ChannelType(models.TextChoices):
        EMAIL = "email", "이메일"
        SMS = "sms", "문자"
        PUSH = "push", "푸시 알림"

    template_name = models.CharField(max_length=200)
    channel_type = models.CharField(max_length=20, choices=ChannelType.choices)
    title_template = models.CharField(max_length=300)
    body_template = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "notification_templates"

    def __str__(self):
        return f"{self.template_name} ({self.channel_type})"




class Notification(models.Model):
    class SendStatus(models.TextChoices):
        PENDING = "pending", "대기"
        SENT = "sent", "발송 완료"
        FAILED = "failed", "발송 실패"

    event = models.ForeignKey(
        "alerts.AlarmEvent", on_delete=models.CASCADE, related_name="notifications"
    )
    receiver = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    channel_type = models.CharField(max_length=20)
    title = models.CharField(max_length=300)
    message = models.TextField()
    send_status = models.CharField(max_length=20, choices=SendStatus.choices, default=SendStatus.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.receiver.username} [{self.channel_type}] {self.send_status}"
