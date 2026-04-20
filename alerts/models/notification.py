from django.db import models


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
