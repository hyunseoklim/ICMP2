/**
 * geofence.js
 * 위험구역(원형 geofence) 생성 / 조회 / 삭제 + CSS transition 애니메이션
 * center_x, center_y, radius 변화 → SVG circle transition 으로 이동/확산 표현
 */

window.geofenceLayer = null;

const SEVERITY_COLOR = {
  danger:  { fill: 'rgba(239,68,68,0.15)',  stroke: '#ef4444' },
  warning: { fill: 'rgba(245,158,11,0.12)', stroke: '#f59e0b' },
  safe:    { fill: 'rgba(34,197,94,0.10)',  stroke: '#22c55e' },
};

// geofenceId → { circle, prevCx, prevCy, prevR }
const geofenceState = {};

// ─── 레이어 초기화 (map_init.js initMap 이후 호출됨) ─────────

function initGeofenceLayer() {
  window.geofenceLayer = L.layerGroup().addTo(map);
}

// ─── Leaflet.draw 원 그리기 버튼 ─────────────────────────────

let drawCircleControl = null;

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-draw-geofence').addEventListener('click', startGeofenceDraw);
});

function startGeofenceDraw() {
  if (!map) return;
  if (!window.geofenceLayer) initGeofenceLayer();

  if (drawCircleControl) {
    drawCircleControl.disable();
  }

  drawCircleControl = new L.Draw.Circle(map, {
    shapeOptions: {
      color: '#ef4444',
      fillColor: 'rgba(239,68,68,0.15)',
      fillOpacity: 1,
      weight: 1.5,
    },
    showRadius: true,
    metric: false,
  });
  drawCircleControl.enable();
  window.geofenceDrawer = drawCircleControl;

  map.once(L.Draw.Event.CREATED, (e) => {
    const layer = e.layer;
    const center = layer.getLatLng();
    const radius = layer.getRadius();

    // CRS.Simple 에서는 getRadius() 가 픽셀 단위
    const cx = center.lng;
    const cy = center.lat;

    const name = prompt('위험구역 이름을 입력하세요', '위험구역');
    if (!name) return;

    const severity = prompt('위험도 (danger / warning / safe)', 'danger') || 'danger';

    const payload = {
      floor: currentFloorId || null,
      name,
      center_x: cx,
      center_y: cy,
      radius,
      severity,
      is_active: true,
    };

    fetch(`${API_BASE}/geofences/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
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
  if (!window.geofenceLayer) initGeofenceLayer();
  window.geofenceLayer.clearLayers();

  const url = floorId
    ? `${API_BASE}/geofences/?floor_id=${floorId}&is_active=true`
    : `${API_BASE}/geofences/?is_active=true`;

  fetch(url)
    .then(r => r.json())
    .then(data => {
      data.forEach(g => renderGeofence(g));
      startGeofencePolling(floorId);
    });
}

// ─── 위험구역 렌더링 ─────────────────────────────────────────

function renderGeofence(g) {
  if (!window.geofenceLayer) initGeofenceLayer();

  const colors = SEVERITY_COLOR[g.severity] || SEVERITY_COLOR.danger;

  const circle = L.circle([g.center_y, g.center_x], {
    radius: g.radius,
    color: colors.stroke,
    fillColor: colors.fill,
    fillOpacity: 1,
    weight: 1.5,
    dashArray: '4,3',
    className: `geofence-circle geofence-${g.severity}`,
  }).addTo(window.geofenceLayer);

  // 이름 레이블
  const label = L.divIcon({
    html: `<div style="font-size:11px;font-weight:500;color:${colors.stroke};white-space:nowrap;text-shadow:0 0 4px #0f1117">${g.name}</div>`,
    iconSize: [0, 0], iconAnchor: [0, 6],
  });
  const labelMarker = L.marker([g.center_y, g.center_x], { icon: label, interactive: false })
    .addTo(window.geofenceLayer);

  // 클릭 팝업
  circle.on('click', () => {
    showDetail('geofence', g);
    addEvent(g.severity, `위험구역 '${g.name}' 클릭`);
  });

  // 우클릭 삭제
  circle.on('contextmenu', () => {
    if (confirm(`'${g.name}' 위험구역을 삭제하시겠습니까?`)) {
      fetch(`${API_BASE}/geofences/${g.id}/`, { method: 'DELETE' })
        .then(() => {
          window.geofenceLayer.removeLayer(circle);
          window.geofenceLayer.removeLayer(labelMarker);
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
    r: g.radius,
  };
}

// ─── 폴링: 변경된 값으로 원 이동/확산 ───────────────────────
/**
 * 서버에서 받은 center_x/center_y/radius 가 이전값과 다르면
 * circle.setLatLng / setRadius 로 업데이트 → Leaflet 이 내부적으로
 * CSS transition 없이 즉시 이동하므로, SVG element 에 transition 을 직접 주입한다.
 */

let geofencePollingTimer = null;

function startGeofencePolling(floorId) {
  if (geofencePollingTimer) clearInterval(geofencePollingTimer);
  geofencePollingTimer = setInterval(() => pollGeofences(floorId), 2000);
}

function pollGeofences(floorId) {
  const url = floorId
    ? `${API_BASE}/geofences/?floor_id=${floorId}&is_active=true`
    : `${API_BASE}/geofences/?is_active=true`;

  fetch(url)
    .then(r => r.json())
    .then(data => {
      data.forEach(g => {
        const state = geofenceState[g.id];
        if (!state) {
          renderGeofence(g);
          return;
        }

        const cxChanged = Math.abs(state.cx - g.center_x) > 0.5;
        const cyChanged = Math.abs(state.cy - g.center_y) > 0.5;
        const rChanged  = Math.abs(state.r - g.radius)    > 0.5;

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

/**
 * Leaflet SVG circle 엘리먼트에 CSS transition 을 주입한다.
 * type: 'position' | 'radius'
 */
function applyCircleTransition(leafletCircle, type) {
  const el = leafletCircle.getElement && leafletCircle.getElement();
  if (!el) return;
  if (type === 'radius') {
    el.style.transition = 'r 0.8s ease';
  } else {
    el.style.transition = 'cx 0.8s ease, cy 0.8s ease';
  }
}