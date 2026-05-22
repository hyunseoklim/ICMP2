import httpx
import os

DJANGO_BASE = os.environ.get("DJANGO_BASE", "http://localhost:8000")

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
            print(f"[sender] Django 장비 조회 실패: {e}")
            return []


async def post_gas_reading(data: dict) -> None:
    # device_uid 기준으로 전송 (ingest_gas 함수가 device_uid로 장비 조회)
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
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            await client.post(
                f"{DJANGO_BASE}/monitoring/api/gas-readings/",
                json=payload,
            )
            print(f"[sender] GasReading POST 성공: {data['device_uid']}")
        except Exception as e:
            print(f"[sender] GasReading POST 실패: {e}")


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
            print(f"[sender] PowerReading POST 성공: {data['device_uid']} {data['channel_code']}")
        except Exception as e:
            print(f"[sender] PowerReading POST 실패: {e}")


async def fetch_location_nodes() -> list[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(f"{DJANGO_BASE}/facilities/api/location-nodes/")
            res.raise_for_status()
            data = res.json()
            results = data.get("results", data) if isinstance(data, dict) else data
            return [{"node_code": n["node_code"], "x": n["x"], "y": n["y"]} for n in results]
        except Exception as e:
            print(f"[sender] LocationNode 조회 실패: {e}")
            return []


async def post_node_reading(data: dict) -> None:
    payload = {"node_code": data["node_code"], "x": data["x"], "y": data["y"]}
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            await client.post(f"{DJANGO_BASE}/monitoring/api/node-readings/", json=payload)
            print(f"[sender] NodeReading POST 성공: {data['node_code']}")
        except Exception as e:
            print(f"[sender] NodeReading POST 실패: {e}")


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
            print(f"[sender] WorkerLocation POST 성공: worker_id={data['worker_id']}")
        except Exception as e:
            print(f"[sender] WorkerLocation POST 실패: {e}")