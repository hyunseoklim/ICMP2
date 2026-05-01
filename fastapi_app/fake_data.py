import random
from datetime import datetime, timezone

# 작업자별 현재 위치
_worker_positions: dict[int, dict] = {
    1: {"x": 100.0, "y": 150.0, "name": "김철수"},
    2: {"x": 300.0, "y": 200.0, "name": "이영희"},
    3: {"x": 450.0, "y": 100.0, "name": "박민준"},
    4: {"x": 200.0, "y": 300.0, "name": "최수진"},
    5: {"x": 380.0, "y": 280.0, "name": "정도현"},
}

# ── 정상 범위 (임계치보다 충분히 낮게) ──────────────────────────
_GAS_RANGES = {
    "co":  (0.0,  20.0),   # 임계치 주의 25,   위험 200
    "h2s": (0.0,   8.0),   # 임계치 주의 10,   위험 15
    "co2": (300.0, 800.0), # 임계치 주의 1000, 위험 5000
    "o2":  (18.5,  23.0),  # 정상 18~23.5 (역방향)
    "no2": (0.0,   2.0),   # 임계치 주의 3,    위험 5
    "so2": (0.0,   1.5),   # 임계치 주의 2,    위험 5
    "o3":  (0.0,   0.04),  # 임계치 주의 0.06, 위험 0.12
    "nh3": (0.0,  20.0),   # 임계치 주의 25,   위험 35
    "voc": (0.0,   0.4),   # 임계치 주의 0.5,  위험 1.0
}

# 전력 채널 목록
_POWER_CHANNELS = [
    {"device_uid": "PWR-001", "channel_code": "slave01", "rated_w": 800},
    {"device_uid": "PWR-001", "channel_code": "slave02", "rated_w": 800},
    {"device_uid": "PWR-001", "channel_code": "slave11", "rated_w": 50},
    {"device_uid": "PWR-001", "channel_code": "slave12", "rated_w": 50},
    {"device_uid": "PWR-001", "channel_code": "slave21", "rated_w": 500},
    {"device_uid": "PWR-001", "channel_code": "slave22", "rated_w": 500},
    {"device_uid": "PWR-001", "channel_code": "slave31", "rated_w": 300},
    {"device_uid": "PWR-001", "channel_code": "slave32", "rated_w": 300},
    {"device_uid": "PWR-001", "channel_code": "slave41", "rated_w": 600},
    {"device_uid": "PWR-001", "channel_code": "slave42", "rated_w": 600},
    {"device_uid": "PWR-001", "channel_code": "slave51", "rated_w": 400},
    {"device_uid": "PWR-001", "channel_code": "slave52", "rated_w": 400},
    {"device_uid": "PWR-001", "channel_code": "slave61", "rated_w": 1000},
    {"device_uid": "PWR-001", "channel_code": "slave62", "rated_w": 1000},
    {"device_uid": "PWR-001", "channel_code": "slave71", "rated_w": 100},
    {"device_uid": "PWR-001", "channel_code": "slave72", "rated_w": 200},
    {"device_uid": "PWR-002", "channel_code": "slave01", "rated_w": 900},
    {"device_uid": "PWR-002", "channel_code": "slave02", "rated_w": 900},
    {"device_uid": "PWR-002", "channel_code": "slave11", "rated_w": 50},
    {"device_uid": "PWR-002", "channel_code": "slave12", "rated_w": 50},
    {"device_uid": "PWR-002", "channel_code": "slave21", "rated_w": 700},
    {"device_uid": "PWR-002", "channel_code": "slave22", "rated_w": 700},
    {"device_uid": "PWR-002", "channel_code": "slave31", "rated_w": 300},
    {"device_uid": "PWR-002", "channel_code": "slave32", "rated_w": 300},
]


# ── 스파이크 생성 ─────────────────────────────────────────────
def _spike(low: float, high: float, warn: float, danger: float) -> float:
    rand = random.random()
    if rand < 0.05:
        # 5% 확률 위험 수준 (danger 초과)
        return round(random.uniform(danger * 1.1, danger * 2.0), 3)
    elif rand < 0.15:
        # 10% 확률 주의 수준 (warn ~ danger 사이)
        return round(random.uniform(warn * 1.05, danger * 0.95), 3)
    else:
        # 85% 정상
        return round(random.uniform(low, high), 3)


