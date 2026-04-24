/**
 * map_events.js
 * 층 데이터 로드, 레이어 ON/OFF, 탭 필터, 상세 패널, 이벤트 로그
 *
 * 역할: 지도 데이터 조작과 직접 관련 없는 레이어 제어, 층 전환,
 *       UI 패널 렌더링, 이벤트 로그 관리
 *
 * 의존성:
 *   map_config.js — cellWidth, cellHeight, imgWidth, imgHeight,
 *                   currentFloorId, imageOverlay, map, API_BASE
 *   map_grid.js   — drawGrid()
 *   map_zone.js   — loadZones()
 * 로드 순서: 모든 map_*.js 중 마지막
 *
 * 함수 목록:
 *   loadFloorData(floorId)    — 층 설정 로드 후 격자·구역·센서 갱신
 *   toggleLayer(name, visible)— 레이어 지도 추가/제거
 *   applyTabFilter(filter)    — 탭별 레이어 일괄 ON/OFF
 *   showDetail(type, data)    — 상세 패널 HTML 렌더링
 *   addEvent(level, message)  — 이벤트 로그 항목 추가
 */

// ─── 층 데이터 로드 ───────────────────────────────────────────

/**
 * loadFloorData
 * 입력: floorId {number|string} — 선택된 층 ID
 * 참조: API_BASE, currentFloorId, imageOverlay, map (map_config.js)
 *       drawGrid() (map_grid.js), loadZones() (map_zone.js)
 * 출력:
 *   - currentFloorId 갱신
 *   - /api/floors/<id>/grid-data/ 에서 meter 기반 격자 정보 수신
 *   - imgWidth(m), imgHeight(m), cellWidth(m), cellHeight(m) 갱신
 *   - imageOverlay bounds 갱신 (meter 기준) + 지도 뷰 재조정
 *   - drawGrid(lines) 재호출로 격자 갱신
 *   - loadZones(), loadGeofences(), loadSensors(), startWorkerSim() 연쇄 호출
 *
 * [수정 내역]
 *   - API 엔드포인트 변경: /floor-grids/ → /floors/<id>/grid-data/
 *   - 좌표계 변경: px → meter
 *   - drawGrid 인자 변경: 4개 px 값 → lines 객체
 */
function loadFloorData(floorId) {
  currentFloorId = floorId;

  // meter 기반 grid-data API 호출
  fetch(`${API_BASE}/floors/${floorId}/grid-data/`)
    .then(r => r.json())
    .then(g => {
      // meter 단위 값으로 전역 변수 갱신
      imgWidth   = g.width;      // m — floor.width
      imgHeight  = g.length;     // m — floor.length
      cellWidth  = g.cell_size;  // m
      cellHeight = g.cell_size;  // m

      // UI 입력 필드 동기화
      document.getElementById('grid-cell-w').value = g.cell_size;
      document.getElementById('grid-cell-h').value = g.cell_size;

      // bounds를 meter 기준으로 설정
      // Leaflet L.CRS.Simple: [[y1,x1],[y2,x2]] → [[0,0],[length,width]]
      const bounds = [[0, 0], [imgHeight, imgWidth]];
      imageOverlay.setBounds(bounds);
      // map.fitBounds(bounds);
      map.setView([imgHeight / 2, imgWidth / 2], 0);

      // 격자 렌더링 — lines를 그대로 전달, JS는 렌더링만
      drawGrid(g.lines);
    });

  loadZones(floorId);

  // 외부 모듈 — 존재할 경우에만 실행
  if (window.loadGeofences)  loadGeofences(floorId);
  if (window.loadSensors)    loadSensors(floorId);
  if (window.startWorkerSim) startWorkerSim();
}

// ─── 레이어 ON/OFF ────────────────────────────────────────────

/**
 * toggleLayer
 * 입력:
 *   name    {string}  — 레이어 키 (아래 layers 맵 참조)
 *   visible {boolean} — true: 지도에 추가 / false: 지도에서 제거
 * 참조:
 *   gridLayer, zoneLayer (map_config.js)
 *   window.geofenceLayer, window.workerLayer, window.gasLayer,
 *   window.powerLayer, window.locationLayer, window.deviceLayer (외부 모듈)
 * 출력: 해당 레이어를 map에 추가하거나 제거
 *
 * 레이어 키 목록:
 *   grid, zone, geofence, worker, gas, power, location, device
 */
function toggleLayer(name, visible) {
  const layers = {
    grid:     gridLayer,
    zone:     zoneLayer,
    geofence: window.geofenceLayer,
    worker:   window.workerLayer,
    gas:      window.gasLayer,
    power:    window.powerLayer,
    location: window.locationLayer,
    device:   window.deviceLayer,
  };

  const layer = layers[name];
  if (!layer) return;

  visible ? map.addLayer(layer) : map.removeLayer(layer);
}

// ─── 탭 필터 ──────────────────────────────────────────────────

/**
 * applyTabFilter
 * 입력: filter {string} — 'all' | 'gas' | 'power' | 'worker' | 'device'
 * 참조: toggleLayer()
 * 출력:
 *   - gas / power / worker / device 레이어 ON/OFF 일괄 적용
 *   - 대응하는 DOM 체크박스(#layer-gas 등) 상태 동기화
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

  document.getElementById('layer-gas').checked    = gasOn;
  document.getElementById('layer-power').checked  = powerOn;
  document.getElementById('layer-worker').checked = workerOn;
  document.getElementById('layer-device').checked = deviceOn;
}

// ─── 상세 패널 ────────────────────────────────────────────────

/**
 * showDetail
 * 입력:
 *   type {string} — 'zone' | 'sensor' | 'worker'
 *   data {object} — API 응답 객체
 *     zone   필드: zone_name, zone_type, cell_row_start/end, cell_col_start/end
 *     sensor 필드: device_name, status, sensor_type, x, y
 *     worker 필드: worker_name, worker_status, cell_no, x, y
 * 참조: DOM — #detail-panel, #detail-content
 * 출력: #detail-panel 표시, #detail-content에 HTML 렌더링
 */
function showDetail(type, data) {
  const panel   = document.getElementById('detail-panel');
  const content = document.getElementById('detail-content');
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
 *   level   {string} — 'info' | 'warning' | 'danger' (CSS 클래스 키)
 *   message {string} — 표시할 메시지
 * 참조: DOM — #event-list, #last-refresh
 * 출력:
 *   - #event-list 최상단에 이벤트 항목 prepend
 *   - 50개 초과 시 가장 오래된 항목 제거
 *   - #last-refresh 텍스트 갱신
 */
function addEvent(level, message) {
  const list = document.getElementById('event-list');
  const now  = new Date().toLocaleTimeString('ko-KR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

  const item = document.createElement('div');
  item.className = `event-item ${level}`;
  item.innerHTML = `<span class="event-time">${now}</span>${message}`;
  list.prepend(item);

  // 최대 50개 유지
  const items = list.querySelectorAll('.event-item');
  if (items.length > 50) items[items.length - 1].remove();

  // 빈 상태 placeholder 제거
  const empty = list.querySelector('[style]');
  if (empty) empty.remove();

  document.getElementById('last-refresh').textContent =
    new Date().toLocaleTimeString('ko-KR');
}