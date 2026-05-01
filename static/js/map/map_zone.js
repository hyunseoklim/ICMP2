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
 * [수정] zone-draw-panel, zone-name-input, zone-cell-info null 체크 추가
 *        → worker_list 등 해당 DOM이 없는 페이지에서도 에러 없이 동작
 */

// ─── 드로우 상태 객체 ─────────────────────────────────────────

const ZoneState = {
    isDrawing:   false,
    dragStart:   null,
    tempRect:    null,
    pendingData: null,
};

// ─── 이벤트 등록 ──────────────────────────────────────────────

function initZoneEvents() {
    map.on('mousedown', onMapMouseDown);
    map.on('mousemove', onMapMouseMove);
    map.on('mouseup',   onMapMouseUp);
}

// ─── 드로우 모드 제어 ─────────────────────────────────────────

function startZoneDraw() {
    ZoneState.isDrawing = true;
    map.dragging.disable();
    map.getContainer().style.cursor = 'crosshair';
}

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

    // [수정] null 체크 — 해당 DOM이 없는 페이지(worker_list 등) 에러 방지
    const panel = document.getElementById('zone-draw-panel');
    if (panel) panel.style.display = 'none';
}

function cancelDraw() {
    cancelZoneDraw();
    if (window.geofenceDrawer) {
        window.geofenceDrawer.disable();
    }
}

// ─── 마우스 이벤트 핸들러 ─────────────────────────────────────

function onMapMouseDown(e) {
    if (!ZoneState.isDrawing) return;
    ZoneState.dragStart = e.latlng;
}

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
            dashArray:   '5, 5',
        }
    ).addTo(map);
}

function onMapMouseUp(e) {
    if (!ZoneState.isDrawing || !ZoneState.dragStart) return;

    const dragEnd = e.latlng;

    const rs = pixelToCell(ZoneState.dragStart.lng, ZoneState.dragStart.lat);
    const re = pixelToCell(dragEnd.lng, dragEnd.lat);

    ZoneState.pendingData = {
        rowStart: Math.min(rs.row, re.row),
        rowEnd:   Math.max(rs.row, re.row),
        colStart: Math.min(rs.col, re.col),
        colEnd:   Math.max(rs.col, re.col),
    };

    const p = ZoneState.pendingData;

    // [수정] null 체크
    const infoEl = document.getElementById('zone-cell-info');
    if (infoEl) {
        infoEl.textContent =
            `셀 범위: (${p.rowStart},${p.colStart}) ~ (${p.rowEnd},${p.colEnd})`;
    }

    // [수정] null 체크
    const panel = document.getElementById('zone-draw-panel');
    if (panel) panel.style.display = 'block';

    ZoneState.dragStart = null;
}

// ─── 좌표 변환 유틸리티 ───────────────────────────────────────

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
        x2: (colEnd  + 1) * cellWidth,
        y2: (rowEnd  + 1) * cellHeight,
    };
}

// ─── Zone 저장 ────────────────────────────────────────────────

function saveZone() {
    // [수정] null 체크
    const nameEl = document.getElementById('zone-name-input');
    const typeEl = document.getElementById('zone-type-input');
    if (!nameEl || !typeEl) return;

    const name = nameEl.value.trim();
    const type = typeEl.value;

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
            data.results.forEach(zone => renderZone(zone, zoneLayer));
        })
        .catch(err => console.error('🚫 [Zone] 데이터 로드 실패:', err));
}

function renderZone(zone, targetLayer) {
    const color = ZONE_COLORS[zone.zone_type] || '#378ADD';

    const b = cellToPixelBounds(
        zone.cell_row_start, zone.cell_row_end,
        zone.cell_col_start, zone.cell_col_end
    );

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

    const cx = (b.x1 + b.x2) / 2;
    const cy = (b.y1 + b.y2) / 2;
    const labelIcon = L.divIcon({
        html:      `<div class="zone-label-text" style="color:${color}">${zone.zone_name}</div>`,
        iconSize:  [0, 0],
        className: 'zone-label-container',
    });
    const marker = L.marker([cy, cx], { icon: labelIcon });

    rect.addTo(targetLayer);
    marker.addTo(targetLayer);

    rect.on('click', () => {
        if (typeof showDetail === 'function') showDetail('zone', zone);
    });
}
