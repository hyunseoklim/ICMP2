/**
 * map_events.js
 * 층 데이터 로드, 레이어 ON/OFF, 탭 필터, 상세 패널, 이벤트 로그
 *
 * 역할: 지도 데이터 조작과 직접 관련 없는 레이어 제어, 층 전환,
 *       UI 패널 렌더링, 이벤트 로그 관리
 *
 * 의존성:
 *   map_config.js — MapManager, cellWidth, cellHeight,
 *                   floorWidthMeters, floorLengthMeters,
 *                   currentFloorId, imageOverlay, map, API_BASE
 *   map_grid.js   — loadGridLayer()
 *   map_zone.js   — loadZoneLayer()
 * 로드 순서: 모든 map_*.js 중 마지막
 *
 * 함수 목록:
 *   loadFloorData(floorId)     — 층 설정 로드 후 격자·구역·센서 갱신
 *   toggleLayer(name, visible) — MapManager 기반 레이어 지도 추가/제거
 *   applyTabFilter(filter)     — 탭별 레이어 일괄 ON/OFF
 *   showDetail(type, data)     — 상세 패널 HTML 렌더링
 *   addEvent(level, message)   — 이벤트 로그 항목 추가
 */

// ─── 층 데이터 로드 ───────────────────────────────────────────

/**
 * loadFloorData
 * 입력: floorId {number|string} — 선택된 층 ID
 * 출력:
 *   - currentFloorId 갱신
 *   - /api/floors/<id>/grid-data/ 에서 meter 기반 격자 정보 수신
 *   - floorWidthMeters(m), floorLengthMeters(m), cellWidth(m), cellHeight(m) 갱신
 *   - imageOverlay bounds 갱신 + 지도 뷰 재조정
 *   - loadGridLayer() 재호출로 SVG 격자 갱신
 *   - loadZoneLayer(), loadGeofences(), loadSensors(), startWorkerSim() 연쇄 호출
 */
function loadFloorData(floorId) {
    currentFloorId = floorId;

    fetch(`${API_BASE}/floors/${floorId}/grid-data/`)
        .then(r => r.json())
        .then(g => {
            floorWidthMeters  = g.width;
            floorLengthMeters = g.length;
            cellWidth         = g.cell_size;
            cellHeight        = g.cell_size;

            const wEl = document.getElementById('grid-cell-w');
            const hEl = document.getElementById('grid-cell-h');
            if (wEl) wEl.value = g.cell_size;
            if (hEl) hEl.value = g.cell_size;

            const bounds = [[0, 0], [floorLengthMeters, floorWidthMeters]];
            imageOverlay.setUrl(g.floor_image || (typeof SAMPLE_IMAGE !== 'undefined' ? SAMPLE_IMAGE : ''));
            imageOverlay.setBounds(bounds);
            
            map.fitBounds(bounds, {
                padding: [0, 0],
                maxZoom: map.getBoundsZoom(bounds, true),
            });
            map.setMaxBounds(bounds);

            // fitBounds 완료 후 격자 그리기
            map.once('moveend', function() {
                loadGridLayer();  // ← moveend 이후 실행!
            });
        });

    loadZoneLayer(floorId);

    if (window.loadGeofences)  loadGeofences(floorId);
    if (window.loadSensors)    loadSensors(floorId);
    if (window.startWorkerSim) startWorkerSim();
}

// ─── 레이어 ON/OFF ────────────────────────────────────────────

/**
 * toggleLayer
 * MapManager에 등록된 레이어를 지도에 추가하거나 제거한다.
 *
 * 입력:
 *   name    {string}  — MAP_LAYERS의 name 값
 *                       (grid, zone, geofence, gas, power, location, device, worker)
 *   visible {boolean} — true: 지도에 추가 / false: 지도에서 제거
 */
function toggleLayer(name, visible) {
    const layer = MapManager.getLayer(name);
    if (!layer) return;
    visible ? map.addLayer(layer) : map.removeLayer(layer);
}

// ─── 탭 필터 ──────────────────────────────────────────────────

