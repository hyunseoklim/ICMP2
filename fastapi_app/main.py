import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from fastapi_app.fake_data import generate_sensor_data, generate_all_location_data, generate_power_data, generate_node_readings
from fastapi_app.sender import fetch_gas_devices, post_gas_reading, post_power_reading, post_location_reading, fetch_location_nodes, post_node_reading

# 연결된 클라이언트 목록
_clients: list[WebSocket] = []

# Django에서 가져온 가스 장비 목록 [{id, device_uid}, ...]
_devices: list[dict] = []
# Django에서 가져온 위치 노드 목록 [{node_code, x, y}, ...]
_nodes: list[dict] = []


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


async def _emit_once() -> None:
    for device in _devices:
        data = generate_sensor_data(device["id"], device["device_uid"])
        await _broadcast(data)
        await post_gas_reading(data)

    for _ in range(5):
        power = generate_power_data()
        await _broadcast(power)
        await post_power_reading(power)

    for location in generate_all_location_data():
        await _broadcast(location)
        await post_location_reading(location)

    if _nodes:
        for node_reading in generate_node_readings(_nodes):
            await post_node_reading(node_reading)


async def _data_loop() -> None:
    while True:
        await _emit_once()
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 Django 장비/노드 목록 로드
    devices = await fetch_gas_devices()
    _devices.extend(devices)

    nodes = await fetch_location_nodes()
    _nodes.extend(nodes)

    if _devices:
        print(f"[FastAPI] 가스 장비 {len(_devices)}개 로드 완료: {[d['device_uid'] for d in _devices]}")
    else:
        print("[FastAPI] 장비 없음 — Django에 가스 장비를 먼저 등록하세요")

    if _nodes:
        print(f"[FastAPI] 위치 노드 {len(_nodes)}개 로드 완료: {[n['node_code'] for n in _nodes]}")
    else:
        print("[FastAPI] 위치 노드 없음 — Django에 LocationNode를 먼저 등록하세요")

    task = asyncio.create_task(_data_loop())
    yield
    task.cancel()


app = FastAPI(title="ICMP2 실시간 데이터 서버", lifespan=lifespan)

Instrumentator(
    excluded_handlers=["/metrics", "/docs", "/openapi.json"]
).instrument(app).expose(app, endpoint="/metrics")

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


@app.post("/trigger")
async def trigger():
    await _emit_once()
    return {"status": "ok", "devices": len(_devices)}


@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(_clients), "devices": len(_devices)}


"""
FastAPI 진입점 (Phase 5에서 작성).

본 파일은 위치 예약용 자리표시자 — 기존 main.py와 충돌하지 않도록 .new 확장자 사용.
Phase 5 진입 시 기존 main.py와 병합하여 결정.

Phase 5에서 작성 예시:
    from fastapi import FastAPI
    from fastapi_app.routers import gas, power
    from fastapi_app.ai_engine.gas.modules.isolation_forest import GasIsolationForestDetector
    from fastapi_app.ai_engine.power.modules.isolation_forest import PowerIsolationForestDetector
    
    app = FastAPI(title="ICMP2 위험 판단 AI 엔진")
    
    # 시작 시 모델 로드 (결정 B 단일 학습 정책)
    @app.on_event("startup")
    def load_models():
        global gas_if_detector, power_if_detector
        gas_if_detector = GasIsolationForestDetector(...)
        gas_if_detector.load("fastapi_app/ai_engine/models/gas/iforest.joblib")
        power_if_detector = PowerIsolationForestDetector(...)
        power_if_detector.load("fastapi_app/ai_engine/models/power/iforest.joblib")
        # ARIMA 21개 로드 ...
    
    # 라우터 등록
    app.include_router(gas.router)
    app.include_router(power.router)
"""
