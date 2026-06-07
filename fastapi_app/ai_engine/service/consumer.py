"""consumer — raw stream 소비 루프 (AI 엔진 서비스).

fan-out(A안): Django ingest와 별도 consumer group(`*_ai`)으로 같은 raw stream을
독립 커서로 소비한다. 따라서 기존 ingest 소비에 영향이 없다.

범위(F1-2): raw를 안전히 소비하고 XACK까지. 분석(F1-3)·결과발행(F1-4)은
`handler`를 통해 주입되며, 현재 기본 핸들러는 trace_id 로그만 남긴다.

패턴은 monitoring/management/commands/consume_gas_stream.py 를 따르되 async
(redis.asyncio)로 작성한다.
"""
import asyncio
import json
import logging
import os
from typing import Awaitable, Callable

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from . import domain

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CONSUMER = "c1"

_COUNT = 20
_BLOCK_MS = 5000

# 핸들러 시그니처: async (stream, payload_dict) -> None
Handler = Callable[[str, dict], Awaitable[None]]


async def _log_handler(stream: str, payload: dict) -> None:
    """기본 핸들러(F1-2) — 소비 검증용 로그만. F1-3/4에서 분석·발행 핸들러로 교체."""
    logger.info("[ai-engine] 소비 %s trace_id=%s", stream, payload.get("trace_id"))


async def _ensure_group(r: "aioredis.Redis", stream: str, group: str) -> None:
    try:
        await r.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info("[ai-engine] 소비그룹 생성 — %s/%s", stream, group)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def consume(r: "aioredis.Redis", stream: str, group: str, handler: Handler) -> None:
    """단일 stream 소비 루프 — XREADGROUP → 디코드 → handler → XACK."""
    await _ensure_group(r, stream, group)
    logger.info("[ai-engine] consume 시작 — %s/%s/%s", stream, group, CONSUMER)
    while True:
        try:
            resp = await r.xreadgroup(
                group, CONSUMER, {stream: ">"}, count=_COUNT, block=_BLOCK_MS
            )
        except Exception as e:  # 연결 단절 등 — 로그 후 재시도
            logger.error("[ai-engine] xreadgroup 실패 %s: %s", stream, e)
            await asyncio.sleep(1)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                try:
                    payload = json.loads(fields["payload"])
                    results = await handler(stream, payload)
                    for res in (results or []):  # 분석 결과 → result stream 발행 (F1-4)
                        await r.xadd(
                            domain.RESULT_STREAM,
                            {"payload": json.dumps(res, ensure_ascii=False, default=str)},
                            maxlen=10000, approximate=True,
                        )
                except Exception as e:  # 개별 메시지 예외 = 로그+스킵(파이프라인 정지 안 함)
                    logger.warning("[ai-engine] 메시지 처리 실패 %s id=%s: %s", stream, msg_id, e)
                finally:
                    await r.xack(stream, group, msg_id)


async def run(handler: Handler = _log_handler) -> None:
    """이 컨테이너 도메인(AI_DOMAIN)의 raw stream만 소비한다 (수직 분리)."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await consume(r, domain.RAW_STREAM, domain.AI_GROUP, handler)
    finally:
        await r.aclose()
