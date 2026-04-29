/**
 * geofence.js
 * 위험구역 생성(원형/폴리곤) / 조회 / 수정 / 삭제
 *
 * USE_WS = false : 폴링 모드 (현재)
 * USE_WS = true  : WebSocket 모드 (팀원 완료 시 전환)
 *
 * WebSocket 메시지 형태:
 *   { "type": "full",  "layer": "geofence", "data": [...] }  — 전체 상태
 *   { "type": "delta", "layer": "geofence", "data": [...] }  — 변경분만
 *
 * 생성 경로:
 *   1. 관리자 수동 — 지도에서 직접 그리기
 *   2. 가스 수치 기반 자동 — 서버가 생성, JS는 폴링/WS로 수신
 *
 * 웹소켓 개발 완료 시 USE_WS: false → true 로만 변경
 */

// ─── CSRF ────────────────────────────────────────────────────

function getCsrfToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (const c of cookies) {
        const [k, v] = c.trim().split('=');
        if (k === name) return decodeURIComponent(v);
    }
    return '';
}

// ─── 상수 ────────────────────────────────────────────────────

const SEVERITY_COLOR = {
    danger:  { fill: 'rgba(239,68,68,0.15)',  stroke: '#ef4444' },
    warning: { fill: 'rgba(245,158,11,0.12)', stroke: '#f59e0b' },
    safe:    { fill: 'rgba(34,197,94,0.10)',  stroke: '#22c55e' },
};

// ─── 상태 저장소 ─────────────────────────────────────────────
// geofenceId → { shape, labelMarker, cx, cy, r, type, severity }
const geofenceState  = {};
const _geofenceCache = {};

// ─── GeofenceLayer 객체 ───────────────────────────────────────

const GeofenceLayer = {
    USE_WS: false, /** 웹소켓 전환: false → true */

    _ws:             null,
    _pollTimer:      null,
    _reconnectTimer: null,  // 재연결 타이머 ID 추적
    _floorId:        null,

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
        // 재연결 타이머 취소 — load()가 다시 호출될 때 기존 타이머 제거
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
        if (this._ws) {
            this._ws.onclose = null;  // 수동 종료 시 재연결 방지
            this._ws.close();
            this._ws = null;
        }
        const layer = MapManager.getLayer('geofence');
        if (layer) layer.clearLayers();
        Object.keys(geofenceState).forEach(k => delete geofenceState[k]);
        Object.keys(_geofenceCache).forEach(k => delete _geofenceCache[k]);
    },

    // ─── 폴링 모드 ──────────────────────────────────────────
    _usePoll(floorId) {
        const url = floorId
            ? `${API_BASE}/geofences/?floor_id=${floorId}&is_active=true`
            : `${API_BASE}/geofences/?is_active=true`;

        const fetch_ = () => {
            fetch(url)
                .then(r => r.json())
                // 폴링은 항상 전체 데이터 → full 처리
                .then(data => _processFullData(data.results))
                .catch(() => {});
        };

        fetch_();
        this._pollTimer = setInterval(fetch_, 2000);
    },

    // ─── WebSocket 모드 ─────────────────────────────────────
    _useWS(floorId) {
        const url = `ws://${location.host}/ws/floor/${floorId}/geofence/`;
        this._ws  = new WebSocket(url);

        this._ws.onopen = () => {
            console.info('[layer:geofence] WebSocket 연결됨');
        };

        this._ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                // full/delta 분리 처리
                if (msg.type === 'full') {
                    _processFullData(msg.data);
                } else if (msg.type === 'delta') {
                    _processDeltaData(msg.data);
                }
            } catch (err) {
                console.warn('[layer:geofence] 메시지 파싱 실패:', err);
            }
        };

        this._ws.onclose = () => {
            console.warn('[layer:geofence] WebSocket 끊김 — 3초 후 재연결');
            this._reconnectTimer = setTimeout(() => {
                this._reconnectTimer = null;
                // 현재 floorId와 일치할 때만 재연결
                // _clear()로 타이머가 취소됐으면 여기까지 오지 않음
                if (this._floorId === floorId) {
                    this._useWS(floorId);
                }
            }, 3000);
        };

        this._ws.onerror = (e) => {
            console.error('[layer:geofence] WebSocket 에러:', e);
        };
    },
};

// ─── 데이터 처리 ─────────────────────────────────────────────

/**
 * _processFullData
 * 전체 목록 기준 처리.
 * 없어진 지오펜스 제거 포함.
 * 폴링 + WS full 메시지 공통 사용.
 */