# ── 가스 센서 데이터 생성 ─────────────────────────────────────
def generate_sensor_data(device_id: int, device_uid: str) -> dict:
    return {
        "type":       "gas_update",
        "device_id":  device_id,
        "device_uid": device_uid,
        # 스파이크 가능 가스 (임계치 명시)
        "co":  _spike(*_GAS_RANGES["co"],  warn=25.0,  danger=200.0),
        "h2s": _spike(*_GAS_RANGES["h2s"], warn=10.0,  danger=15.0),
        "co2": _spike(*_GAS_RANGES["co2"], warn=1000.0, danger=5000.0),
        "no2": _spike(*_GAS_RANGES["no2"], warn=3.0,   danger=5.0),
        "so2": _spike(*_GAS_RANGES["so2"], warn=2.0,   danger=5.0),
        "o3":  _spike(*_GAS_RANGES["o3"],  warn=0.06,  danger=0.12),
        "nh3": _spike(*_GAS_RANGES["nh3"], warn=25.0,  danger=35.0),
        "voc": _spike(*_GAS_RANGES["voc"], warn=0.5,   danger=1.0),
        # o2는 역방향이라 별도 처리 (18 이하 위험, 23.5 초과 주의)
        "o2":  _generate_o2(),
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


def _generate_o2() -> float:
    rand = random.random()
    if rand < 0.05:
        # 5% 위험 (16 미만)
        return round(random.uniform(12.0, 15.9), 2)
    elif rand < 0.15:
        # 10% 주의 (16~18)
        return round(random.uniform(16.0, 17.9), 2)
    elif rand < 0.20:
        # 5% 고농도 주의 (23.5 초과)
        return round(random.uniform(23.6, 25.0), 2)
    else:
        # 80% 정상 (18~23.5)
        return round(random.uniform(18.5, 23.0), 2)


# ── 전력 채널 데이터 생성 ─────────────────────────────────────
def generate_power_data() -> dict:
    ch = random.choice(_POWER_CHANNELS)
    rated_w = ch["rated_w"]

    rand = random.random()
    if rand < 0.05:
        # 5% 통신불능
        current_a, voltage_v, power_w = -1, -1, -1
    elif rand < 0.15:
        # 10% OFF
        current_a, voltage_v, power_w = 0, 0, 0
    elif rand < 0.25:
        # 10% 위험 (75% 초과)
        power_w   = round(random.uniform(rated_w * 0.76, rated_w * 1.2), 1)
        voltage_v = 220.0
        current_a = round(power_w / voltage_v, 1)
    elif rand < 0.40:
        # 15% 주의 (50~75%)
        power_w   = round(random.uniform(rated_w * 0.51, rated_w * 0.74), 1)
        voltage_v = 220.0
        current_a = round(power_w / voltage_v, 1)
    else:
        # 60% 정상 (0~50%)
        power_w   = round(random.uniform(0, rated_w * 0.49), 1)
        voltage_v = 220.0
        current_a = round(power_w / voltage_v, 1)

    return {
        "type":         "power_update",
        "device_uid":   ch["device_uid"],
        "channel_code": ch["channel_code"],
        "current_a":    current_a,
        "voltage_v":    voltage_v,
        "power_w":      power_w,
        "measured_at":  datetime.now(timezone.utc).isoformat(),
    }


# ── 작업자 위치 데이터 생성 ───────────────────────────────────
def generate_location_data() -> dict:
    worker_id = random.choice(list(_worker_positions.keys()))
    pos = _worker_positions[worker_id]

    pos["x"] = round(max(0, min(600, pos["x"] + random.uniform(-8, 8))), 2)
    pos["y"] = round(max(0, min(400, pos["y"] + random.uniform(-8, 8))), 2)

    return {
        "type":        "location",
        "worker_id":   worker_id,
        "worker_name": pos["name"],
        "x":           pos["x"],
        "y":           pos["y"],
    }


def generate_all_location_data(floor_id: int = 1) -> list[dict]:
    """전체 작업자 위치를 한꺼번에 업데이트해서 반환"""
    result = []
    for worker_id, pos in _worker_positions.items():
        pos["x"] = round(max(0, min(600, pos["x"] + random.uniform(-8, 8))), 2)
        pos["y"] = round(max(0, min(400, pos["y"] + random.uniform(-8, 8))), 2)
        result.append({
            "type":        "location",
            "worker_id":   worker_id,
            "worker_name": pos["name"],
            "x":           pos["x"],
            "y":           pos["y"],
            "floor_id":    floor_id,
        })
    return result