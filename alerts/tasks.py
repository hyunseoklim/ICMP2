import logging
import time

import requests
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from prometheus_client import Counter, Histogram

# ── 커스텀 Prometheus 메트릭 ──────────────────────────────────────────────────
ALARM_EVENT_COUNTER = Counter(
    'icmp2_alarm_events_total',
    '알람 이벤트 발생 건수',
    ['severity'],
)
AI_FORECAST_DURATION = Histogram(
    'icmp2_ai_forecast_duration_seconds',
    'AI ARIMA 예측 처리 시간(초)',
    ['task_type'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
AI_INGEST_DURATION = Histogram(
    'icmp2_ai_ingest_duration_seconds',
    'Celery ingest(STEP B~E) 처리 시간(초)',
    buckets=[0.05, 0.1, 0.3, 0.5, 1.0, 2.0, 5.0],
)
CELERY_TASK_COUNTER = Counter(
    'icmp2_celery_tasks_total',
    'Celery task 완료 건수',
    ['task_name', 'status'],
)

logger = logging.getLogger(__name__)

# 3. RiskCriteria.color_type → Slack emoji / Discord embed color 매핑
_COLOR_EMOJI = {
    'red':    '🔴',
    'orange': '🟠',
    'yellow': '🟡',
    'green':  '🟢',
    'gray':   '⚪',
}
_COLOR_DISCORD = {
    'red':    0xFF0000,
    'orange': 0xFF8800,
    'yellow': 0xFFCC00,
    'green':  0x00CC00,
    'gray':   0xAAAAAA,
}
_SEVERITY_EMOJI_FALLBACK = {
    'danger': '🔴', 'warning': '🟡', 'anomaly': '🟠', 'predictive_warning': '🔵',
}
_SEVERITY_COLOR_FALLBACK = {
    'danger': 0xFF0000, 'warning': 0xFFCC00, 'anomaly': 0xFF8800, 'predictive_warning': 0x0088FF,
}

# 12. AlarmEvent.event_type → AlarmPolicy.event_type 매핑
_POLICY_EVENT_TYPE = {
    'gas':   '가스 경보',
    'power': '전력 이상',
}


def _build_alert_payload(event) -> dict:
    return {
        'id': event.id,
        'title': event.title,
        'message': event.message,
        'severity': event.severity,
        'event_type': event.event_type,
        'facility': str(event.facility) if event.facility else '',
        'occurred_at': event.occurred_at.isoformat(),
    }


def _get_risk_criteria(severity: str):
    """3. RiskCriteria — stage_code=severity로 조회. 없으면 None.

    관리자가 stage_code를 AlarmEvent.Severity 값('danger','warning' 등)과
    일치하도록 등록해야 연동된다.
    """
    try:
        from .models import RiskCriteria
        return RiskCriteria.objects.filter(stage_code__iexact=severity, is_active=True).first()
    except Exception:
        return None


def _get_alarm_policy(event_type: str):
    """12. AlarmPolicy — event_type으로 조회. 없으면 None."""
    try:
        from manager.models import AlarmPolicy
        policy_event_name = _POLICY_EVENT_TYPE.get(event_type, '')
        if not policy_event_name:
            return None
        return AlarmPolicy.objects.filter(event_type=policy_event_name, is_active=True).first()
    except Exception:
        return None


def _render_policy_message(event, alarm_policy) -> tuple:
    """12. AlarmPolicy의 alarm_title/alarm_content 템플릿을 이벤트 데이터로 렌더링.

    반환: (title, content, targets)
    alarm_policy가 없거나 필드가 비어 있으면 event 기본값 사용.
    """
    replacements = {
        '{이벤트상세}': event.get_event_type_display(),
        '{발생대상}':   str(event.device or event.facility or '-'),
        '{상태}':       event.get_severity_display(),
        '{발생시각}':   event.occurred_at.strftime('%Y-%m-%d %H:%M:%S'),
    }

    if alarm_policy:
        title   = alarm_policy.alarm_title   or event.title
        content = alarm_policy.alarm_content or event.message
        targets = alarm_policy.targets       or ''
    else:
        title   = event.title
        content = event.message
        targets = ''

    for placeholder, value in replacements.items():
        title   = title.replace(placeholder, value)
        content = content.replace(placeholder, value)

    return title, content, targets


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_slack_notification(self, event_id: int):
    from .models import AlarmEvent
    webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', '')
    if not webhook_url:
        return

    try:
        event = AlarmEvent.objects.select_related('facility', 'device').get(pk=event_id)
    except AlarmEvent.DoesNotExist:
        return

    # 3 & 4: RiskCriteria → emoji(color_type) + 알림 강조(alert_emphasis)
    risk = _get_risk_criteria(event.severity)
    if risk:
        severity_emoji = _COLOR_EMOJI.get(risk.color_type, '⚪')
        emphasis = f"[{risk.alert_emphasis}] " if risk.alert_emphasis else ''
    else:
        severity_emoji = _SEVERITY_EMOJI_FALLBACK.get(event.severity, '⚪')
        emphasis = ''

    # 12: AlarmPolicy → alarm_title/alarm_content 템플릿 + targets
    alarm_policy = _get_alarm_policy(event.event_type)
    title, content, targets = _render_policy_message(event, alarm_policy)

    target_str = f"  |  수신 대상: {targets}" if targets else ''
    text = (
        f"{severity_emoji} *[ICMP2 알림]* {emphasis}{title}\n"
        f"> {content}\n"
        f"> 시설: {event.facility or '-'}  |  발생: {event.occurred_at.strftime('%Y-%m-%d %H:%M:%S')}{target_str}"
    )

    try:
        resp = requests.post(webhook_url, json={'text': text}, timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Slack 알림 실패 (event=%s): %s", event_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_discord_notification(self, event_id: int):
    from .models import AlarmEvent
    webhook_url = getattr(settings, 'DISCORD_WEBHOOK_URL', '')
    if not webhook_url:
        return

    try:
        event = AlarmEvent.objects.select_related('facility', 'device').get(pk=event_id)
    except AlarmEvent.DoesNotExist:
        return

    # 3 & 4: RiskCriteria → embed 색상(color_type) + 알림 강조(alert_emphasis)
    risk = _get_risk_criteria(event.severity)
    if risk:
        color = _COLOR_DISCORD.get(risk.color_type, 0xAAAAAA)
        emphasis = risk.alert_emphasis or ''
    else:
        color = _SEVERITY_COLOR_FALLBACK.get(event.severity, 0xAAAAAA)
        emphasis = ''

    # 12: AlarmPolicy → alarm_title/alarm_content 템플릿 + targets
    alarm_policy = _get_alarm_policy(event.event_type)
    title, content, targets = _render_policy_message(event, alarm_policy)

    fields = [
        {'name': '시설',      'value': str(event.facility or '-'),                      'inline': True},
        {'name': '발생 시각', 'value': event.occurred_at.strftime('%Y-%m-%d %H:%M:%S'), 'inline': True},
    ]
    if targets:
        fields.append({'name': '수신 대상', 'value': targets, 'inline': True})
    if emphasis:
        fields.append({'name': '알림 강조', 'value': emphasis, 'inline': True})

    payload = {
        'embeds': [{
            'title':       title,
            'description': content,
            'color':       color,
            'fields':      fields,
        }]
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Discord 알림 실패 (event=%s): %s", event_id, exc)
        raise self.retry(exc=exc)


@shared_task
def push_websocket_alert(event_id: int):
    """WebSocket으로 관제 대시보드에 실시간 알림 푸시."""
    from .models import AlarmEvent
    try:
        event = AlarmEvent.objects.select_related('facility', 'device').get(pk=event_id)
    except AlarmEvent.DoesNotExist:
        return

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'alerts',
        {
            'type': 'alert_message',
            'data': _build_alert_payload(event),
        },
    )


@shared_task
def send_all_notifications(event_id: int):
    """AlarmEvent 발생 시 AlarmPolicy에 따라 채널별 알림 발송 (중복 방지 포함)."""
    from django.core.cache import cache
    from .models import AlarmEvent
    from manager.models import AlarmPolicy

    try:
        event = AlarmEvent.objects.select_related(
            'rule', 'rule__threshold_policy', 'facility'
        ).get(pk=event_id)
    except AlarmEvent.DoesNotExist:
        return

    # 6. ThresholdPolicy.action_type 참조
    # shutdown: 하드웨어 미구현 단계 — 알림은 유지하되 로그 기록
    # NOTE: ThresholdPolicy.action_type = "notify" (기본값), "shutdown" 감지 시 로그 기록
    rule = event.rule
    if rule and getattr(rule, 'threshold_policy_id', None):
        tp = rule.threshold_policy
        if tp and tp.action_type == 'shutdown':
            logger.info(
                "ThresholdPolicy shutdown action 감지 — event=%s metric=%s (알림 발송 유지, 하드웨어 차단 미구현)",
                event_id, tp.metric_code,
            )

    # 중복 방지 (5분 쿨다운)
    rule_id = event.rule_id or 0
    facility_id = event.facility_id or 0
    dedup_key = f"alarm:dedup:{rule_id}:{facility_id}"
    if cache.get(dedup_key):
        logger.info("중복 알람 방지 — event=%s key=%s", event_id, dedup_key)
        return
    cache.set(dedup_key, 1, timeout=300)

    # 12. AlarmPolicy 조회 → 채널 파싱
    policy_event_name = _POLICY_EVENT_TYPE.get(event.event_type, '')
    alarm_policy = None
    if policy_event_name:
        alarm_policy = AlarmPolicy.objects.filter(
            event_type=policy_event_name, is_active=True
        ).first()

    # 채널 파싱 — 정책 없으면 전체 발송 (폴백)
    if alarm_policy:
        ch_list = [c.strip() for c in alarm_policy.channels.split(',')]
        send_websocket = any('관제' in c or '실시간' in c for c in ch_list)
        send_slack    = 'Slack'   in ch_list
        send_discord  = 'Discord' in ch_list
    else:
        send_websocket = True
        send_slack     = True
        send_discord   = True

    if send_websocket:
        push_websocket_alert.delay(event_id)
    if send_slack:
        send_slack_notification.delay(event_id)
    if send_discord:
        send_discord_notification.delay(event_id)


# ---------------------------------------------------------------------------
# 7. MISSING 장비 감지 — AlarmRule.missing_timeout_seconds 기반 주기 체크
# ---------------------------------------------------------------------------

@shared_task
def check_missing_devices():
    """MISSING 규칙 — Device.last_seen_at 기준 미수신 타임아웃 감지.

    Celery Beat으로 매 60초마다 실행 (settings.CELERY_BEAT_SCHEDULE).
    AlarmRule(rule_type='missing').missing_timeout_seconds를 기준으로
    데이터 미수신 장비를 탐지해 AlarmEvent를 생성한다.
    - 이미 OPEN 이벤트가 있으면 last_seen_at·message만 갱신 (중복 생성 방지)
    - 수신 재개(last_seen_at >= cutoff)된 장비는 OPEN 이벤트 자동 종료
    """
    from datetime import timedelta

    from django.utils import timezone

    from monitoring.models import Device

    from .models import AlarmEvent, AlarmRule, EventHistory
    from .services import create_alarm_event

    rules = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.MISSING,
        is_active=True,
        missing_timeout_seconds__isnull=False,
    )
    if not rules.exists():
        return

    now = timezone.now()
    for rule in rules:
        timeout = timedelta(seconds=rule.missing_timeout_seconds)
        cutoff = now - timeout

        # 미수신 장비 탐지
        missing_devices = Device.objects.filter(
            facility__isnull=False,
            last_seen_at__isnull=False,
            last_seen_at__lt=cutoff,
        ).select_related('facility')

        for device in missing_devices:
            elapsed = int((now - device.last_seen_at).total_seconds())
            msg = f"마지막 수신 {elapsed}초 전 (기준: {rule.missing_timeout_seconds}초)"

            open_event = AlarmEvent.objects.filter(
                rule=rule,
                device=device,
                event_status=AlarmEvent.EventStatus.OPEN,
            ).first()

            if open_event:
                open_event.last_seen_at = now
                open_event.message = msg
                open_event.save(update_fields=['last_seen_at', 'message', 'updated_at'])
            else:
                create_alarm_event(
                    rule=rule,
                    facility=device.facility,
                    severity=AlarmEvent.Severity.WARNING,
                    title=f"[MISSING] {device.device_uid} 데이터 미수신",
                    device=device,
                    message=msg,
                )

        # 수신 재개 장비 → OPEN 이벤트 자동 종료
        recovered_devices = Device.objects.filter(
            facility__isnull=False,
            last_seen_at__isnull=False,
            last_seen_at__gte=cutoff,
        )
        for device in recovered_devices:
            open_event = AlarmEvent.objects.filter(
                rule=rule,
                device=device,
                event_status=AlarmEvent.EventStatus.OPEN,
            ).first()
            if open_event:
                open_event.event_status = AlarmEvent.EventStatus.CLOSED
                open_event.closed_at = now
                open_event.save(update_fields=['event_status', 'closed_at', 'updated_at'])
                EventHistory.objects.create(
                    alarm_event=open_event,
                    action_type='close',
                    action_note='데이터 수신 재개로 자동 종료',
                )


# ---------------------------------------------------------------------------
# B. 가스 센서 인제스트 태스크 (FastAPI → Celery 큐 → 파이프라인)
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def ingest_gas_task(self, payload: dict):
    """
    FastAPI가 Celery 큐에 넣은 가스 센서 데이터를 받아
    DB 저장 + STEP B/C/D/E 파이프라인을 실행한다.

    Celery Worker가 순서대로 보장 처리 (메시지 유실 없음).
    """
    device_uid = payload.get('device_uid')
    if not device_uid:
        logger.warning("ingest_gas_task: payload에 device_uid 없음")
        return

    try:
        from monitoring.services import process_gas_ingest
        _t = time.time()
        process_gas_ingest(device_uid, payload)
        AI_INGEST_DURATION.observe(time.time() - _t)
        CELERY_TASK_COUNTER.labels(task_name='ingest_gas', status='success').inc()
        logger.debug("ingest_gas_task 완료 — device=%s", device_uid)
    except Exception as exc:
        CELERY_TASK_COUNTER.labels(task_name='ingest_gas', status='failure').inc()
        logger.error("ingest_gas_task 실패 — device=%s: %s", device_uid, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# B-2. 가스 예측 태스크 (STEP G — forecast 전용 큐 / 단일 동시성 worker)
# ---------------------------------------------------------------------------

@shared_task
def forecast_gas_task(device_uid: str, payload: dict):
    """STEP G — 가스 예측 서브시스템(ARIMA 사전 경고) 실행.

    settings.CELERY_TASK_ROUTES로 'forecast' 큐에 라우팅되며, 단일 동시성
    (--concurrency=1) worker가 소비한다 → PredictionSubsystem 상태가 한
    프로세스에 보존된다.

    상태기를 다루므로 Celery 자동 재시도를 쓰지 않는다(재시도 = 같은
    reading 중복 처리 → 윈도우·K-카운터 오염). run_forecast 내부의
    idempotency 가드가 중복·역순 reading을 차단하고, 한 reading 처리
    실패는 다음 reading(다음 케이던스)에 자연 복구된다.
    """
    if not device_uid:
        return
    try:
        from monitoring.ai.gas_forecast import run_forecast
        from monitoring.models import Device
        from alerts.services import trigger_forecast_alarms, save_forecast_snapshots

        _t = time.time()
        results = run_forecast(device_uid, payload)
        AI_FORECAST_DURATION.labels(task_type='gas').observe(time.time() - _t)

        if not results:
            return  # idempotency 가드에 의해 skip됨
        # results: [(ForecastPolicyResult, ARIMAResult|None), ...]
        policy_results = [pr for pr, _ in results]
        device = Device.objects.filter(device_uid=device_uid).first()
        if device:
            save_forecast_snapshots(device, results)         # 등급 + 곡선(튜플) → 스냅샷 upsert
            trigger_forecast_alarms(device, policy_results)  # CONFIRMED 시 predictive_warning 알람
        CELERY_TASK_COUNTER.labels(task_name='forecast_gas', status='success').inc()
        logger.debug("forecast_gas_task 완료 — device=%s", device_uid)
    except Exception as exc:
        CELERY_TASK_COUNTER.labels(task_name='forecast_gas', status='failure').inc()
        logger.error("forecast_gas_task 실패 — device=%s: %s", device_uid, exc)
        # 재시도하지 않음 — 다음 reading에서 복구


# ---------------------------------------------------------------------------
# B-3. 전력 예측 태스크 (STEP G — forecast 전용 큐 / Phase D M1)
# ---------------------------------------------------------------------------

@shared_task
def forecast_power_task(device_uid: str, channel_code: str, payload: dict):
    """STEP G — 전력 예측 서브시스템(ARIMA 사전 경고) 실행.

    settings.CELERY_TASK_ROUTES로 'forecast' 큐에 라우팅. 단일 동시성
    (--concurrency=1) worker가 소비 → PredictionSubsystem 상태가 한
    프로세스에 보존된다 (gas D2 아키텍처 미러).

    상태기를 다루므로 Celery 자동 재시도를 쓰지 않는다 — 재시도 = 같은
    reading 중복 처리 → 윈도우·K-카운터 오염. run_forecast 내부의
    idempotency 가드가 중복·역순 reading을 차단하고, 한 reading 처리
    실패는 다음 reading(다음 케이던스)에 자연 복구된다.
    """
    if not device_uid or not channel_code:
        return
    try:
        from monitoring.ai.power_forecast import run_forecast
        from monitoring.models import Device, DeviceChannel
        from alerts.services import trigger_forecast_alarms, save_forecast_snapshots

        _t = time.time()
        results = run_forecast(device_uid, channel_code, payload)
        AI_FORECAST_DURATION.labels(task_type='power').observe(time.time() - _t)

        if not results:
            return  # idempotency 가드에 의해 skip됨

        device = Device.objects.filter(device_uid=device_uid).first()
        if not device:
            return
        channel = DeviceChannel.objects.filter(
            device=device, channel_code=channel_code,
        ).first()
        if not channel:
            return

        # results: [(ForecastPolicyResult, ARIMAResult|None), ...]
        policy_results = [pr for pr, _ in results]
        save_forecast_snapshots(device, results, channel=channel)
        trigger_forecast_alarms(device, policy_results, channel=channel)
        CELERY_TASK_COUNTER.labels(task_name='forecast_power', status='success').inc()
        logger.debug(
            "forecast_power_task 완료 — device=%s ch=%s", device_uid, channel_code,
        )
    except Exception as exc:
        CELERY_TASK_COUNTER.labels(task_name='forecast_power', status='failure').inc()
        logger.error(
            "forecast_power_task 실패 — device=%s ch=%s: %s",
            device_uid, channel_code, exc,
        )
        # 재시도하지 않음 — 다음 reading에서 복구


# ---------------------------------------------------------------------------
# C. Redis Pub/Sub 수신 (레거시 — ingest_gas_task로 대체됨)
# ---------------------------------------------------------------------------

@shared_task
def consume_redis_pubsub():
    """
    Redis Pub/Sub 'sensor_events' 채널을 구독하여
    FastAPI가 publish한 가스 센서 데이터를 수신하고 처리한다.

    Celery Beat으로 settings.REDIS_PUBSUB_TIMEOUT(기본 30초) 간격마다 실행.
    한 번 실행 시 timeout_sec 동안 메시지를 소비한 뒤 종료.
    """
    import json
    import time

    import redis
    from django.conf import settings

    redis_url   = getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
    channel     = getattr(settings, 'REDIS_PUBSUB_CHANNEL', 'sensor_events')
    timeout_sec = getattr(settings, 'REDIS_PUBSUB_TIMEOUT', 30)

    r  = redis.Redis.from_url(redis_url)
    ps = r.pubsub()
    ps.subscribe(channel)
    logger.info("Redis Pub/Sub 구독 시작 — channel=%s", channel)

    deadline = time.time() + timeout_sec
    for message in ps.listen():
        if time.time() > deadline:
            break
        if message['type'] != 'message':
            continue

        try:
            data = json.loads(message['data'])
        except (ValueError, TypeError):
            logger.warning("Pub/Sub 메시지 파싱 실패: %s", message['data'])
            continue

        _handle_pubsub_message(data)

    ps.unsubscribe(channel)


def _handle_pubsub_message(data: dict):
    """
    FastAPI가 publish한 가스 센서 raw 데이터를 받아
    DB 저장 + STEP B/C/D/E 파이프라인을 실행한다.

    메시지 형식 (fastapi_app/sender.py의 publish_gas_reading 참고):
    {
        "device_uid":  "GAS-001",
        "measured_at": "2026-05-22T10:00:00+00:00",
        "co": 5.2, "h2s": 1.1, "co2": 420.0,
        "o2": 20.9, "no2": 0.5, "so2": 0.3,
        "o3": 0.02, "nh3": 3.0, "voc": 0.1
    }
    """
    device_uid = data.get('device_uid')
    if not device_uid:
        logger.warning("Pub/Sub 메시지에 device_uid 없음: %s", data)
        return

    try:
        from monitoring.services import process_gas_ingest
        process_gas_ingest(device_uid, data)
        logger.debug("Pub/Sub 처리 완료 — device=%s", device_uid)
    except Exception as exc:  # noqa: BLE001
        logger.error("Pub/Sub 처리 실패 — device=%s: %s", device_uid, exc)


# ---------------------------------------------------------------------------
# D. 데이터 보관 주기 자동 삭제 (DataRetentionPolicy)
# ---------------------------------------------------------------------------

@shared_task
def run_data_retention():
    """
    DataRetentionPolicy 설정에 따라 만료 데이터를 삭제한다.
    - 만료 7일 전: Slack/Discord + WebSocket(관리자 전용)으로 사전 알림
    - 만료 당일:   정책의 delete_schedule이 오늘에 해당하면 삭제 후 알림

    Celery Beat으로 매일 새벽 3시 실행 (settings.CELERY_BEAT_SCHEDULE).
    각 정책의 delete_schedule을 확인해 오늘이 삭제 일정에 해당하는지 판단한다.
    """
    import calendar
    from datetime import timedelta

    from django.utils import timezone

    from alerts.models import AlarmEvent
    from manager.models import DataRetentionPolicy
    from monitoring.models import GasReading, NodeReading, PowerReading
    from facilities.models import WorkerLocation

    # raw/location: (device_type, data_category) → (모델, 타임스탬프 필드, 보관기간 필드)
    # 보관기간 필드: 'origin_days'(원천 raw) or 'history_days'(이력 event/location)
    RAW_MAP = {
        ('gas',   'raw'):      (GasReading,    'measured_at'),
        ('power', 'raw'):      (PowerReading,  'measured_at'),
        ('node',  'raw'):      (NodeReading,   'received_at'),
        ('node',  'location'): (WorkerLocation,'measured_at'),
    }

    now = timezone.localtime()  # KST 기준
    today = now.date()

    def _is_schedule_today(schedule: str) -> bool:
        if schedule == 'daily':
            return True
        if schedule == 'monthly_1':
            return today.day == 1
        if schedule == 'monthly_15':
            return today.day == 15
        if schedule == 'monthly_last':
            last_day = calendar.monthrange(today.year, today.month)[1]
            return today.day == last_day
        if schedule == 'quarterly':
            quarter_ends = {3: 31, 6: 30, 9: 30, 12: 31}
            return today.month in quarter_ends and today.day == quarter_ends[today.month]
        return False

    # AlarmEvent는 device_type 구분 없이 하나의 테이블 — 중복 삭제 방지용
    event_processed = False

    for policy in DataRetentionPolicy.objects.filter(is_active=True):
        key = (policy.device_type, policy.data_category)
        label = f"{policy.get_device_type_display()} / {policy.get_data_category_display()}"

        # ── aggregate: 집계 모델 미구현 → skip ───────────────────
        if policy.data_category == 'aggregate':
            logger.warning("run_data_retention: aggregate 모델 미구현 — %s", label)
            continue

        # ── event: AlarmEvent (device_type 무관, history_days 기준) ──
        if policy.data_category == 'event':
            if event_processed:
                continue
            retention_days = policy.history_days
            cutoff = now - timedelta(days=retention_days)
            warn_cutoff = now - timedelta(days=max(retention_days - 7, 0))

            soon_count = AlarmEvent.objects.filter(occurred_at__lt=warn_cutoff).count()
            if soon_count > 0:
                _notify_retention_warning("이벤트 이력 (전체)", retention_days, soon_count)

            if _is_schedule_today(policy.delete_schedule):
                deleted_count, _ = AlarmEvent.objects.filter(occurred_at__lt=cutoff).delete()
                if deleted_count > 0:
                    logger.info("데이터 삭제 완료 — 이벤트 이력: %d건", deleted_count)
                    _notify_retention_deleted("이벤트 이력 (전체)", deleted_count)

            event_processed = True
            continue

        # ── raw / location: 개별 모델 매핑 ───────────────────────
        mapping = RAW_MAP.get(key)
        if not mapping:
            logger.warning("run_data_retention: 매핑 없음 — %s/%s", policy.device_type, policy.data_category)
            continue

        model, ts_field = mapping
        # location은 이력 성격 → history_days, raw는 원천 → origin_days
        retention_days = policy.history_days if policy.data_category == 'location' else policy.origin_days
        cutoff = now - timedelta(days=retention_days)
        warn_cutoff = now - timedelta(days=max(retention_days - 7, 0))

        soon_count = model.objects.filter(**{f"{ts_field}__lt": warn_cutoff}).count()
        if soon_count > 0:
            _notify_retention_warning(label, retention_days, soon_count)

        if not _is_schedule_today(policy.delete_schedule):
            continue

        deleted_count, _ = model.objects.filter(**{f"{ts_field}__lt": cutoff}).delete()
        if deleted_count > 0:
            logger.info("데이터 삭제 완료 — %s: %d건", label, deleted_count)
            _notify_retention_deleted(label, deleted_count)


def _notify_retention_warning(label: str, retention_days: int, count: int) -> None:
    """만료 7일 전 — Slack/Discord/WebSocket 사전 알림."""
    message = (
        f"⚠️ [데이터 보관 주기 만료 예정]\n"
        f"대상: {label}\n"
        f"보관 기간: {retention_days}일\n"
        f"7일 이내 삭제 예정 데이터: {count:,}건\n"
        f"관리자 페이지에서 내보내기 후 확인하세요."
    )
    _send_slack(message)
    _send_discord(message)
    _push_websocket_system(message, level='warning')


def _notify_retention_deleted(label: str, count: int) -> None:
    """삭제 완료 — Slack/Discord 알림."""
    message = (
        f"🗑️ [데이터 자동 삭제 완료]\n"
        f"대상: {label}\n"
        f"삭제 건수: {count:,}건"
    )
    _send_slack(message)
    _send_discord(message)
    _push_websocket_system(message, level='info')


def _send_slack(text: str) -> None:
    slack_url = settings.SLACK_WEBHOOK_URL
    if not slack_url:
        return
    try:
        requests.post(slack_url, json={'text': text}, timeout=5)
    except Exception as exc:
        logger.warning("Slack 발송 실패 (retention): %s", exc)


def _send_discord(text: str) -> None:
    discord_url = settings.DISCORD_WEBHOOK_URL
    if not discord_url:
        return
    try:
        requests.post(discord_url, json={'content': text}, timeout=5)
    except Exception as exc:
        logger.warning("Discord 발송 실패 (retention): %s", exc)


def _push_websocket_system(message: str, level: str = 'info') -> None:
    """슈퍼관리자/관리자 전용 WebSocket 시스템 알림 (system_alerts 그룹)."""
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'system_alerts',
            {
                'type': 'system_message',
                'data': {
                    'message': message,
                    'level': level,
                },
            },
        )
        logger.debug("WebSocket 시스템 알림 발송 완료")
    except Exception as exc:
        logger.warning("WebSocket 시스템 알림 실패 (retention): %s", exc)
