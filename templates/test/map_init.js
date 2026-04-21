/**
 * map_init.js
 * Leaflet 초기화, 공장 평면도 이미지 오버레이, meshgrid 격자 렌더링, zone 레이어 관리
 */

let map, imageOverlay, gridLayer, zoneLayer;
let imgWidth = 1000, imgHeight = 1000;
let cellWidth = 50, cellHeight = 50;
let currentFloorId = null;
let zoneDrawMode = false;
let zoneDragStart = null, zoneDragEnd = null;
let zoneHighlightRect = null;

const GRID_COLOR = 'rgb(255, 0, 0)';
const GRID_WEIGHT = 0.5;

// ─── Leaflet 초기화 ───────────────────────────────────────────

function initMap() {
  map = L.map('map', {
    crs: L.CRS.Simple,
    minZoom: -3,
    maxZoom: 3,
    zoomControl: false,
  });

  // 샘플 이미지 바운드 (이미지 크기 기준)
  const bounds = [[0, 0], [imgHeight, imgWidth]];

  imageOverlay = L.imageOverlay(SAMPLE_IMAGE, bounds, { opacity: 0.85 }).addTo(map);
  map.fitBounds(bounds);

  gridLayer = L.layerGroup().addTo(map);
  zoneLayer = L.layerGroup().addTo(map); 

  drawGrid(cellWidth, cellHeight, imgWidth, imgHeight);

  // zone 드래그 이벤트
  map.on('mousedown', onMapMouseDown);
  map.on('mousemove', onMapMouseMove);
  map.on('mouseup', onMapMouseUp);
}


// ─── 격자 렌더링 ─────────────────────────────────────────────

function drawGrid(_cellWidth, _cellHeight, _imageWidth, _imageHeight) {
  gridLayer.clearLayers();
  const cols = Math.ceil(_imageWidth / _cellWidth);
  const rows = Math.ceil(_imageHeight / _cellHeight);

  for (let c = 0; c <= cols; c++) {
    const x = c * _cellWidth;
    L.polyline([[0, x], [_imageHeight, x]], { color: GRID_COLOR, weight: GRID_WEIGHT }).addTo(gridLayer);
  }
  for (let r = 0; r <= rows; r++) {
    const y = r * _cellHeight;
    L.polyline([[y, 0], [y, _imageWidth]], { color: GRID_COLOR, weight: GRID_WEIGHT }).addTo(gridLayer);
  }
}

function applyGrid() {
  cellWidth = parseInt(document.getElementById('grid-cell-w').value) || 50;
  cellHeight = parseInt(document.getElementById('grid-cell-h').value) || 50;
  drawGrid(cellWidth, cellHeight, imgWidth, imgHeight);

  if (currentFloorId) {
    const cols = Math.ceil(imgWidth / cellWidth);
    const rows = Math.ceil(imgHeight / cellHeight);
    const url = `${API_BASE}/floor-grids/`;
    fetch(`${url}?floor_id=${currentFloorId}`)
      .then(r => r.json())
      .then(data => {
        if (data.length > 0) {
          fetch(`${url}${data[0].id}/`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cell_width: cellWidth, cell_height: cellHeight, cols, rows }),
          });
        } else {
          fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              floor: currentFloorId,
              cell_width: cellWidth, cell_height: cellHeight,
              cols, rows,
              img_width: imgWidth, img_height: imgHeight,
            }),
          });
        }
      });
  }
}

// ─── zone 드래그 그리기 ──────────────────────────────────────

function startZoneDraw() {
  zoneDrawMode = true;
  map.dragging.disable();
  map.getContainer().style.cursor = 'crosshair';
}

function cancelZoneDraw() {
  zoneDrawMode = false;
  map.dragging.enable();
  map.getContainer().style.cursor = '';
  if (zoneHighlightRect) { map.removeLayer(zoneHighlightRect); zoneHighlightRect = null; }
  document.getElementById('zone-draw-panel').style.display = 'none';
  zoneDragStart = null; zoneDragEnd = null;
}

function cancelDraw() {
  cancelZoneDraw();
  if (window.geofenceDrawer) {
    window.geofenceDrawer.disable();
  }
}

function onMapMouseDown(e) {
  if (!zoneDrawMode) return;
  zoneDragStart = e.latlng;
}

