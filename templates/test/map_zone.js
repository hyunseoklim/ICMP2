/**
 * map_zone.js
 * Zone 드래그 그리기, 저장, 렌더링
 *
 * 역할: 사용자가 지도 위에서 드래그하여 구역을 지정하고 저장하는 전체 흐름 담당
 *       저장된 구역 데이터를 zoneLayer 위에 렌더링
 *       Zone 드로우 모드 전용 마우스 이벤트 핸들러 포함
 *
 * 의존성: map_config.js (map, zoneLayer, zoneDrawMode, zoneDragStart,
 *                        zoneDragEnd, zoneHighlightRect, cellWidth, cellHeight,
 *                        currentFloorId, ZONE_COLORS, API_BASE)
 *         showDetail() — map_events.js에서 정의 (클릭 팝업용)
 * 로드 순서: map_config.js, map_core.js, map_grid.js 다음
 *
 * 함수 목록:
 *   initZoneEvents()            — 지도 마우스 이벤트 등록 (initMap 완료 후 1회)
 *   startZoneDraw()             — 드로우 모드 진입
 *   cancelZoneDraw()            — 드로우 모드 취소 및 임시 사각형 제거
 *   cancelDraw()                — cancelZoneDraw + geofence 드로우 해제
 *   onMapMouseDown(e)           — 드래그 시작 좌표 저장
 *   onMapMouseMove(e)           — 드래그 중 임시 사각형 갱신
 *   onMapMouseUp(e)             — 드래그 종료, 셀 범위 계산, 패널 표시
 *   pixelToCell(px, py)         — 픽셀 좌표 → 셀 인덱스 {col, row}
 *   cellToPixelBounds(rs,re,cs,ce) — 셀 인덱스 → 픽셀 범위 {x1,y1,x2,y2}
 *   saveZone()                  — 패널 입력값으로 API POST 후 재렌더링
 *   loadZones(floorId)          — API GET 후 zoneLayer 전체 재렌더링
 *   renderZone(zone)            — 단일 zone 객체를 zoneLayer에 추가
 */

// ─── 이벤트 등록 ──────────────────────────────────────────────

/**
 * initZoneEvents
 * 입력: 없음
 * 참조: map (map_config.js)
 * 출력: map에 mousedown / mousemove / mouseup 핸들러 등록
 *
 * 호출 시점: initMap() 완료 직후 DOMContentLoaded에서 호출
 * 주의: 핸들러는 zoneDrawMode가 false이면 즉시 return하므로
 *       일반 지도 조작에 영향을 주지 않음
 */
function initZoneEvents() {
  map.on('mousedown', onMapMouseDown);
  map.on('mousemove', onMapMouseMove);
  map.on('mouseup',   onMapMouseUp);
}

// ─── 드로우 모드 제어 ─────────────────────────────────────────

/**
 * startZoneDraw
 * 입력: 없음
 * 참조: map, zoneDrawMode (map_config.js)
 * 출력: 드로우 모드 활성화, 지도 드래그 비활성화, 커서 crosshair
 */
function startZoneDraw() {
  zoneDrawMode = true;
  map.dragging.disable();
  map.getContainer().style.cursor = 'crosshair';
}

/**
 * cancelZoneDraw
 * 입력: 없음
 * 참조: map, zoneDrawMode, zoneHighlightRect, zoneDragStart, zoneDragEnd
 *       (map_config.js)
 * 출력: 드로우 모드 해제, 임시 사각형 제거, 패널 숨김, 상태 초기화
 */
function cancelZoneDraw() {
  zoneDrawMode = false;
  map.dragging.enable();
  map.getContainer().style.cursor = '';

  if (zoneHighlightRect) {
    map.removeLayer(zoneHighlightRect);
    zoneHighlightRect = null;
  }

  document.getElementById('zone-draw-panel').style.display = 'none';
  zoneDragStart = null;
  zoneDragEnd   = null;
}

/**
 * cancelDraw
 * 입력: 없음
 * 참조: window.geofenceDrawer (외부 모듈)
 * 출력: cancelZoneDraw() 호출 + geofence 드로우 비활성화
 */
