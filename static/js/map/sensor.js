/**
 * sensor.js
 * 센서 위치 조회 → Leaflet 마커 렌더링 (2초 폴링)
 *
 * API: /facilities/api/sensor-locations/?floor_id=<id>
 * 반환 필드: id, device_id, sensor_type, x, y, device_name, is_active
 *
 * 상태(normal/warning/danger)는 monitoring 앱 담당.
 * 현재는 위치 마커만 렌더링. 추후 monitoring API 병합 시 상태 반영.
 */

// sensorId → Leaflet marker
/**
 * sensor.js
 * 센서 위치 + 상태 렌더링
 *
 * USE_WS = false : 폴링 모드 (현재)
 * USE_WS = true  : WebSocket 모드 (팀원 완료 시 전환)
 *
 * WebSocket 메시지 형태:
 *   { "type": "full",  "layer": "sensor", "data": [...] }
 *   { "type": "delta", "layer": "sensor", "data": [...] }
 */
 /** 웹 소켓 개발이 완료되면 아래의 USE_WS를 True로 바꿔 놓으면 websocket 로직이 적용됨 */

const SensorLayer = {
    USE_WS: false,/** 웹소켓 전환 False -> True */

    _ws:        null,
    _pollTimer: null,
    _floorId:   null,

    // ─── 공통 진입점 ────────────────────────────────────────
    load(floorId) {
        this._floorId = floorId;
        this._clear();
        this.USE_WS ? this._useWS(floorId) : this._usePoll(floorId);
    },

    destroy() {
        this._clear();
    },

    _clear() {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        if (this._ws) {
            this._ws.onclose = null;  // 재연결 방지
            this._ws.close();
            this._ws = null;
        }
        // 마커 제거
        ['gas', 'power', 'locationNode',].forEach(name => {
            const layer = MapManager.getLayer(name);
            if (layer) layer.clearLayers();
        });
        Object.keys(sensorMarkers).forEach(k => delete sensorMarkers[k]);
    },

    // ─── 폴링 모드 ──────────────────────────────────────────
    _usePoll(floorId) {
        const url = `${API_BASE}/sensor-locations/?floor_id=${floorId}`;

        const fetch_ = () => {
            fetch(url)
                .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
                .then(data => data.results.forEach(s => renderOrUpdateSensor(s)))
                .catch(err => console.warn('[layer:sensor] 폴링 실패:', err));
        };

        fetch_();
        this._pollTimer = setInterval(fetch_, 2000);
    },

    // ─── WebSocket 모드 ─────────────────────────────────────
    _useWS(floorId) {
        const url = `ws://${location.host}/ws/floor/${floorId}/sensor/`;
        this._ws  = new WebSocket(url);

        this._ws.onopen = () => {
            console.info('[layer:sensor] WebSocket 연결됨');
        };

        this._ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'full' || msg.type === 'delta') {
                    msg.data.forEach(s => renderOrUpdateSensor(s));
                }
            } catch (err) {
                console.warn('[layer:sensor] 메시지 파싱 실패:', err);
            }
        };

        this._ws.onclose = () => {
            console.warn('[layer:sensor] WebSocket 끊김 — 3초 후 재연결');
            setTimeout(() => {
                if (this._floorId) this._useWS(this._floorId);
            }, 3000);
        };

        this._ws.onerror = (e) => {
            console.error('[layer:sensor] WebSocket 에러:', e);
        };
    },
};

// ─── 마커 상태 저장소 ─────────────────────────────────────────
const sensorMarkers = {};

// ─── 마커 색상 ───────────────────────────────────────────────
const STATUS_COLOR = {
    normal:  '#22c55e',
    warning: '#f59e0b',
    danger:  '#ef4444',
    offline: '#475569',
};

function sensorIcon(sensor) {
    const status = sensor.status || 'normal';
    const color  = STATUS_COLOR[status] || '#64748b';
    const symbol = sensor.sensor_type === 'power'    ? '⚡'
                 : sensor.sensor_type === 'location' ? '📡'
                 : 'G';

    return L.divIcon({
        html: `<div style="
            width:20px;height:20px;border-radius:50%;
            background:${color};border:2px solid #0f1117;
            display:flex;align-items:center;justify-content:center;
            font-size:9px;font-weight:700;color:#0f1117;
            box-shadow:0 0 6px ${color}66;
        ">${symbol}</div>`,
        iconSize:   [20, 20],
        iconAnchor: [10, 10],
        className:  '',
    });
}

