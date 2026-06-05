import asyncio
import json
import logging
import os
import uuid

import httpx
import redis

logger = logging.getLogger(__name__)

DJANGO_BASE = os.environ.get("DJANGO_BASE", "http://localhost:8000")
REDIS_URL   = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# 가스 원천 Redis Stream (단계별 파이프라인 전송)
GAS_STREAM = "stream:gas:raw"
_redis_stream = None


def _stream_client() -> "redis.Redis":
    global _redis_stream
    if _redis_stream is None:
        _redis_stream = redis.Redis.from_url(REDIS_URL)
    return _redis_stream


# 원천 경계 값 검증 (범위·결측) — 검증된 데이터만(태그 달고) 하류로
GAS_FIELDS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']
GAS_VALID_RANGE = {
    'co': (0, 10000), 'h2s': (0, 1000), 'co2': (0, 50000),
    'o2':  (0, 30),   'no2': (0, 1000), 'so2': (0, 1000),
    'o3':  (0, 100),  'nh3': (0, 1000), 'voc': (0, 10000),
}


def _validate_gas(payload: dict):
    """범위·결측 검증 → (quality_flag, violations). 위반은 버리지 않고 태깅."""
    violations = [
        f for f in GAS_FIELDS
        if payload.get(f) is not None
        and not (GAS_VALID_RANGE[f][0] <= float(payload[f]) <= GAS_VALID_RANGE[f][1])
    ]
    missing = sum(1 for f in GAS_FIELDS if payload.get(f) is None)
    if violations:
        quality_flag = 'invalid'
    elif missing == len(GAS_FIELDS):
        quality_flag = 'missing'
    elif missing:
        quality_flag = 'partial'
    else:
        quality_flag = 'ok'
    return quality_flag, violations


async def xadd_gas_reading(data: dict) -> None:
    """가스 원천 1건을 Redis Stream에 적재 (XADD). consumer가 단계별 처리."""
    payload = {
        "device_uid":  data["device_uid"],
        "measured_at": data["measured_at"],
        "co":  data["co"],  "h2s": data["h2s"], "co2": data["co2"],
        "o2":  data["o2"],  "no2": data["no2"], "so2": data["so2"],
        "o3":  data["o3"],  "nh3": data["nh3"], "voc": data["voc"],
    }
    # ── 원천 경계: 값 검증 + trace_id 부여 (tick_id는 보류) ──
    quality_flag, violations = _validate_gas(payload)
    payload["trace_id"]     = str(uuid.uuid4())   # reading 1건당 계보 키
    payload["quality_flag"] = quality_flag
    if violations:
        payload["violations"] = violations
    try:
        await asyncio.to_thread(
            _stream_client().xadd,
            GAS_STREAM, {"payload": json.dumps(payload)},
            maxlen=10000, approximate=True,
        )
        logger.info("Redis Stream XADD 성공: %s", data['device_uid'])
    except Exception as e:
        logger.error("Redis Stream XADD 실패: %s", e)


# 전력 원천 Redis Stream (가스 패턴 미러)
POWER_STREAM = "stream:power:raw"
POWER_FIELDS = ['current_a', 'voltage_v', 'power_w']
POWER_VALID_RANGE = {'current_a': (0, 1000), 'voltage_v': (0, 500), 'power_w': (0, 1_000_000)}


def _validate_power(payload: dict):
    """전력 값 검증. -1=통신불능(comm_err), 0=OFF(정상). 범위위반=invalid."""
    vals = [payload.get(f, -1.0) for f in POWER_FIELDS]
    if all(v in (-1, -1.0) for v in vals):
        return 'comm_err', []
    violations = [
        f for f in POWER_FIELDS
        if payload.get(f) not in (None, -1, -1.0)
        and not (POWER_VALID_RANGE[f][0] <= float(payload[f]) <= POWER_VALID_RANGE[f][1])
    ]
    if violations:
        return 'invalid', violations
    if any(v in (-1, -1.0) for v in vals):
        return 'partial', []
    return 'ok', []


async def xadd_power_reading(data: dict) -> None:
    """전력 원천 1건을 Redis Stream에 적재 (XADD). consume_power_stream이 단계별 처리."""
    payload = {
        "device_uid":   data["device_uid"],
        "channel_code": data["channel_code"],
        "measured_at":  data.get("measured_at"),
        "current_a":    data["current_a"],
        "voltage_v":    data["voltage_v"],
        "power_w":      data["power_w"],
    }
    quality_flag, violations = _validate_power(payload)
    payload["trace_id"]     = str(uuid.uuid4())
    payload["quality_flag"] = quality_flag
    if violations:
        payload["violations"] = violations
    try:
        await asyncio.to_thread(
            _stream_client().xadd,
            POWER_STREAM, {"payload": json.dumps(payload)},
            maxlen=10000, approximate=True,
        )
    except Exception as e:
        logger.error("power XADD 실패: %s", e)

# 시작 시 Django에서 가스 장비 목록을 가져옴
# 반환값: [{"id": 1, "device_uid": "AA:BB:CC"}, ...]
async def fetch_gas_devices() -> list[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(
                f"{DJANGO_BASE}/monitoring/api/devices/",
                params={"device_type": "gas"},
            )
            res.raise_for_status()
            data = res.json()
            results = data.get("results", data) if isinstance(data, dict) else data
            return [{"id": d["id"], "device_uid": d["device_uid"]} for d in results]
        except Exception as e:
            logger.error("Django 장비 조회 실패: %s", e)
            return []


async def post_power_reading(data: dict) -> None:
    payload = {
        "device_uid":   data["device_uid"],
        "channel_code": data["channel_code"],
        "measured_at":  data.get("measured_at"),
        "current_a":    data["current_a"],
        "voltage_v":    data["voltage_v"],
        "power_w":      data["power_w"],
    }
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            await client.post(
                f"{DJANGO_BASE}/monitoring/api/power-readings/",
                json=payload,
            )
            logger.info("PowerReading POST 성공: %s %s", data['device_uid'], data['channel_code'])
        except Exception as e:
            logger.error("PowerReading POST 실패: %s", e)


async def fetch_location_nodes() -> list[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(f"{DJANGO_BASE}/facilities/api/location-nodes/")
            res.raise_for_status()
            data = res.json()
            results = data.get("results", data) if isinstance(data, dict) else data
            return [{"node_code": n["node_code"], "x": n["x"], "y": n["y"]} for n in results]
        except Exception as e:
            logger.error("LocationNode 조회 실패: %s", e)
            return []


async def post_node_reading(data: dict) -> None:
    payload = {"node_code": data["node_code"], "x": data["x"], "y": data["y"]}
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            await client.post(f"{DJANGO_BASE}/monitoring/api/node-readings/", json=payload)
            logger.info("NodeReading POST 성공: %s", data['node_code'])
        except Exception as e:
            logger.error("NodeReading POST 실패: %s", e)


async def post_location_reading(data: dict) -> None:
    payload = {
        "worker_id": data["worker_id"],
        "x":         data["x"],
        "y":         data["y"],
        "floor_id":  data.get("floor_id", 1),
    }
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            await client.post(
                f"{DJANGO_BASE}/facilities/api/worker-locations/dummy/",
                json=payload,
            )
            logger.info("WorkerLocation POST 성공: worker_id=%s", data['worker_id'])
        except Exception as e:
            logger.error("WorkerLocation POST 실패: %s", e)