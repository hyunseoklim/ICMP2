import httpx

DJANGO_BASE = "http://localhost:8000"

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
    payload = {
        "device": data["device_id"],
        "co":  data["co"],
        "h2s": data["h2s"],
        "co2": data["co2"],
        "o2":  data["o2"],
        "no2": data["no2"],
        "so2": data["so2"],
        "o3":  data["o3"],
        "nh3": data["nh3"],
        "voc": data["voc"],
        "measured_at": data["measured_at"],
    }
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            await client.post(f"{DJANGO_BASE}/monitoring/api/gas-readings/", json=payload)
            print(f"[sender] GasReading POST 성공: {payload['device']}")
        except Exception as e:
            print(f"[sender] GasReading POST 실패: {e}")
