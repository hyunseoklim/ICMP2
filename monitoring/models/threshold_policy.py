from django.db import models


class ThresholdPolicy(models.Model):
    class ActionType(models.TextChoices):
        ALERT = "alert", "알림"
        SHUTDOWN = "shutdown", "장비 차단"

    metric_code = models.CharField(max_length=50, unique=True)
    normal_min = models.FloatField(null=True, blank=True)
    normal_max = models.FloatField(null=True, blank=True)
    warning_min = models.FloatField(null=True, blank=True)
    warning_max = models.FloatField(null=True, blank=True)
    danger_min = models.FloatField(null=True, blank=True)
    danger_max = models.FloatField(null=True, blank=True)
    action_type = models.CharField(max_length=20, choices=ActionType.choices, default=ActionType.ALERT)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "threshold_policies"

    def __str__(self):
        return f"{self.metric_code} [{self.action_type}]"
