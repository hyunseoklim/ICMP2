import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

# 앱 로그를 stdout으로 — 미설정 시 root 기본(WARNING)이라 INFO 로그가 안 보였다.
# LOG_LEVEL env로 조정 가능(기본 INFO). uvicorn 자체 로거와 별개로 동작.
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from fastapi_app.fake_data import generate_sensor_data, generate_all_location_data, generate_all_power_data, generate_node_readings
from fastapi_app import fake_data2
from fastapi_app.sender import fetch_gas_devices, queue_gas_reading, post_power_reading, post_location_reading, fetch_location_nodes, post_node_reading

# 데이터 생성 독립 플래그 (둘 다 켜면 동시 실행) — env로 토글, 재빌드 불필요.
#   ENABLE_LOAD  : fake_data(랜덤 부하) 생성기
#   ENABLE_STORY : fake_data2(통합 검증 스토리) 생성기
def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")

ENABLE_LOAD  = _truthy(os.environ.get("ENABLE_LOAD",  "false"))
ENABLE_STORY = _truthy(os.environ.get("ENABLE_STORY", "true"))
STORY_TICK_SECONDS = float(os.environ.get("STORY_TICK_SECONDS", "2"))

# 웹소켓에 연결된 클라이언트 목록
_clients: list[WebSocket] = []

# Django에서 가져온 가스 장비 목록 [{id, device_uid}, ...]
_devices: list[dict] = []
# Django에서 가져온 위치 노드 목록 [{node_code, x, y}, ...]
_nodes: list[dict] = []

# 실행 중인 스토리 재생 태스크 핸들 — /story/restart 에서 취소·재시작에 사용.
_story_task: "asyncio.Task | None" = None


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
        await queue_gas_reading(data)

    for power in generate_all_power_data():
        await _broadcast(power)
        await post_power_reading(power)

    for location in generate_all_location_data():
        await _broadcast(location)
        await post_location_reading(location)

    if _nodes:
        for node_reading in generate_node_readings(_nodes):
            await post_node_reading(node_reading)

#data_loop는 none이 default이며 데이터 loop가 변경되면 _emit_once하고 60초 주기로 한다.
async def _data_loop() -> None:
    while True:
        if not _devices:
            devices = await fetch_gas_devices()
            if devices:
                _devices.extend(devices)
                logger.info("가스 장비 재로드 완료: %s", [d['device_uid'] for d in _devices])
        if not _nodes:
            nodes = await fetch_location_nodes()
            if nodes:
                _nodes.extend(nodes)
                logger.info("위치 노드 재로드 완료: %s", [n['node_code'] for n in _nodes])
        await _emit_once()
        await asyncio.sleep(60)


async def _story_loop() -> None:
    """통합 검증 스토리(fake_data2) 1회 가속 재생.

    load 모드의 _emit_once(전체 장비·채널·작업자 송신) 대신, 스토리 대상만
    (GAS-001·PWR-001/slave61·작업자5) 1 논리분=1 tick으로 STORY_TICK_SECONDS
    간격으로 송신한다. 송신 경로(sender)는 load와 동일 — 파이프라인 보존.
    """
    logger.info("STORY 모드 시작 — tick=%ss, %d~%d분",
                STORY_TICK_SECONDS, fake_data2.STORY_START, fake_data2.STORY_END)
    # 논리분당 STORY_DENSITY점(가스 ARIMA 정규경로 충족). m은 float로 누적.
    m = float(fake_data2.STORY_START)
    while m <= fake_data2.STORY_END:
        gas = fake_data2.generate_gas_tick(m)
        await _broadcast(gas)
        await queue_gas_reading(gas)

        pwr = fake_data2.generate_power_tick(m)
        await _broadcast(pwr)
        await post_power_reading(pwr)

        for loc in fake_data2.generate_worker_ticks(m):
            await _broadcast(loc)
            await post_location_reading(loc)

        m += fake_data2.STORY_STEP
        await asyncio.sleep(STORY_TICK_SECONDS)
    logger.info("STORY 모드 종료 — 스토리 1회 재생 완료")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 Django 장비/노드 목록 로드
    devices = await fetch_gas_devices()
    _devices.extend(devices)

    nodes = await fetch_location_nodes()
    _nodes.extend(nodes)

    if _devices:
        logger.info("가스 장비 %d개 로드 완료: %s", len(_devices), [d['device_uid'] for d in _devices])
    else:
        logger.warning("장비 없음 — Django에 가스 장비를 먼저 등록하세요")

    if _nodes:
        logger.info("위치 노드 %d개 로드 완료: %s", len(_nodes), [n['node_code'] for n in _nodes])
    else:
        logger.warning("위치 노드 없음 — Django에 LocationNode를 먼저 등록하세요")

    # 켜진 생성기만 태스크 생성 (둘 다 켜면 동시 실행)
    logger.info("생성기 플래그 — ENABLE_LOAD=%s ENABLE_STORY=%s", ENABLE_LOAD, ENABLE_STORY)
    global _story_task
    tasks = []
    if ENABLE_LOAD:
        tasks.append(asyncio.create_task(_data_loop()))
    if ENABLE_STORY:
        _story_task = asyncio.create_task(_story_loop())
        tasks.append(_story_task)
    if not tasks:
        logger.warning("생성기 비활성 — ENABLE_LOAD/ENABLE_STORY 모두 false")
    yield
    for t in tasks:
        t.cancel()


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


@app.post("/story/restart")
async def restart_story():
    """실행 중인 스토리 루프를 취소하고 처음(STORY_START)부터 다시 재생한다.

    재배포·pod 재시작 없이 호출만으로 스토리를 재실행하기 위한 제어 endpoint.
    기존 태스크가 unwind되는 중 새 루프와 잠깐 동시 송신하는 것을 막기 위해
    cancel 후 await로 종료를 기다린 뒤 새 태스크를 만든다.
    """
    global _story_task
    if _story_task and not _story_task.done():
        _story_task.cancel()
        try:
            await _story_task
        except asyncio.CancelledError:
            pass
    _story_task = asyncio.create_task(_story_loop())
    return {"status": "restarted"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.append(ws)
    logger.info("WS 연결됨 — 현재 %d명", len(_clients))
    try:
        while True:
            await ws.receive_text()  # 연결 유지 (클라이언트 ping 수신용)
    except WebSocketDisconnect:
        _clients.remove(ws)
        logger.info("WS 해제됨 — 현재 %d명", len(_clients))


@app.post("/trigger")
async def trigger():
    await _emit_once()
    return {"status": "ok", "devices": len(_devices)}


@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(_clients), "devices": len(_devices)}

