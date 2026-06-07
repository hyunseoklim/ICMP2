"""consume_gas_result — AI 엔진 가스 결과 stream(stream:gas:result) 소비 → DB 적재.

AI 엔진(ai-engine-gas)이 XADD한 결과를 group `result`로 읽어 DetectionResult/
ForecastSnapshot에 적재한다. consume_gas_stream(원천)과 대칭.

실행: python manage.py consume_gas_result
"""
import json
import logging
import time

import redis
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

STREAM = "stream:gas:result"
GROUP = "result"
CONSUMER = "c1"


class Command(BaseCommand):
    help = "AI 가스 결과 stream(stream:gas:result) 소비 → DetectionResult/ForecastSnapshot 적재"

    def handle(self, *args, **options):
        url = getattr(settings, "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
        r = redis.Redis.from_url(url)

        try:
            r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
            logger.info("소비그룹 생성 — %s/%s", STREAM, GROUP)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        from monitoring.result_ingest import store_result

        self.stdout.write(self.style.SUCCESS(f"consume_gas_result 시작 — {STREAM}/{GROUP}/{CONSUMER}"))

        while True:
            try:
                resp = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=50, block=5000)
            except Exception:
                logger.exception("XREADGROUP 실패 — 1초 후 재시도")
                time.sleep(1)
                continue

            if not resp:
                continue

            for _stream_name, messages in resp:
                for msg_id, fields in messages:
                    try:
                        raw = fields.get(b"payload") or fields.get("payload")
                        store_result(json.loads(raw))
                    except Exception:
                        logger.exception("가스 결과 처리 실패 — id=%s", msg_id)
                    finally:
                        r.xack(STREAM, GROUP, msg_id)
