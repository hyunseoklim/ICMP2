from django.db import models
from django.utils import timezone

from monitoring.models import ThresholdPolicy


class RiskCriteria(models.Model):
    class ColorType(models.TextChoices):
        GREEN  = 'green',  '녹색'
        YELLOW = 'yellow', '황색'
        ORANGE = 'orange', '주황'
        RED    = 'red',    '적색'
        GRAY   = 'gray',   '회색'

    stage_code     = models.CharField(max_length=50, unique=True)
    stage_name     = models.CharField(max_length=100)
    color_type     = models.CharField(max_length=20, choices=ColorType.choices, default=ColorType.GRAY)
    alert_emphasis = models.CharField(max_length=100, blank=True, default='')
    priority       = models.PositiveIntegerField(default=1)
    is_active      = models.BooleanField(default=True)
    description    = models.TextField(blank=True, default='')
    updated_at     = models.DateTimeField(auto_now=True)
    updated_by     = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table = 'risk_criteria'
        ordering = ['priority']

    def __str__(self):
        return f"{self.stage_name} ({self.stage_code})"


class AlarmRule(models.Model):
    class RuleType(models.TextChoices):
        THRESHOLD = "threshold", "임계치 초과"
        MISSING = "missing", "데이터 누락"
        OFFLINE = "offline", "장비 오프라인"
        POWER = "power", "전력 이상"
        AI = "ai", "AI 이상 탐지"
        FORECAST = "forecast", "AI 예측 경보"

    class ActionType(models.TextChoices):
        NOTIFY = "notify", "알림"
        SHUTDOWN = "shutdown", "장비 차단"

    rule_name = models.CharField(max_length=200)

    rule_type = models.CharField(max_length=20, choices=RuleType.choices)

    action_type = models.CharField(
        max_length=20,
        choices=ActionType.choices,
        default=ActionType.NOTIFY,
    )

    is_active = models.BooleanField(default=True)

    # THRESHOLD 규칙일 때 사용. metric_code는 ThresholdPolicy.metric_code가 source of truth
    threshold_policy = models.ForeignKey(
        ThresholdPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alarm_rules",
    )

    # MISSING / OFFLINE 규칙일 때 기준 시간(초)
    # TODO: OFFLINE도 이 필드를 같이 쓸지,
    #       아니면 monitoring의 device_status / last_seen 기준으로 따로 판단할지 협의 필요
    missing_timeout_seconds = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table = "alarm_rules"
        ordering = ["id"]

    def __str__(self):
        return f"{self.rule_name} ({self.rule_type})"


class AlarmEvent(models.Model):
    class Severity(models.TextChoices):
        NORMAL             = "normal",             "정상"
        WARNING            = "warning",            "주의"
        DANGER             = "danger",             "위험"
        ANOMALY            = "anomaly",            "통계/AI 이상 탐지"
        PREDICTIVE_WARNING = "predictive_warning", "AI 조기 예측 경보"

    class EventType(models.TextChoices):
        GAS = "gas", "유해가스"
        POWER = "power", "전력"
        LOCATION = "location", "위치"
        DEVICE = "device", "장비 상태"

    class EventStatus(models.TextChoices):
        OPEN = "open", "조치 필요"
        ACKNOWLEDGED = "acknowledged", "조치 중"
        CLOSED = "closed", "조치 완료"

    rule = models.ForeignKey(
        "alerts.AlarmRule",
        on_delete=models.CASCADE,
        related_name="events",
    )

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.CASCADE,
        related_name="alarm_events",
    )

    device = models.ForeignKey(
        "monitoring.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarm_events",
    )

    channel = models.ForeignKey(
        "monitoring.DeviceChannel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarm_events",
    )

    worker = models.ForeignKey(
        "facilities.Worker",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarm_events",
    )

    severity = models.CharField(max_length=20, choices=Severity.choices, db_index=True)

    event_type = models.CharField(max_length=20, choices=EventType.choices)

    title = models.CharField(max_length=200)

    message = models.TextField(blank=True)

    event_status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.OPEN,
        db_index=True,
    )

    occurred_at  = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, help_text="마지막 감지 시각 (이상 지속 시 갱신)")
    current_value = models.FloatField(null=True, blank=True, help_text="마지막 감지 시 측정값 (대표값)")

    acknowledged_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_events",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    closed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "alarm_events"
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"[{self.severity}] {self.title} ({self.event_status})"


