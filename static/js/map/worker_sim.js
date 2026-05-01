/**
 * worker_sim.js - 최종 통합 버전
 * 1. WorkerLayer 객체를 통한 구조적 관리
 * 2. Polling / WebSocket 모드 분리
 * 3. Polling 테스트용 자동 이동 시뮬레이션 플래그 추가
 */

const WorkerLayer = {
    USE_WS: true,          // true: WebSocket 모드, false: Polling 모드
    USE_SIMULATION: false,  // true: polling 테스트용 자동 이동 사용


    _ws:         null,
    _pollTimer:  null,
    _floorId:    null,

    // ─── 공통 진입점 ────────────────────────────────────────
    load(floorId) {
        this._floorId = floorId;
        this._clear();

        this.USE_WS ? this._useWS(floorId) : this._usePoll(floorId);
    },

    destroy() {
        this._clear();
    },

    _clear() {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }

        if (this._ws) {
            this._ws.onclose = null; // 수동 종료 시 재연결 방지
            this._ws.close();
            this._ws = null;
        }

        clearWorkerMarkers();
    },

    // ─── 폴링 모드 ──────────────────────────────────────────
    _usePoll(floorId) {
        const url = `${API_BASE}/worker-locations/dummy/?floor_id=${floorId}`;

        const fetch_ = () => {
            fetch(url)
                .then(r => {
                    if (!r.ok) throw new Error(r.status);
                    return r.json();
                })
                .then(data => {
                    data.forEach(loc => renderOrMoveWorker(loc));
                })
                .catch(err => {
                    console.warn('[layer:worker] 폴링 실패:', err);
                });
        };

        fetch_();

        if (!this.USE_SIMULATION) {
            this._pollTimer = setInterval(fetch_, 500);
        } else {
            simulateWorkerMove();
        }
    },

    // ─── WebSocket 모드 ─────────────────────────────────────
    _useWS(floorId) {
        const url = `ws://${location.host}/ws/floor/${floorId}/worker/`;
        this._ws = new WebSocket(url);

        this._ws.onopen = () => {
            console.info('[layer:worker] WebSocket 연결됨');
        };

        this._ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);

                if (msg.type === 'full' || msg.type === 'delta') {
                    msg.data.forEach(loc => renderOrMoveWorker(loc));
                }
            } catch (err) {
                console.warn('[layer:worker] 메시지 파싱 실패:', err);
            }
        };

        this._ws.onclose = () => {
            console.warn('[layer:worker] WebSocket 끊김 — 3초 후 재연결');

            setTimeout(() => {
                if (this._floorId) this._useWS(this._floorId);
            }, 3000);
        };

        this._ws.onerror = () => {
            console.warn('[layer:worker] WebSocket 실패 — polling 모드로 전환');
            this._ws = null;
            if (this.USE_SIMULATION) simulateWorkerMove();
        };
    },
};

// ─── 마커 상태 저장소 ─────────────────────────────────────────
const workerMarkers = {};

// ─── 마커 아이콘 ──────────────────────────────────────────────
const WORKER_STATUS_COLOR = {
    safe:     '#22c55e',  // 초록
    warning:  '#f59e0b',  // 노랑
    danger:   '#ef4444',  // 빨강
    on_duty:  '#22c55e',  // safe와 동일
    off_duty: '#475569',  // 회색
};

function workerIcon(status, name) {
    const color = WORKER_STATUS_COLOR[status] || '#f59e0b';
    const initial = name ? name[0] : 'W';

    return L.divIcon({
        html: `<div style="
            width:18px;
            height:18px;
            border-radius:3px;
            background:${color};
            border:2px solid #0f1117;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:9px;
            font-weight:700;
            color:#0f1117;
            box-shadow:0 0 4px ${color}88;
        ">${initial}</div>`,
        iconSize:   [18, 18],
        iconAnchor: [9, 9],
        className:  '',
    });
}
 //───────────────────────────────────────────────────────────────────────────────────────────────