function onMapMouseMove(e) {
  if (!zoneDrawMode || !zoneDragStart) return;
  const start = zoneDragStart, end = e.latlng;
  if (zoneHighlightRect) map.removeLayer(zoneHighlightRect);
  zoneHighlightRect = L.rectangle(
    [[start.lat, start.lng], [end.lat, end.lng]],
    { color: '#378ADD', weight: 1.5, fillColor: '#378ADD', fillOpacity: 0.2 }
  ).addTo(map);
}

function onMapMouseUp(e) {
  if (!zoneDrawMode || !zoneDragStart) return;
  zoneDragEnd = e.latlng;
  map.dragging.enable();
  map.getContainer().style.cursor = '';
  zoneDrawMode = false;

  const rs = pixelToCell(zoneDragStart.lng, zoneDragStart.lat);
  const re = pixelToCell(zoneDragEnd.lng, zoneDragEnd.lat);

  const rowStart = Math.min(rs.row, re.row);
  const rowEnd   = Math.max(rs.row, re.row);
  const colStart = Math.min(rs.col, re.col);
  const colEnd   = Math.max(rs.col, re.col);

  document.getElementById('zone-cell-info').textContent =
    `셀 범위: (${rowStart},${colStart}) ~ (${rowEnd},${colEnd})`;
  document.getElementById('zone-draw-panel').style.display = 'block';

  window._pendingZone = { rowStart, rowEnd, colStart, colEnd };
}

function pixelToCell(px, py) {
  return {
    col: Math.floor(px / cellWidth),
    row: Math.floor(py / cellHeight),
  };
}

function cellToPixelBounds(rowStart, rowEnd, colStart, colEnd) {
  return {
    x1: colStart * cellWidth,
    y1: rowStart * cellHeight,
    x2: (colEnd + 1) * cellWidth,
    y2: (rowEnd + 1) * cellHeight,
  };
}

// ─── zone 저장 ───────────────────────────────────────────────

