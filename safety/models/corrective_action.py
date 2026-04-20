from django.db import models


class CorrectiveAction(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "미완료"
        IN_PROGRESS = "in_progress", "진행 중"
        COMPLETED = "completed", "완료"

    incident = models.ForeignKey(
        "safety.Incident", on_delete=models.CASCADE, related_name="corrective_actions"
    )
    action_title = models.CharField(max_length=200)
    assignee = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="corrective_actions"
    )
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    class Meta:
        db_table = "corrective_actions"
        ordering = ["due_date"]

    def __str__(self):
        return f"{self.action_title} [{self.status}]"
