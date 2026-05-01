import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from fastapi_app.fake_data import generate_sensor_data, generate_all_location_data, generate_power_data
from fastapi_app.sender import fetch_gas_devices, post_gas_reading, post_power_reading, post_location_reading

# 연결된 클라이언트 목록
_clients: list[WebSocket] = []

# Django에서 가져온 가스 장비 목록 [{id, device_uid}, ...]
_devices: list[dict] = []


async def _broadcast(message: dict) -> None:
    text = json.dumps(message, ensure_ascii=False)
    dead = []
    for ws in _clients:
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.remove(ws)


async def _data_loop() -> None:
    """60초마다 센서 데이터 + 전력 데이터 + 위치 데이터 broadcast"""
    while True:
        # 가스 센서 데이터
        for device in _devices:
            data = generate_sensor_data(device["id"], device["device_uid"])
            await _broadcast(data)
            await post_gas_reading(data)

        # 전력 데이터 (채널별로 여러 번)
        for _ in range(5):  # 한 루프에 5개 채널 데이터 전송
            power = generate_power_data()
            await _broadcast(power)
            await post_power_reading(power)

        # 위치 데이터 - 전체 작업자 한꺼번에
        for location in generate_all_location_data():
            await _broadcast(location)
            await post_location_reading(location)

        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 Django 장비 목록 로드
    devices = await fetch_gas_devices()
    _devices.extend(devices)

    if _devices:
        print(f"[FastAPI] 장비 {len(_devices)}개 로드 완료: {[d['device_uid'] for d in _devices]}")
    else:
        print("[FastAPI] 장비 없음 — Django에 가스 장비를 먼저 등록하세요")

    task = asyncio.create_task(_data_loop())
    yield
    task.cancel()


app = FastAPI(title="ICMP2 실시간 데이터 서버", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.append(ws)
    print(f"[WS] 연결됨 — 현재 {len(_clients)}명")
    try:
        while True:
            await ws.receive_text()  # 연결 유지 (클라이언트 ping 수신용)
    except WebSocketDisconnect:
        _clients.remove(ws)
        print(f"[WS] 해제됨 — 현재 {len(_clients)}명")


@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(_clients), "devices": len(_devices)}