function saveZone() {
  const name = document.getElementById('zone-name-input').value.trim();
  const type = document.getElementById('zone-type-input').value;
  if (!name) { alert('구역 이름을 입력하세요'); return; }
  if (!currentFloorId) { alert('층을 먼저 선택하세요'); return; }

  const p = window._pendingZone;
  fetch(`${API_BASE}/zones/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      floor: currentFloorId,
      zone_name: name,
      zone_type: type,
      cell_row_start: p.rowStart,
      cell_row_end: p.rowEnd,
      cell_col_start: p.colStart,
      cell_col_end: p.colEnd,
    }),
  })
    .then(r => r.json())
    .then(() => {
      cancelZoneDraw();
      loadZones(currentFloorId);
      addEvent('info', `zone '${name}' 생성됨`);
    });
}

// ─── zone 렌더링 ─────────────────────────────────────────────

const ZONE_COLORS = {
  work: '#378ADD', storage: '#639922', rest: '#1D9E75',
  utility: '#BA7517', passage: '#888780', etc: '#534AB7',
};

function loadZones(floorId) {
  fetch(`${API_BASE}/zones/?floor_id=${floorId}`)
    .then(r => r.json())
    .then(data => {
      zoneLayer.clearLayers();
      data.forEach(zone => renderZone(zone));
    });
}

function renderZone(zone) {
  const color = ZONE_COLORS[zone.zone_type] || '#378ADD';
  const b = cellToPixelBounds(zone.cell_row_start, zone.cell_row_end, zone.cell_col_start, zone.cell_col_end);
  const rect = L.rectangle(
    [[b.y1, b.x1], [b.y2, b.x2]],
    { color, weight: 1, fillColor: color, fillOpacity: 0.12, dashArray: '4,3' }
  ).addTo(zoneLayer);

  const cx = (b.x1 + b.x2) / 2;
  const cy = (b.y1 + b.y2) / 2;
  const label = L.divIcon({
    html: `<div style="font-size:11px;color:${color};font-weight:500;white-space:nowrap">${zone.zone_name}</div>`,
    iconSize: [0, 0], iconAnchor: [0, 0],
  });
  L.marker([cy, cx], { icon: label }).addTo(zoneLayer);

  rect.on('click', () => showDetail('zone', zone));
}

// ─── 층 데이터 로드 ──────────────────────────────────────────

function loadFloorData(floorId) {
  currentFloorId = floorId;

  fetch(`${API_BASE}/floor-grids/?floor_id=${floorId}`)
    .then(r => r.json())
    .then(data => {
      if (data.length > 0) {
        const g = data[0];
        cellWidth = g.cell_width; cellHeight = g.cell_height;
        imgWidth = g.img_width; imgHeight = g.img_height;
        document.getElementById('grid-cell-w').value = cellWidth;
        document.getElementById('grid-cell-h').value = cellHeight;
      }
      const bounds = [[0, 0], [imgHeight, imgWidth]];
      imageOverlay.setBounds(bounds);
      map.fitBounds(bounds);
      drawGrid(cellWidth, cellHeight, imgWidth, imgHeight);
    });

  loadZones(floorId);
  if (window.loadGeofences) loadGeofences(floorId);
  if (window.loadSensors) loadSensors(floorId);
  if (window.startWorkerSim) startWorkerSim();
}

// ─── 레이어 ON/OFF ───────────────────────────────────────────

function toggleLayer(name, visible) {
  const layers = {
    grid: gridLayer,
    zone: zoneLayer,
    geofence: window.geofenceLayer,
    worker: window.workerLayer,
    gas: window.gasLayer,
    power: window.powerLayer,
    location: window.locationLayer,
    device: window.deviceLayer,
  };
  const layer = layers[name];
  if (!layer) return;
  visible ? map.addLayer(layer) : map.removeLayer(layer);
}

// ─── 탭 필터 ─────────────────────────────────────────────────

function applyTabFilter(filter) {
  const gasOn = filter === 'all' || filter === 'gas';
  const powerOn = filter === 'all' || filter === 'power';
  const workerOn = filter === 'all' || filter === 'worker';
  const deviceOn = filter === 'all' || filter === 'device';

  toggleLayer('gas', gasOn);
  toggleLayer('power', powerOn);
  toggleLayer('worker', workerOn);
  toggleLayer('device', deviceOn);

  document.getElementById('layer-gas').checked = gasOn;
  document.getElementById('layer-power').checked = powerOn;
  document.getElementById('layer-worker').checked = workerOn;
  document.getElementById('layer-device').checked = deviceOn;
}

// ─── 지도 조작 ───────────────────────────────────────────────

function fitMapView() {
  const bounds = [[0, 0], [imgHeight, imgWidth]];
  map.fitBounds(bounds);
}
function zoomIn() { map.zoomIn(); }
function zoomOut() { map.zoomOut(); }

// ─── 상세 패널 ───────────────────────────────────────────────

function showDetail(type, data) {
  const panel = document.getElementById('detail-panel');
  const content = document.getElementById('detail-content');
  panel.style.display = 'block';

  let html = '';
  if (type === 'zone') {
    html = `<div class="popup-title">${data.zone_name}</div>
      <div class="popup-row"><span>유형</span><span class="popup-val">${data.zone_type}</span></div>
      <div class="popup-row"><span>셀 범위</span><span class="popup-val">(${data.cell_row_start},${data.cell_col_start})~(${data.cell_row_end},${data.cell_col_end})</span></div>`;
  } else if (type === 'sensor') {
    const statusClass = data.status === 'danger' ? 'danger' : data.status === 'warning' ? 'warning' : 'normal';
    html = `<div class="popup-title">${data.device_name}</div>
      <div class="popup-row"><span>상태</span><span class="popup-val ${statusClass}">${data.status}</span></div>
      <div class="popup-row"><span>종류</span><span class="popup-val">${data.sensor_type}</span></div>
      <div class="popup-row"><span>위치</span><span class="popup-val">(${data.x}, ${data.y})</span></div>`;
  } else if (type === 'worker') {
    html = `<div class="popup-title">${data.worker_name}</div>
      <div class="popup-row"><span>상태</span><span class="popup-val">${data.worker_status}</span></div>
      <div class="popup-row"><span>셀</span><span class="popup-val">${data.cell_no || '-'}</span></div>
      <div class="popup-row"><span>위치</span><span class="popup-val">(${data.x}, ${data.y})</span></div>`;
  }
  content.innerHTML = html;
}

// ─── 이벤트 로그 ─────────────────────────────────────────────

function addEvent(level, message) {
  const list = document.getElementById('event-list');
  const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const item = document.createElement('div');
  item.className = `event-item ${level}`;
  item.innerHTML = `<span class="event-time">${now}</span>${message}`;
  list.prepend(item);
  const items = list.querySelectorAll('.event-item');
  if (items.length > 50) items[items.length - 1].remove();

  const empty = list.querySelector('[style]');
  if (empty) empty.remove();

  document.getElementById('last-refresh').textContent =
    new Date().toLocaleTimeString('ko-KR');
}

// ─── 초기화 ──────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initMap();
});