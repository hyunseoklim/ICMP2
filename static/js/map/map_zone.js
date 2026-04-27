/**
 * map_zone.js
 * Zone 드래그 그리기, 저장, 렌더링
 *
 * 역할: 사용자가 지도 위에서 드래그하여 구역을 지정하고 저장하는 전체 흐름 담당
 *       저장된 구역 데이터를 MapManager의 zone 레이어 위에 렌더링
 *
 * 의존성:
 *   map_config.js — map, MapManager, cellWidth, cellHeight,
 *                   currentFloorId, ZONE_COLORS, API_BASE
 *   map_events.js — showDetail(), addEvent()
 * 로드 순서: map_config.js, map_core.js, map_grid.js 다음
 *
 * 함수 목록:
 *   initZoneEvents()               — 지도 마우스 이벤트 등록 (1회)
 *   startZoneDraw()                — 드로우 모드 진입
 *   cancelZoneDraw()               — 드로우 모드 취소 및 임시 사각형 제거
 *   cancelDraw()                   — cancelZoneDraw + geofence 드로우 해제
 *   onMapMouseDown(e)              — 드래그 시작 좌표 저장
 *   onMapMouseMove(e)              — 드래그 중 임시 사각형 갱신
 *   onMapMouseUp(e)                — 드래그 종료, 셀 범위 계산, 패널 표시
 *   pixelToCell(px, py)            — meter 좌표 → 셀 인덱스 {col, row}
 *   cellToPixelBounds(rs,re,cs,ce) — 셀 인덱스 → meter 범위 {x1,y1,x2,y2}
 *   saveZone()                     — 패널 입력값으로 API POST 후 재렌더링
 *   loadZoneLayer(floorId)         — API GET 후 zone 레이어 전체 재렌더링
 *   renderZone(zone, targetLayer)  — 단일 zone 객체를 대상 레이어에 추가
 */

// ─── 드로우 상태 객체 ─────────────────────────────────────────
// 전역 변수 오염 방지: Zone 드로우 관련 상태를 단일 객체로 캡슐화

const ZoneState = {
    isDrawing:   false,   // 드로우 모드 활성 여부
    dragStart:   null,    // 드래그 시작 좌표 (L.LatLng)
    tempRect:    null,    // 드래그 중인 임시 사각형 객체
    pendingData: null,    // 저장 대기 중인 셀 범위 { rowStart, rowEnd, colStart, colEnd }
};

// ─── 이벤트 등록 ──────────────────────────────────────────────

/**
 * initZoneEvents
 * map에 mousedown / mousemove / mouseup 핸들러를 등록한다.
 * 핸들러 내부에서 ZoneState.isDrawing을 확인하므로
 * 드로우 모드가 아닐 때는 일반 지도 조작에 영향을 주지 않는다.
 */
function initZoneEvents() {
    map.on('mousedown', onMapMouseDown);
    map.on('mousemove', onMapMouseMove);
    map.on('mouseup',   onMapMouseUp);
}

// ─── 드로우 모드 제어 ─────────────────────────────────────────

/**
 * startZoneDraw
 * 드로우 모드를 활성화하고 지도 드래그를 비활성화한다.
 */
function startZoneDraw() {
    ZoneState.isDrawing = true;
    map.dragging.disable();
    map.getContainer().style.cursor = 'crosshair';
}

/**
 * cancelZoneDraw
 * 드로우 모드를 해제하고 임시 사각형과 패널을 정리한다.
 */
function cancelZoneDraw() {
    ZoneState.isDrawing = false;
    map.dragging.enable();
    map.getContainer().style.cursor = '';

    if (ZoneState.tempRect) {
        map.removeLayer(ZoneState.tempRect);
        ZoneState.tempRect = null;
    }

    ZoneState.dragStart   = null;
    ZoneState.pendingData = null;

    const panel = document.getElementById('zone-draw-panel');
    if (panel) panel.style.display = 'none';
}

/**
 * cancelDraw
 * cancelZoneDraw + geofence 드로우 비활성화를 함께 처리한다.
 */
function cancelDraw() {
    cancelZoneDraw();
    if (window.geofenceDrawer) {
        window.geofenceDrawer.disable();
    }
}

// ─── 마우스 이벤트 핸들러 ─────────────────────────────────────

/**
 * onMapMouseDown
 * 드래그 시작 좌표를 ZoneState에 저장한다.
 */
function onMapMouseDown(e) {
    if (!ZoneState.isDrawing) return;
    ZoneState.dragStart = e.latlng;
}

/**
 * onMapMouseMove
 * 드래그 중 임시 사각형을 실시간으로 갱신한다.
 * 임시 사각형은 확정된 구역이 아니므로 map에 직접 추가한다.
 */
function onMapMouseMove(e) {
    if (!ZoneState.isDrawing || !ZoneState.dragStart) return;

    const start = ZoneState.dragStart;
    const end   = e.latlng;

    if (ZoneState.tempRect) map.removeLayer(ZoneState.tempRect);

    ZoneState.tempRect = L.rectangle(
        [[start.lat, start.lng], [end.lat, end.lng]],
        {
            color:       '#378ADD',
            weight:      1.5,
            fillColor:   '#378ADD',
            fillOpacity: 0.2,
            dashArray:   '5, 5',   // 점선: "그리는 중"임을 표시
        }
    ).addTo(map);
}

