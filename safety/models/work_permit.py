from django.db import models


class WorkPermit(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "승인 대기"
        APPROVED = "approved", "승인"
        REJECTED = "rejected", "반려"
        EXPIRED = "expired", "만료"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="work_permits"
    )
    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="work_permits"
    )
    worker = models.ForeignKey(
        "facilities.Worker", on_delete=models.CASCADE, related_name="work_permits"
    )
    approver = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_permits"
    )
    permit_type = models.CharField(max_length=50)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = "work_permits"
        ordering = ["-start_at"]

    def __str__(self):
        return f"{self.worker.worker_name} {self.permit_type} [{self.status}]"
