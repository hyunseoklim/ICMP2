from django.db import models
from django.conf import settings


class Notice(models.Model):
    CATEGORY_CHOICES = [
        ('운영 공지', '운영 공지'),
        ('안전 공지', '안전 공지'),
        ('시스템 공지', '시스템 공지'),
    ]

    title      = models.CharField(max_length=255, verbose_name='공지 제목')
    category   = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name='게시 구분')
    content    = models.TextField(verbose_name='공지 내용')
    is_exposed = models.BooleanField(default=True, verbose_name='노출 여부')
    author     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='notices',
        verbose_name='작성자',
    )
    view_count = models.PositiveIntegerField(default=0, verbose_name='조회수')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='등록일')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일')

    class Meta:
        db_table            = 'notices'
        ordering            = ['-created_at']
        verbose_name        = '공지사항'
        verbose_name_plural = '공지사항 목록'

    def __str__(self):
        return self.title


class NoticeAttachment(models.Model):
    notice        = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name='attachments')
    file          = models.FileField(upload_to='notices/', verbose_name='파일')
    original_name = models.CharField(max_length=255, verbose_name='원본 파일명')
    file_size     = models.PositiveIntegerField(verbose_name='파일 크기(bytes)')
    uploaded_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table     = 'notice_attachments'
        verbose_name = '공지 첨부파일'

    def __str__(self):
        return self.original_name

    def get_ext(self):
        return self.original_name.rsplit('.', 1)[-1].lower() if '.' in self.original_name else ''

    def get_size_display(self):
        if self.file_size >= 1024 * 1024:
            return f"{self.file_size / (1024 * 1024):.1f}MB"
        return f"{round(self.file_size / 1024)}KB"


class AlarmSendHistory(models.Model):
    CHANNEL_CHOICES = [
        ('SMS',         'SMS'),
        ('이메일',      '이메일'),
        ('앱 푸시',     '앱 푸시'),
        ('관제 실시간 알림', '관제 실시간 알림'),
    ]
    RESULT_CHOICES = [
        ('성공', '성공'),
        ('실패', '실패'),
        ('지연', '지연'),
    ]

    sent_at      = models.DateTimeField(verbose_name='발송 시각')
    channel      = models.CharField(max_length=20, choices=CHANNEL_CHOICES, verbose_name='발송 채널')
    targets      = models.CharField(max_length=100, verbose_name='수신 역할')
    result       = models.CharField(max_length=10, choices=RESULT_CHOICES, verbose_name='발송 결과')
    alarm_policy = models.ForeignKey(
        'AlarmPolicy',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='send_histories',
        verbose_name='연결 정책',
    )
    policy_name  = models.CharField(max_length=200, blank=True, verbose_name='연결 알림 정책명')
    scope        = models.CharField(max_length=100, blank=True, verbose_name='적용 역할 범위')
    content      = models.TextField(verbose_name='발송 내용')
    reason       = models.TextField(blank=True, verbose_name='결과 메모')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'alarm_send_histories'
        ordering            = ['-sent_at']
        verbose_name        = '알림 발송 이력'
        verbose_name_plural = '알림 발송 이력 목록'

    def __str__(self):
        return f"[{self.channel}] {self.targets} — {self.result}"


class AlarmPolicy(models.Model):
    EVENT_CHOICES = [
        ('가스 경보',                   '가스 경보'),
        ('전력 이상',                   '전력 이상'),
        ('위험구역 진입',               '위험구역 진입'),
        ('PPE 미착용',                  'PPE 미착용'),
        ('작업 안전 체크리스트 미완료', '작업 안전 체크리스트 미완료'),
        ('VR 교육 미이수',              'VR 교육 미이수'),
    ]

    name              = models.CharField(max_length=200, verbose_name='정책명')
    event_type        = models.CharField(max_length=50, choices=EVENT_CHOICES, verbose_name='이벤트 상세')
    channels          = models.CharField(max_length=100, verbose_name='발송 채널')   # "앱, 관제 실시간 알림"
    targets           = models.CharField(max_length=100, verbose_name='수신 대상')   # "관리자, 작업자"
    is_active         = models.BooleanField(default=True, verbose_name='사용 여부')
    condition_summary = models.TextField(blank=True, verbose_name='적용 조건 요약')
    alarm_title       = models.CharField(max_length=200, blank=True, verbose_name='알림 제목')
    alarm_content     = models.TextField(blank=True, verbose_name='알림 내용')
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'alarm_policies'
        ordering            = ['-updated_at']
        verbose_name        = '알림 정책'
        verbose_name_plural = '알림 정책 목록'

    def __str__(self):
        return self.name


