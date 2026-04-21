/**
 * worker_sim.js
 * 작업자 위치 시뮬레이션 — 2초마다 API 폴링 → 마커 이동
 *
 * curl 로 작업자 위치 주입:
 * curl -X POST http://localhost:8000/api/worker-locations/dummy/ \
 *   -H "Content-Type: application/json" \
 *   -d '{"worker_id":1,"x":320,"y":250,"cell_no":"5-6","floor_id":1}'
 *
 * 추후 WebSocket 으로 교체 시 startWorkerSim() 내부의 setInterval 을
 * WebSocket onmessage 핸들러로 교체한다.
 */

window.workerLayer = null;

// workerId → { marker, prevX, prevY }
const workerMarkers = {};
let workerPollingTimer = null;

// ─── 레이어 초기화 ────────────────────────────────────────────

function initWorkerLayer() {
  window.workerLayer = L.layerGroup().addTo(map);
}

// ─── 시뮬레이션 시작 ─────────────────────────────────────────

function startWorkerSim() {
  if (!window.workerLayer) initWorkerLayer();
  if (workerPollingTimer) clearInterval(workerPollingTimer);

  fetchWorkerLocations();
  workerPollingTimer = setInterval(fetchWorkerLocations, 2000);
}

function stopWorkerSim() {
  if (workerPollingTimer) {
    clearInterval(workerPollingTimer);
    workerPollingTimer = null;
  }
}

// ─── 위치 폴링 ────────────────────────────────────────────────

function fetchWorkerLocations() {
  fetch(`${API_BASE}/worker-locations/dummy/`)
    .then(r => r.json())
    .then(data => {
      data.forEach(loc => renderOrMoveWorker(loc));
    })
    .catch(() => {});
}

// ─── 마커 렌더/이동 ──────────────────────────────────────────

const WORKER_STATUS_COLOR = {
  on_duty: '#f59e0b',
  danger:  '#ef4444',
  off_duty: '#475569',
};

function workerIcon(status, name) {
  const color = WORKER_STATUS_COLOR[status] || '#f59e0b';
  const initial = name ? name[0] : 'W';
  return L.divIcon({
    html: `<div style="
      width:18px;height:18px;border-radius:3px;
      background:${color};
      border:2px solid #0f1117;
      display:flex;align-items:center;justify-content:center;
      font-size:9px;font-weight:700;color:#0f1117;
      box-shadow:0 0 4px ${color}88;
    ">${initial}</div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    className: '',
  });
}

function renderOrMoveWorker(loc) {
  const layer = window.workerLayer;
  if (!layer) return;

  if (workerMarkers[loc.worker_id]) {
    const state = workerMarkers[loc.worker_id];
    const prev = state.marker.getLatLng();

    const dx = Math.abs(prev.lng - loc.x);
    const dy = Math.abs(prev.lat - loc.y);

    if (dx > 1 || dy > 1) {
      // 이동 감지 → 마커 위치 업데이트 + 이벤트
      state.marker.setLatLng([loc.y, loc.x]);
      state.marker.setIcon(workerIcon(loc.worker_status, loc.worker_name));
      state.marker._locData = loc;

      if (loc.worker_status === 'danger') {
        addEvent('danger', `${loc.worker_name} 위험구역 진입 감지`);
      }
    }
  } else {
    // 신규 마커 생성
    const marker = L.marker([loc.y, loc.x], {
      icon: workerIcon(loc.worker_status, loc.worker_name),
      title: loc.worker_name,
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
    <div class="popup-row"><span>셀</span><span class="popup-val">${loc.cell_no || '-'}</span></div>
    <div class="popup-row"><span>위치</span><span class="popup-val">(${loc.x}, ${loc.y})</span></div>
    <div class="popup-row" style="font-size:10px;color:var(--text-muted)">
      <span>갱신</span><span>${new Date(loc.measured_at).toLocaleTimeString('ko-KR')}</span>
    </div>`;

  marker.bindPopup(html, { maxWidth: 160, closeButton: true }).openPopup();
}