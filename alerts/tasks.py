import logging

import requests
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings

logger = logging.getLogger(__name__)


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

    severity_emoji = {'danger': '🔴', 'warning': '🟡', 'anomaly': '🟠', 'predictive_warning': '🔵'}.get(
        event.severity, '⚪'
    )
    text = (
        f"{severity_emoji} *[ICMP2 알림]* {event.title}\n"
        f"> {event.message}\n"
        f"> 시설: {event.facility or '-'}  |  발생: {event.occurred_at.strftime('%Y-%m-%d %H:%M:%S')}"
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

    color_map = {'danger': 0xFF0000, 'warning': 0xFFCC00, 'anomaly': 0xFF8800, 'predictive_warning': 0x0088FF}
    payload = {
        'embeds': [{
            'title': event.title,
            'description': event.message,
            'color': color_map.get(event.severity, 0xAAAAAA),
            'fields': [
                {'name': '시설', 'value': str(event.facility or '-'), 'inline': True},
                {'name': '발생 시각', 'value': event.occurred_at.strftime('%Y-%m-%d %H:%M:%S'), 'inline': True},
            ],
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
    """AlarmEvent 발생 시 모든 채널 알림 발송 (중복 방지 포함)."""
    from django.core.cache import cache

    from .models import AlarmEvent
    try:
        event = AlarmEvent.objects.select_related('rule', 'facility').get(pk=event_id)
    except AlarmEvent.DoesNotExist:
        return

    rule_id = event.rule_id or 0
    facility_id = event.facility_id or 0
    dedup_key = f"alarm:dedup:{rule_id}:{facility_id}"

    if cache.get(dedup_key):
        logger.info("중복 알람 방지 — event=%s key=%s", event_id, dedup_key)
        return

    cache.set(dedup_key, 1, timeout=300)  # 5분 쿨다운

    push_websocket_alert.delay(event_id)
    send_slack_notification.delay(event_id)
    send_discord_notification.delay(event_id)


# ---------------------------------------------------------------------------
# A. AI 추론 요청 + 알림 발송 오케스트레이터
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def process_alarm_event(self, event_id: int):
    """
    AlarmEvent 생성 후 AI 서버에 추론을 요청하고, 결과를 이벤트에 반영한 뒤 알림을 발송한다.
    AI_SERVER_URL 미설정 시 AI 단계를 건너뛰고 알림만 발송한다.
    """
    from django.conf import settings
    from django.core.cache import cache

    from .models import AlarmEvent

    try:
        event = AlarmEvent.objects.select_related('rule', 'facility', 'device').get(pk=event_id)
    except AlarmEvent.DoesNotExist:
        logger.warning("process_alarm_event: AlarmEvent %s 없음", event_id)
        return

    ai_server_url = getattr(settings, 'AI_SERVER_URL', '')

    if ai_server_url:
        # --- AI 추론 요청 (엔드포인트 확정 후 payload/URL 교체) ---
        ai_endpoint = f"{ai_server_url.rstrip('/')}/predict"
        payload = {
            'event_id':   event_id,
            'event_type': event.event_type,
            'severity':   event.severity,
            'device_id':  event.device_id,
            'facility_id': event.facility_id,
            'message':    event.message,
        }
        try:
            resp = requests.post(ai_endpoint, json=payload, timeout=10)
            resp.raise_for_status()
            ai_result = resp.json()

            # AI 결과로 severity/message 보강 (팀원1 응답 스펙 확정 후 키 수정)
            new_severity = ai_result.get('severity')
            ai_note      = ai_result.get('message', '')
            update_fields = []
            if new_severity and new_severity != event.severity:
                event.severity = new_severity
                update_fields.append('severity')
            if ai_note:
                event.message = f"[AI] {ai_note}\n{event.message}"
                update_fields.append('message')
            if update_fields:
                update_fields.append('updated_at')
                event.save(update_fields=update_fields)

        except Exception as exc:
            logger.error("AI 추론 요청 실패 (event=%s): %s", event_id, exc)
            # AI 서버 장애 알림 (중복 방지 5분)
            ai_down_key = 'ai_server:down_notified'
            if not cache.get(ai_down_key):
                cache.set(ai_down_key, 1, timeout=300)
                notify_ai_server_down.delay(str(exc))
            # AI 실패해도 알림 발송은 계속 진행
    else:
        logger.debug("AI_SERVER_URL 미설정 — AI 추론 단계 건너뜀 (event=%s)", event_id)

    send_all_notifications.delay(event_id)


# ---------------------------------------------------------------------------
# C. AI 서버 장애 알림
# ---------------------------------------------------------------------------

@shared_task
def notify_ai_server_down(error_msg: str = ''):
    """AI 서버 응답 실패 시 Slack/Discord로 담당자에게 알림."""
    from django.conf import settings
    from django.utils import timezone

    text = (
        f"🚨 *[ICMP2 시스템 경고]* AI 서버 응답 실패\n"
        f"> {error_msg or '알 수 없는 오류'}\n"
        f"> 발생 시각: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    slack_url = getattr(settings, 'SLACK_WEBHOOK_URL', '')
    if slack_url:
        try:
            requests.post(slack_url, json={'text': text}, timeout=5)
        except Exception as exc:
            logger.warning("AI 장애 Slack 알림 실패: %s", exc)

    discord_url = getattr(settings, 'DISCORD_WEBHOOK_URL', '')
    if discord_url:
        payload = {
            'embeds': [{
                'title': 'AI 서버 응답 실패',
                'description': error_msg or '알 수 없는 오류',
                'color': 0xFF0000,
                'fields': [{'name': '발생 시각', 'value': timezone.now().strftime('%Y-%m-%d %H:%M:%S')}],
            }]
        }
        try:
            requests.post(discord_url, json=payload, timeout=5)
        except Exception as exc:
            logger.warning("AI 장애 Discord 알림 실패: %s", exc)


# ---------------------------------------------------------------------------
# B. Redis Pub/Sub 수신 → process_alarm_event 트리거
# ---------------------------------------------------------------------------

@shared_task
def consume_redis_pubsub():
    """
    Redis Pub/Sub 채널을 구독하여 수신된 센서 이벤트를 처리한다.
    채널명은 settings.REDIS_PUBSUB_CHANNEL (기본값: 'sensor_events').
    팀원2가 채널명 확정 시 settings.py의 REDIS_PUBSUB_CHANNEL 값만 교체하면 된다.

    사용법: celery -A config worker 실행 후
            celery -A config call alerts.tasks.consume_redis_pubsub
            또는 Celery Beat 스케줄로 주기 실행.
    """
    import json

    import redis
    from django.conf import settings

    redis_url   = getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/1')
    channel     = getattr(settings, 'REDIS_PUBSUB_CHANNEL', 'sensor_events')
    timeout_sec = getattr(settings, 'REDIS_PUBSUB_TIMEOUT', 30)

    r  = redis.Redis.from_url(redis_url)
    ps = r.pubsub()
    ps.subscribe(channel)
    logger.info("Redis Pub/Sub 구독 시작 — channel=%s", channel)

    deadline = __import__('time').time() + timeout_sec
    for message in ps.listen():
        if __import__('time').time() > deadline:
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
    팀원2가 Redis에 publish하는 메시지를 받아 AlarmEvent를 생성하고
    process_alarm_event task를 트리거한다.

    예상 메시지 형식 (팀원2 확정 후 필드명 조정):
    {
        "event_type": "gas"|"power"|"device",
        "device_id": 123,
        "facility_id": 456,
        "severity": "danger"|"warning"|"anomaly",
        "title": "CO 농도 이상 감지",
        "message": "CO: 55ppm (위험)",
        "current_value": 55.0
    }
    """
    from .models import AlarmEvent, AlarmRule
    from .services import create_alarm_event

    device_id   = data.get('device_id')
    facility_id = data.get('facility_id')
    severity    = data.get('severity', AlarmEvent.Severity.WARNING)
    title       = data.get('title', '센서 이상 감지')
    message     = data.get('message', '')
    current_val = data.get('current_value')

    if not device_id or not facility_id:
        logger.warning("Pub/Sub 메시지 필수 필드 누락: %s", data)
        return

    try:
        from monitoring.models import Device
        from facilities.models import Facility
        device   = Device.objects.get(pk=device_id)
        facility = Facility.objects.get(pk=facility_id)
    except Exception as exc:
        logger.warning("Pub/Sub device/facility 조회 실패: %s", exc)
        return

    rule = AlarmRule.objects.filter(is_active=True).first()
    if not rule:
        logger.warning("활성 AlarmRule 없음 — Pub/Sub 이벤트 무시")
        return

    event = create_alarm_event(
        rule=rule,
        facility=facility,
        severity=severity,
        title=title,
        device=device,
        message=message,
        current_value=current_val,
    )
    # create_alarm_event 내부에서 send_all_notifications.delay() 호출됨.
    # AI 추론도 원하면 아래 주석 해제:
    # process_alarm_event.delay(event.id)
