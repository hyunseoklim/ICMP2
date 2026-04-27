/**
 * worker_sim.js
 * 작업자 위치 시뮬레이션 — 2초마다 API 폴링 → 마커 이동
 *
 * 변경 사항:
 *   - initWorkerLayer() 제거: 레이어는 MapManager.syncLayers()에서 일괄 생성됨
 *   - window.workerLayer 전역 변수 제거
 *   - renderOrMoveWorker()에서 MapManager.getLayer('worker')로 레이어 참조
 */

// workerId → { marker }
const workerMarkers = {};
let workerPollingTimer = null;

// ─── 시뮬레이션 시작 ─────────────────────────────────────────

function simulateWorkerMove() {
    Object.values(workerMarkers).forEach(w => {
        const latlng = w.marker.getLatLng();
        let newLat = latlng.lat;
        let newLng = latlng.lng;

        // x, y 각각 0.1m씩 증가, 건물 범위 벗어나면 반대로
        newLng += 0.1;
        newLat += 0.1;

        if (newLng > floorWidthMeters)  newLng = 0;
        if (newLat > floorLengthMeters) newLat = 0;

        w.marker.setLatLng([newLat, newLng]);
    });
}
// 움직임을 테스트하기 위해 잠시 주석처리
// function startWorkerSim() {
//     if (workerPollingTimer) clearInterval(workerPollingTimer);
//     fetchWorkerLocations();
//     workerPollingTimer = setInterval(fetchWorkerLocations, 2000);
// }
// 움직임 테스트를 위한 임시 로직
function startWorkerSim() {
    if (workerPollingTimer) clearInterval(workerPollingTimer);
    fetchWorkerLocations();
    workerPollingTimer = setInterval(() => {
        fetchWorkerLocations();
        simulateWorkerMove();  // ← 추가
    }, 500);
}

function stopWorkerSim() {
    if (workerPollingTimer) {
        clearInterval(workerPollingTimer);
        workerPollingTimer = null;
    }
}

// ─── 초기화 ──────────────────────────────────────────────────
function clearWorkerMarkers() {          // ← 여기 추가
    stopWorkerSim();
    Object.values(workerMarkers).forEach(w => w.marker.remove());
    Object.keys(workerMarkers).forEach(k => delete workerMarkers[k]);
}


// ─── 위치 폴링 ────────────────────────────────────────────────

function fetchWorkerLocations() {
    fetch(`${API_BASE}/worker-locations/dummy/`)
        .then(r => r.json())
        .then(data => data.forEach(loc => renderOrMoveWorker(loc)))
        .catch(() => {});
}

// ─── 마커 렌더/이동 ──────────────────────────────────────────

const WORKER_STATUS_COLOR = {
    on_duty:  '#f59e0b',
    danger:   '#ef4444',
    off_duty: '#475569',
};

function workerIcon(status, name) {
    const color   = WORKER_STATUS_COLOR[status] || '#f59e0b';
    const initial = name ? name[0] : 'W';
    return L.divIcon({
        html: `<div style="
      width:18px;height:18px;border-radius:3px;
      background:${color};border:2px solid #0f1117;
      display:flex;align-items:center;justify-content:center;
      font-size:9px;font-weight:700;color:#0f1117;
      box-shadow:0 0 4px ${color}88;
    ">${initial}</div>`,
        iconSize:   [18, 18],
        iconAnchor: [9, 9],
        className:  '',
    });
}

function renderOrMoveWorker(loc) {
    const layer = MapManager.getLayer('worker');
    if (!layer) return;

    if (loc.snap_x === undefined || loc.snap_y === undefined) return;

    if (workerMarkers[loc.worker_id]) {
        const state = workerMarkers[loc.worker_id];
        const prev  = state.marker.getLatLng();
        const dx    = Math.abs(prev.lng - loc.snap_x);
        const dy    = Math.abs(prev.lat - loc.snap_y);

        if (dx > 0 || dy > 0) {
            state.marker.setLatLng([loc.snap_y, loc.snap_x]);
            state.marker.setIcon(workerIcon(loc.worker_status, loc.worker_name));
            state.marker._locData = loc;

            if (loc.worker_status === 'danger') {
                addEvent('danger', `${loc.worker_name} 위험구역 진입 감지`);
            }
        }
    } else {
        const marker = L.marker([loc.snap_y, loc.snap_x], {
            icon:         workerIcon(loc.worker_status, loc.worker_name),
            title:        loc.worker_name,
            zIndexOffset: 100,
        }).addTo(layer);

        marker._locData = loc;
        marker.on('click', () => {
            showDetail('worker', loc);
            showWorkerPopup(marker, loc);
        });

        workerMarkers[loc.worker_id] = { marker };
    }
}

function showWorkerPopup(marker, loc) {
    const statusLabel = {
        on_duty: '근무중', danger: '위험', off_duty: '비근무',
    }[loc.worker_status] || loc.worker_status;

    const statusClass = loc.worker_status === 'danger' ? 'danger' : 'normal';

    const html = `
    <div class="popup-title">${loc.worker_name}</div>
    <div class="popup-row"><span>상태</span><span class="popup-val ${statusClass}">${statusLabel}</span></div>
    <div class="popup-row"><span>셀</span><span class="popup-val">${loc.grid_index !== undefined ? loc.grid_index : '-'}</span></div>
    <div class="popup-row"><span>위치</span><span class="popup-val">(${loc.snap_x}, ${loc.snap_y})</span></div>
    <div class="popup-row" style="font-size:10px;color:var(--text-muted)">
      <span>갱신</span><span>${new Date(loc.measured_at).toLocaleTimeString('ko-KR')}</span>
    </div>`;

    marker.bindPopup(html, { maxWidth: 160, closeButton: true }).openPopup();
}