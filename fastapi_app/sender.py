import asyncio
import logging
import os

import httpx
from celery import Celery

logger = logging.getLogger(__name__)

DJANGO_BASE = os.environ.get("DJANGO_BASE", "http://localhost:8000")
REDIS_URL   = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Django 없이 태스크 큐잉만 담당하는 Celery 클라이언트
_celery = Celery(broker=REDIS_URL)

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


async def purge_story_data(device_uids: list[str]) -> None:
    """스토리 재시작 직전 대상 장비의 누적 시계열·예측을 Django에서 삭제.

    차트는 DB 최신 N개를 폴링해 그리므로, DB를 비우지 않으면 새 회차에도
    직전 추세가 잔류한다(앱 프로세스 재시작과 무관 — 데이터는 DB에 있음).
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(
                f"{DJANGO_BASE}/monitoring/api/story/purge/",
                json={"device_uids": device_uids},
            )
            res.raise_for_status()
            logger.info("스토리 데이터 purge 성공: %s", res.json().get("deleted"))
        except Exception as e:
            logger.error("스토리 데이터 purge 실패: %s", e)


async def queue_gas_reading(data: dict) -> None:
    payload = {
        "device_uid":  data["device_uid"],
        "measured_at": data["measured_at"],
        "co":  data["co"],
        "h2s": data["h2s"],
        "co2": data["co2"],
        "o2":  data["o2"],
        "no2": data["no2"],
        "so2": data["so2"],
        "o3":  data["o3"],
        "nh3": data["nh3"],
        "voc": data["voc"],
    }
    try:
        # send_task는 Redis에 쓰기만 하므로 to_thread로 이벤트 루프 블로킹 방지
        await asyncio.to_thread(
            _celery.send_task,
            'alerts.tasks.ingest_gas_task',
            args=[payload],
        )
        logger.info("Celery 큐 전송 성공: %s", data['device_uid'])
    except Exception as e:
        logger.error("Celery 큐 전송 실패: %s", e)


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