function cancelDraw() {
  cancelZoneDraw();
  if (window.geofenceDrawer) {
    window.geofenceDrawer.disable();
  }
}

// ─── 마우스 이벤트 핸들러 (Zone 드로우 모드 전용) ────────────

/**
 * onMapMouseDown
 * 입력: e {L.LeafletMouseEvent} — Leaflet 마우스 이벤트
 * 참조: zoneDrawMode, zoneDragStart (map_config.js)
 * 출력: zoneDragStart에 시작 좌표(L.LatLng) 저장
 */
function onMapMouseDown(e) {
  if (!zoneDrawMode) return;
  zoneDragStart = e.latlng;
}

/**
 * onMapMouseMove
 * 입력: e {L.LeafletMouseEvent}
 * 참조: zoneDrawMode, zoneDragStart, zoneHighlightRect, map (map_config.js)
 * 출력: 기존 임시 사각형 제거 후 현재 범위로 새 사각형 렌더링
 */
function onMapMouseMove(e) {
  if (!zoneDrawMode || !zoneDragStart) return;

  const start = zoneDragStart;
  const end   = e.latlng;

  if (zoneHighlightRect) map.removeLayer(zoneHighlightRect);

  zoneHighlightRect = L.rectangle(
    [[start.lat, start.lng], [end.lat, end.lng]],
    { color: '#378ADD', weight: 1.5, fillColor: '#378ADD', fillOpacity: 0.2 }
  ).addTo(map);
}

/**
 * onMapMouseUp
 * 입력: e {L.LeafletMouseEvent}
 * 참조: zoneDrawMode, zoneDragStart, cellWidth, cellHeight (map_config.js)
 * 출력:
 *   - zoneDragEnd 저장
 *   - window._pendingZone = { rowStart, rowEnd, colStart, colEnd }
 *   - #zone-cell-info 텍스트 갱신
 *   - #zone-draw-panel 표시
 */
function onMapMouseUp(e) {
  if (!zoneDrawMode || !zoneDragStart) return;

  zoneDragEnd = e.latlng;
  map.dragging.enable();
  map.getContainer().style.cursor = '';
  zoneDrawMode = false;

  const rs = pixelToCell(zoneDragStart.lng, zoneDragStart.lat);
  const re = pixelToCell(zoneDragEnd.lng,   zoneDragEnd.lat);

  const rowStart = Math.min(rs.row, re.row);
  const rowEnd   = Math.max(rs.row, re.row);
  const colStart = Math.min(rs.col, re.col);
  const colEnd   = Math.max(rs.col, re.col);

  document.getElementById('zone-cell-info').textContent =
    `셀 범위: (${rowStart},${colStart}) ~ (${rowEnd},${colEnd})`;
  document.getElementById('zone-draw-panel').style.display = 'block';

  window._pendingZone = { rowStart, rowEnd, colStart, colEnd };
}

// ─── 좌표 변환 유틸리티 ───────────────────────────────────────

/**
 * pixelToCell
 * 입력:
 *   px {number} — 픽셀 x 좌표 (Leaflet latlng.lng)
 *   py {number} — 픽셀 y 좌표 (Leaflet latlng.lat)
 * 참조: cellWidth, cellHeight (map_config.js)
 * 출력: { col {number}, row {number} } — 0-based 셀 인덱스
 */
function pixelToCell(px, py) {
  return {
    col: Math.floor(px / cellWidth),
    row: Math.floor(py / cellHeight),
  };
}

/**
 * cellToPixelBounds
 * 입력:
 *   rowStart {number} — 시작 행 인덱스
 *   rowEnd   {number} — 종료 행 인덱스
 *   colStart {number} — 시작 열 인덱스
 *   colEnd   {number} — 종료 열 인덱스
 * 참조: cellWidth, cellHeight (map_config.js)
 * 출력: { x1, y1, x2, y2 } — 픽셀 경계값
 *   x1 = colStart * cellWidth
 *   y1 = rowStart * cellHeight
 *   x2 = (colEnd + 1) * cellWidth
 *   y2 = (rowEnd + 1) * cellHeight
 */
