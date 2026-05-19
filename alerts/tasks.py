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