// ─── [SIM] 강제 이동 시뮬레이션 로직 ──────────────────────────
// USE_SIMULATION: false 로 바꾸면 호출되지 않음
const WORKER_ROUTES = {

    1: {  // 김철수 — 위험구역 순찰
        name: '김철수',
        path: [
            {x:  5, y: 10},
            {x:  8, y:  8},
            {x: 10, y:  5},
            {x: 12, y:  8},
            {x: 10, y: 12},
            {x:  7, y: 15},
            {x:  5, y: 12},
        ],
        step: 0,
    },
    2: {  // 이영희 — safe → danger → safe
        name: '이영희',
        path: [
            {x: 2,  y: 15},
            {x: 6,  y: 10},
            {x: 8,  y:  5},
            {x: 10, y:  5},
            {x: 14, y:  5},
            {x: 20, y: 10},
        ],
        step: 0,
    },
    3: {  // 박민준 — safe → warning → danger → safe
        name: '박민준',
        path: [
            {x: 45, y:  2},
            {x: 35, y:  3},
            {x: 26, y:  4},
            {x: 25, y:  5},
            {x: 25, y: 12},
            {x: 25, y: 14},
            {x: 25, y: 15},
            {x: 30, y: 20},
        ],
        step: 0,
    },
    4: {  // 최수진 — 항상 safe (대조군)
        name: '최수진',
        path: [
            {x: 40, y:  5},
            {x: 45, y: 10},
            {x: 45, y: 20},
            {x: 40, y: 28},
            {x: 35, y: 15},
        ],
        step: 0,
    },
    5: {  // 정도현 — danger 체류 → 탈출 → safe
        name: '정도현',
        path: [
            {x: 15, y: 25},
            {x: 12, y: 22},
            {x: 10, y: 20},
            {x:  5, y: 15},
            {x:  5, y: 28},
        ],
        step: 0,
    },
};