/**
 * applyTabFilter
 * 입력: filter {string} — 'all' | 'gas' | 'power' | 'worker' | 'device'
 * 출력: 각 레이어 ON/OFF + 대응 체크박스 상태 동기화
 */
function applyTabFilter(filter) {
    const gasOn    = filter === 'all' || filter === 'gas';
    const powerOn  = filter === 'all' || filter === 'power';
    const workerOn = filter === 'all' || filter === 'worker';
    const deviceOn = filter === 'all' || filter === 'device';

    toggleLayer('gas',    gasOn);
    toggleLayer('power',  powerOn);
    toggleLayer('worker', workerOn);
    toggleLayer('device', deviceOn);

    const sync = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.checked = val;
    };
    sync('layer-gas',    gasOn);
    sync('layer-power',  powerOn);
    sync('layer-worker', workerOn);
    sync('layer-device', deviceOn);
}

// ─── 상세 패널 ────────────────────────────────────────────────

/**
 * showDetail
 * 입력:
 *   type {string} — 'zone' | 'sensor' | 'worker'
 *   data {object} — API 응답 객체
 */
function showDetail(type, data) {
    const panel   = document.getElementById('detail-panel');
    const content = document.getElementById('detail-content');
    if (!panel || !content) return;
    panel.style.display = 'block';

    let html = '';

    if (type === 'zone') {
        html = `
      <div class="popup-title">${data.zone_name}</div>
      <div class="popup-row">
        <span>유형</span>
        <span class="popup-val">${data.zone_type}</span>
      </div>
      <div class="popup-row">
        <span>셀 범위</span>
        <span class="popup-val">
          (${data.cell_row_start},${data.cell_col_start})
          ~
          (${data.cell_row_end},${data.cell_col_end})
        </span>
      </div>`;

    } else if (type === 'sensor') {
        const statusClass = data.status === 'danger'  ? 'danger'
                          : data.status === 'warning' ? 'warning'
                          : 'normal';
        html = `
      <div class="popup-title">${data.device_name}</div>
      <div class="popup-row">
        <span>상태</span>
        <span class="popup-val ${statusClass}">${data.status}</span>
      </div>
      <div class="popup-row">
        <span>종류</span>
        <span class="popup-val">${data.sensor_type}</span>
      </div>
      <div class="popup-row">
        <span>위치</span>
        <span class="popup-val">(${data.x}, ${data.y})</span>
      </div>`;

    } else if (type === 'worker') {
        html = `
      <div class="popup-title">${data.worker_name}</div>
      <div class="popup-row">
        <span>상태</span>
        <span class="popup-val">${data.worker_status}</span>
      </div>
      <div class="popup-row">
        <span>셀</span>
        <span class="popup-val">${data.cell_no || '-'}</span>
      </div>
      <div class="popup-row">
        <span>위치</span>
        <span class="popup-val">(${data.x}, ${data.y})</span>
      </div>`;
    }

    content.innerHTML = html;
}

// ─── 이벤트 로그 ──────────────────────────────────────────────

/**
 * addEvent
 * 입력:
 *   level   {string} — 'info' | 'warning' | 'danger'
 *   message {string} — 표시할 메시지
 * 출력:
 *   - #event-list 최상단에 항목 추가
 *   - 50개 초과 시 가장 오래된 항목 제거
 */
function addEvent(level, message) {
    const list = document.getElementById('event-list');
    if (!list) return;

    const now = new Date().toLocaleTimeString('ko-KR', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
    });

    const item = document.createElement('div');
    item.className = `event-item-map ${level}`;
    item.innerHTML = `<span class="event-time">${now}</span>${message}`;
    list.prepend(item);

    const items = list.querySelectorAll('.event-item-map');
    if (items.length > 50) items[items.length - 1].remove();

    const empty = list.querySelector('[style]');
    if (empty) empty.remove();

    const refreshEl = document.getElementById('last-refresh');
    if (refreshEl) refreshEl.textContent = new Date().toLocaleTimeString('ko-KR');
}