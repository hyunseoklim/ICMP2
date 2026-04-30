/**
 * equipment.js
 * 설비 마커 렌더링 — 사각형(center_x/y 기준, width/height 크기)
 *
 * API: /facilities/api/equipments/?floor_id=<id>&is_placed=true
 * 레이어: MapManager.getLayer('equipment')
 * 폴링 없음 — 층 선택 시 1회 로드 (위치 고정)
 */

const equipmentMarkers = {};

function loadEquipments(floorId) {
    if (!floorId) return;

    const layer = MapManager.getLayer('equipment');
    if (!layer) return;

    layer.clearLayers();
    Object.keys(equipmentMarkers).forEach(k => delete equipmentMarkers[k]);

    fetch(`${API_BASE}/equipments/?floor_id=${floorId}&is_placed=true`)
        .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(data => data.results.forEach(eq => renderEquipment(eq, layer)))
        .catch(err => console.warn('[layer:equipment] fetch 실패:', err));
}

function renderEquipment(eq, layer) {
    const color = eq.status === 'active'      ? '#f59e0b'
                : eq.status === 'maintenance' ? '#ef4444'
                : '#475569';

    // center_x/y + width/height → bounds
    const x1 = eq.center_x - eq.width  / 2;
    const x2 = eq.center_x + eq.width  / 2;
    const y1 = eq.center_y - eq.height / 2;
    const y2 = eq.center_y + eq.height / 2;

    const rect = L.rectangle(
        [[y1, x1], [y2, x2]],
        {
            color,
            weight:      1.5,
            fillColor:   color,
            fillOpacity: 0.25,
        }
    ).addTo(layer);

    // 이름 라벨
    const labelIcon = L.divIcon({
        html:      `<div style="font-size:10px;font-weight:600;color:${color};white-space:nowrap;text-shadow:0 0 3px #0f1117">${eq.equipment_name}</div>`,
        iconSize:  [0, 0],
        className: '',
    });
    const label = L.marker([eq.center_y, eq.center_x], {
        icon:        labelIcon,
        interactive: false,
    }).addTo(layer);

    rect.on('click', () => {
        rect.bindPopup(`
            <div class="popup-title">${eq.equipment_name}</div>
            <div class="popup-row">
                <span>코드</span>
                <span class="popup-val">${eq.equipment_code}</span>
            </div>
            <div class="popup-row">
                <span>상태</span>
                <span class="popup-val">${eq.status}</span>
            </div>
            <div class="popup-row">
                <span>크기</span>
                <span class="popup-val">${eq.width}m × ${eq.height}m</span>
            </div>
            <div class="popup-row">
                <span>위치</span>
                <span class="popup-val">(${eq.center_x}, ${eq.center_y})</span>
            </div>
        `, { maxWidth: 180, closeButton: true }).openPopup();
    });

    equipmentMarkers[eq.id] = { rect, label };
}