let _simTimer = null;
function simulateWorkerMove() {
    console.log('[sim] simulateWorkerMove 호출됨');
    console.log('[sim] _simTimer:', _simTimer);

    if (_simTimer) {
        console.log('[sim] 이미 실행 중, 스킵');
        return;
    }

    console.log('[sim] setInterval 등록 시작');

    _simTimer = setInterval(async () => {
        console.log('[sim] tick — step 실행');

        const postPromises = Object.entries(WORKER_ROUTES).map(([workerId, route]) => {
            const pos = route.path[route.step];
            console.log(`[sim] POST worker_id=${workerId} x=${pos.x} y=${pos.y}`);

            return fetch(`${API_BASE}/worker-locations/dummy/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({
                    worker_id: parseInt(workerId),
                    x: pos.x,
                    y: pos.y,
                    floor_id: currentFloorId,
                }),
            });
        });

        await Promise.all(postPromises);
        console.log('[sim] POST 완료');

        const res = await fetch(`${API_BASE}/worker-locations/dummy/?floor_id=${currentFloorId}`);
        if (!res.ok) {
            console.warn('[sim] GET 실패:', res.status);
            return;
        }
        const data = await res.json();
        console.log('[sim] GET 결과:', data.map(d => `${d.worker_name}:${d.worker_status}`));

        data.forEach(loc => renderOrMoveWorker(loc));

        Object.values(WORKER_ROUTES).forEach(route => {
            route.step = (route.step + 1) % route.path.length;
        });

    }, 500);

    console.log('[sim] setInterval 등록 완료, _simTimer:', _simTimer);
}
// function simulateWorkerMove() {
//     const API = `${API_BASE}/worker-locations/dummy/`;
//     const INTERVAL_MS = 2000;  // 2초마다 한 step 이동

//     if (_simTimer) return;  // 중복 실행 방지

//     _simTimer = setInterval(async () => {
//         const postPromises = Object.entries(WORKER_ROUTES).map(([workerId, route]) => {
//             const pos = route.path[route.step];

//             return fetch(`${API_BASE}/worker-locations/dummy/`, {
//                 method: 'POST',
//                 headers: {'Content-Type': 'application/json',
//                           'X-CSRFToken': getCookie('csrftoken')},
//                 body: JSON.stringify({
//                     worker_id: parseInt(workerId),
//                     x: pos.x,
//                     y: pos.y,
//                     floor_id: currentFloorId,
//                 }),
//             });
//         });

//         // 모든 작업자 위치 POST 완료 후
//         await Promise.all(postPromises);

//         // GET으로 전체 상태 조회
//         const res = await fetch(`${API_BASE}/worker-locations/dummy/?floor_id=${currentFloorId}`);
//         if (!res.ok) return;
//         const data = await res.json();

//         // 마커 갱신
//         data.forEach(loc => renderOrMoveWorker(loc));

//         // 다음 step으로 이동 (경로 끝나면 처음으로)
//         Object.values(WORKER_ROUTES).forEach(route => {
//             route.step = (route.step + 1) % route.path.length;
//         });

//     }, INTERVAL_MS);
// }

function stopSimulation() {
    if (_simTimer) {
        clearInterval(_simTimer);
        _simTimer = null;
    }
}

// CSRF 토큰 헬퍼
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}
 //───────────────────────────────────────────────────────────────────────────────────────────────
// ─── 끝 [SIM] 강제 이동 시뮬레이션 로직 ──────────────────────────

// ─── 마커 렌더/이동 ───────────────────────────────────────────
function renderOrMoveWorker(loc) {
    const layer = MapManager.getLayer('worker');

    if (!layer) return;
    if (loc.snap_x === undefined || loc.snap_y === undefined) return;

    if (workerMarkers[loc.worker_id]) {
        const state = workerMarkers[loc.worker_id];
        const prev = state.marker.getLatLng();

        const dx = Math.abs(prev.lng - loc.snap_x);
        const dy = Math.abs(prev.lat - loc.snap_y);

        // 변경 후
        const prevStatus = state.marker._locData?.worker_status;

        if (dx > 0 || dy > 0) {
            state.marker.setLatLng([loc.snap_y, loc.snap_x]);
        }

        // 위치 변경 여부와 무관하게 항상 아이콘/상태 갱신
        state.marker.setIcon(workerIcon(loc.worker_status, loc.worker_name));
        state.marker._locData = loc;

        // 이전 상태와 달라졌을 때만 이벤트 발생
        if (loc.worker_status !== prevStatus) {
            if (loc.worker_status === 'danger') {
                if (typeof addEvent === 'function') {
                    addEvent('danger', `${loc.worker_name} 위험구역 진입`);
                }
            } else if (loc.worker_status === 'warning') {
                if (typeof addEvent === 'function') {
                    addEvent('warning', `${loc.worker_name} 주의구역 진입`);
                }
            } else if (loc.worker_status === 'safe' && prevStatus !== undefined) {
                if (typeof addEvent === 'function') {
                    addEvent('safe', `${loc.worker_name} 안전구역 복귀`);
                }
            }
        }
    } else {
        const marker = L.marker([loc.snap_y, loc.snap_x], {
            icon: workerIcon(loc.worker_status, loc.worker_name),
            title: loc.worker_name,
            zIndexOffset: 100,
        }).addTo(layer);

        marker._locData = loc;

        marker.on('click', () => {
            if (typeof showDetail === 'function') {
                showDetail('worker', loc);
            }

            showWorkerPopup(marker, loc);
        });

        workerMarkers[loc.worker_id] = { marker };
    }
}

// ─── 마커 제거 ───────────────────────────────────────────────
function clearWorkerMarkers() {
    const layer = MapManager.getLayer('worker');

    Object.values(workerMarkers).forEach(w => {
        if (layer) {
            layer.removeLayer(w.marker);
        }
    });

    Object.keys(workerMarkers).forEach(k => {
        delete workerMarkers[k];
    });
}

// ─── 작업자 팝업 ─────────────────────────────────────────────
function showWorkerPopup(marker, loc) {
    const statusLabel = {
        safe:     '안전',
        warning:  '주의',
        danger:   '위험',
        on_duty:  '근무중',
        off_duty: '비근무',
    }[loc.worker_status] || loc.worker_status;

    const statusClass = {
        safe:    'normal',
        warning: 'warning',
        danger:  'danger',
    }[loc.worker_status] || 'normal';

    marker.bindPopup(`
        <div class="popup-title">${loc.worker_name}</div>

        <div class="popup-row">
            <span>상태</span>
            <span class="popup-val ${statusClass}">${statusLabel}</span>
        </div>

        <div class="popup-row">
            <span>셀</span>
            <span class="popup-val">
                ${loc.grid_index !== undefined ? loc.grid_index : '-'}
            </span>
        </div>

        <div class="popup-row">
            <span>위치</span>
            <span class="popup-val">(${loc.snap_x}, ${loc.snap_y})</span>
        </div>

        <div class="popup-row" style="font-size:10px;color:var(--text-muted)">
            <span>갱신</span>
            <span>${new Date(loc.measured_at).toLocaleTimeString('ko-KR')}</span>
        </div>
    `, {
        maxWidth: 160,
        closeButton: true,
    }).openPopup();
}

// ─── 외부 호출 인터페이스 ─────────────────────────────────────
function startWorkerSim() {
    WorkerLayer.load(currentFloorId);
}

function stopWorkerSim() {
    WorkerLayer.destroy();
}