class ChecklistSnapshot(models.Model):
    """반영 저장 이력 — 저장 시점의 체크리스트 전체 스냅샷"""
    saved_at = models.DateTimeField(auto_now_add=True)
    saved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='저장자',
    )
    data = models.JSONField(verbose_name='스냅샷 데이터')

    class Meta:
        db_table     = 'checklist_snapshots'
        ordering     = ['-saved_at']
        verbose_name = '체크리스트 반영 이력'

    def __str__(self):
        return self.saved_at.strftime('%Y-%m-%d %H:%M')


class VREducation(models.Model):
    title       = models.CharField(max_length=200, verbose_name='교육명')
    target      = models.CharField(max_length=100, verbose_name='적용 대상')
    is_active   = models.BooleanField(default=True, verbose_name='사용 상태')
    duration    = models.PositiveIntegerField(default=0, verbose_name='재생 시간(초)')
    description = models.TextField(blank=True, verbose_name='교육 설명')
    memo        = models.TextField(blank=True, verbose_name='운영 메모')
    video       = models.FileField(upload_to='vr_education/videos/', null=True, blank=True, verbose_name='영상 파일')
    thumbnail   = models.ImageField(upload_to='vr_education/thumbnails/', null=True, blank=True, verbose_name='썸네일')
    updated_at  = models.DateTimeField(auto_now=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table     = 'vr_educations'
        verbose_name = 'VR 교육'

    def __str__(self):
        return self.title

    @property
    def duration_display(self):
        if not self.duration:
            return "미설정"
        m, s = divmod(self.duration, 60)
        return f"{m:02d}분 {s:02d}초"

    @property
    def duration_badge(self):
        if not self.duration:
            return "--:--"
        m, s = divmod(self.duration, 60)
        return f"{m:02d}:{s:02d}"

class DataRetentionPolicy(models.Model):

    DEVICE_TYPE = [
        ('gas',   '유해가스 센서'),
        ('power', '스마트 전력 시스템'),
        ('node',  '위치 노드'),
    ]

    DATA_CATEGORY = [
        ('raw',       '원천 로그'),
        ('event',     '이벤트 이력'),
        ('aggregate', '집계 이력'),
        ('location',  '위치 이력'),
    ]

    DELETE_SCHEDULE = [
        ('daily',        '매일'),
        ('monthly_1',    '매월 1일'),
        ('monthly_15',   '매월 15일'),
        ('monthly_last', '매월 말일'),
        ('quarterly',    '분기말'),
    ]

    device_type     = models.CharField(max_length=20, choices=DEVICE_TYPE)
    data_category   = models.CharField(max_length=20, choices=DATA_CATEGORY)
    origin_days     = models.PositiveIntegerField(help_text="원천 데이터 보관 기간(일)")
    history_days    = models.PositiveIntegerField(help_text="이력 데이터 보관 기간(일)")
    delete_schedule = models.CharField(max_length=20, choices=DELETE_SCHEDULE)
    is_active       = models.BooleanField(default=True)
    memo            = models.TextField(blank=True)
    manager         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='retention_policies',
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'data_retention_policies'
        ordering            = ['device_type', 'data_category']
        verbose_name        = '데이터 보관 주기'
        verbose_name_plural = '데이터 보관 주기 목록'

    def __str__(self):
        return f"{self.get_device_type_display()} / {self.get_data_category_display()}"

    @property
    def manager_name(self):
        if not self.manager:
            return '-'
        u = self.manager
        return getattr(u, 'name', None) or u.get_full_name() or u.username