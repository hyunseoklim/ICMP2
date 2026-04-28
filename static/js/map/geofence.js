/**
 * geofence.js
 * 위험구역(원형 geofence) 생성 / 조회 / 삭제 + CSS transition 애니메이션
 *
 * 변경 사항:
 *   - initGeofenceLayer() 제거: 레이어는 MapManager.syncLayers()에서 일괄 생성됨
 *   - window.geofenceLayer 전역 변수 제거
 *   - geofenceLayer 참조를 MapManager.getLayer('geofence')로 교체
 */


const SEVERITY_COLOR = {
    danger:  { fill: 'rgba(239,68,68,0.15)',  stroke: '#ef4444' },
    warning: { fill: 'rgba(245,158,11,0.12)', stroke: '#f59e0b' },
    safe:    { fill: 'rgba(34,197,94,0.10)',  stroke: '#22c55e' },
};

// geofenceId → { circle, labelMarker, cx, cy, r }
const geofenceState = {};

// ─── Leaflet.draw 원 그리기 버튼 ─────────────────────────────

let drawCircleControl = null;

document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btn-draw-geofence');
    if (btn) btn.addEventListener('click', startGeofenceDraw);
});

function startGeofenceDraw() {
    if (!map) return;

    if (drawCircleControl) drawCircleControl.disable();

    drawCircleControl = new L.Draw.Circle(map, {
        shapeOptions: {
            color:       '#ef4444',
            fillColor:   'rgba(239,68,68,0.15)',
            fillOpacity: 1,
            weight:      1.5,
        },
        showRadius: true,
        metric:     false,
    });
    drawCircleControl.enable();
    window.geofenceDrawer = drawCircleControl;

    map.once(L.Draw.Event.CREATED, (e) => {
        const center = e.layer.getLatLng();
        const radius = e.layer.getRadius();
        const cx     = center.lng;
        const cy     = center.lat;

        const name     = prompt('위험구역 이름을 입력하세요', '위험구역');
        if (!name) return;
        const severity = prompt('위험도 (danger / warning / safe)', 'danger') || 'danger';

        fetch(`${API_BASE}/geofences/`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                floor:     currentFloorId || null,
                name,
                center_x:  cx,
                center_y:  cy,
                radius,
                severity,
                is_active: true,
            }),
        })
        .then(r => r.json())
        .then(data => {
            renderGeofence(data);
            addEvent('danger', `위험구역 '${data.name}' 생성됨`);
        });
    });
}

// ─── 위험구역 조회 ───────────────────────────────────────────

function loadGeofences(floorId) {
    const layer = MapManager.getLayer('geofence');
    if (!layer) return;
    layer.clearLayers();

    const url = floorId
        ? `${API_BASE}/geofences/?floor_id=${floorId}&is_active=true`
        : `${API_BASE}/geofences/?is_active=true`;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            data.results.forEach(g => renderGeofence(g));
            startGeofencePolling(floorId);
        });
}

// ─── 위험구역 렌더링 ─────────────────────────────────────────

function renderGeofence(g) {
    const layer = MapManager.getLayer('geofence');
    if (!layer) return;

    const colors = SEVERITY_COLOR[g.severity] || SEVERITY_COLOR.danger;

    const circle = L.circle([g.center_y, g.center_x], {
        radius:      g.radius,
        color:       colors.stroke,
        fillColor:   colors.fill,
        fillOpacity: 1,
        weight:      1.5,
        dashArray:   '4,3',
        className:   `geofence-circle geofence-${g.severity}`,
    }).addTo(layer);

    const label = L.divIcon({
        html:      `<div style="font-size:11px;font-weight:500;color:${colors.stroke};white-space:nowrap;text-shadow:0 0 4px #0f1117">${g.name}</div>`,
        iconSize:  [0, 0],
        iconAnchor:[0, 6],
    });
    const labelMarker = L.marker([g.center_y, g.center_x], {
        icon:        label,
        interactive: false,
    }).addTo(layer);

    circle.on('click', () => {
        showDetail('geofence', g);
        addEvent(g.severity, `위험구역 '${g.name}' 클릭`);
    });

    circle.on('contextmenu', () => {
        if (confirm(`'${g.name}' 위험구역을 삭제하시겠습니까?`)) {
            fetch(`${API_BASE}/geofences/${g.id}/`, { method: 'DELETE' })
                .then(() => {
                    layer.removeLayer(circle);
                    layer.removeLayer(labelMarker);
                    delete geofenceState[g.id];
                    addEvent('info', `위험구역 '${g.name}' 삭제됨`);
                });
        }
    });

    geofenceState[g.id] = {
        circle,
        labelMarker,
        cx: g.center_x,
        cy: g.center_y,
        r:  g.radius,
    };
}

// ─── 폴링: 변경된 값으로 원 이동/확산 ───────────────────────

let geofencePollingTimer = null;

function startGeofencePolling(floorId) {
    if (geofencePollingTimer) clearInterval(geofencePollingTimer);
    geofencePollingTimer = setInterval(() => pollGeofences(floorId), 2000);
}

function pollGeofences(floorId) {
    const layer = MapManager.getLayer('geofence');
    if (!layer) return;

    const url = floorId
        ? `${API_BASE}/geofences/?floor_id=${floorId}&is_active=true`
        : `${API_BASE}/geofences/?is_active=true`;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            data.results.forEach(g => {
                const state = geofenceState[g.id];
                if (!state) {
                    renderGeofence(g);
                    return;
                }

                const cxChanged = Math.abs(state.cx - g.center_x) > 0.5;
                const cyChanged = Math.abs(state.cy - g.center_y) > 0.5;
                const rChanged  = Math.abs(state.r  - g.radius)   > 0.5;

                if (cxChanged || cyChanged) {
                    applyCircleTransition(state.circle, 'position');
                    state.circle.setLatLng([g.center_y, g.center_x]);
                    state.labelMarker.setLatLng([g.center_y, g.center_x]);
                    state.cx = g.center_x;
                    state.cy = g.center_y;

                    if (g.severity === 'danger') {
                        addEvent('danger', `위험구역 '${g.name}' 이동 감지`);
                    }
                }

                if (rChanged) {
                    applyCircleTransition(state.circle, 'radius');
                    state.circle.setRadius(g.radius);
                    state.r = g.radius;

                    if (g.radius > state.r) {
                        addEvent('danger', `위험구역 '${g.name}' 확산 (r=${Math.round(g.radius)})`);
                    }
                }
            });
        });
}

function applyCircleTransition(leafletCircle, type) {
    const el = leafletCircle.getElement && leafletCircle.getElement();
    if (!el) return;
    el.style.transition = type === 'radius'
        ? 'r 0.8s ease'
        : 'cx 0.8s ease, cy 0.8s ease';
}