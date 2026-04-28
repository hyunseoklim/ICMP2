from django.db import models


class SafetyCheckItem(models.Model):
    category = models.CharField(max_length=100)
    category_order = models.PositiveIntegerField(default=0)
    item_text = models.TextField()
    item_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "safety_check_items"
        ordering = ["category_order", "item_order"]

    def __str__(self):
        return f"[{self.category}] {self.item_text[:40]}"


class SafetyCheckSession(models.Model):
    worker = models.ForeignKey(
        "facilities.Worker", on_delete=models.CASCADE, related_name="safety_sessions"
    )
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="safety_sessions"
    )
    check_date = models.DateField()
    checklist_completed = models.BooleanField(default=False)
    checklist_completed_at = models.DateTimeField(null=True, blank=True)
    vr_completed = models.BooleanField(default=False)
    vr_completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "safety_check_sessions"
        unique_together = ("worker", "check_date")
        ordering = ["-check_date"]

    @property
    def is_fully_completed(self):
        return self.checklist_completed and self.vr_completed

    def __str__(self):
        return f"{self.worker.worker_name} {self.check_date}"


class SafetyCheckItemResult(models.Model):
    session = models.ForeignKey(
        "safety.SafetyCheckSession", on_delete=models.CASCADE, related_name="item_results"
    )
    item = models.ForeignKey(
        "safety.SafetyCheckItem", on_delete=models.CASCADE, related_name="results"
    )
    is_checked = models.BooleanField(default=False)

    class Meta:
        db_table = "safety_check_item_results"
        unique_together = ("session", "item")

    def __str__(self):
        return f"{self.session} - {self.item.item_text[:30]}"


class Incident(models.Model):
    class Severity(models.TextChoices):
        LOW = "low", "낮음"
        MEDIUM = "medium", "보통"
        HIGH = "high", "높음"
        CRITICAL = "critical", "중대"

    class Status(models.TextChoices):
        OPEN = "open", "발생"
        INVESTIGATING = "investigating", "조사 중"
        CLOSED = "closed", "종료"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="incidents"
    )
    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents"
    )
    worker = models.ForeignKey(
        "facilities.Worker", on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents"
    )
    incident_type = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    occurred_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    class Meta:
        db_table = "incidents"
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"[{self.severity}] {self.title} ({self.status})"


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


class RiskAssessment(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = "low", "낮음"
        MEDIUM = "medium", "보통"
        HIGH = "high", "높음"

    class Status(models.TextChoices):
        DRAFT = "draft", "작성 중"
        ACTIVE = "active", "적용 중"
        ARCHIVED = "archived", "보관"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="risk_assessments"
    )
    zone = models.ForeignKey(
        "facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="risk_assessments"
    )
    title = models.CharField(max_length=200)
    hazard_type = models.CharField(max_length=100)
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices)
    action_plan = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        db_table = "risk_assessments"

    def __str__(self):
        return f"{self.title} [{self.risk_level}]"


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
