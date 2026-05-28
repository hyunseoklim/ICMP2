"""facilities 도메인 이벤트 발행자.

Redis Pub/Sub 채널 `facilities.events`로 이벤트를 발행한다.
청자는 자신을 등록할 뿐, 발행자는 청자의 존재를 모른다.
"""
import json
import logging
from dataclasses import asdict, is_dataclass

import redis
from django.conf import settings

from .definitions import FloorDimensionsChanged, FloorGridChanged

logger = logging.getLogger(__name__)

CHANNEL = "facilities.events"

_REGISTERED_EVENTS = {
    "FloorGridChanged": FloorGridChanged,
    "FloorDimensionsChanged": FloorDimensionsChanged,
}

_redis_client = None


def _client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        url = getattr(settings, "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
        _redis_client = redis.Redis.from_url(url)
    return _redis_client


def publish(event) -> None:
    if not is_dataclass(event):
        raise TypeError(f"event must be a dataclass, got {type(event).__name__}")
    type_name = type(event).__name__
    if type_name not in _REGISTERED_EVENTS:
        raise ValueError(f"Unknown event type: {type_name}")
    payload = {"type": type_name, **asdict(event)}
    try:
        _client().publish(CHANNEL, json.dumps(payload))
        logger.info("Published %s payload=%s", type_name, payload)
    except Exception:
        logger.exception("Failed to publish %s", type_name)
