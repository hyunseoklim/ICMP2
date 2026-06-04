import uuid

from django.db import models

# ── Device ────────────────────────────────────────────────
class Device(models.Model):

    class DeviceType(models.TextChoices):
        GAS   = "gas",   "유해가스 센서"
        POWER = "power", "스마트 파워 디바이스"
        LOC   = "loc",   "위치 노드"

    class Status(models.TextChoices):
        ACTIVE = "active", "정상"
        INACTIVE = "inactive", "비활성"
        FAULT    = "fault",    "장애"

    # 위치
    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="devices")
    building = models.ForeignKey("facilities.Building", on_delete=models.SET_NULL, null=True, blank=True, related_name="devices")
    floor = models.ForeignKey("facilities.Floor", on_delete=models.SET_NULL, null=True, blank=True, related_name="devices")
    zone = models.ForeignKey("facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="devices")
    equipment = models.ForeignKey("facilities.Equipment", on_delete=models.SET_NULL, null=True, blank=True, related_name="devices", help_text="연결 설비")

    # 관리 담당
    department = models.ForeignKey("accounts.Department", on_delete=models.SET_NULL, null=True, blank=True, related_name="devices")
    manager = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_devices")

    # 장비 기본 정보
    device_type = models.CharField(max_length=20, choices=DeviceType.choices)
    device_code = models.CharField(max_length=50, help_text="장비 코드 ex) 001")
    device_uid = models.CharField(max_length=100, unique=True, help_text="MAC address")
    device_name = models.CharField(max_length=200)
    software_version = models.CharField(max_length=50, blank=True)
    model_name = models.CharField(max_length=100, blank=True)

    # 통신 정보
    ip_address = models.GenericIPAddressField(null=True, help_text="장비 통신 IP")
    port       = models.PositiveIntegerField(help_text="통신 PORT")

    # 운영 정보
    is_active    = models.BooleanField(default=True, help_text="사용 여부")
    installed_at = models.DateTimeField(null=True, blank=True, help_text="설치일")
    status       = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    last_seen_at = models.DateTimeField(null=True, blank=True, help_text="마지막 연결일시")
    note         = models.TextField(blank=True, help_text="비고")

    class Meta:
        db_table            = "devices"
        ordering            = ["-last_seen_at"]
        verbose_name        = "장비"
        verbose_name_plural = "장비 목록"

    def __str__(self):
        return f"{self.device_name} ({self.device_uid})"


# ── DeviceChannel ──────────────────────────────────────────

class DeviceChannel(models.Model):

    class ChannelCode(models.TextChoices):
        SLAVE01 = "slave01", "1CH"
        SLAVE02 = "slave02", "2CH"
        SLAVE11 = "slave11", "3CH"
        SLAVE12 = "slave12", "4CH"
        SLAVE21 = "slave21", "5CH"
        SLAVE22 = "slave22", "6CH"
        SLAVE31 = "slave31", "7CH"
        SLAVE32 = "slave32", "8CH"
        SLAVE41 = "slave41", "9CH"
        SLAVE42 = "slave42", "10CH"
        SLAVE51 = "slave51", "11CH"
        SLAVE52 = "slave52", "12CH"
        SLAVE61 = "slave61", "13CH"
        SLAVE62 = "slave62", "14CH"
        SLAVE71 = "slave71", "15CH"
        SLAVE72 = "slave72", "16CH"

    class Status(models.TextChoices):
        ACTIVE   = "active",   "활성"
        INACTIVE = "inactive", "비활성"

    device       = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="channels")
    channel_code = models.CharField(max_length=10, choices=ChannelCode.choices, help_text="slave01~slave72")
    channel_name = models.CharField(max_length=100, blank=True, help_text="관리자 등록 채널명 ex) 압연기 전원")
    x_position   = models.FloatField(null=True, blank=True, help_text="공장 지도 X좌표")
    y_position   = models.FloatField(null=True, blank=True, help_text="공장 지도 Y좌표")
    is_active    = models.BooleanField(default=True, help_text="ON/OFF 스위치 상태")
    status       = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    rated_power_w = models.PositiveIntegerField(default=1000, help_text="채널 정격 전력(W). 카탈로그 기준 1CH Max 1000W. 설비별 실제값으로 수정 하도록")

    class Meta:
        db_table            = "device_channels"
        unique_together     = ("device", "channel_code")
        verbose_name        = "장비 채널"
        verbose_name_plural = "장비 채널 목록"

    def __str__(self):
        return f"{self.device.device_name} {self.channel_code}"
    

