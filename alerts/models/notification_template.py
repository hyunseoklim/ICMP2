from django.db import models


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
