from django.db import models


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