function _processFullData(results) {
    const activeIds = new Set(results.map(g => g.id));

    // 응답에 없는 지오펜스 제거 (비활성화 or 삭제됨)
    Object.keys(geofenceState).forEach(id => {
        if (!activeIds.has(parseInt(id))) {
            _removeGeofence(id);
        }
    });

    results.forEach(g => _applyGeofence(g));
}

/**
 * _processDeltaData
 * 변경분만 처리.
 * 없어진 것 제거 로직 없음 — delta에 없다고 삭제하면 안 됨.
 * id 기준으로 캐시와 병합 후 적용.
 */
function _processDeltaData(results) {
    results.forEach(g => {
        // is_active=false로 명시적으로 온 경우만 제거
        if (g.is_active === false) {
            _removeGeofence(g.id);
            return;
        }

        // 캐시와 병합 — delta는 변경된 필드만 오므로
        // 기존 캐시에 변경분을 덮어써서 완전한 객체 생성
        // 예) 캐시: { id:1, center_x:10, radius:5, severity:"warning" }
        //     delta: { id:1, severity:"danger" }
        //     병합: { id:1, center_x:10, radius:5, severity:"danger" }
        const merged = Object.assign({}, _geofenceCache[g.id] || {}, g);
        _applyGeofence(merged);
    });
}

/**
 * _applyGeofence
 * 단일 지오펜스 캐싱 + 렌더링/갱신.
 * full/delta/신규생성 공통 사용.
 * id 기준으로 기존 상태와 비교하여 변경분만 적용.
 */
function _applyGeofence(g) {
    // layer null 체크
    const layer = MapManager.getLayer('geofence');
    if (!layer) return;

    // 캐시 갱신 (id 기준)
    _geofenceCache[g.id] = g;

    const state = geofenceState[g.id];

    // 신규 — 렌더링
    if (!state) {
        renderGeofence(g);
        return;
    }

    // severity 변경 — 색상이 달라지므로 완전 재렌더링
    if (state.severity !== g.severity) {
        layer.removeLayer(state.shape);
        layer.removeLayer(state.labelMarker);
        delete geofenceState[g.id];
        renderGeofence(g);
        return;
    }

    // 폴리곤 — 좌표 배열 전체 교체가 필요하므로 항상 재렌더링
    // severity 변경 없어도 좌표 변경이 올 수 있으므로 부분 갱신 하지 않음
    if (g.geofence_type === 'polygon') {
        layer.removeLayer(state.shape);
        layer.removeLayer(state.labelMarker);
        delete geofenceState[g.id];
        renderGeofence(g);
        return;
    }

    // 원형 — 위치/반경 변화만 부분 갱신
    if (g.geofence_type === 'circle' && state.type === 'circle') {
        const cxChanged = Math.abs(state.cx - g.center_x) > 0.5;
        const cyChanged = Math.abs(state.cy - g.center_y) > 0.5;
        const rChanged  = Math.abs(state.r  - g.radius)   > 0.5;

        if (cxChanged || cyChanged) {
            applyCircleTransition(state.shape, 'position');
            state.shape.setLatLng([g.center_y, g.center_x]);
            state.labelMarker.setLatLng([g.center_y, g.center_x]);
            state.cx = g.center_x;
            state.cy = g.center_y;
            if (typeof addEvent === 'function' && g.severity === 'danger')
                addEvent('danger', `위험구역 '${g.name}' 이동 감지`);
        }

        if (rChanged) {
            const prevR = state.r;  // 덮어쓰기 전에 저장
            applyCircleTransition(state.shape, 'radius');
            state.shape.setRadius(g.radius);
            state.r = g.radius;
            if (typeof addEvent === 'function' && g.radius > prevR)
                addEvent('danger', `위험구역 '${g.name}' 확산 (r=${Math.round(g.radius)})`);
        }
    }
}

/**
 * _removeGeofence
 * 단일 지오펜스 제거.
 * full/delta 공통 사용.
 */
function _removeGeofence(id) {
    const layer = MapManager.getLayer('geofence');
    const state = geofenceState[id];
    if (state && layer) {
        layer.removeLayer(state.shape);
        layer.removeLayer(state.labelMarker);
    }
    delete geofenceState[id];
    delete _geofenceCache[id];
}

// ─── 드로우 모드 ─────────────────────────────────────────────

let drawControl = null;

document.addEventListener('DOMContentLoaded', () => {
    const circleBtn  = document.getElementById('btn-draw-geofence');
    const polygonBtn = document.getElementById('btn-draw-geofence-polygon');
    if (circleBtn)  circleBtn.addEventListener('click',  () => startGeofenceDraw('circle'));
    if (polygonBtn) polygonBtn.addEventListener('click', () => startGeofenceDraw('polygon'));
});

