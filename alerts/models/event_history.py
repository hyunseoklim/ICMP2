from django.db import models


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