/**
 * onMapMouseUp
 * 드래그를 종료하고 셀 범위를 계산하여 저장 패널을 표시한다.
 */
function onMapMouseUp(e) {
    if (!ZoneState.isDrawing || !ZoneState.dragStart) return;

    const dragEnd = e.latlng;

    // meter 좌표 → 셀 인덱스 변환
    const rs = pixelToCell(ZoneState.dragStart.lng, ZoneState.dragStart.lat);
    const re = pixelToCell(dragEnd.lng, dragEnd.lat);

    ZoneState.pendingData = {
        rowStart: Math.min(rs.row, re.row),
        rowEnd:   Math.max(rs.row, re.row),
        colStart: Math.min(rs.col, re.col),
        colEnd:   Math.max(rs.col, re.col),
    };

    const p = ZoneState.pendingData;
    const infoEl = document.getElementById('zone-cell-info');
    if (infoEl) {
        infoEl.textContent =
            `셀 범위: (${p.rowStart},${p.colStart}) ~ (${p.rowEnd},${p.colEnd})`;
    }

    const panel = document.getElementById('zone-draw-panel');
    if (panel) panel.style.display = 'block';

    // 드로우 모드는 유지하되 드래그는 종료
    ZoneState.dragStart = null;
}

// ─── 좌표 변환 유틸리티 ───────────────────────────────────────

/**
 * pixelToCell
 * Leaflet latlng(meter 좌표) → 0-based 셀 인덱스
 *
 * 입력:
 *   px {number} — Leaflet latlng.lng (x, meter)
 *   py {number} — Leaflet latlng.lat (y, meter)
 * 출력: { col, row }
 */
function pixelToCell(px, py) {
    return {
        col: Math.floor(px / cellWidth),
        row: Math.floor(py / cellHeight),
    };
}

/**
 * cellToPixelBounds
 * 셀 인덱스 범위 → meter 경계값 (Leaflet 좌표계)
 *
 * 입력: rowStart, rowEnd, colStart, colEnd (0-based)
 * 출력: { x1, y1, x2, y2 } (meter)
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
 * 패널 입력값을 API에 POST하고 zone 레이어를 새로고침한다.
 */
function saveZone() {
    const name = document.getElementById('zone-name-input').value.trim();
    const type = document.getElementById('zone-type-input').value;

    if (!name) { alert('구역 이름을 입력하세요'); return; }
    if (!currentFloorId) { alert('층 정보를 확인할 수 없습니다'); return; }
    if (!ZoneState.pendingData) return;

    const p = ZoneState.pendingData;

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
    .then(r => {
        if (!r.ok) throw new Error('서버 응답 에러');
        return r.json();
    })
    .then(() => {
        cancelZoneDraw();
        loadZoneLayer(currentFloorId);
        if (typeof addEvent === 'function') addEvent('info', `구역 '${name}' 생성 완료`);
    })
    .catch(err => alert(`저장 실패: ${err.message}`));
}

// ─── Zone 렌더링 ──────────────────────────────────────────────

/**
 * loadZoneLayer
 * MapManager로부터 zone 레이어를 수령하여
 * 서버 데이터를 기반으로 구역을 전체 재렌더링한다.
 *
 * 입력: floorId {number|string}
 */
function loadZoneLayer(floorId) {
    if (!floorId) {
        console.warn('⚠️ [Zone] floorId가 없어 로드할 수 없습니다.');
        return;
    }

    const zoneLayer = MapManager.getLayer('zone');
    if (!zoneLayer) return;

    zoneLayer.clearLayers();

    fetch(`${API_BASE}/zones/?floor_id=${floorId}`)
        .then(r => r.json())
        .then(data => {
            data.forEach(zone => renderZone(zone, zoneLayer));
        })
        .catch(err => console.error('🚫 [Zone] 데이터 로드 실패:', err));
}

/**
 * renderZone
 * 단일 zone 객체를 생성하여 지정된 레이어에 삽입한다.
 *
 * 입력:
 *   zone        {object}       — API 응답 zone 객체
 *   targetLayer {L.LayerGroup} — 그려질 레이어 (MapManager에서 수령)
 */
function renderZone(zone, targetLayer) {
    const color = ZONE_COLORS[zone.zone_type] || '#378ADD';

    const b = cellToPixelBounds(
        zone.cell_row_start, zone.cell_row_end,
        zone.cell_col_start, zone.cell_col_end
    );

    // 구역 본체 (사각형)
    const rect = L.rectangle(
        [[b.y1, b.x1], [b.y2, b.x2]],
        {
            color:       color,
            weight:      1,
            fillColor:   color,
            fillOpacity: 0.15,
            dashArray:   '4,3',
        }
    );

    // 구역 이름 라벨 (중앙 배치)
    const cx = (b.x1 + b.x2) / 2;
    const cy = (b.y1 + b.y2) / 2;
    const labelIcon = L.divIcon({
        html:      `<div class="zone-label-text" style="color:${color}">${zone.zone_name}</div>`,
        iconSize:  [0, 0],
        className: 'zone-label-container',
    });
    const marker = L.marker([cy, cx], { icon: labelIcon });

    // MapManager가 관리하는 targetLayer에 추가
    rect.addTo(targetLayer);
    marker.addTo(targetLayer);

    // 클릭 이벤트
    rect.on('click', () => {
        if (typeof showDetail === 'function') showDetail('zone', zone);
    });
}