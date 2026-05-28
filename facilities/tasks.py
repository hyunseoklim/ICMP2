"""facilities 도메인 Celery 태스크.

`consume_facilities_events`: Redis Pub/Sub `facilities.events` 채널을 구독하고
들어온 메시지를 events.handlers.dispatch로 라우팅한다.

`get_message(timeout=...)` 폴링으로 deadline을 정확히 지킨다.
`ps.listen()`은 메시지 미수신 시 무한 블록되어 worker thread를 점유하므로 사용하지 않는다.
"""
import json
import logging
import time

import redis
from celery import shared_task
from django.conf import settings

from .events.handlers import dispatch
from .events.publisher import CHANNEL

logger = logging.getLogger(__name__)

LISTEN_SEC = 30
POLL_INTERVAL_SEC = 1.0


@shared_task
def consume_facilities_events() -> None:
    redis_url = getattr(settings, "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    r = redis.Redis.from_url(redis_url)
    ps = r.pubsub()
    ps.subscribe(CHANNEL)
    logger.info("Subscribed to %s for %ss", CHANNEL, LISTEN_SEC)

    deadline = time.time() + LISTEN_SEC
    try:
        while time.time() < deadline:
            message = ps.get_message(timeout=POLL_INTERVAL_SEC)
            if message is None:
                continue
            if message.get("type") != "message":
                continue
            raw = message["data"]
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError):
                logger.warning("Pub/Sub 메시지 파싱 실패: %s", raw)
                continue
            dispatch(payload)
    finally:
        ps.unsubscribe(CHANNEL)
        ps.close()