# ── DeviceStatusLog ────────────────────────────────────────

class DeviceStatusLog(models.Model):

    device         = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="status_logs")
    status_code    = models.CharField(max_length=50)
    status_message = models.TextField(blank=True)
    occurred_at    = models.DateTimeField()

    class Meta:
        db_table            = "device_status_logs"
        ordering            = ["-occurred_at"]
        verbose_name        = "장비 상태 이력"
        verbose_name_plural = "장비 상태 이력 목록"

    def __str__(self):
        return f"{self.device.device_uid} [{self.status_code}] @ {self.occurred_at}"


# ── GasReading ─────────────────────────────────────────────

class GasReading(models.Model):

    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="gas_readings")
    co  = models.FloatField(null=True, blank=True, help_text="일산화탄소 ppm")
    h2s = models.FloatField(null=True, blank=True, help_text="황화수소 ppm")
    co2 = models.FloatField(null=True, blank=True, help_text="이산화탄소 ppm")
    o2  = models.FloatField(null=True, blank=True, help_text="산소 %")
    no2 = models.FloatField(null=True, blank=True, help_text="이산화질소 ppm")
    so2 = models.FloatField(null=True, blank=True, help_text="이산화황 ppm")
    o3  = models.FloatField(null=True, blank=True, help_text="오존 ppm")
    nh3 = models.FloatField(null=True, blank=True, help_text="암모니아 ppm")
    voc = models.FloatField(null=True, blank=True, help_text="휘발성유기화합물 ppm")
    measured_at = models.DateTimeField(help_text="센서 측정 시각", db_index=True)
    received_at = models.DateTimeField(auto_now_add=True, help_text="서버 수신 시각")
    quality_flag = models.CharField(
        max_length=20, default='ok',
        help_text="ok / missing / comm_err / partial / invalid",
    )
    raw_payload = models.JSONField(null=True, blank=True, help_text="원본 수신 payload")

    # ── trace_id 계보 (단계별 파생·알람까지 상관) ──
    trace_id = models.UUIDField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="측정 1건 고유 ID — 원천↔파생 DetectionResult↔알람 상관 키",
    )
    tick_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="한 emit 사이클 공유 ID — 가스·전력·위치 교차 상관",
    )
    ts_fallback = models.BooleanField(
        default=False,
        help_text="measured_at 파싱 실패로 서버 now() 대체됐는지",
    )

    class Meta:
        db_table            = "gas_readings"
        ordering            = ["-measured_at"]
        verbose_name        = "유해가스 측정값"
        verbose_name_plural = "유해가스 측정값 목록"
        unique_together = [('device', 'measured_at')]
        indexes = [
            models.Index(fields=['device', 'measured_at']),
        ]

    def __str__(self):
        return f"{self.device.device_uid} @ {self.measured_at}"


# ── DetectionResult (단계별 판정 계보의 척추) ──────────────

class DetectionResult(models.Model):
    """원천 1건(trace_id)에 대한 단계별 검출 결과. 한 trace_id로 5단계 조회·역추적."""

    class Stage(models.TextChoices):
        THRESHOLD   = "THRESHOLD",   "임계 판정"
        ZSCORE      = "ZSCORE",      "Z-score"
        CHANGEPOINT = "CHANGEPOINT", "변화점"
        IF          = "IF",          "Isolation Forest"
        ARIMA       = "ARIMA",       "ARIMA 예측"
        POLICY      = "POLICY",      "정책 엔진 (현재 상태 통합)"

    trace_id    = models.UUIDField(db_index=True, help_text="원천 GasReading.trace_id 계보 키")
    gas_reading = models.ForeignKey(
        GasReading, on_delete=models.CASCADE, null=True, blank=True, related_name="detections",
        help_text="원천 참조 (trace_id로도 연결되나 FK 편의)",
    )
    device      = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="detections")
    sensor_type = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="채널/가스종. IF는 null=9채널 전체",
    )
    stage  = models.CharField(max_length=20, choices=Stage.choices, db_index=True)
    level  = models.CharField(max_length=20, help_text="판정 등급 (정상/주의/위험/이상 등)")
    score  = models.FloatField(null=True, blank=True, help_text="수치 (z·mahalanobis·예측편차 등)")
    detail = models.JSONField(null=True, blank=True, help_text="단계별 상세 (anchor·곡선·임계비교 등)")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "detection_results"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=['trace_id']),
            models.Index(fields=['device', 'sensor_type', 'created_at']),
            models.Index(fields=['stage', 'level']),
        ]

    def __str__(self):
        return f"{self.stage} [{self.level}] {self.sensor_type or '*'} ev={self.trace_id}"


