/**
 * worker_sim.js - 최종 통합 버전
 * 1. WorkerLayer 객체를 통한 구조적 관리
 * 2. Polling / WebSocket 모드 분리
 * 3. Polling 테스트용 자동 이동 시뮬레이션 플래그 추가
 */

const WorkerLayer = {
    USE_WS: false,          // true: WebSocket 모드, false: Polling 모드
    USE_SIMULATION: true,  // true: polling 테스트용 자동 이동 사용

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

                    // [SIM] polling 테스트용 자동 이동
                    if (this.USE_SIMULATION) {
                         this._pollTimer = setInterval(simulateWorkerMove, 500);
                    }
                })
                .catch(err => {
                    console.warn('[layer:worker] 폴링 실패:', err);
                });
        };

        fetch_();

        // // 시뮬레이션 확인용 빠른 갱신 주기
        // this._pollTimer = setInterval(fetch_, 500);
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
                if (this._floorId) {
                    this._useWS(this._floorId);
                }
            }, 3000);
        };

        this._ws.onerror = (e) => {
            console.error('[layer:worker] WebSocket 에러:', e);
        };
    },
};

// ─── 마커 상태 저장소 ─────────────────────────────────────────
const workerMarkers = {};

// ─── 마커 아이콘 ──────────────────────────────────────────────
const WORKER_STATUS_COLOR = {
    on_duty:  '#f59e0b',
    danger:   '#ef4444',
    off_duty: '#475569',
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

// ─── [SIM] 강제 이동 시뮬레이션 로직 ──────────────────────────
// USE_SIMULATION: false 로 바꾸면 호출되지 않음
function simulateWorkerMove() {
    Object.values(workerMarkers).forEach(w => {
        const latlng = w.marker.getLatLng();

        let newLat = latlng.lat + 0.1;
        let newLng = latlng.lng + 0.1;

        // 경계값 체크
        if (typeof floorWidthMeters !== 'undefined' && newLng > floorWidthMeters) {
            newLng = 0;
        }

        if (typeof floorLengthMeters !== 'undefined' && newLat > floorLengthMeters) {
            newLat = 0;
        }

        w.marker.setLatLng([newLat, newLng]);
    });
}

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

        if (dx > 0 || dy > 0) {
            state.marker.setLatLng([loc.snap_y, loc.snap_x]);
            state.marker.setIcon(workerIcon(loc.worker_status, loc.worker_name));
            state.marker._locData = loc;

            if (loc.worker_status === 'danger') {
                if (typeof addEvent === 'function') {
                    addEvent('danger', `${loc.worker_name} 위험구역 진입 감지`);
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
        on_duty: '근무중',
        danger: '위험',
        off_duty: '비근무',
    }[loc.worker_status] || loc.worker_status;

    const statusClass = loc.worker_status === 'danger' ? 'danger' : 'normal';

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