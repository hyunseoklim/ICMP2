/**
 * location_node.js
 * 위치 노드(고정 인프라) 마커 렌더링
 *
 * API: /facilities/api/location-nodes/?floor_id=<id>
 * 레이어: MapManager.getLayer('locationNode')
 * 폴링 없음 — 층 선택 시 1회 로드 (위치 고정)
 */

const locationNodeMarkers = {};

function loadLocationNodes(floorId) {
    if (!floorId) return;

    const layer = MapManager.getLayer('locationNode');
    if (!layer) return;

    layer.clearLayers();
    Object.keys(locationNodeMarkers).forEach(k => delete locationNodeMarkers[k]);

    fetch(`${API_BASE}/location-nodes/?floor_id=${floorId}`)
        .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(data => data.results.forEach(node => renderLocationNode(node, layer)))
        .catch(err => console.warn('[layer:locationNode] fetch 실패:', err));
}

function renderLocationNode(node, layer) {
    const color = node.status === 'active' ? '#06b6d4' : '#475569';

    const icon = L.divIcon({
        html: `<div style="
            width:14px;height:14px;border-radius:2px;
            background:${color};border:2px solid #0f1117;
            display:flex;align-items:center;justify-content:center;
            font-size:8px;font-weight:700;color:#0f1117;
            box-shadow:0 0 4px ${color}88;
        ">📡</div>`,
        iconSize:   [14, 14],
        iconAnchor: [7, 7],
        className:  '',
    });

    const marker = L.marker([node.y, node.x], {
        icon,
        title: node.node_name,
    }).addTo(layer);

    marker.on('click', () => {
        if (typeof showDetail === 'function') {
            showDetail('locationNode', node);
        }
        marker.bindPopup(`
            <div class="popup-title">${node.node_name}</div>
            <div class="popup-row">
                <span>코드</span>
                <span class="popup-val">${node.node_code || '-'}</span>
            </div>
            <div class="popup-row">
                <span>상태</span>
                <span class="popup-val">${node.status}</span>
            </div>
            <div class="popup-row">
                <span>위치</span>
                <span class="popup-val">(${node.x}, ${node.y})</span>
            </div>
        `, { maxWidth: 160, closeButton: true }).openPopup();
    });

    locationNodeMarkers[node.id] = marker;
}