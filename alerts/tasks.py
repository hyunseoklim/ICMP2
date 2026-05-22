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
        process_gas_ingest(device_uid, payload)
        logger.debug("ingest_gas_task 완료 — device=%s", device_uid)
    except Exception as exc:
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
        from alerts.services import trigger_forecast_alarms

        results = run_forecast(device_uid, payload)
        if not results:
            return  # idempotency 가드에 의해 skip됨
        device = Device.objects.filter(device_uid=device_uid).first()
        if device:
            trigger_forecast_alarms(device, results)
        logger.debug("forecast_gas_task 완료 — device=%s", device_uid)
    except Exception as exc:
        logger.error("forecast_gas_task 실패 — device=%s: %s", device_uid, exc)
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
    except Exception as exc:
        logger.error("Pub/Sub 처리 실패 — device=%s: %s", device_uid, exc)