# ── DropLog (들어왔으나 거부된 원천 추적) ──────────────────

class DropLog(models.Model):
    """ingest 경계에서 거부된 payload. 무음 드롭 금지 — 사후 추적용."""

    trace_id   = models.UUIDField(null=True, blank=True, db_index=True)
    device_uid = models.CharField(max_length=100, db_index=True)
    reason     = models.CharField(
        max_length=100,
        help_text="device_not_found / inactive / invalid_range / parse_fail 등",
    )
    raw_payload = models.JSONField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "drop_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"DROP {self.device_uid} ({self.reason}) @ {self.created_at}"


# ── PowerReading ─────────────────────────────────────

class PowerStatusReading(models.Model):
    """ON/OFF 상태 - 부팅 or 상태변경 시 이벤트성 전송 (ON=255, OFF=0)"""

    device      = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="power_status_readings")
    channel     = models.ForeignKey(DeviceChannel, on_delete=models.PROTECT, related_name="status_readings")
    status_value = models.IntegerField(help_text="ON=255 / OFF=0")
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = "power_status_readings"
        ordering            = ["-received_at"]
        verbose_name        = "전력 ON/OFF 상태"
        verbose_name_plural = "전력 ON/OFF 상태 목록"

    def __str__(self):
        status = "ON" if self.status_value == 255 else "OFF"
        return f"{self.device.device_uid} {self.channel.channel_code} {status}"

class PowerReading(models.Model):
    """전력/전압/전류 통합 테이블 - 1분 1회 (Insert 최소화 구조)"""
    device      = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="power_readings")
    channel     = models.ForeignKey(DeviceChannel, on_delete=models.PROTECT, related_name="power_readings")
    
    # 3개의 모델을 하나로 합침
    # Phase C-5: IntegerField → FloatField (Finding-3 부분 마이그레이션).
    # 사유: 시뮬레이션·송수신은 float 0.1 정밀도 보존하나 IntegerField가
    # truncation 발생 (저전력 그룹 current_a 0.0~0.1A → 0 손실).
    # 마이그레이션 시 raw_payload(jsonb)에서 float 원본 복원.
    current_a   = models.FloatField(default=-1.0, help_text="전류 A, -1=통신불능")
    voltage_v   = models.FloatField(default=-1.0, help_text="전압 V, -1=통신불능")
    power_w     = models.FloatField(default=-1.0, help_text="전력 W, -1=통신불능")
    
    temperature_c = models.FloatField(null=True, blank=True, help_text="온도 ℃")

    # db_index=True 추가 완료
    measured_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)
    quality_flag = models.CharField(
        max_length=20, default='ok',
        help_text="ok / missing / comm_err / partial / invalid",
    )
    raw_payload = models.JSONField(null=True, blank=True, help_text="원본 수신 payload")

    # ── trace_id 계보 (가스와 동일 — 단계별 파생·알람 상관) ──
    trace_id = models.UUIDField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="측정 1건 고유 ID — 원천↔DetectionResult↔알람 상관 키",
    )
    tick_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="한 emit 사이클 공유 ID (교차 상관, 현재 보류)",
    )
    ts_fallback = models.BooleanField(
        default=False,
        help_text="measured_at 파싱 실패로 서버 now() 대체됐는지",
    )

    class Meta:
        db_table            = "power_readings"
        ordering            = ["-measured_at"]
        verbose_name        = "스마트파워 측정값"
        verbose_name_plural = "스마트파워 측정값 목록"
        indexes = [
            models.Index(fields=['channel', 'measured_at']),
        ]

    def __str__(self):
        return f"{self.device.device_uid} {self.channel.channel_code} @ {self.measured_at}"


