"""consume_power_stream — 전력 원천 Redis Stream 소비자 (가스 패턴 미러).

FastAPI가 XADD한 stream:power:raw 를 소비그룹으로 읽어 단계별 파이프라인에 투입한다.
HTTP POST 경로를 대체하는 전송 계층.

실행: python manage.py consume_power_stream
"""
import json
import logging

import redis
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

STREAM = "stream:power:raw"
GROUP = "power_ingest"
CONSUMER = "c1"


class Command(BaseCommand):
    help = "전력 원천 Redis Stream(stream:power:raw) 소비 → 단계별 파이프라인 투입"

    def handle(self, *args, **options):
        url = getattr(settings, "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
        r = redis.Redis.from_url(url)

        try:
            r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
            logger.info("소비그룹 생성 — %s/%s", STREAM, GROUP)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        from monitoring.services import process_power_ingest

        self.stdout.write(self.style.SUCCESS(f"consume_power_stream 시작 — {STREAM}/{GROUP}/{CONSUMER}"))
        logger.info("consume_power_stream 시작 — %s/%s", STREAM, GROUP)

        while True:
            try:
                resp = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=20, block=5000)
            except Exception:
                logger.exception("XREADGROUP 실패 — 1초 후 재시도")
                import time
                time.sleep(1)
                continue

            if not resp:
                continue

            for _stream_name, messages in resp:
                for msg_id, fields in messages:
                    try:
                        raw = fields.get(b"payload") or fields.get("payload")
                        payload = json.loads(raw)
                        device_uid = payload.get("device_uid")
                        channel_code = payload.get("channel_code")
                        if not device_uid or not channel_code:
                            logger.warning("payload device_uid/channel_code 없음 — id=%s", msg_id)
                        else:
                            process_power_ingest(device_uid, channel_code, payload)
                    except Exception:
                        logger.exception("전력 스트림 처리 실패 — id=%s", msg_id)
                    finally:
                        r.xack(STREAM, GROUP, msg_id)
