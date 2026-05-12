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

    class Meta:
        db_table            = "gas_readings"
        ordering            = ["-measured_at"]
        verbose_name        = "유해가스 측정값"
        verbose_name_plural = "유해가스 측정값 목록"
        # 복합 인덱스 (특정 장비의 시간대별 조회 성능 향상)
        indexes = [
            models.Index(fields=['device', 'measured_at']),
        ]

    def __str__(self):
        return f"{self.device.device_uid} @ {self.measured_at}"


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
    current_a   = models.IntegerField(default=-1, help_text="전류 A, -1=통신불능")
    voltage_v   = models.IntegerField(default=-1, help_text="전압 V, -1=통신불능")
    power_w     = models.IntegerField(default=-1, help_text="전력 W, -1=통신불능")
    
    # db_index=True 추가 완료
    measured_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)

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


# ── ThresholdPolicy ────────────────────────────────────────

class ThresholdPolicy(models.Model):

    class ActionType(models.TextChoices):
        ALERT    = "alert",    "알림"
        SHUTDOWN = "shutdown", "장비 차단"

    metric_code = models.CharField(max_length=50, unique=True)
    normal_min  = models.FloatField(null=True, blank=True)
    normal_max  = models.FloatField(null=True, blank=True)
    warning_min = models.FloatField(null=True, blank=True)
    warning_max = models.FloatField(null=True, blank=True)
    danger_min  = models.FloatField(null=True, blank=True)
    danger_max  = models.FloatField(null=True, blank=True)
    action_type = models.CharField(max_length=20, choices=ActionType.choices, default=ActionType.ALERT)
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table            = "threshold_policies"
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