# ── NodeReading ────────────────────────────────────────────

class NodeReading(models.Model):
    """위치 노드 수신 로그 - 노드가 수신한 좌표 데이터"""
    node        = models.ForeignKey("facilities.LocationNode", on_delete=models.PROTECT, related_name="readings")
    x           = models.FloatField(null=True, blank=True, help_text="수신 X 좌표")
    y           = models.FloatField(null=True, blank=True, help_text="수신 Y 좌표")
    received_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table            = "node_readings"
        ordering            = ["-received_at"]
        verbose_name        = "위치 노드 수신 로그"
        verbose_name_plural = "위치 노드 수신 로그 목록"
        indexes = [
            models.Index(fields=['node', 'received_at']),
        ]

    def __str__(self):
        return f"{self.node.node_name} @ {self.received_at}"


# ── ThresholdPolicy ────────────────────────────────────────

class ThresholdPolicy(models.Model):

    class ActionType(models.TextChoices):
        NOTIFY   = "notify",   "알림"
        SHUTDOWN = "shutdown", "장비 차단"

    metric_code = models.CharField(max_length=50)
    category    = models.CharField(max_length=50, default='TH_GAS')
    unit        = models.CharField(max_length=20, blank=True, default='')
    condition   = models.CharField(max_length=10, default='이상')
    scope       = models.CharField(max_length=200, blank=True, default='')
    description = models.TextField(blank=True, default='')
    normal_min  = models.FloatField(null=True, blank=True)
    normal_max  = models.FloatField(null=True, blank=True)
    warning_min = models.FloatField(null=True, blank=True)
    warning_max = models.FloatField(null=True, blank=True)
    danger_min  = models.FloatField(null=True, blank=True)
    danger_max  = models.FloatField(null=True, blank=True)
    action_type = models.CharField(max_length=20, choices=ActionType.choices, default=ActionType.NOTIFY)
    is_active   = models.BooleanField(default=True)
    updated_at  = models.DateTimeField(auto_now=True)
    updated_by  = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table            = "threshold_policies"
        unique_together     = ('metric_code', 'category')
        verbose_name        = "임계치 정책"
        verbose_name_plural = "임계치 정책 목록"

    def __str__(self):
        return f"{self.metric_code} [{self.action_type}]"


# ── InspectionLog ──────────────────────────────────────────

class InspectionLog(models.Model):

    class InspectionType(models.TextChoices):
        REGULAR  = "regular",  "정기 점검"
        ABNORMAL = "abnormal", "이상 점검"

    class InspectionStatus(models.TextChoices):
        NORMAL          = "normal",          "정상"
        ACTION_REQUIRED = "action_required", "조치 필요"

    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="inspections")
    inspector = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="inspections")
    inspection_type      = models.CharField(max_length=20, choices=InspectionType.choices)
    inspection_date      = models.DateField(help_text="점검일")
    status               = models.CharField(max_length=20, choices=InspectionStatus.choices)
    note                 = models.TextField(blank=True, help_text="점검 의견")
    expected_action_date = models.DateField(null=True, blank=True, help_text="예상 조치일")
    created_at           = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = "inspection_logs"
        ordering            = ["-inspection_date"]
        verbose_name        = "점검 이력"
        verbose_name_plural = "점검 이력 목록"

    def __str__(self):
        return f"[{self.device}] {self.inspection_date} ({self.status})"


# ── ActionLog ──────────────────────────────────────────────

class ActionLog(models.Model):

    inspection = models.OneToOneField(InspectionLog, on_delete=models.PROTECT, related_name="action")
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="actions")
    action_date = models.DateField(help_text="조치 완료일")
    action_note = models.TextField(blank=True, help_text="조치 의견")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = "action_logs"
        verbose_name        = "조치 이력"
        verbose_name_plural = "조치 이력 목록"

    def __str__(self):
        return f"[{self.inspection.device}] 조치 {self.action_date}"