class EventHistory(models.Model):
    class ActionType(models.TextChoices):
        ACKNOWLEDGE = "acknowledge", "확인"
        CLOSE = "close", "종료"
        REOPEN = "reopen", "재오픈"

    alarm_event = models.ForeignKey(
        "alerts.AlarmEvent",
        on_delete=models.CASCADE,
        related_name="histories",
    )

    action_type = models.CharField(max_length=20, choices=ActionType.choices)

    action_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_histories",
    )

    action_note = models.TextField(blank=True)

    action_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_histories"
        ordering = ["-action_at"]
        verbose_name_plural = "event histories"

    def __str__(self):
        return f"Event {self.alarm_event_id} [{self.action_type}] @ {self.action_at}"


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
    send_status = models.CharField(
        max_length=20, choices=SendStatus.choices, default=SendStatus.PENDING
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.receiver.username} [{self.channel_type}] {self.send_status}"


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


class ForecastSnapshot(models.Model):
    """STEP G — 채널별 최신 AI 예측 결과 (채널당 1행 upsert).

    'AI 예측' 탭/위젯이 조회하는 최신 예측 스냅샷. unique_together로
    채널당 1행을 갱신하므로 행 수가 고정된다 — 디스크 무증가.
    곡선 필드(forecast_mean·ci_*)는 v2(곡선 차트)용.

    Phase D M1-1 (2026-05-23) — power 채널 지원 확장:
        - channel FK 추가 (gas는 null=True로 호환성 유지)
        - sensor_type max_length 10 → 20 (power 합성키 대비)
        - unique_together (device, channel, sensor_type) — channel=NULL 그룹은
          기존 gas 동작과 동일 (PostgreSQL NULL은 unique 비교에서 다르게 처리됨)
    """

    device = models.ForeignKey(
        "monitoring.Device", on_delete=models.CASCADE, related_name="forecast_snapshots"
    )
    channel = models.ForeignKey(
        "monitoring.DeviceChannel",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="forecast_snapshots",
        help_text="전력 채널 (gas는 NULL)",
    )
    sensor_type = models.CharField(max_length=20, help_text="채널 종류 (gas: co/h2s/..., power: voltage/current/power)")
    updated_at = models.DateTimeField(auto_now=True, help_text="갱신 시각 (예측 신선도 감시용)")

    # 2축 등급 (ForecastPolicyResult — confidence는 enum name 저장)
    headline_severity = models.CharField(
        max_length=10, null=True, blank=True, help_text="danger / caution / None"
    )
    headline_confidence = models.CharField(
        max_length=20,
        help_text="NORMAL/TENTATIVE/CONFIRMED_WARNING/CONFIRMED_STRONG/UNKNOWN",
    )
    caution_confidence = models.CharField(max_length=20)
    danger_confidence = models.CharField(max_length=20)
    caution_eta_step = models.IntegerField(null=True, blank=True, help_text="주의 임계 도달 예측 스텝")
    danger_eta_step = models.IntegerField(null=True, blank=True)
    path = models.CharField(max_length=10, help_text="normal / degraded / unknown")
    forecast_steps = models.IntegerField(default=0, help_text="예측 수평 H")
    reason = models.TextField(blank=True)

    # 곡선 (v2 — ARIMAResult 노출 시 채움)
    forecast_mean = models.JSONField(null=True, blank=True)
    ci_lower = models.JSONField(null=True, blank=True)
    ci_upper = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "forecast_snapshots"
        unique_together = [("device", "channel", "sensor_type")]
        ordering = ["device", "channel", "sensor_type"]

    def __str__(self):
        ch = f"/{self.channel.channel_code}" if self.channel_id else ""
        return f"{self.device.device_uid}{ch} {self.sensor_type} → {self.headline_confidence}"
