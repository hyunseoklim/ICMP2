from django.db import models


class Worker(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "재직 중"
        INACTIVE = "inactive", "퇴직"

    user = models.OneToOneField(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="worker"
    )
    worker_no = models.CharField(max_length=50, unique=True)
    worker_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "workers"

    def __str__(self):
        return f"{self.worker_name} ({self.worker_no})"
