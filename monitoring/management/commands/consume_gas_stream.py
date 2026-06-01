"""consume_gas_stream — 가스 원천 Redis Stream 소비자.

FastAPI가 XADD한 stream:gas:raw 를 소비그룹으로 읽어 단계별 파이프라인에 투입한다.
Pub/Sub(레거시)·celery 직접 큐잉을 대체하는 전송 계층.

Slice 1.5(전송만): 기존 process_gas_ingest를 그대로 호출해 스트림 흐름을 검증한다.
Slice 2에서 이 호출부를 단계별(유효성→threshold→z-score→DetectionResult) 로직으로 교체.

실행: python manage.py consume_gas_stream
"""
import json
import logging

import redis
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

STREAM = "stream:gas:raw"
GROUP = "gas_ingest"
CONSUMER = "c1"


class Command(BaseCommand):
    help = "가스 원천 Redis Stream(stream:gas:raw) 소비 → 단계별 파이프라인 투입"

    def handle(self, *args, **options):
        url = getattr(settings, "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
        r = redis.Redis.from_url(url)

        # 소비그룹 생성 (스트림 없으면 같이 생성). 이미 있으면 무시.
        try:
            r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
            logger.info("소비그룹 생성 — %s/%s", STREAM, GROUP)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        from monitoring.services import process_gas_ingest

        self.stdout.write(self.style.SUCCESS(f"consume_gas_stream 시작 — {STREAM}/{GROUP}/{CONSUMER}"))
        logger.info("consume_gas_stream 시작 — %s/%s", STREAM, GROUP)

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
                        if not device_uid:
                            logger.warning("payload device_uid 없음 — id=%s", msg_id)
                        else:
                            process_gas_ingest(device_uid, payload)
                    except Exception:
                        logger.exception("가스 스트림 처리 실패 — id=%s", msg_id)
                    finally:
                        # poison 메시지 무한 재처리 방지 — 처리 시도 후 ACK
                        r.xack(STREAM, GROUP, msg_id)
