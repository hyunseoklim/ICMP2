/**
 * sensor.js
 * 센서 더미 데이터 조회 → Leaflet 마커 렌더링
 * curl 로 주입된 데이터를 2초마다 폴링하여 마커 상태를 갱신한다.
 *
 * curl 주입 예시:
 * curl -X POST http://localhost:8000/api/sensors/ \
 *   -H "Content-Type: application/json" \
 *   -d '{"device_id":"G2","device_name":"G2 유해가스 센서","sensor_type":"gas","x":400,"y":300,"status":"danger","latest_value":{"co":32,"o2":18.1}}'
 *
 * curl -X PATCH http://localhost:8000/api/sensors/1/ \
 *   -H "Content-Type: application/json" \
 *   -d '{"status":"warning","latest_value":{"co":15}}'
 */

window.gasLayer      = null;
window.powerLayer    = null;
window.locationLayer = null;
window.deviceLayer   = null;

// sensorId → Leaflet marker
const sensorMarkers = {};
let sensorPollingTimer = null;

// ─── 레이어 초기화 ────────────────────────────────────────────

function initSensorLayers() {
  window.gasLayer      = L.layerGroup().addTo(map);
  window.powerLayer    = L.layerGroup().addTo(map);
  window.locationLayer = L.layerGroup().addTo(map);
  window.deviceLayer   = L.layerGroup().addTo(map);
}

// ─── 센서 조회 + 폴링 ─────────────────────────────────────────

function loadSensors(floorId) {
  if (!window.gasLayer) initSensorLayers();

  const url = floorId
    ? `${API_BASE}/sensors/?floor_id=${floorId}`
    : `${API_BASE}/sensors/`;

  fetch(url)
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(data => data.forEach(s => renderOrUpdateSensor(s)))
    .catch(err => console.warn('sensor fetch 실패:', err));

  if (sensorPollingTimer) clearInterval(sensorPollingTimer);
  sensorPollingTimer = setInterval(() => {
  fetch(url)
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(data => data.forEach(s => renderOrUpdateSensor(s)))
    .catch(err => console.warn('sensor fetch 실패:', err));
  }, 2000);
}

// ─── 마커 색상 규칙 ───────────────────────────────────────────

const STATUS_COLOR = {
  normal:  '#22c55e',
  warning: '#f59e0b',
  danger:  '#ef4444',
  offline: '#475569',
};

const TYPE_SHAPE = {
  gas:      'circle',
  power:    'circle',
  location: 'circle',
};

function sensorIcon(sensor) {
  const color = STATUS_COLOR[sensor.status] || '#64748b';

  // 종류별 내부 기호
  const symbol = sensor.sensor_type === 'power'    ? '⚡'
               : sensor.sensor_type === 'location' ? '📡'
               : 'G';

  return L.divIcon({
    html: `<div style="
      width:20px;height:20px;border-radius:50%;
      background:${color};
      border:2px solid #0f1117;
      display:flex;align-items:center;justify-content:center;
      font-size:9px;font-weight:700;color:#0f1117;
      box-shadow:0 0 6px ${color}66;
    ">${symbol}</div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    className: '',
  });
}

// ─── 마커 렌더/갱신 ───────────────────────────────────────────

function renderOrUpdateSensor(sensor) {
  const layer = layerForType(sensor.sensor_type);
  if (!layer) return;

  if (sensorMarkers[sensor.id]) {
    // 기존 마커 아이콘/위치 갱신
    const m = sensorMarkers[sensor.id];
    m.setLatLng([sensor.y, sensor.x]);
    m.setIcon(sensorIcon(sensor));
    m._sensorData = sensor;
  } else {
    // 신규 마커 생성
    const marker = L.marker([sensor.y, sensor.x], {
      icon: sensorIcon(sensor),
      title: sensor.device_name,
    }).addTo(layer);

    marker._sensorData = sensor;

    marker.on('click', () => {
      showDetail('sensor', sensor);
      showSensorPopup(marker, sensor);
    });

    sensorMarkers[sensor.id] = marker;
  }

  if (sensor.status === 'danger') {
    addEvent('danger', `${sensor.device_name} 위험 상태 감지`);
  }
}

function layerForType(type) {
  if (type === 'gas')      return window.gasLayer;
  if (type === 'power')    return window.powerLayer;
  if (type === 'location') return window.locationLayer;
  return window.deviceLayer;
}

function showSensorPopup(marker, sensor) {
  const statusClass = sensor.status === 'danger' ? 'danger'
                    : sensor.status === 'warning' ? 'warning' : 'normal';

  let valHtml = '';
  if (sensor.latest_value && typeof sensor.latest_value === 'object') {
    Object.entries(sensor.latest_value).forEach(([k, v]) => {
      valHtml += `<div class="popup-row"><span>${k}</span><span class="popup-val">${v}</span></div>`;
    });
  }

  const html = `
    <div class="popup-title">${sensor.device_name}</div>
    <div class="popup-row"><span>상태</span><span class="popup-val ${statusClass}">${sensor.status}</span></div>
    <div class="popup-row"><span>종류</span><span class="popup-val">${sensor.sensor_type}</span></div>
    ${valHtml}
    <div class="popup-row" style="margin-top:4px;font-size:10px;color:var(--text-muted)">
      <span>위치</span><span>(${sensor.x}, ${sensor.y})</span>
    </div>`;

  marker.bindPopup(html, { maxWidth: 180, closeButton: true }).openPopup();
}