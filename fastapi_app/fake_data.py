import random
from datetime import datetime, timezone

# 작업자별 현재 위치 (x, y: 공장 지도 픽셀 좌표)
# seed_dummy 기준: W001 김철수, W002 이영희, W003 박민준, W004 최수진, W005 정도현
_worker_positions: dict[int, dict] = {
    1: {"x": 100.0, "y": 150.0, "name": "김철수"},
    2: {"x": 300.0, "y": 200.0, "name": "이영희"},
    3: {"x": 450.0, "y": 100.0, "name": "박민준"},
    4: {"x": 200.0, "y": 300.0, "name": "최수진"},
    5: {"x": 380.0, "y": 280.0, "name": "정도현"},
}

# 가스 정상 범위 (임계치 초과 알람 유도용)
_GAS_RANGES = {
    "co":  (0.0, 30.0),   # 간헐적으로 50 이상 → 위험
    "h2s": (0.0, 5.0),
    "co2": (300.0, 800.0),
    "o2":  (19.0, 21.0),
    "no2": (0.0, 1.0),
    "so2": (0.0, 1.0),
    "o3":  (0.0, 0.1),
    "nh3": (0.0, 10.0),
    "voc": (0.0, 50.0),
}

# 가끔 임계치 초과값 생성 (약 10% 확률)
def _spike(low: float, high: float) -> float:
    if random.random() < 0.1:
        return round(high * random.uniform(1.5, 2.5), 2)
    return round(random.uniform(low, high), 2)


def generate_sensor_data(device_id: int, device_uid: str) -> dict:
    return {
        "type": "sensor",
        "device_id": device_id,
        "device_uid": device_uid,
        "co":  _spike(*_GAS_RANGES["co"]),
        "h2s": _spike(*_GAS_RANGES["h2s"]),
        "co2": round(random.uniform(*_GAS_RANGES["co2"]), 2),
        "o2":  round(random.uniform(*_GAS_RANGES["o2"]), 2),
        "no2": round(random.uniform(*_GAS_RANGES["no2"]), 3),
        "so2": round(random.uniform(*_GAS_RANGES["so2"]), 3),
        "o3":  round(random.uniform(*_GAS_RANGES["o3"]), 3),
        "nh3": round(random.uniform(*_GAS_RANGES["nh3"]), 2),
        "voc": round(random.uniform(*_GAS_RANGES["voc"]), 2),
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


def generate_location_data() -> dict:
    worker_id = random.choice(list(_worker_positions.keys()))
    pos = _worker_positions[worker_id]

    # 조금씩 랜덤 이동 (공장 경계 0~600 클램프)
    pos["x"] = round(max(0, min(600, pos["x"] + random.uniform(-8, 8))), 2)
    pos["y"] = round(max(0, min(400, pos["y"] + random.uniform(-8, 8))), 2)

    return {
        "type": "location",
        "worker_id": worker_id,
        "worker_name": pos["name"],
        "x": pos["x"],
        "y": pos["y"],
    }