// ─── 마커 렌더/갱신 ───────────────────────────────────────────
function renderOrUpdateSensor(sensor) {
    const layer = layerForType(sensor.sensor_type);
    if (!layer) return;

    if (sensorMarkers[sensor.id]) {
        const m = sensorMarkers[sensor.id];
        m.setLatLng([sensor.y, sensor.x]);
        m.setIcon(sensorIcon(sensor));
        m._sensorData = sensor;
    } else {
        const marker = L.marker([sensor.y, sensor.x], {
            icon:  sensorIcon(sensor),
            title: sensor.device_name,
        }).addTo(layer);

        marker.on('mouseover', function() {
            const el = this.getElement();
            if (el) {
                const inner = el.querySelector('div');
                if (inner) {
                    inner.style.border       = '2px solid #ffffff';
                    inner.style.boxShadow    = `0 0 10px #ffffff88`;
                    inner.style.transform    = 'scale(1.25)';
                    inner.style.transition   = 'transform 0.15s ease, box-shadow 0.15s ease';
                }
            }
            // 호버 팝오버 — tooltip 방식
            this.bindTooltip(`
                <div style="font-size:11px;font-weight:600">${sensor.device_name}</div>
                <div style="font-size:10px;color:#94a3b8">${sensor.sensor_type} · ${sensor.status || 'normal'}</div>
            `, { sticky: true, opacity: 0.95 }).openTooltip();
        });

        marker.on('mouseout', function() {
            const el = this.getElement();
            if (el) {
                const inner = el.querySelector('div');
                if (inner) {
                    // 원래 아이콘 색으로 복원
                    const color = STATUS_COLOR[sensor.status || 'normal'] || '#64748b';
                    inner.style.border    = `2px solid #0f1117`;
                    inner.style.boxShadow = `0 0 6px ${color}66`;
                    inner.style.transform = 'scale(1)';
                }
            }
            this.closeTooltip();
        });
        // ─── 호버 끝 ────────────────────────────────────────

        marker.on('click', () => {
            if (window._MAP_CLICK_NAVIGATE) {
                location.href = `/facilities/monitoring/?type=sensor&id=${sensor.id}&floor_id=${window._MAP_FLOOR_ID || currentFloorId}`;
                return;
            }
            if (typeof showDetail === 'function') showDetail('sensor', sensor);
            showSensorPopup(marker, sensor);
        });

        sensorMarkers[sensor.id] = marker;
    }

    if (sensor.status === 'danger') {
        if (typeof addEvent === 'function')
            addEvent('danger', `${sensor.device_name} 위험 상태 감지`);
    }
}

function layerForType(type) {
    if (type === 'gas')      return MapManager.getLayer('gas');
    if (type === 'power')    return MapManager.getLayer('power');
    if (type === 'location') return MapManager.getLayer('locationNode');
    // 추후 새 sensor_type 추가 시 여기에 추가
    return null
    // return MapManager.getLayer('device');
}

function showSensorPopup(marker, sensor) {
    const status      = sensor.status || 'normal';
    const statusClass = status === 'danger'  ? 'danger'
                      : status === 'warning' ? 'warning' : 'normal';

    let valHtml = '';
    if (sensor.latest_value && typeof sensor.latest_value === 'object') {
        Object.entries(sensor.latest_value).forEach(([k, v]) => {
            valHtml += `<div class="popup-row"><span>${k}</span><span class="popup-val">${v}</span></div>`;
        });
    }

    marker.bindPopup(`
        <div class="popup-title">${sensor.device_name}</div>
        <div class="popup-row">
            <span>상태</span>
            <span class="popup-val ${statusClass}">${status}</span>
        </div>
        <div class="popup-row">
            <span>종류</span>
            <span class="popup-val">${sensor.sensor_type}</span>
        </div>
        ${valHtml}
        <div class="popup-row" style="font-size:10px;color:var(--text-muted)">
            <span>위치</span><span>(${sensor.x}, ${sensor.y})</span>
        </div>
    `, { maxWidth: 180, closeButton: true }).openPopup();
}

// ─── 외부 호출 인터페이스 (map_event.js에서 호출) ──────────────
function loadSensors(floorId) {
    SensorLayer.load(floorId);
}