function cellToPixelBounds(rowStart, rowEnd, colStart, colEnd) {
  return {
    x1: colStart * cellWidth,
    y1: rowStart * cellHeight,
    x2: (colEnd  + 1) * cellWidth,
    y2: (rowEnd  + 1) * cellHeight,
  };
}

// ─── Zone 저장 ────────────────────────────────────────────────

/**
 * saveZone
 * 입력:
 *   DOM — #zone-name-input (구역 이름), #zone-type-input (구역 유형)
 *   window._pendingZone — { rowStart, rowEnd, colStart, colEnd }
 * 참조: currentFloorId, API_BASE (map_config.js)
 * 출력:
 *   - API POST /zones/
 *   - cancelZoneDraw() 호출
 *   - loadZones(currentFloorId) 호출로 zoneLayer 갱신
 *   - addEvent() 호출로 이벤트 로그 기록
 */
function saveZone() {
  const name = document.getElementById('zone-name-input').value.trim();
  const type = document.getElementById('zone-type-input').value;

  if (!name)           { alert('구역 이름을 입력하세요'); return; }
  if (!currentFloorId) { alert('층을 먼저 선택하세요');   return; }

  const p = window._pendingZone;

  fetch(`${API_BASE}/zones/`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      floor:          currentFloorId,
      zone_name:      name,
      zone_type:      type,
      cell_row_start: p.rowStart,
      cell_row_end:   p.rowEnd,
      cell_col_start: p.colStart,
      cell_col_end:   p.colEnd,
    }),
  })
    .then(r => r.json())
    .then(() => {
      cancelZoneDraw();
      loadZones(currentFloorId);
      addEvent('info', `zone '${name}' 생성됨`);
    });
}

// ─── Zone 렌더링 ──────────────────────────────────────────────

/**
 * loadZones
 * 입력: floorId {number|string} — 층 ID
 * 참조: API_BASE, zoneLayer (map_config.js)
 * 출력: API GET 후 zoneLayer 초기화, renderZone 반복 호출
 */
function loadZones(floorId) {
  fetch(`${API_BASE}/zones/?floor_id=${floorId}`)
    .then(r => r.json())
    .then(data => {
      zoneLayer.clearLayers();
      data.forEach(zone => renderZone(zone));
    });
}

/**
 * renderZone
 * 입력: zone {object} — API 응답 zone 객체
 *   zone.zone_type       — 색상 키
 *   zone.cell_row_start/end, zone.cell_col_start/end — 셀 범위
 *   zone.zone_name       — 라벨 텍스트
 * 참조: ZONE_COLORS, zoneLayer, cellToPixelBounds (map_config.js)
 * 출력:
 *   - zoneLayer에 L.Rectangle 추가 (색상 + 점선 테두리)
 *   - zoneLayer에 L.Marker (divIcon 라벨) 추가
 *   - rect.click → showDetail('zone', zone) 호출
 */
function renderZone(zone) {
  const color = ZONE_COLORS[zone.zone_type] || '#378ADD';
  const b     = cellToPixelBounds(
    zone.cell_row_start, zone.cell_row_end,
    zone.cell_col_start, zone.cell_col_end
  );

  const rect = L.rectangle(
    [[b.y1, b.x1], [b.y2, b.x2]],
    { color, weight: 1, fillColor: color, fillOpacity: 0.12, dashArray: '4,3' }
  ).addTo(zoneLayer);

  // 구역 이름 라벨 (중앙 배치)
  const cx    = (b.x1 + b.x2) / 2;
  const cy    = (b.y1 + b.y2) / 2;
  const label = L.divIcon({
    html:      `<div style="font-size:11px;color:${color};font-weight:500;white-space:nowrap">${zone.zone_name}</div>`,
    iconSize:  [0, 0],
    iconAnchor:[0, 0],
  });
  L.marker([cy, cx], { icon: label }).addTo(zoneLayer);

  rect.on('click', () => showDetail('zone', zone));
}