function startGeofenceDraw(type) {
    if (!map) return;
    if (drawControl) drawControl.disable();

    const options = {
        shapeOptions: {
            color:       '#ef4444',
            fillColor:   'rgba(239,68,68,0.15)',
            fillOpacity: 1,
            weight:      1.5,
        },
    };

    drawControl = type === 'circle'
        ? new L.Draw.Circle(map,  { ...options, showRadius: true, metric: false })
        : new L.Draw.Polygon(map, { ...options, showArea: false });

    drawControl.enable();
    window.geofenceDrawer = drawControl;

    map.once(L.Draw.Event.CREATED, (e) => {
        type === 'circle'
            ? _handleCircleCreated(e)
            : _handlePolygonCreated(e);
    });
}

function _handleCircleCreated(e) {
    const center = e.layer.getLatLng();
    _showGeofenceForm({
        geofence_type: 'circle',
        center_x: center.lng,
        center_y: center.lat,
        radius:   e.layer.getRadius(),
    });
}

function _handlePolygonCreated(e) {
    const latlngs      = e.layer.getLatLngs()[0];
    const polygon_data = latlngs.map(ll => [ll.lng, ll.lat]);
    const cx = polygon_data.reduce((s, p) => s + p[0], 0) / polygon_data.length;
    const cy = polygon_data.reduce((s, p) => s + p[1], 0) / polygon_data.length;
    _showGeofenceForm({
        geofence_type: 'polygon',
        polygon_data,
        center_x: cx,
        center_y: cy,
    });
}

// ─── 생성/수정 공통 폼 ───────────────────────────────────────

function _showGeofenceForm(shapeData, existing) {
    const isEdit   = !!existing;
    const name     = prompt('위험구역 이름을 입력하세요', isEdit ? existing.name : '위험구역');
    if (!name) return;
    const severity = prompt('위험도 (danger / warning / safe)', isEdit ? existing.severity : 'danger') || 'danger';

    const body = {
        floor:         currentFloorId || null,
        name,
        severity,
        is_active:     true,
        geofence_type: shapeData.geofence_type,
        ...shapeData,
    };

    const headers = {
        'Content-Type': 'application/json',
        'X-CSRFToken':  getCsrfToken(),
    };

    if (isEdit) {
        // 수정 — PATCH
        fetch(`${API_BASE}/geofences/${existing.id}/`, {
            method: 'PATCH', headers, body: JSON.stringify(body),
        })
        .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(() => {
            GeofenceLayer.load(currentFloorId);
            if (typeof addEvent === 'function')
                addEvent('info', `위험구역 '${name}' 수정됨`);
        })
        .catch(err => console.error('[geofence] 수정 실패:', err));
    } else {
        // 생성 — POST
        fetch(`${API_BASE}/geofences/`, {
            method: 'POST', headers, body: JSON.stringify(body),
        })
        .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(data => {
            // renderGeofence + 캐싱을 _applyGeofence()로 통일
            _applyGeofence(data);
            if (typeof addEvent === 'function')
                addEvent('danger', `위험구역 '${data.name}' 생성됨`);
        })
        .catch(err => console.error('[geofence] 생성 실패:', err));
    }
}

// ─── 수정 진입점 ─────────────────────────────────────────────

function editGeofence(g) {
    const layer = MapManager.getLayer('geofence');
    if (!layer) return;

    const state = geofenceState[g.id];
    if (state) {
        layer.removeLayer(state.shape);
        layer.removeLayer(state.labelMarker);
        delete geofenceState[g.id];
    }

    startGeofenceDraw(g.geofence_type);

    map.once(L.Draw.Event.CREATED, (e) => {
        map.off(L.Draw.Event.CREATED);
        let shapeData;
        if (g.geofence_type === 'circle') {
            const center = e.layer.getLatLng();
            shapeData = {
                geofence_type: 'circle',
                center_x: center.lng,
                center_y: center.lat,
                radius:   e.layer.getRadius(),
            };
        } else {
            const latlngs      = e.layer.getLatLngs()[0];
            const polygon_data = latlngs.map(ll => [ll.lng, ll.lat]);
            const cx = polygon_data.reduce((s, p) => s + p[0], 0) / polygon_data.length;
            const cy = polygon_data.reduce((s, p) => s + p[1], 0) / polygon_data.length;
            shapeData = { geofence_type: 'polygon', polygon_data, center_x: cx, center_y: cy };
        }
        _showGeofenceForm(shapeData, g);
    });
}

// ─── 렌더링 ──────────────────────────────────────────────────

