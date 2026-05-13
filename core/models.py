from django.db import models


class CommonCode(models.Model):
    group_code = models.CharField(max_length=50)
    code = models.CharField(max_length=50)
    code_name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "common_codes"
        unique_together = ("group_code", "code")
        ordering = ["group_code", "sort_order"]

    def __str__(self):
        return f"[{self.group_code}] {self.code} - {self.code_name}"


class SystemLog(models.Model):
    log_type = models.CharField(max_length=50)
    source = models.CharField(max_length=100)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "system_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.log_type} | {self.source} @ {self.created_at}"


class ChangeLog(models.Model):
    actor_id = models.BigIntegerField(null=True, blank=True)   # T1-δ F2: BigInt
    target_type = models.CharField(max_length=100)
    target_id = models.BigIntegerField()                       # T1-δ F2: BigAutoField PK 호환
    action_type = models.CharField(max_length=50)
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "change_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action_type} on {self.target_type}({self.target_id}) by actor {self.actor_id}"