function renderGeofence(g) {
    const layer = MapManager.getLayer('geofence');
    if (!layer) return;

    const colors = SEVERITY_COLOR[g.severity] || SEVERITY_COLOR.danger;
    let shape, labelLat, labelLng;

    if (g.geofence_type === 'polygon' && g.polygon_data) {
        const latlngs = g.polygon_data.map(([x, y]) => [y, x]);
        shape = L.polygon(latlngs, {
            color: colors.stroke, fillColor: colors.fill,
            fillOpacity: 1, weight: 1.5, dashArray: '4,3',
            className: `geofence-polygon geofence-${g.severity}`,
        }).addTo(layer);
        labelLng = g.center_x;
        labelLat = g.center_y;
        geofenceState[g.id] = { shape, type: 'polygon', severity: g.severity };
    } else {
        shape = L.circle([g.center_y, g.center_x], {
            radius: g.radius, color: colors.stroke, fillColor: colors.fill,
            fillOpacity: 1, weight: 1.5, dashArray: '4,3',
            className: `geofence-circle geofence-${g.severity}`,
        }).addTo(layer);
        labelLat = g.center_y;
        labelLng = g.center_x;
        geofenceState[g.id] = {
            shape, type: 'circle', severity: g.severity,
            cx: g.center_x, cy: g.center_y, r: g.radius,
        };
    }

    const labelIcon = L.divIcon({
        html: `<div style="font-size:11px;font-weight:500;color:${colors.stroke};white-space:nowrap;text-shadow:0 0 4px #0f1117">${g.name}</div>`,
        iconSize: [0, 0], iconAnchor: [0, 6],
    });
    const labelMarker = L.marker([labelLat, labelLng], {
        icon: labelIcon, interactive: false,
    }).addTo(layer);

    geofenceState[g.id].labelMarker = labelMarker;

    shape.on('click', () => {
        if (typeof showDetail === 'function') showDetail('geofence', g);
        _showGeofencePopup(shape, g);
    });

    shape.on('contextmenu', () => {
        if (confirm(`'${g.name}' 위험구역을 삭제하시겠습니까?`)) {
            _deleteGeofence(g.id, g.name);
        }
    });
}

// ─── 팝업 ────────────────────────────────────────────────────

function _showGeofencePopup(shape, g) {
    const colors   = SEVERITY_COLOR[g.severity] || SEVERITY_COLOR.danger;
    const sizeInfo = g.geofence_type === 'circle' ? `반경 ${g.radius}m` : '폴리곤';

    shape.bindPopup(`
        <div class="popup-title">${g.name}</div>
        <div class="popup-row"><span>위험도</span>
            <span class="popup-val" style="color:${colors.stroke}">${g.severity}</span></div>
        <div class="popup-row"><span>형태</span>
            <span class="popup-val">${g.geofence_type === 'circle' ? '원형' : '폴리곤'}</span></div>
        <div class="popup-row"><span>크기</span>
            <span class="popup-val">${sizeInfo}</span></div>
        <div class="popup-row" style="margin-top:6px;gap:4px;display:flex">
            <button onclick="_onEditGeofence(${g.id})"
                style="flex:1;padding:3px 6px;font-size:10px;
                       background:#1e293b;border:1px solid #334155;
                       color:#94a3b8;border-radius:3px;cursor:pointer">수정</button>
            <button onclick="_onDeleteGeofence(${g.id},'${g.name}')"
                style="flex:1;padding:3px 6px;font-size:10px;
                       background:#1e293b;border:1px solid #ef4444;
                       color:#ef4444;border-radius:3px;cursor:pointer">삭제</button>
        </div>
    `, { maxWidth: 200, closeButton: true }).openPopup();
}

window._onEditGeofence = function(id) {
    const g = _geofenceCache[id];
    if (g) editGeofence(g);
};

window._onDeleteGeofence = function(id, name) {
    if (!confirm(`'${name}' 위험구역을 삭제하시겠습니까?`)) return;
    _deleteGeofence(id, name);
};

function _deleteGeofence(id, name) {
    fetch(`${API_BASE}/geofences/${id}/`, {
        method:  'DELETE',
        headers: { 'X-CSRFToken': getCsrfToken() },
    })
    .then(() => {
        _removeGeofence(id);
        if (typeof addEvent === 'function')
            addEvent('info', `위험구역 '${name}' 삭제됨`);
    })
    .catch(err => console.error('[geofence] 삭제 실패:', err));
}

// ─── CSS transition ───────────────────────────────────────────

function applyCircleTransition(leafletCircle, type) {
    const el = leafletCircle.getElement && leafletCircle.getElement();
    if (!el) return;
    el.style.transition = type === 'radius'
        ? 'r 0.8s ease'
        : 'cx 0.8s ease, cy 0.8s ease';
}

// ─── 외부 호출 인터페이스 (map_event.js에서 호출) ──────────────
function loadGeofences(floorId) {
    GeofenceLayer.load(floorId);
}