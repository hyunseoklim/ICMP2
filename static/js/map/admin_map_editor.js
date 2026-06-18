/**
 * admin_map_editor.js  (admin/map/map.html 전용)
 *
 * 역할:
 *   1. 좌측 패널 ↔ Leaflet 지도 연동
 *   2. API 호출 (Equipment, Sensor, LocationNode)
 *   3. divIcon HTML 카드 렌더링
 *   4. 자동 위험구역 잠금 처리
 *   5. 좌표 변환 (m ↔ cm)
 *
 * 의존성:
 *   map_only.html 의 Leaflet 인스턴스 (map, MapManager)
 *   map_event.js — loadFloorData, toggleLayer, applyPendingFocus 훅
 *   geofence.js — geofenceState (자동 위험구역 잠금용)
 *
 * 로드 순서:
 *   map_*.js 들 다음, map.html 의 인라인 JS 다음
 *
 * window 전역에 의존:
 *   API_BASE         — '/facilities/api'
 *   currentFloorId   — 현재 활성 floor id (map_config.js)
 *   MAP_AUTO_FLOOR_ID — Django 가 출력한 floor id
 *
 * 단계별 진행:
 *   3-A: 골격 + 좌표 변환 유틸 + Equipment API 호출 (현재)
 *   3-B: Sensor, LocationNode API 호출 추가
 *   3-C: 자동 위험구역 잠금
 *   3-D: divIcon HTML 빌더
 *   3-E: 마커 렌더링
 *   3-F: 좌측 패널 ↔ 지도 연동
 *   3-G: 호버·hover 효과
 */

(function () {
    'use strict';

    // ─── 글로벌 상태 (모듈 스코프) ─────────────────────────────────

    /** API 응답 데이터 캐시 */
    const dataCache = {
        equipment:    [],   // GET /equipments/ 응답
        sensor:       [],   // GET /sensor-locations/ 응답 (gas + power)
        locationNode: [],   // GET /location-nodes/ 응답
        // geofence 는 geofenceState 를 통해 접근 (별도 캐시 불필요)
    };

    /** 우리가 만든 Leaflet 마커 참조 */
    const markerRefs = {
        equipment:    {},   // { id: L.Marker }
        sensor:       {},   // { id: L.Marker }
        locationNode: {},   // { id: L.Marker }
    };

    /** 편집 변경사항 누적 ([저장] 시 일괄 전송) */
    const pendingChanges = {
        equipment:    { add: [], update: {}, delete: [] },
        sensor:       { add: [], update: {}, delete: [] },
        locationNode: { add: [], update: {}, delete: [] },
        geofence:     { add: [], update: {}, delete: [] },
    };

    /** 에디터 상태 */
    const editorState = {
        mode: 'view',          // 'view' | 'edit' | 'create' | 'zone-create' | 'zone-edit'
        activeObject: null,    // 편집 중인 객체 { type, id }
        isDirty: false,        // pendingChanges 에 변경사항 있는지
    };

    // 디버깅용 전역 노출
    window._mapEditor = { dataCache, markerRefs, pendingChanges, editorState };

    /**
     * window._mapEditor.debugState()
     * 콘솔에서 호출 — 현재 편집 상태를 한눈에 dump.
     * 사용: 콘솔에 `_mapEditor.debugState()` 입력
     */
    window._mapEditor.debugState = function() {
        const dump = {
            editCtx: {
                active:       editCtx.active,
                type:         editCtx.type,
                pk:           editCtx.pk,
                dirty:        editCtx.dirty,
                resizing:     editCtx.resizing,
                zoneHandling: editCtx.zoneHandling,
                origLatLng:   editCtx.origLatLng,
            },
            'editCtx.data':    editCtx.data ? { ...editCtx.data } : null,
            'popover._latlng': editCtx.popover && editCtx.popover._latlng,
            'popover._map?':   !!(editCtx.popover && editCtx.popover._map),
            editorState: { ...editorState },
            pendingChanges: {
                equipment_update_count:    Object.keys(pendingChanges.equipment.update    || {}).length,
                sensor_update_count:       Object.keys(pendingChanges.sensor.update       || {}).length,
                locationNode_update_count: Object.keys(pendingChanges.locationNode.update || {}).length,
                geofence_update_count:     Object.keys(pendingChanges.geofence.update     || {}).length,
            },
            UI: {
                'edit-mode-btn.disabled':         document.getElementById('edit-mode-btn')?.disabled,
                'edit-save-btn-floating exists':  !!document.getElementById('edit-save-btn-floating'),
                'edit-actions-wrap display':      document.getElementById('edit-actions-wrap')?.style.display,
            },
        };
        console.group('[_mapEditor.debugState]');
        Object.entries(dump).forEach(([k, v]) => console.log(k, v));
        console.groupEnd();
        return dump;
    };

    // ─── 좌표 변환 유틸 ───────────────────────────────────────────

    /**
     * metersToCmDisplay
     * 입력: meters {number} — 미터 단위 좌표/크기
     * 출력: {number} — cm 단위 (정수 반올림)
     *
     * 예: 15.05m → 1505
     */
    function metersToCmDisplay(meters) {
        return Math.round(meters * 100);
    }

    /**
     * markerToMeters
     * 입력: marker {L.Marker}
     * 출력: { x: number, y: number } — 미터 단위 좌표
     */
    function markerToMeters(marker) {
        const ll = marker.getLatLng();
        return { x: ll.lng, y: ll.lat };
    }

    /**
     * pixelToMeters
     * 입력: pixelX, pixelY {number} — 화면 픽셀 좌표
     * 출력: { x: number, y: number } — 미터 단위 (Leaflet 변환)
     */
    function pixelToMeters(pixelX, pixelY) {
        if (!window.map) return { x: 0, y: 0 };
        const cp = L.point(pixelX, pixelY);
        const ll = map.containerPointToLatLng(cp);
        return { x: ll.lng, y: ll.lat };
    }

    /**
     * getMapCenterMeters
     * 출력: { x: number, y: number } — 현재 지도 중앙의 미터 좌표
     */
    function getMapCenterMeters() {
        if (!window.map) return { x: 0, y: 0 };
        const c = map.getCenter();
        return { x: c.lng, y: c.lat };
    }

    /**
     * isRectColliding
     * 입력: r1, r2 — 각각 { center_x, center_y, width, height }
     * 출력: {boolean} — 두 사각형이 겹치는지 (AABB)
     */
    function isRectColliding(r1, r2) {
        return (
            r1.center_x - r1.width/2  < r2.center_x + r2.width/2  &&
            r1.center_x + r1.width/2  > r2.center_x - r2.width/2  &&
            r1.center_y - r1.height/2 < r2.center_y + r2.height/2 &&
            r1.center_y + r1.height/2 > r2.center_y - r2.height/2
        );
    }

    // P3-3 (R2-G-7): 주어진 임시 facility 데이터가 다른 설비와 겹치는지 검사
    // 자기 자신은 제외 (임시 객체는 'temp-<code>' id 이므로 dataCache 와 매칭 안 됨)
    function _checkFacilityCollision(tempData) {
        if (!tempData || tempData.center_x == null || tempData.center_y == null) return false;
        const r1 = {
            center_x: tempData.center_x,
            center_y: tempData.center_y,
            width:    tempData.width  || 1.0,
            height:   tempData.height || 1.0,
        };
        for (const eq of dataCache.equipment) {
            if (eq.center_x == null || eq.center_y == null) continue;  // 미배치 EQ 건너뜀
            const r2 = {
                center_x: eq.center_x,
                center_y: eq.center_y,
                width:    eq.width  || 1.0,
                height:   eq.height || 1.0,
            };
            if (isRectColliding(r1, r2)) return true;
        }
        return false;
    }

    // ─── API 호출 함수 ────────────────────────────────────────────

    /**
     * fetchEquipments
     * 입력: floorId {number}
     * 출력: Promise<Array> — Equipment 목록
     *
     * 부수효과: dataCache.equipment 갱신
     */
    function fetchEquipments(floorId) {
        const url = `${API_BASE}/equipments/?floor_id=${floorId}`;
        return fetch(url)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
                const items = data.results || [];
                dataCache.equipment = items;
                console.info(`[admin_map_editor] Equipment 데이터 수신: ${items.length}개`, items);
                return items;
            })
            .catch(err => {
                console.warn('[admin_map_editor] Equipment 조회 실패:', err);
                return [];
            });
    }
    /**
     * fetchSensors
     * 입력: floorId {number}
     * 출력: Promise<Array> — Sensor 목록 (gas + power 통합)
     *
     * 부수효과: dataCache.sensor 갱신
     *
     * 응답 예: { results: [{id, device_id, sensor_type, x, y, device_name, is_active}, ...] }
     * sensor_type 은 'gas' 또는 'power' (요구사항 결정 5-3: 'a' — 위치만 추가 가능)
     */
    function fetchSensors(floorId) {
        const url = `${API_BASE}/sensor-locations/?floor_id=${floorId}`;
        return fetch(url)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
                const items = data.results || [];
                dataCache.sensor = items;
                console.info(`[admin_map_editor] Sensor 데이터 수신: ${items.length}개 (gas+power 통합)`, items);
                return items;
            })
            .catch(err => {
                console.warn('[admin_map_editor] Sensor 조회 실패:', err);
                return [];
            });
    }

    /**
     * fetchLocationNodes
     * 입력: floorId {number}
     * 출력: Promise<Array> — LocationNode 목록
     *
     * 부수효과: dataCache.locationNode 갱신
     *
     * 응답 예: { results: [{id, node_name, x, y, status, ...}, ...] }
     * 주의: node_code 가 API 응답에 누락 (서버측 보완 필요 — R 항목으로 등록됨)
     */
    function fetchLocationNodes(floorId) {
        const url = `${API_BASE}/location-nodes/?floor_id=${floorId}`;
        return fetch(url)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
                const items = data.results || [];
                dataCache.locationNode = items;
                console.info(`[admin_map_editor] LocationNode 데이터 수신: ${items.length}개`, items);
                return items;
            })
            .catch(err => {
                console.warn('[admin_map_editor] LocationNode 조회 실패:', err);
                return [];
            });
    }
    // ─── 자동 위험구역 잠금 처리 ───────────────────────────────────
    /**
     * setupAutoGeofenceLock
     * 현재 등록된 모든 위험구역에 대해 자동/수동 분기 → 잠금/실선 적용.
     *
     * 원래 layeradd 이벤트로 새 도형 추가 시점에 반응하려 했으나
     * L.LayerGroup 은 layeradd 를 발화하지 않음 (L.FeatureGroup 만 발화).
     * 따라서 layeradd 의존 대신 geofenceState 를 직접 순회.
     *
     * 호출 시점:
     *   - applyPendingFocus 안에서 (Promise.all 의 .then() 직후)
     *   - WebSocket 갱신 시에도 자동 적용되려면 별도 단계 필요
     *     (편집 페이지의 일시적 사용 특성상 일단 1회 적용으로 충분)
     *
     * 결정 사항 (요구사항 합의):
     *   - E-3-1: name.startswith('[자동]') 으로 구분
     *   - 결정 2-a: 자동은 수정/삭제 불가
     *   - 결정 A: 우리 페이지에서만 잠금 (다른 페이지 영향 없음)
     */
    function setupAutoGeofenceLock() {
        if (typeof geofenceState === 'undefined') {
            console.warn('[admin_map_editor] geofenceState 미정의 — 잠금 건너뜀');
            return;
        }

        let autoCount = 0, manualCount = 0;

        Object.entries(geofenceState).forEach(([id, state]) => {
            const g = _geofenceCache[id];
            if (!g) return;
            const isAuto = g.name && g.name.startsWith('[자동]');

            if (isAuto) {
                if (state.shape)       _lockAutoShape(state.shape, g);
                if (state.labelMarker) _lockAutoLabel(state.labelMarker, g);
                autoCount++;
            } else {
                if (state.shape) _restoreManualShape(state.shape, g);
                manualCount++;
            }
        });

        console.info(`[admin_map_editor] 위험구역 잠금: 자동 ${autoCount}개 (점선·🔒), 수동 ${manualCount}개 (실선)`);
    }

    // ─── Geofence 호버 팝오버 덮어쓰기 (R1-G — P1-4b) ────────────
    // geofence.js 의 기존 mouseover/mouseout 핸들러를 admin 페이지에 한해 제거하고
    // 우리 호버 팝오버로 덮어쓴다. geofence.js 자체는 수정하지 않아
    // 다른 페이지(모니터링 등)에는 영향 없음.
    function overrideGeofenceHoverPopover() {
        if (typeof geofenceState === 'undefined') {
            console.warn('[admin_map_editor] geofenceState 미정의 — 호버 덮어쓰기 건너뜀');
            return;
        }

        let count = 0;
        Object.entries(geofenceState).forEach(([id, state]) => {
            const shape = state.shape;
            const g = _geofenceCache[id];
            if (!shape || !g) return;

            // 기존 geofence.js 의 mouseover/mouseout 핸들러 + 툴팁 해제
            try {
                shape.off('mouseover');
                shape.off('mouseout');
                shape.unbindTooltip();
            } catch (e) {
                console.warn(`[admin_map_editor] Geofence ${id} 기존 hover 해제 실패:`, e);
            }

            // 우리 호버 팝오버 부착 (함수형 content → _geofenceCache 갱신 시 자동 반영)
            attachHoverPopover(shape, g, buildGeofencePopover);

            // P4-1 (R2-A): geofence shape 클릭 → 편집 모드 진입
            // 자동 위험구역도 진입 가능 — Phase 5 에서 *편집 불가* 처리
            shape.on('click', function(e) {
                if (placeCtx.active) return;
                if (e && e.originalEvent) L.DomEvent.stopPropagation(e);
                _startEditMode('zone', parseInt(id), shape, g);
            });

            // P1-5: hover 시 자기 severity 색 유지 + weight 증가 (SVG outline 불가 대안)
            shape.on('mouseover', function() {
                this._prevStyleP15 = {
                    weight: this.options.weight,
                    color:  this.options.color,
                };
                this.setStyle({ weight: 4 });
            });
            shape.on('mouseout', function() {
                if (this._prevStyleP15) {
                    this.setStyle(this._prevStyleP15);
                    this._prevStyleP15 = null;
                }
            });
            count++;
        });

        console.info(`[admin_map_editor] Geofence 호버 팝오버 적용: ${count}개`);
    }

    /**
     * _findGeofenceByLayer
     * 주어진 leaflet layer 가 어느 geofenceState 의 shape 또는 labelMarker 인지 검색
     *
     * 반환: { id, state, isShape: boolean } 또는 null
     */
    function _findGeofenceByLayer(layer) {
        if (typeof geofenceState === 'undefined') return null;

        for (const id in geofenceState) {
            const state = geofenceState[id];
            if (state.shape === layer) {
                return { id, state, isShape: true };
            }
            if (state.labelMarker === layer) {
                return { id, state, isShape: false };
            }
        }
        return null;
    }

    /**
     * _lockAutoShape
     * 자동 위험구역 도형에 잠금 스타일 + 이벤트 제거 적용
     */
    function _lockAutoShape(shape, g) {
        try {
            shape.setStyle({
                dashArray:   '8, 6',         // 자동: 큰 간격 점선 (수동은 4,3 또는 실선)
                fillOpacity: 0.08,           // 더 옅게
            });
        } catch (e) {
            console.warn(`[admin_map_editor] 자동 ${g.id} 스타일 적용 실패:`, e);
        }

        try {
            shape.off('click');
            shape.off('mouseover');
            shape.off('mouseout');
            shape.off('contextmenu');
        } catch (e) {
            console.warn(`[admin_map_editor] 자동 ${g.id} 이벤트 제거 실패:`, e);
        }
    }

    /**
     * _restoreManualShape
     * 수동 위험구역 — 실선으로 (geofence.js 기본은 점선 '4,3')
     * 이벤트는 geofence.js 가 등록한 것 그대로 유지
     */
    function _restoreManualShape(shape, g) {
        try {
            shape.setStyle({
                dashArray:   null,            // 수동: 실선
                fillOpacity: 1,
            });
        } catch (e) {
            console.warn(`[admin_map_editor] 수동 ${g.id} 스타일 적용 실패:`, e);
        }
    }

    /**
     * _lockAutoLabel
     * 자동 위험구역 라벨에 🔒 prefix 추가
     */
    function _lockAutoLabel(labelMarker, g) {
        try {
            const lockedIcon = L.divIcon({
                html: `<div style="font-size:11px;font-weight:500;color:#9ca3af;white-space:nowrap;text-shadow:0 0 4px #0f1117">🔒 ${g.name}</div>`,
                iconSize:   [0, 0],
                iconAnchor: [0, 6],
            });
            labelMarker.setIcon(lockedIcon);
        } catch (e) {
            console.warn(`[admin_map_editor] 자동 ${g.id} 라벨 변경 실패:`, e);
        }
    }
    // ─── divIcon HTML 빌더 (단계 3-D — 정의만, 사용은 단계 3-E) ──────

    /**
     * buildEquipmentIcon
     * Equipment (설비) 의 divIcon 생성
     *
     * 입력:
     *   eq   — Equipment 객체 { id, equipment_code, equipment_name, status, ... }
     *   mode — 'view' | 'edit' | 'create'
     *
     * 출력: L.DivIcon
     *
     * 디자인: 파란 테두리 카드 (.obj-card-facility)
     *   - 코드 + 이름 + 상태 점
     */
    function buildEquipmentIcon(eq, mode = 'view') {
        const editClass = mode === 'edit' ? ' obj-edit-mode' : '';
        const createClass = mode === 'create' ? ' obj-create-mode' : '';
        const status = eq.status || 'normal';
        const statusColor = status === 'normal' ? '#22c55e'
                         : status === 'warning' ? '#f59e0b'
                         : status === 'danger'  ? '#ef4444'
                         : '#94a3b8';
        const statusText = status === 'normal' ? '정상'
                        : status === 'warning' ? '경고'
                        : status === 'danger'  ? '위험'
                        : '미상';

        // P3-4 (R3-E): 생성 중일 때 뱃지 추가
        const creatingBadge = mode === 'create' ? '<span class="creating-badge">생성 중</span>' : '';
        // P3-6 (R3-F): 생성 중일 때 [x] 삭제 버튼
        const creatingDeleteBtn = mode === 'create'
            ? '<button type="button" class="creating-delete-btn" data-placing-delete="1" aria-label="삭제">×</button>'
            : '';
        const html = `
            <div style="position:relative;">
                ${creatingBadge}
                ${creatingDeleteBtn}
                <div class="obj-card-facility${editClass}${createClass}" data-obj-type="facility" data-obj-id="${eq.id}">
                    <span class="text-xs font-mono text-blue-400 font-semibold">${eq.equipment_code}</span>
                    <p class="text-sm font-bold text-slate-800 mt-0.5">${eq.equipment_name}</p>
                    <div class="mt-2 flex items-center gap-1">
                        <span class="w-1.5 h-1.5 rounded-full" style="background:${statusColor};"></span>
                        <span class="text-xs text-slate-500">${statusText}</span>
                    </div>
                </div>
            </div>
        `;

        return L.divIcon({
            html,
            className: 'admin-map-divicon admin-equipment-icon',
            iconSize:  null,      // 컨텐츠에 맞춰
            iconAnchor: [70, 35], // 중앙 (카드 폭 약 140, 높이 약 70 가정)
        });
    }

    /**
     * buildGasIcon
     * 가스 센서 divIcon 생성
     *
     * 입력:
     *   sensor — { id, device_id, device_name, sensor_type='gas', ... }
     *   mode   — 'view' | 'edit' | 'create'
     *
     * 디자인: 노란 테두리 카드 (.obj-card-gas)
     */
    function buildGasIcon(sensor, mode = 'view') {
        const editClass   = mode === 'edit'   ? ' obj-edit-mode'   : '';
        const createClass = mode === 'create' ? ' obj-create-mode' : '';

        // R1-H: 텍스트 없는 디자인 — 작은 아이콘만. 코드·이름은 호버 팝오버에서 표시(P1-4).
        // P3-4 (R3-E): 생성 중일 때 뱃지 추가
        const creatingBadge = mode === 'create' ? '<span class="creating-badge">생성 중</span>' : '';
        // P3-6 (R3-F): 생성 중일 때 [x] 삭제 버튼
        const creatingDeleteBtn = mode === 'create'
            ? '<button type="button" class="creating-delete-btn" data-placing-delete="1" aria-label="삭제">×</button>'
            : '';
        const html = `
            <div style="position:relative;">
                ${creatingBadge}
                ${creatingDeleteBtn}
                <div class="obj-icon-gas${editClass}${createClass}" data-obj-type="gas" data-obj-id="${sensor.id}">
                    <i data-lucide="cloud" class="w-4 h-4"></i>
                </div>
            </div>
        `;

        return L.divIcon({
            html,
            className: 'admin-map-divicon admin-gas-icon',
            iconSize:  [28, 28],
            iconAnchor: [14, 14],
        });
    }

    /**
     * buildPowerIcon
     * 스마트 전력 시스템 divIcon 생성
     *
     * 입력:
     *   sensor — { id, device_id, device_name, sensor_type='power', ... }
     *   mode   — 'view' | 'edit' | 'create'
     *
     * 디자인: 어두운 카드 (.obj-card-power)
     */
    function buildPowerIcon(sensor, mode = 'view') {
        const editClass   = mode === 'edit'   ? ' obj-edit-mode'   : '';
        const createClass = mode === 'create' ? ' obj-create-mode' : '';

        // R1-H: 텍스트 없는 디자인
        // P3-4 (R3-E): 생성 중일 때 뱃지 추가
        const creatingBadge = mode === 'create' ? '<span class="creating-badge">생성 중</span>' : '';
        // P3-6 (R3-F): 생성 중일 때 [x] 삭제 버튼
        const creatingDeleteBtn = mode === 'create'
            ? '<button type="button" class="creating-delete-btn" data-placing-delete="1" aria-label="삭제">×</button>'
            : '';
        const html = `
            <div style="position:relative;">
                ${creatingBadge}
                ${creatingDeleteBtn}
                <div class="obj-icon-power${editClass}${createClass}" data-obj-type="power" data-obj-id="${sensor.id}">
                    <i data-lucide="zap" class="w-4 h-4"></i>
                </div>
            </div>
        `;

        return L.divIcon({
            html,
            className: 'admin-map-divicon admin-power-icon',
            iconSize:  [28, 28],
            iconAnchor: [14, 14],
        });
    }

    /**
     * buildNodeIcon
     * 위치 노드 divIcon 생성
     *
     * 입력:
     *   node — { id, node_name, status, ... }
     *   mode — 'view' | 'edit' | 'create'
     *
     * 디자인: 보라 테두리 작은 카드 (.obj-card-node)
     */
    function buildNodeIcon(node, mode = 'view') {
        const editClass   = mode === 'edit'   ? ' obj-edit-mode'   : '';
        const createClass = mode === 'create' ? ' obj-create-mode' : '';

        // R1-H: 텍스트 없는 디자인
        // P3-4 (R3-E): 생성 중일 때 뱃지 추가
        const creatingBadge = mode === 'create' ? '<span class="creating-badge">생성 중</span>' : '';
        // P3-6 (R3-F): 생성 중일 때 [x] 삭제 버튼
        const creatingDeleteBtn = mode === 'create'
            ? '<button type="button" class="creating-delete-btn" data-placing-delete="1" aria-label="삭제">×</button>'
            : '';
        const html = `
            <div style="position:relative;">
                ${creatingBadge}
                ${creatingDeleteBtn}
                <div class="obj-icon-node${editClass}${createClass}" data-obj-type="node" data-obj-id="${node.id}">
                    <i data-lucide="map-pin" class="w-4 h-4"></i>
                </div>
            </div>
        `;

        return L.divIcon({
            html,
            className: 'admin-map-divicon admin-node-icon',
            iconSize:  [24, 24],
            iconAnchor: [12, 12],
        });
    }

    // ─── 옵션 D: 편집 모드용 divIcon 빌더 (popover 내용을 marker._icon 자체로) ─────
    function buildEquipmentEditIcon(eq) {
        return L.divIcon({
            html: buildEquipmentEditPopover(eq),
            className: 'admin-map-divicon admin-edit-icon admin-edit-icon-facility',
            iconSize: null,
            iconAnchor: [0, 0],
        });
    }
    function buildSensorEditIcon(sensor) {
        return L.divIcon({
            html: buildSensorEditPopover(sensor),
            className: 'admin-map-divicon admin-edit-icon admin-edit-icon-sensor',
            iconSize: null,
            iconAnchor: [0, 0],
        });
    }
    function buildNodeEditIcon(node) {
        return L.divIcon({
            html: buildNodeEditPopover(node),
            className: 'admin-map-divicon admin-edit-icon admin-edit-icon-node',
            iconSize: null,
            iconAnchor: [0, 0],
        });
    }

    // ─── 호버 팝오버 (R1-B-3 인프라) ────────────────────────────────
    //
    // attachHoverPopover
    // L.Marker 또는 L.Layer 에 hover 팝오버를 바인딩.
    // contentBuilder(data) 가 HTML 문자열을 반환하면 hover 시 표시됨.
    // dataRef 는 객체 참조 또는 getter 함수(가변 객체의 최신 상태 반영용).
    // 빈 문자열을 반환하면 바인딩하지 않음 (객체별 데이터 부족 시 노출 회피).
    //
    // 사용 예:
    //   attachHoverPopover(marker, eq, buildEquipmentPopover);
    //   attachHoverPopover(marker, () => placeCtx.tempData, buildPowerPopover);
    function attachHoverPopover(layer, dataRef, contentBuilder) {
        if (!layer || !contentBuilder) return;
        const getData = (typeof dataRef === 'function') ? dataRef : () => dataRef;
        // 초기 검증 — 빈 HTML 반환 시 바인딩 안 함
        if (!contentBuilder(getData())) return;
        // 함수형 content — 호버 시마다 contentBuilder 재실행 → 최신 데이터 반영
        layer.bindTooltip(() => contentBuilder(getData()), {
            className:  'admin-map-popover',
            direction:  'top',
            offset:     [0, -8],
            opacity:    1,
            permanent:  false,
            sticky:     false,
        });
    }

    // ─── 호버 팝오버 contentBuilder (P1-4a) ─────────────────────────
    // 객체별 호버 팝오버 HTML 생성. 빈 문자열 반환 시 바인딩 건너뜀.

    function buildEquipmentPopover(eq) {
        if (!eq) return '';
        return `
            <div class="popover-title">
                <span class="popover-badge" data-type="facility">설비</span>
                <span>${eq.equipment_code || ''}</span>
            </div>
            <div class="popover-row">
                <span class="key">설비명</span>
                <span class="val">${eq.equipment_name || '-'}</span>
            </div>
        `;
    }

    function buildGasPopover(sensor) {
        if (!sensor) return '';
        const code = formatCode(sensor, 'gas');
        return `
            <div class="popover-title">
                <span class="popover-badge" data-type="gas">유해가스 센서</span>
                <span>${code}</span>
            </div>
        `;
    }

    // 전력은 좌표 X/Y 포함 — 드래그 중 실시간 반영 (마커가 draggable 일 때)
    function buildPowerPopover(sensor) {
        if (!sensor) return '';
        const code = formatCode(sensor, 'power');
        const xCm = metersToCmDisplay(sensor.x ?? 0);
        const yCm = metersToCmDisplay(sensor.y ?? 0);
        return `
            <div class="popover-title">
                <span class="popover-badge" data-type="power">스마트 전력</span>
                <span>${code}</span>
            </div>
            <div class="popover-row">
                <span class="key">좌표</span>
                <span class="val">(${xCm}cm, ${yCm}cm)</span>
            </div>
        `;
    }

    function buildNodePopover(node) {
        if (!node) return '';
        const code = formatCode(node, 'node');
        return `
            <div class="popover-title">
                <span class="popover-badge" data-type="node">위치 노드</span>
                <span>${code}</span>
            </div>
        `;
    }

    // 위험구역 호버 팝오버 — geofence.js 의 _geofenceCache 데이터 사용
    // 표기 규칙은 P0-b 와 동일: DG_<RED|YEL|SAF>_<id> + 한글 위험도 라벨
    function buildGeofencePopover(g) {
        if (!g) return '';
        const sevToken = g.severity === 'danger'  ? 'RED'
                       : g.severity === 'warning' ? 'YEL'
                       : g.severity === 'safe'    ? 'SAF'
                       : 'UNK';
        const sevLabel = g.severity === 'danger'  ? '위험'
                       : g.severity === 'warning' ? '주의'
                       : g.severity === 'safe'    ? '안전'
                       : '미상';
        const code = `DG_${sevToken}_${g.id}`;
        return `
            <div class="popover-title">
                <span class="popover-badge" data-type="zone-${g.severity || 'danger'}">${sevLabel}</span>
                <span>${code}</span>
            </div>
            <div class="popover-row">
                <span class="key">이름</span>
                <span class="val">${g.name || '-'}</span>
            </div>
        `;
    }

    // δ: 설비 통합 popover — action 영역(우상, 버튼만) + card 영역(우하, 어두운 카드)
    // - 일반:    action = [크기 편집] + [×]
    // - resizing: action = [완료(dirty=파란/비dirty=회색)] + [×]
    function buildEquipmentEditPopover(eq) {
        if (!eq) return '';
        const inResize = !!editCtx.resizing;
        const doneActive = !!editCtx.dirty;
        const cx = metersToCmDisplay(eq.center_x ?? 0);
        const cy = metersToCmDisplay(eq.center_y ?? 0);
        const w  = metersToCmDisplay(eq.width  ?? 1.0);
        const h  = metersToCmDisplay(eq.height ?? 1.0);
        const leftBtn = inResize
            ? `<button type="button" class="ext-action-done-btn" data-edit-done="1" ${doneActive ? '' : 'disabled'}>완료</button>`
            : `<button type="button" class="ext-action-resize-btn" data-edit-resize="1">크기 편집</button>`;
        return `
            <div class="ext-action-area">
                ${leftBtn}
                <button type="button" class="ext-action-delete-btn" data-edit-delete="1" aria-label="삭제">×</button>
            </div>
            <div class="ext-card-area">
                <div class="popover-title">
                    <span class="popover-badge" data-type="facility">설비</span>
                    <span>${eq.equipment_code || ''}  ${eq.equipment_name || ''}</span>
                </div>
                <div class="popover-section-title">현재 좌표 및 크기</div>
                <div class="popover-info-value">X ${cx} / Y ${cy}</div>
                <div class="popover-info-value">가로 ${w}cm / 세로 ${h}cm</div>
            </div>
        `;
    }

    // δ: 가스/전력 통합 popover — action: [×] 만, card: 객체 정보 + 좌표
    function buildSensorEditPopover(sensor) {
        if (!sensor) return '';
        const code = formatCode(sensor, sensor.sensor_type || 'gas');
        const isPower = sensor.sensor_type === 'power';
        const label   = isPower ? '스마트 전력' : '유해가스 센서';
        const badgeType = sensor.sensor_type || 'gas';
        const x = metersToCmDisplay(sensor.x ?? 0);
        const y = metersToCmDisplay(sensor.y ?? 0);
        return `
            <div class="ext-action-area">
                <button type="button" class="ext-action-delete-btn" data-edit-delete="1" aria-label="삭제">×</button>
            </div>
            <div class="ext-card-area">
                <div class="popover-title">
                    <span class="popover-badge" data-type="${badgeType}">${label}</span>
                    <span>${code}</span>
                </div>
                <div class="popover-section-title">현재 좌표</div>
                <div class="popover-info-value">X ${x} / Y ${y}</div>
            </div>
        `;
    }

    // δ: 위치 노드 통합 popover — action: [×] 만, card: 객체 정보 + 좌표
    function buildNodeEditPopover(node) {
        if (!node) return '';
        const code = formatCode(node, 'node');
        const x = metersToCmDisplay(node.x ?? 0);
        const y = metersToCmDisplay(node.y ?? 0);
        return `
            <div class="ext-action-area">
                <button type="button" class="ext-action-delete-btn" data-edit-delete="1" aria-label="삭제">×</button>
            </div>
            <div class="ext-card-area">
                <div class="popover-title">
                    <span class="popover-badge" data-type="node">위치 노드</span>
                    <span>${code}</span>
                </div>
                <div class="popover-section-title">현재 좌표</div>
                <div class="popover-info-value">X ${x} / Y ${y}</div>
            </div>
        `;
    }

    // δ: 위험구역 통합 popover — action 영역(우상, [크기편집/완료] + [×]) + card 영역
    // card 영역 안에 위험도 토글 + [완료](위험도 결정 전용)
    // 자동 위험구역은 편집 불가 안내
    function buildGeofenceEditPopover(g) {
        if (!g) return '';
        const sevToken = g.severity === 'danger'  ? 'RED'
                       : g.severity === 'warning' ? 'YEL'
                       : g.severity === 'safe'    ? 'SAF' : 'UNK';
        const sevLabel = g.severity === 'danger'  ? '위험'
                       : g.severity === 'warning' ? '주의'
                       : g.severity === 'safe'    ? '안전' : '미상';
        const code = `DG_${sevToken}_${g.id}`;
        const isAuto = g.name && g.name.startsWith('[자동]');

        const cx = metersToCmDisplay(g.center_x ?? 0);
        const cy = metersToCmDisplay(g.center_y ?? 0);
        let sizeText;
        if (g.geofence_type === 'circle') {
            sizeText = `반경 ${metersToCmDisplay(g.radius ?? 0)}cm`;
        } else {
            sizeText = `꼭짓점 ${(g.polygon_data || []).length}개`;
        }

        // 외부 action — facility 와 동일 패턴 ([크기 편집]↔[완료] + [×])
        // 자동 위험구역은 액션 표시 안 함
        const inResize     = !!editCtx.resizing;
        const doneActive   = !!editCtx.dirty;
        const externalLeft = inResize
            ? `<button type="button" class="ext-action-done-btn" data-edit-done="1" ${doneActive ? '' : 'disabled'}>완료</button>`
            : `<button type="button" class="ext-action-resize-btn" data-edit-resize="1">크기 편집</button>`;
        const externalActions = isAuto
            ? ''
            : `<div class="ext-action-area">
                ${externalLeft}
                <button type="button" class="ext-action-delete-btn" data-edit-delete="1" aria-label="삭제">×</button>
               </div>`;

        // card 내부 — 위험도 토글 + [완료] (위험도 결정 완료 전용, severityDirty 기반)
        const sevDirty = !!editCtx.severityDirty;
        const cardActions = isAuto
            ? `<div class="popover-row" style="margin-top:8px; color:#94a3b8;">자동 생성된 위험구역은 수정 불가</div>`
            : `<div class="zone-edit-popover-actions">
                <button type="button" class="severity-pick-btn" data-zone-edit-severity="warning"
                        aria-selected="${g.severity === 'warning'}">🟡 주의</button>
                <button type="button" class="severity-pick-btn" data-zone-edit-severity="danger"
                        aria-selected="${g.severity === 'danger'}">🔴 위험</button>
                <button type="button" class="zone-edit-done-btn" data-zone-edit-done="1"
                        ${sevDirty ? '' : 'disabled style="opacity:0.5;cursor:not-allowed;"'}>완료</button>
               </div>`;

        return `
            ${externalActions}
            <div class="ext-card-area">
                <div class="popover-title">
                    <span class="popover-badge" data-type="zone-${g.severity || 'danger'}">${sevLabel}</span>
                    <span>${code}  ${g.name || ''}</span>
                </div>
                <div class="popover-section-title">현재 ${g.geofence_type === 'circle' ? '중심 좌표 / 반경' : '중심 좌표 / 꼭짓점'}</div>
                <div class="popover-info-value">X ${cx} / Y ${cy}</div>
                <div class="popover-info-value">${sizeText}</div>
                <div class="popover-section-title" style="margin-top:10px;">위험도</div>
                ${cardActions}
            </div>
        `;
    }

    // type → contentBuilder 디스패처 (생성 모드 임시 마커에서 사용)
    function getPopoverBuilderForType(type) {
        switch (type) {
            case 'facility': return buildEquipmentPopover;
            case 'gas':      return buildGasPopover;
            case 'power':    return buildPowerPopover;
            case 'node':     return buildNodePopover;
            default:         return null;
        }
    }

    // ─── γ-1: 정보 popover 빌더 — 좌표·크기 표시 (액션 popover 바로 아래) ─────
    // 액션 popover 와 같은 어두운 카드 디자인. 마커 drag 중 좌표 실시간 갱신 대상.

    function buildEquipmentInfoPopover(eq) {
        if (!eq) return '';
        const cx = metersToCmDisplay(eq.center_x ?? 0);
        const cy = metersToCmDisplay(eq.center_y ?? 0);
        const w  = metersToCmDisplay(eq.width  ?? 1.0);
        const h  = metersToCmDisplay(eq.height ?? 1.0);
        return `
            <div class="popover-section-title">현재 좌표 및 크기</div>
            <div class="popover-info-value">X ${cx} / Y ${cy}</div>
            <div class="popover-info-value">가로 ${w}cm / 세로 ${h}cm</div>
        `;
    }

    function buildSensorInfoPopover(sensor) {
        if (!sensor) return '';
        const x = metersToCmDisplay(sensor.x ?? 0);
        const y = metersToCmDisplay(sensor.y ?? 0);
        return `
            <div class="popover-section-title">현재 좌표</div>
            <div class="popover-info-value">X ${x} / Y ${y}</div>
        `;
    }

    function buildNodeInfoPopover(node) {
        if (!node) return '';
        const x = metersToCmDisplay(node.x ?? 0);
        const y = metersToCmDisplay(node.y ?? 0);
        return `
            <div class="popover-section-title">현재 좌표</div>
            <div class="popover-info-value">X ${x} / Y ${y}</div>
        `;
    }

    // γ: 편집/정보 popover 빌더 type 디스패처 (_startEditMode, drag.popoverSync, dragEnd 공통 사용)
    function getEditPopoverBuilder(type) {
        if (type === 'facility')                        return buildEquipmentEditPopover;
        if (type === 'gas' || type === 'power')         return buildSensorEditPopover;
        if (type === 'node')                            return buildNodeEditPopover;
        return null;
    }
    function getInfoPopoverBuilder(type) {
        if (type === 'facility')                        return buildEquipmentInfoPopover;
        if (type === 'gas' || type === 'power')         return buildSensorInfoPopover;
        if (type === 'node')                            return buildNodeInfoPopover;
        return null;
    }

        // ─── 코드 폴백 유틸 (단계 3-E 에서 마커 + 카드 양쪽에서 사용) ─────
    // ─── 마커 렌더링 (단계 3-E) ──────────────────────────────────────

    /**
     * clearAllMarkers
     * 우리가 추가한 모든 마커 제거 + markerRefs 비우기
     * (재렌더링 또는 페이지 정리 시 호출)
     */
    function clearAllMarkers() {
        ['equipment', 'sensor', 'locationNode'].forEach(type => {
            Object.values(markerRefs[type]).forEach(marker => {
                if (marker && map) map.removeLayer(marker);
            });
            markerRefs[type] = {};
        });
    }

    /**
     * renderEquipments
     * Equipment 데이터를 지도에 마커로 표시.
     *
     * 좌표: { x, y } (미터 단위) → L.marker([y, x])
     *      Leaflet CRS.Simple 에서 lat=y, lng=x
     *
     * 마커 참조: markerRefs.equipment[id] = L.Marker
     */
    function renderEquipments() {
        let count = 0;
        dataCache.equipment.forEach(eq => {
            // 좌표 검증 — Equipment 모델은 center_x/center_y 필드명 사용
            if (eq.center_x == null || eq.center_y == null) {
                console.warn(`[admin_map_editor] Equipment ${eq.id} 좌표 누락(미배치), 렌더 건너뜀`);
                return;
            }

            const icon = buildEquipmentIcon(eq, 'view');
            const marker = L.marker([eq.center_y, eq.center_x], { icon, draggable: true }).addTo(map);
            if (marker.dragging) marker.dragging.disable();   // 뷰 모드: 편집 진입 시 enable
            attachHoverPopover(marker, eq, buildEquipmentPopover);
            // P4-1 (R2-A): 마커 클릭 → 편집 모드 진입
            marker.on('click', function(e) {
                if (placeCtx.active) return;
                // 옵션 D: button click 이 marker click 으로 bubble — _bindEditPopoverActions 가 처리하도록 skip
                if (e.originalEvent && e.originalEvent.target && e.originalEvent.target.closest('button')) return;
                // 옵션 D: 동일 객체 재click → loop 방지
                if (editCtx.active && editCtx.marker === marker) {
                    L.DomEvent.stopPropagation(e);
                    return;
                }
                L.DomEvent.stopPropagation(e);
                _startEditMode('facility', eq.id, marker, eq);
            });
            markerRefs.equipment[eq.id] = marker;
            count++;
        });
        console.info(`[admin_map_editor] Equipment 마커 ${count}개 렌더링 완료`);
    }

    /**
     * renderSensors
     * Sensor 데이터 (gas + power 통합) 를 sensor_type 으로 분기하여 마커 표시.
     *
     * 마커 참조: markerRefs.sensor[id] = L.Marker
     */
    function renderSensors() {
        let gasCount = 0, powerCount = 0;
        dataCache.sensor.forEach(s => {
            if (s.x == null || s.y == null) {
                console.warn(`[admin_map_editor] Sensor ${s.id} 좌표 누락, 렌더 건너뜀`);
                return;
            }

            let icon, popoverBuilder;
            if (s.sensor_type === 'gas') {
                icon = buildGasIcon(s, 'view');
                popoverBuilder = buildGasPopover;
                gasCount++;
            } else if (s.sensor_type === 'power') {
                icon = buildPowerIcon(s, 'view');
                popoverBuilder = buildPowerPopover;
                powerCount++;
            } else {
                console.warn(`[admin_map_editor] Sensor ${s.id} 미지원 sensor_type='${s.sensor_type}'`);
                return;
            }

            const marker = L.marker([s.y, s.x], { icon, draggable: true }).addTo(map);
            if (marker.dragging) marker.dragging.disable();   // 뷰 모드: 편집 진입 시 enable
            attachHoverPopover(marker, s, popoverBuilder);
            // P4-1 (R2-A): 마커 클릭 → 편집 모드 진입 (sensor_type 으로 분기: 'gas' | 'power')
            marker.on('click', function(e) {
                if (placeCtx.active) return;
                // 옵션 D: button click skip + 동일 객체 재click loop 방지
                if (e.originalEvent && e.originalEvent.target && e.originalEvent.target.closest('button')) return;
                if (editCtx.active && editCtx.marker === marker) {
                    L.DomEvent.stopPropagation(e);
                    return;
                }
                L.DomEvent.stopPropagation(e);
                _startEditMode(s.sensor_type, s.id, marker, s);
            });
            markerRefs.sensor[s.id] = marker;
        });
        console.info(`[admin_map_editor] Sensor 마커 렌더링 완료: gas ${gasCount}개, power ${powerCount}개`);
    }

    /**
     * renderLocationNodes
     * LocationNode 데이터를 지도에 마커로 표시.
     *
     * 마커 참조: markerRefs.locationNode[id] = L.Marker
     */
    function renderLocationNodes() {
        let count = 0;
        dataCache.locationNode.forEach(n => {
            if (n.x == null || n.y == null) {
                console.warn(`[admin_map_editor] LocationNode ${n.id} 좌표 누락, 렌더 건너뜀`);
                return;
            }

            const icon = buildNodeIcon(n, 'view');
            const marker = L.marker([n.y, n.x], { icon, draggable: true }).addTo(map);
            if (marker.dragging) marker.dragging.disable();   // 뷰 모드: 편집 진입 시 enable
            attachHoverPopover(marker, n, buildNodePopover);
            // P4-1 (R2-A): 마커 클릭 → 편집 모드 진입
            marker.on('click', function(e) {
                if (placeCtx.active) return;
                // 옵션 D: button click skip + 동일 객체 재click loop 방지
                if (e.originalEvent && e.originalEvent.target && e.originalEvent.target.closest('button')) return;
                if (editCtx.active && editCtx.marker === marker) {
                    L.DomEvent.stopPropagation(e);
                    return;
                }
                L.DomEvent.stopPropagation(e);
                _startEditMode('node', n.id, marker, n);
            });
            markerRefs.locationNode[n.id] = marker;
            count++;
        });
        console.info(`[admin_map_editor] LocationNode 마커 ${count}개 렌더링 완료`);
    }

    /**
     * renderAllMarkers
     * 모든 객체의 마커를 일괄 렌더링.
     * (Geofence 는 geofence.js 가 별도 처리)
     *
     * 호출 시점: applyPendingFocus 의 Promise.all().then() 안
     */
    function renderAllMarkers() {
        // 멱등성: 기존 마커 제거 후 재렌더링
        clearAllMarkers();

        renderEquipments();
        renderSensors();
        renderLocationNodes();

        // divIcon 안의 <i data-lucide="..."> 를 SVG 로 변환 (R1-H 아이콘 표시)
        if (typeof lucide !== 'undefined') lucide.createIcons();

        console.info('[admin_map_editor] 전체 마커 렌더링 완료');
    }

    

    // 디버깅 노출
    window._mapEditor.renderAllMarkers = renderAllMarkers;
    window._mapEditor.clearAllMarkers  = clearAllMarkers;

    // ─── 좌측 패널 ↔ 지도 매핑 (단계 3-F) ──────────────────────────

    /**
     * resolveMarkerByPanelCode
     * 좌측 패널의 코드 (EQ-001, GAS-001, LOC-001, DG-001 등) 를
     * 지도의 실제 마커로 변환.
     *
     * 매핑 규칙 (정합성 R9~R11 가 해결되기 전 임시 매핑):
     *   - facility: equipment_code 완전 일치
     *   - gas/power: device_name 일치 (좌측 panel 의 name 과 비교)
     *   - node: node_name 일치 (node_code API 응답에 없으므로)
     *   - zone: DG-NNN → PK 추출 (정규식)
     *
     * 입력:
     *   code — 좌측 패널의 data-id (예: 'EQ-001', 'GAS-001')
     *   type — 좌측 패널의 data-type (예: 'facility', 'gas', 'power', 'node', 'zone')
     *   name — 좌측 패널의 name (매칭 보조용, 선택)
     *
     * 출력:
     *   { marker, data, type } 또는 null (매핑 실패)
     */
    function resolveMarkerByPanelCode(code, type, name) {
        if (type === 'facility') {
            const eq = dataCache.equipment.find(e => e.equipment_code === code);
            if (!eq) return null;
            const marker = markerRefs.equipment[eq.id];
            if (!marker) {
                // Equipment 데이터는 있지만 좌표가 없어 마커가 렌더링되지 않음
                // (현재 Equipment 모델에 좌표 필드 없음 — R12)
                console.warn(`[admin_map_editor] Equipment ${code} 의 마커 없음 (좌표 부재 — 배치 흐름 별도 단계)`);
                return null;
            }
            return { marker, data: eq, type };
        }
        if (type === 'gas' || type === 'power') {
            // 좌측 패널: GAS-001 (가스센서-A) — name 과 일치 검색
            // device_code 가 없으므로 name 으로 임시 매핑
            const sensor = dataCache.sensor.find(s =>
                s.sensor_type === type && s.device_name === name
            );
            if (!sensor) return null;
            return { marker: markerRefs.sensor[sensor.id], data: sensor, type };
        }
        if (type === 'node') {
            // T1-α Z1: API 응답에 node_code 포함 후 정식 매핑
            const node = dataCache.locationNode.find(n => n.node_code === name);
            if (!node) return null;
            return { marker: markerRefs.locationNode[node.id], data: node, type };
        }
        if (type === 'zone') {
            // DG_<RED|YEL|SAF>_<id> → PK 추출
            const match = code.match(/^DG_(?:RED|YEL|SAF)_(\d+)$/);
            if (!match) return null;
            const pk = parseInt(match[1]);
            const state = (typeof geofenceState !== 'undefined') ? geofenceState[pk] : null;
            if (!state) return null;
            return { marker: state.shape, data: _geofenceCache[pk], type };
        }
        return null;
    }

    /**
     * focusMarker
     * 지도를 마커 위치로 이동 + 강조 효과.
     *
     * 동작:
     *   1. 지도 중앙을 마커 위치로 이동 (animate)
     *   2. 마커에 강조 효과 (잠시 outline 추가, fade out)
     *
     * 입력:
     *   resolved — resolveMarkerByPanelCode 의 결과
     */
    function focusMarker(resolved) {
        if (!resolved || !resolved.marker) return;

        const { marker, data, type } = resolved;
        let latlng = null;

        // 마커 위치 추출 — 타입별로 다른 방식
        if (type === 'zone') {
            // Geofence — center_x, center_y 사용
            if (data.center_x != null && data.center_y != null) {
                latlng = L.latLng(data.center_y, data.center_x);
            }
        } else {
            // Equipment, Sensor, LocationNode — L.Marker 의 getLatLng
            if (marker && marker.getLatLng) {
                latlng = marker.getLatLng();
            }
        }

        if (!latlng) {
            console.warn('[admin_map_editor] 마커 위치 추출 실패');
            return;
        }

        // 1) 지도 이동 (현재 줌 유지)
        map.panTo(latlng, { animate: true, duration: 0.5 });

        // 2) 마커 강조 효과
        _highlightMarker(marker, type);

        console.info(`[admin_map_editor] 포커스: type=${type}, code=${data.equipment_code || data.device_name || data.node_name || data.name}`);
    }

    /**
     * _highlightMarker
     * 마커에 잠시 강조 효과 추가 (3초 후 자동 제거)
     *
     * 동작 방식:
     *   - L.Marker (divIcon) — DOM 요소에 outline 추가
     *   - L.Circle/Polygon (geofence) — setStyle 로 weight 증가
     */
    function _highlightMarker(marker, type) {
        if (!marker) return;

        // 이전 강조 제거
        clearMarkerHighlight();

        // 신규 강조
        window._lastHighlightedMarker = { marker, type };

        if (type === 'zone') {
            // Geofence — setStyle 로 강조
            try {
                marker.setStyle({ weight: 5, color: '#3b82f6' });
            } catch (e) { /* ignore */ }
            // 3초 후 원래 스타일 복원
            window._highlightTimer = setTimeout(() => {
                clearMarkerHighlight();
            }, 3000);
        } else {
            // divIcon 마커 — DOM 요소에 outline 추가
            const el = marker.getElement && marker.getElement();
            if (el) {
                const card = el.querySelector('[data-obj-type]');
                if (card) {
                    card.style.outline = '4px solid #1d4ed8';
                    card.style.outlineOffset = '-2px';
                    card.style.boxShadow = '0 0 20px rgba(29, 78, 216, 0.5)';
                    card.style.zIndex = '999';
                }
            }
            window._highlightTimer = setTimeout(() => {
                clearMarkerHighlight();
            }, 3000);
        }
    }

    /**
     * setupPanelMarkerLinking
     * 좌측 패널 .object-item 클릭 시 지도 마커 포커스.
     *
     * 호출 시점: applyPendingFocus 의 마커 렌더링 직후.
     * 멱등성: 한 번만 등록되도록 플래그 사용.
     */
    function setupPanelMarkerLinking() {
        if (window._panelLinkingRegistered) {
            return;
        }
        window._panelLinkingRegistered = true;

        document.querySelectorAll('.object-item').forEach(item => {
            // 클릭 — 배치된 객체: 마커 포커스 / 미배치 객체: 배치 모드 진입
            item.addEventListener('click', function() {
                const code = this.dataset.id;
                const pk   = parseInt(this.dataset.pk);   // P3-7: DB PK
                const type = this.dataset.type;
                const placed = this.dataset.placed === 'true';
                const name = this.querySelector('p')?.textContent.trim();

                console.info(`[admin_map_editor] 패널 클릭: code=${code}, pk=${pk}, type=${type}, placed=${placed}, name="${name}"`);

                if (!placed) {
                    // 단계 3-Z.1: 미배치 객체 클릭 → 배치 모드 진입
                    if (type === 'zone') {
                        // 위험구역은 별도 [위험 구역 추가] 버튼으로 처리
                        console.info('[admin_map_editor] 위험구역은 [위험 구역 추가] 버튼 사용');
                        return;
                    }
                    _startPlaceMode({ code, type, name, pk, panelItem: this });
                    return;
                }

                const resolved = resolveMarkerByPanelCode(code, type, name);
                if (!resolved) {
                    console.warn(`[admin_map_editor] 매핑 실패: ${code} — 마커가 지도에 없음 (좌표 부재 또는 데이터 불일치)`);
                    return;
                }

                focusMarker(resolved);
                // P4-1 (R3-C): 배치완료 항목 클릭 → 편집 모드 진입
                _startEditMode(type, pk, resolved.marker, resolved.data);
            });

            // 마우스 진입 — 지도 마커에 .panel-hover 클래스 추가 (단계 3-G.3)
            item.addEventListener('mouseenter', function() {
                const code = this.dataset.id;
                const type = this.dataset.type;
                const placed = this.dataset.placed === 'true';
                const name = this.querySelector('p')?.textContent.trim();

                if (!placed) return;  // 미배치는 호버 강조 안 함

                const resolved = resolveMarkerByPanelCode(code, type, name);
                if (!resolved) return;

                _addPanelHover(resolved);
            });

            // 마우스 이탈 — 강조 해제
            item.addEventListener('mouseleave', function() {
                const code = this.dataset.id;
                const type = this.dataset.type;
                const name = this.querySelector('p')?.textContent.trim();
                if (this.dataset.placed !== 'true') return;

                const resolved = resolveMarkerByPanelCode(code, type, name);
                if (!resolved) return;

                _removePanelHover(resolved);
            });
        });

        console.info('[admin_map_editor] 좌측 패널 ↔ 지도 연동 활성화');
    }
    // ─── 미배치 → 배치 흐름 (단계 3-Z) ──────────────────────────────

    /**
     * Place 컨텍스트 — 모듈 스코프 변수
     */
    const placeCtx = {
        active:       false,
        type:         null,         // 'facility' | 'gas' | 'power' | 'node'
        code:         null,         // 'EQ-001', 'GAS-001', etc.
        name:         null,         // '압축기-A', etc.
        panelItem:    null,         // 좌측 패널 DOM 요소
        marker:       null,         // 임시 마커 (지도에 추가됨)
        mapClickHandler: null,      // map.once 의 핸들러 참조 (취소용)
        drawer:       null,         // P3-2b: facility 사각형 그리기용 L.Draw.Rectangle
        rectShape:    null,         // P3-2b: 그려진 임시 L.Rectangle
        _colliding:   false,        // P3-3: 다른 설비와 충돌 중인지 여부 (저장 차단용)
        pk:           null,         // P3-7: DB PK (PATCH 대상 매핑용)
    };

    /** P4-1: 편집 모드 컨텍스트 */
    const editCtx = {
        active:     false,
        type:       null,    // 'facility' | 'gas' | 'power' | 'node' | 'zone'
        pk:         null,    // DB PK
        marker:     null,    // 클릭된 마커 또는 shape
        data:       null,    // 객체 데이터 (eq/sensor/node/geofence)
        popover:    null,    // δ: 통합 popover (좌상 action + 좌하 card 두 영역 포함)
        dirty:      false,   // P5-B: 변경 사항 누적 — Phase 6 [완료] PATCH 시 활용
        severityDirty: false,// δ: 위험구역 위험도 변경 dirty (popover 내부 [완료] 활성 조건)
        origLatLng: null,    // P5-B: 진입 시 원위치 백업 (Q2 실패 복원용)
        rectShape:  null,    // P5-C-1: facility 편집 시 임시 L.Rectangle 인스턴스
        resizing:   false,   // P5-C-3: 4꼭짓점 핸들 활성 여부 (γ-3 [크기편집]↔[완료] 토글 키)
        zoneHandling: false, // P5-D-B: 위험구역 핸들 편집 활성 여부
    };

    /**
     * _startPlaceMode
     * 미배치 객체 클릭 시 배치 모드 진입.
     *
     * 동작:
     *   1. placeCtx 에 정보 저장
     *   2. editorState.mode = 'create'
     *   3. 좌측 패널 항목 강조
     *   4. 지도 커서 변경 (crosshair)
     *   5. map.once('click') 청취 — 다음 클릭이 배치 위치
     */
    function _startPlaceMode({ code, type, name, pk, panelItem }) {
        // 기존 배치 모드가 있으면 취소
        if (placeCtx.active) {
            _cancelPlaceMode();
        }

        placeCtx.active = true;
        placeCtx.type = type;
        placeCtx.code = code;
        placeCtx.name = name;
        placeCtx.pk = pk;            // P3-7: DB PK 저장
        placeCtx.panelItem = panelItem;
        placeCtx.marker = null;

        editorState.mode = 'create';
        editorState.activeObject = { type, code, name };

        // 좌측 패널 항목 강조
        panelItem.style.outline = '3px solid #3b82f6';
        panelItem.style.outlineOffset = '2px';
        panelItem.style.background = '#eff6ff';

        // 지도 컨테이너 커서 변경
        const mapContainer = map.getContainer();
        if (mapContainer) {
            mapContainer.style.cursor = 'crosshair';
        }

// [편집] 버튼을 [완료] 로 변경 (단계 3-Z.3 추가)
        const editBtn = document.getElementById('edit-mode-btn');
        if (editBtn) {
            editBtn.innerHTML = '<i data-lucide="check" class="w-4 h-4"></i> 완료';
            editBtn.classList.replace('bg-slate-800', 'bg-blue-600');
            editBtn.classList.replace('hover:bg-slate-700', 'hover:bg-blue-700');
            editBtn.setAttribute('aria-pressed', 'true');
        }
        const modeBadge = document.getElementById('mode-badge');
        modeBadge?.classList.remove('hidden');
        modeBadge?.classList.add('flex');
        if (typeof lucide !== 'undefined') lucide.createIcons();

        // 안내 — 콘솔 + (선택) 사용자에게 안내 메시지
        console.info(`[admin_map_editor] 배치 모드 진입: ${code} ${name} (${type}) — 지도에서 위치를 클릭하세요`);

        // P3-5 (R3-G): 다른 객체 불투명화
        _setPlacingFade(true);

        // P3-2a (R3-A): 가스/노드/전력은 지도 중앙에 즉시 배치, 사용자는 드래그로 조정
        // facility 는 P3-2b 에서 사각형 그리기 모드로 분기 — 현재는 기존 클릭 흐름 유지
        if (type === 'facility') {
            // P3-2b (R3-D): facility 는 꼭짓점 → 영역 드래그로 사각형 그리기
            _startFacilityRectDraw();
        } else {
            // 점 객체(가스/노드/전력) — 지도 중앙에 즉시 마커 생성
            _placeAt(map.getCenter());
        }
    }

    /**
     * _placeAt
     * 지도 클릭 위치에 임시 마커 추가.
     */
    function _placeAt(latlng) {
        if (!placeCtx.active) return;

        const { type, code, name } = placeCtx;

        // 임시 객체 데이터 구성 (빌더 함수의 인자 형식)
        const tempData = _buildTempObjectData(type, code, name, latlng);

        // 빌더 호출 — mode='create' 로 점선 outline 추가
        let icon;
        if (type === 'facility') {
            icon = buildEquipmentIcon(tempData, 'create');
        } else if (type === 'gas') {
            icon = buildGasIcon(tempData, 'create');
        } else if (type === 'power') {
            icon = buildPowerIcon(tempData, 'create');
        } else if (type === 'node') {
            icon = buildNodeIcon(tempData, 'create');
        } else {
            console.warn(`[admin_map_editor] 지원하지 않는 type: ${type}`);
            _cancelPlaceMode();
            return;
        }

        // 마커 추가 — draggable 옵션
        const marker = L.marker(latlng, {
            icon,
            draggable: true,
        }).addTo(map);

        placeCtx.marker = marker;
        // 임시 좌표 저장 (단계 3-Z.3 의 payload 에 사용)
        placeCtx.latlng = latlng;

        // P1-4a: 임시 마커에도 호버 팝오버 — 드래그 중 좌표 실시간 갱신
        const popoverBuilder = getPopoverBuilderForType(type);
        if (popoverBuilder) {
            attachHoverPopover(marker, tempData, popoverBuilder);
        }

        // 단계 3-Z.2: 드래그 이벤트 청취
        marker.on('dragstart', function() {
            console.info(`[admin_map_editor] 드래그 시작: ${code}`);
            // 드래그 중 시각 효과 — 카드 강조 (반투명 + z-index)
            const el = this.getElement && this.getElement();
            if (el) {
                el.style.zIndex = '999';
                el.style.opacity = '0.7';
            }
        });

        // P1-4a: 드래그 *중* 좌표 갱신 — 팝오버가 열려 있으면 실시간 표시
        marker.on('drag', function() {
            const newLatLng = this.getLatLng();
            // P3-1: facility 는 center_x/center_y, 그 외는 x/y
            if (type === 'facility') {
                tempData.center_x = newLatLng.lng;
                tempData.center_y = newLatLng.lat;
            } else {
                tempData.x = newLatLng.lng;
                tempData.y = newLatLng.lat;
            }
            if (popoverBuilder && this.getTooltip()) {
                this.setTooltipContent(popoverBuilder(tempData));
                if (!this.isTooltipOpen()) this.openTooltip();
            }
        });

        marker.on('dragend', function() {
            const newLatLng = this.getLatLng();
            placeCtx.latlng = newLatLng;
            // P3-1: facility 는 center_x/center_y, 그 외는 x/y
            if (type === 'facility') {
                tempData.center_x = newLatLng.lng;
                tempData.center_y = newLatLng.lat;
            } else {
                tempData.x = newLatLng.lng;
                tempData.y = newLatLng.lat;
            }

            // 시각 효과 원복
            const el = this.getElement && this.getElement();
            if (el) {
                el.style.zIndex = '';
                el.style.opacity = '';
            }

            console.info(`[admin_map_editor] 드래그 종료: ${code} → 새 위치 (${newLatLng.lng.toFixed(2)}, ${newLatLng.lat.toFixed(2)})`);
        });

        // 지도 커서 원복
        const mapContainer = map.getContainer();
        if (mapContainer) {
            mapContainer.style.cursor = '';
        }

        // P3-6: [x] 삭제 버튼 이벤트 위임 등록 (1회만)
        _bindPlacingDeleteHandler();

        console.info(`[admin_map_editor] 임시 마커 배치: ${code} at (${latlng.lng.toFixed(2)}, ${latlng.lat.toFixed(2)}) — 드래그로 위치 미세 조정 가능`);
        console.info(`[admin_map_editor] [완료] 버튼은 단계 3-Z.3 에서 활성화 예정`);
    }

    // P3-2b (R3-D): facility 사각형 그리기 모드 활성화
    // 사용자가 지도에서 mousedown → 드래그 → mouseup 으로 영역 결정
    function _startFacilityRectDraw() {
        if (typeof L.Draw === 'undefined') {
            console.warn('[admin_map_editor] Leaflet.Draw 미로드 — facility 사각형 그리기 불가');
            return;
        }

        // 기존 drawer 정리 (안전)
        if (placeCtx.drawer) {
            try { placeCtx.drawer.disable(); } catch (e) { /* ignore */ }
            placeCtx.drawer = null;
        }

        // 사각형 drawer 생성
        placeCtx.drawer = new L.Draw.Rectangle(map, {
            shapeOptions: {
                color:       '#3b82f6',
                fillColor:   'rgba(59,130,246,0.15)',
                fillOpacity: 1,
                weight:      2,
                dashArray:   '4,3',
            },
        });
        placeCtx.drawer.enable();

        // CREATED 이벤트 1회 청취 → _handleFacilityRectCreated
        map.once(L.Draw.Event.CREATED, _handleFacilityRectCreated);

        console.info('[admin_map_editor] facility 사각형 그리기 시작 — 영역을 드래그하세요');
    }

    // P3-2b: 사각형 그리기 완료 — bounds 에서 center/width/height 계산
    function _handleFacilityRectCreated(e) {
        const layer = e.layer;
        if (!layer || !layer.getBounds) return;

        const bounds = layer.getBounds();
        const center = bounds.getCenter();
        const width  = Math.abs(bounds.getEast()  - bounds.getWest());
        const height = Math.abs(bounds.getNorth() - bounds.getSouth());

        // drawer 비활성화 (재사용 방지)
        if (placeCtx.drawer) {
            try { placeCtx.drawer.disable(); } catch (err) { /* ignore */ }
            placeCtx.drawer = null;
        }

        // P3-2c: L.Rectangle + 중심 마커 표시 (Q-가 buildEquipmentIcon, Q2-a 마커 마스터)
        layer.addTo(map);
        _placeFacilityRect(layer, center, width, height);

        console.info(`[admin_map_editor] facility 사각형 그리기 완료: center=(${center.lng.toFixed(2)},${center.lat.toFixed(2)}), w=${width.toFixed(2)}m, h=${height.toFixed(2)}m`);
    }

    // P3-2c (R3-D 완료 후 표시): facility 임시 마커 + L.Rectangle 동기 표시
    // Q-가: 기존 buildEquipmentIcon 카드 사용
    // Q2-a: 마커가 마스터 — 마커 드래그 시 사각형도 같은 중심으로 setBounds
    function _placeFacilityRect(layer, center, width, height) {
        if (!placeCtx.active) return;

        // 사각형 시각 정리 — 그리기 중엔 점선(dashArray), 완료 후엔 실선
        if (layer && layer.setStyle) {
            layer.setStyle({
                dashArray:   null,
                fillOpacity: 0.18,
            });
        }

        // tempData 구성 (P3-1 형식 — center_x/center_y/width/height)
        const tempData = _buildTempObjectData(placeCtx.type, placeCtx.code, placeCtx.name, center);
        tempData.width  = width;
        tempData.height = height;

        // 중심에 기존 buildEquipmentIcon 카드 (mode='create' 점선 outline + 펄스)
        const icon = buildEquipmentIcon(tempData, 'create');
        const marker = L.marker(center, {
            icon,
            draggable: true,
        }).addTo(map);

        placeCtx.marker    = marker;
        placeCtx.latlng    = center;
        placeCtx.rectShape = layer;

        // 호버 팝오버 부착 (P1-4a 인프라)
        attachHoverPopover(marker, tempData, buildEquipmentPopover);

        // 지도 커서 원복 (_startPlaceMode 에서 crosshair 였음)
        const mapContainer = map.getContainer();
        if (mapContainer) mapContainer.style.cursor = '';

        // lucide 아이콘 재렌더 (카드 안 SVG)
        if (typeof lucide !== 'undefined') lucide.createIcons();

        // Q2-a: 마커 dragstart/drag/dragend → 사각형 동기
        marker.on('dragstart', function() {
            const el = this.getElement && this.getElement();
            if (el) {
                el.style.zIndex = '999';
                el.style.opacity = '0.7';
            }
        });

        marker.on('drag', function() {
            const newLatLng = this.getLatLng();
            tempData.center_x = newLatLng.lng;
            tempData.center_y = newLatLng.lat;
            // 사각형 동기 — 새 중심 기준으로 bounds 재계산
            if (placeCtx.rectShape) {
                const halfW = tempData.width  / 2;
                const halfH = tempData.height / 2;
                placeCtx.rectShape.setBounds([
                    [newLatLng.lat - halfH, newLatLng.lng - halfW],
                    [newLatLng.lat + halfH, newLatLng.lng + halfW],
                ]);
            }
            if (this.getTooltip()) {
                this.setTooltipContent(buildEquipmentPopover(tempData));
            }
            // P3-3 (R2-G-7): 충돌 검사 + 시각 피드백 (사각형 + 카드 둘 다 빨강)
            const colliding = _checkFacilityCollision(tempData);
            placeCtx._colliding = colliding;
            if (placeCtx.rectShape && placeCtx.rectShape.setStyle) {
                placeCtx.rectShape.setStyle({
                    color:     colliding ? '#ef4444' : '#3b82f6',
                    fillColor: colliding ? 'rgba(239,68,68,0.18)' : 'rgba(59,130,246,0.18)',
                });
            }
            const el = this.getElement && this.getElement();
            const card = el ? el.querySelector('.obj-card-facility') : null;
            if (card) {
                card.style.outline = colliding ? '3px solid #ef4444' : '';
            }
        });

        marker.on('dragend', function() {
            const newLatLng = this.getLatLng();
            placeCtx.latlng    = newLatLng;
            tempData.center_x  = newLatLng.lng;
            tempData.center_y  = newLatLng.lat;
            const el = this.getElement && this.getElement();
            if (el) {
                el.style.zIndex = '';
                el.style.opacity = '';
            }
            console.info(`[admin_map_editor] facility dragend: center=(${newLatLng.lng.toFixed(2)},${newLatLng.lat.toFixed(2)})`);
        });

        // P3-6: [x] 삭제 버튼 이벤트 위임 등록 (1회만)
        _bindPlacingDeleteHandler();

        console.info(`[admin_map_editor] facility 배치: ${placeCtx.code}, w=${width.toFixed(2)}m, h=${height.toFixed(2)}m`);
    }

    /**
     * _buildTempObjectData
     * 미배치 객체의 임시 데이터 구성 (빌더 함수 인자 형식).
     */
    function _buildTempObjectData(type, code, name, latlng) {
        const x = latlng.lng;
        const y = latlng.lat;

        if (type === 'facility') {
            // P3-1: Equipment 모델 필드명 (center_x/center_y/width/height)에 맞춤
            // width/height 는 P3-2 에서 사각형 드래그로 결정 — 임시 기본값 1.0m
            return {
                id: 'temp-' + code,
                equipment_code: code,
                equipment_name: name,
                status: 'normal',
                center_x: x,
                center_y: y,
                width:    1.0,
                height:   1.0,
            };
        }
        if (type === 'gas' || type === 'power') {
            return {
                id: 'temp-' + code,
                device_id: null,
                device_code: code,  // 폴백 우선순위
                device_name: name,
                sensor_type: type,
                x, y,
            };
        }
        if (type === 'node') {
            return {
                id: 'temp-' + code,
                node_code: code,
                node_name: name,
                status: 'normal',
                x, y,
            };
        }
        return null;
    }

    /**
     * _cancelPlaceMode
     * 배치 모드 취소 — 임시 마커 제거 + 컨텍스트 초기화.
     */
    function _cancelPlaceMode() {
        if (!placeCtx.active) return;

        // [완료] 버튼을 [편집] 으로 원복 (단계 3-Z.3 추가)
        const editBtn = document.getElementById('edit-mode-btn');
        if (editBtn) {
            editBtn.innerHTML = '<i data-lucide="pencil" class="w-4 h-4"></i> 편집';
            editBtn.classList.replace('bg-blue-600', 'bg-slate-800');
            editBtn.classList.replace('hover:bg-blue-700', 'hover:bg-slate-700');
            editBtn.setAttribute('aria-pressed', 'false');
        }
        const modeBadge = document.getElementById('mode-badge');
        modeBadge?.classList.add('hidden');
        modeBadge?.classList.remove('flex');
        if (typeof lucide !== 'undefined') lucide.createIcons();

        // 임시 마커 제거
        if (placeCtx.marker) {
            try { map.removeLayer(placeCtx.marker); } catch (e) { /* ignore */ }
        }

        // P3-2b: facility 사각형 그리기 drawer + 임시 사각형 정리
        if (placeCtx.drawer) {
            try { placeCtx.drawer.disable(); } catch (e) { /* ignore */ }
            placeCtx.drawer = null;
        }
        if (placeCtx.rectShape) {
            try { map.removeLayer(placeCtx.rectShape); } catch (e) { /* ignore */ }
            placeCtx.rectShape = null;
        }

        // map.once 청취 취소
        if (placeCtx.mapClickHandler) {
            try { map.off('click', placeCtx.mapClickHandler); } catch (e) { /* ignore */ }
        }

        // 좌측 패널 항목 강조 해제
        if (placeCtx.panelItem) {
            placeCtx.panelItem.style.outline = '';
            placeCtx.panelItem.style.outlineOffset = '';
            placeCtx.panelItem.style.background = '';
        }

        // 지도 커서 원복
        const mapContainer = map.getContainer();
        if (mapContainer) {
            mapContainer.style.cursor = '';
        }

        // 컨텍스트 초기화
        placeCtx.active = false;
        placeCtx.type = null;
        placeCtx.code = null;
        placeCtx.name = null;
        placeCtx.pk = null;            // P3-7
        placeCtx.panelItem = null;
        placeCtx.marker = null;
        placeCtx.mapClickHandler = null;

        editorState.mode = 'view';
        editorState.activeObject = null;

        // P3-5 (R3-G): 불투명화 복원
        _setPlacingFade(false);

        console.info('[admin_map_editor] 배치 모드 취소');
    }

    // P3-5 (R3-G): 배치 모드 진입 시 다른 객체 불투명화 / 종료 시 복원
    function _setPlacingFade(active) {
        // DivIcon 마커 (Equipment / Sensor / LocationNode)
        ['equipment', 'sensor', 'locationNode'].forEach(type => {
            Object.values(markerRefs[type]).forEach(marker => {
                const el = marker && marker.getElement && marker.getElement();
                if (el) {
                    el.classList.toggle('placing-mode-faded', active);
                }
            });
        });
        // Geofence shape · label
        if (typeof geofenceState !== 'undefined') {
            Object.values(geofenceState).forEach(state => {
                if (state.shape && state.shape.setStyle) {
                    if (active) {
                        state.shape.setStyle({ opacity: 0.4, fillOpacity: 0.05 });
                    } else {
                        state.shape.setStyle({ opacity: 1 });
                    }
                }
                if (state.labelMarker) {
                    const el = state.labelMarker.getElement && state.labelMarker.getElement();
                    if (el) el.classList.toggle('placing-mode-faded', active);
                }
            });
        }
    }

    // P5-C-2 (R2-G-1): 편집 팝오버 안 [크기 편집]/[삭제] 버튼 — map container 단위 이벤트 위임 (1회 등록)
    function _bindEditPopoverActions() {
        if (map._editPopoverActionsBound) return;
        map._editPopoverActionsBound = true;
        const container = map.getContainer();
        container.addEventListener('click', function(e) {
            if (!editCtx.active) return;
            // δ: 외부 action [크기 편집] (data-edit-resize) — facility / zone 공통
            const resizeBtn = e.target.closest('[data-edit-resize]');
            if (resizeBtn) {
                e.preventDefault();
                e.stopPropagation();
                if (editCtx.type === 'zone') {
                    _startZoneHandlesEdit();
                } else {
                    _startFacilityResize();
                }
                return;
            }
            // P5-C-2 + P5-E (R2-G-5): [삭제] 버튼 → 재확인 + 처리
            const deleteBtn = e.target.closest('[data-edit-delete]');
            if (deleteBtn) {
                e.preventDefault();
                e.stopPropagation();
                _confirmDeleteObject();
                return;
            }
            // P5-D-B: 위험구역 [편집] 버튼
            const zoneHandlesBtn = e.target.closest('[data-zone-edit-handles]');
            if (zoneHandlesBtn) {
                e.preventDefault();
                e.stopPropagation();
                _startZoneHandlesEdit();
                return;
            }
            // P5-D-C: 위험구역 [위험도] 버튼
            const sevBtn = e.target.closest('[data-zone-edit-severity]');
            if (sevBtn) {
                e.preventDefault();
                e.stopPropagation();
                _onZoneSeverityChange(sevBtn.dataset.zoneEditSeverity);
                return;
            }
            // δ: 위험구역 popover 내부 [완료] (data-zone-edit-done) — 위험도 결정 완료 전용
            // severityDirty 만 리셋. 편집 모드는 유지. 우하단 [저장]에는 영향 없음.
            const zoneDoneBtn = e.target.closest('[data-zone-edit-done]');
            if (zoneDoneBtn) {
                e.preventDefault();
                e.stopPropagation();
                if (zoneDoneBtn.disabled) return;
                _finishZoneSeverityEdit();
                return;
            }
            // δ: 외부 action 의 [완료] (data-edit-done) — facility / zone 공통
            // resizing 중이면 _finishFacilityResize / _finishZoneResize 같이 핸들 비활성 + 텍스트 복원.
            // 일반 상태에선 [크기 편집] 표시이므로 이 분기 진입 X.
            const editDoneBtn = e.target.closest('[data-edit-done]');
            if (editDoneBtn) {
                e.preventDefault();
                e.stopPropagation();
                if (editDoneBtn.disabled) return;
                if (editCtx.type === 'facility' && editCtx.resizing) {
                    _finishFacilityResize();
                } else if (editCtx.type === 'zone' && editCtx.resizing) {
                    // zone 의 [완료] 도 동일 패턴 — 핸들 비활성 + 외부 action 텍스트 복원
                    if (editCtx.marker && editCtx.marker.editing && editCtx.marker.editing.disable) {
                        try { editCtx.marker.editing.disable(); } catch (e2) { /* ignore */ }
                    }
                    if (editCtx.marker && editCtx.marker.off) editCtx.marker.off('edit');
                    editCtx.resizing     = false;
                    editCtx.zoneHandling = false;
                    _safeSetTooltipContent(editCtx.popover, buildGeofenceEditPopover(editCtx.data));
                } else {
                    _exitEditMode();
                }
                return;
            }
        }, true);
    }

    // P3-6 (R3-F): [x] 삭제 버튼 — map container 단위 이벤트 위임 (1회 등록)
    function _bindPlacingDeleteHandler() {
        if (map._placingDeleteBound) return;
        map._placingDeleteBound = true;
        const container = map.getContainer();
        container.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-placing-delete]');
            if (!btn) return;
            if (!placeCtx.active) return;
            e.preventDefault();
            e.stopPropagation();
            _cancelPlaceMode();
        }, true);
    }

    // P4-1 (R2-A + R3-C): 편집 모드 진입 — 마커 클릭 또는 좌측 패널 배치완료 클릭
    function _startEditMode(type, pk, marker, data) {
        if (placeCtx.active) {
            console.info('[admin_map_editor] 배치 모드 중 — 편집 모드 진입 차단');
            return;
        }
        if (editCtx.active) {
            // 다른 객체 편집 중이면 먼저 종료
            _exitEditMode();
        }

        editCtx.active = true;
        editCtx.type   = type;
        editCtx.pk     = pk;
        editCtx.marker = marker;
        editCtx.data   = data;

        editorState.mode = 'edit';
        editorState.activeObject = { type, pk };

        // Q2-다: [편집] 버튼 → [완료] 로 변경
        const editBtn = document.getElementById('edit-mode-btn');
        if (editBtn) {
            editBtn.setAttribute('aria-pressed', 'true');
            editBtn.innerHTML = '<i data-lucide="check" class="w-4 h-4"></i> 완료';
            editBtn.classList.replace('bg-slate-800', 'bg-blue-600');
            editBtn.classList.replace('hover:bg-slate-700', 'hover:bg-blue-700');
        }
        const modeBadge = document.getElementById('mode-badge');
        modeBadge?.classList.remove('hidden');
        modeBadge?.classList.add('flex');
        if (typeof lucide !== 'undefined') lucide.createIcons();

        // P4-2: 시각 효과
        _setPlacingFade(true);          // R2-B: 다른 객체 불투명화
        closePanelForEdit();             // R2-E: 객체 선택 패널 자동 숨김
        _addEditingBadge(marker);        // R2-G-8: "편집 중" 뱃지
        _showEditGuide(type);            // P5-A (R2-N/S): 편집 방법 안내 표시

        // P6-AB: 진입 시 dirty 초기화 + 우하단 [완료] 비활성
        editCtx.dirty = false;
        const editBtnInit = document.getElementById('edit-mode-btn');
        if (editBtnInit) {
            editBtnInit.disabled = true;
            editBtnInit.style.opacity = '0.5';
            editBtnInit.style.cursor  = 'not-allowed';
        }

        // P6-CDE: 편집 모드 진입 시 우하단 [전체 되돌리기]/[저장] 표시 + [편집] 숨김
        _showEditActionsBar();

        // P5-B (R2-K): gas/power/node 편집 모드 진입 시 마커 드래그 활성
        if ((type === 'gas' || type === 'power' || type === 'node') && marker) {
            if (marker.getLatLng) editCtx.origLatLng = marker.getLatLng();
            if (marker.dragging && marker.dragging.enable) marker.dragging.enable();
            // dragend 핸들러 — _exitEditMode 에서 marker.off('dragend') 로 해제
            marker.on('dragend', function() {
                _onSensorNodeDragEnd(this, type, data);
            });
        }

        // P5-C-1 (R2-G-6 + R2-J 준비): facility 편집 모드 — 임시 사각형 생성 + 마커 드래그 활성
        if (type === 'facility' && marker) {
            const eq = data;
            const cx = eq.center_x, cy = eq.center_y;
            const w  = eq.width  || 1.0;
            const h  = eq.height || 1.0;
            if (cx != null && cy != null) {
                editCtx.rectShape = L.rectangle([
                    [cy - h/2, cx - w/2],
                    [cy + h/2, cx + w/2],
                ], {
                    color:       '#3b82f6',
                    fillColor:   'rgba(59,130,246,0.18)',
                    fillOpacity: 1,
                    weight:      2,
                }).addTo(map);
            }
            if (marker.getLatLng) editCtx.origLatLng = marker.getLatLng();
            if (marker.dragging && marker.dragging.enable) marker.dragging.enable();
            marker.on('dragend', function() {
                _onFacilityDragEnd(this, eq);
            });
            // P5-C-2: 편집 팝오버 액션 버튼 이벤트 위임 등록 (1회만)
            _bindEditPopoverActions();
        }

        // P4-3/P4-4: type 별 편집 팝오버 표시
        if (type === 'zone') {
            // P4-4 (Q4-가): zone 은 별도 L.Tooltip(permanent) — P2-5a 패턴
            if (editCtx.popover) {
                try { map.removeLayer(editCtx.popover); } catch (e) { /* ignore */ }
                editCtx.popover = null;
            }
            if (marker && marker.closeTooltip) marker.closeTooltip();  // 호버 팝오버 잠시 닫기
            const latlng = (marker && marker.getLatLng)
                ? marker.getLatLng()
                : L.latLng(data.center_y, data.center_x);
            editCtx.popover = L.tooltip({
                className:   'zone-create-popover zone-edit-popover',  // CSS 재사용 (어두운 카드)
                permanent:   true,
                direction:   'right',
                interactive: false,   // _bindEditPopoverActions 가 캡쳐 phase 로 처리. leaflet 자체 hit test 불필요
                opacity:     1,
                offset:      [20, 0],
            })
            .setLatLng(latlng)
            .setContent(buildGeofenceEditPopover(data))
            .addTo(map);

            // P5-D-A (R2-G-6): 위험구역 도형 자체 draggable — 자동 위험구역은 제외
            const isAuto = data.name && data.name.startsWith('[자동]');
            if (!isAuto && marker) {
                _enableShapeDrag(marker, data);
            }
        } else {
            // δ: facility/gas/power/node — 통합 popover (좌상단 action + 좌하단 card 두 영역)
            // 우측 컨테이너 자체는 투명. drag 시 setLatLng 동기 + 좌표 실시간 갱신.
            const editBuilder = getEditPopoverBuilder(type);
            if (editBuilder && marker) {
                if (marker.unbindTooltip) marker.unbindTooltip();
                if (editCtx.popover) {
                    try { map.removeLayer(editCtx.popover); } catch (e) { /* ignore */ }
                    editCtx.popover = null;
                }
                const latlng = marker.getLatLng();
                // δ: 통합 popover — admin-edit-container 클래스 (투명 배경, 그림자 없음)
                //    내부의 .ext-card-area 만 어두운 카드 디자인. .ext-action-area 는 버튼만.
                editCtx.popover = L.tooltip({
                    className:   'admin-edit-container',
                    permanent:   true,
                    direction:   'right',
                    interactive: false,
                    opacity:     1,
                    offset:      [20, 0],
                })
                .setLatLng(latlng)
                .setContent(editBuilder(data))
                .addTo(map);
                // drag 중 popover 위치 + 좌표·크기 텍스트 실시간 갱신
                marker.on('drag', function() {
                    const ll = this.getLatLng();
                    _safeSetTooltipLatLng(editCtx.popover, ll);
                    // data 좌표 임시 업데이트 + popover 재렌더링
                    if (type === 'facility') {
                        editCtx.data.center_x = ll.lng;
                        editCtx.data.center_y = ll.lat;
                    } else {
                        editCtx.data.x = ll.lng;
                        editCtx.data.y = ll.lat;
                    }
                    const eb = getEditPopoverBuilder(type);
                    if (eb) _safeSetTooltipContent(editCtx.popover, eb(editCtx.data));
                    // facility 사각형도 함께 따라옴
                    if (type === 'facility' && editCtx.rectShape) {
                        const halfW = (editCtx.data.width  || 1.0) / 2;
                        const halfH = (editCtx.data.height || 1.0) / 2;
                        editCtx.rectShape.setBounds([
                            [ll.lat - halfH, ll.lng - halfW],
                            [ll.lat + halfH, ll.lng + halfW],
                        ]);
                    }
                });
            }
        }

        console.info(`[admin_map_editor] 편집 모드 진입: type=${type}, pk=${pk}`);
        // P4-4: 위험구역 클릭 팝오버 추가
    }

    function _exitEditMode() {
        if (!editCtx.active) return;

        // P4-3/P4-4: 컨텍스트 백업 (복원에 사용 — 초기화 후엔 참조 불가)
        const prevMarker       = editCtx.marker;
        const prevType         = editCtx.type;
        const prevPk           = editCtx.pk;           // P6-AB
        const prevData         = editCtx.data;
        const prevPopover      = editCtx.popover;      // P4-4
        // δ: infoPopover 폐기 — popover 통합으로 별도 정보 popover 없음
        const prevRectShape    = editCtx.rectShape;    // P5-C-1
        const prevResizing     = editCtx.resizing;     // P5-C-3
        const prevZoneHandling = editCtx.zoneHandling; // P5-D-B
        const prevDirty        = editCtx.dirty;        // P6-AB

        editCtx.active     = false;
        editCtx.type       = null;
        editCtx.pk         = null;
        editCtx.marker     = null;
        editCtx.data       = null;
        editCtx.popover      = null;            // P4-4
        editCtx.severityDirty = false;          // δ: 위험구역 위험도 변경 dirty 초기화
        editCtx.dirty        = false;           // P5-B
        editCtx.origLatLng   = null;            // P5-B
        editCtx.rectShape    = null;            // P5-C-1
        editCtx.resizing     = false;           // P5-C-3
        editCtx.zoneHandling = false;           // P5-D-B

        editorState.mode = 'view';
        editorState.activeObject = null;

        // [편집] 버튼 복원
        const editBtn = document.getElementById('edit-mode-btn');
        if (editBtn) {
            editBtn.setAttribute('aria-pressed', 'false');
            editBtn.innerHTML = '<i data-lucide="pencil" class="w-4 h-4"></i> 편집';
            editBtn.classList.replace('bg-blue-600', 'bg-slate-800');
            editBtn.classList.replace('hover:bg-blue-700', 'hover:bg-slate-700');
        }
        const modeBadge = document.getElementById('mode-badge');
        modeBadge?.classList.add('hidden');
        modeBadge?.classList.remove('flex');
        if (typeof lucide !== 'undefined') lucide.createIcons();

        // P4-3/P4-4: 호버 팝오버 복원
        if (prevType === 'zone') {
            // P4-4: 별도 L.Tooltip 제거 — shape 의 호버 팝오버는 그대로 살아 있음
            if (prevPopover) {
                try { map.removeLayer(prevPopover); } catch (e) { /* ignore */ }
            }
            // P5-D-A: 위험구역 도형 드래그 해제
            if (prevMarker) _disableShapeDrag(prevMarker);
            // P5-D-B: zoneHandling 정리 — 핸들 비활성 + edit 이벤트 해제
            if (prevZoneHandling && prevMarker) {
                if (prevMarker.editing && prevMarker.editing.disable) {
                    try { prevMarker.editing.disable(); } catch (e) { /* ignore */ }
                }
                if (prevMarker.off) prevMarker.off('edit');
            }
        } else if (prevMarker && prevType && prevData) {
            // δ: 통합 popover 제거 + drag 동기 핸들러 해제 + 호버 popover 재바인드
            // view icon 은 진입 시 교체 안 했으므로 복원 불필요
            if (prevPopover) {
                try { map.removeLayer(prevPopover); } catch (e) { /* ignore */ }
            }
            if (prevMarker.off) prevMarker.off('drag');
            const restoreBuilder =
                prevType === 'facility' ? buildEquipmentPopover :
                prevType === 'gas'      ? buildGasPopover :
                prevType === 'power'    ? buildPowerPopover :
                prevType === 'node'     ? buildNodePopover :
                null;
            if (restoreBuilder && prevMarker.bindTooltip) {
                try {
                    attachHoverPopover(prevMarker, prevData, restoreBuilder);
                } catch (e) { /* ignore */ }
            }
        }

        // P5-B: gas/power/node 마커 드래그 해제 + dragend 핸들러 제거
        if (prevMarker && (prevType === 'gas' || prevType === 'power' || prevType === 'node')) {
            if (prevMarker.dragging && prevMarker.dragging.disable) prevMarker.dragging.disable();
            if (prevMarker.off) prevMarker.off('dragend');
        }

        // P5-C-1: facility 편집 종료 — 드래그 해제 + 임시 사각형 제거
        if (prevMarker && prevType === 'facility') {
            if (prevMarker.dragging && prevMarker.dragging.disable) prevMarker.dragging.disable();
            if (prevMarker.off) prevMarker.off('dragend');
        }
        // γ-3 (P5-C-3): facility 크기 편집(resize) 중이었으면 핸들 비활성 + 'edit' 핸들러 off
        // 우하단 [편집] 버튼 활성 복원은 더 이상 불필요 (γ-3 에서 _startFacilityResize 가 우하단 버튼을 건드리지 않음)
        if (prevType === 'facility' && prevResizing) {
            if (prevRectShape && prevRectShape.editing && prevRectShape.editing.disable) {
                try { prevRectShape.editing.disable(); } catch (e) { /* ignore */ }
            }
            if (prevRectShape && prevRectShape.off) {
                prevRectShape.off('edit');
            }
        }
        if (prevRectShape) {
            try { map.removeLayer(prevRectShape); } catch (e) { /* ignore */ }
        }

        // P6-AB: dirty 시 pendingChanges 에 누적 (PATCH 는 P6-CDE [저장])
        if (prevDirty && prevType && prevPk && prevData) {
            const cat = prevType === 'facility'                       ? 'equipment'
                      : (prevType === 'gas' || prevType === 'power')   ? 'sensor'
                      : prevType === 'node'                            ? 'locationNode'
                      : prevType === 'zone'                            ? 'geofence'
                      : null;
            if (cat && pendingChanges[cat]) {
                pendingChanges[cat].update[prevPk] = prevData;
                editorState.isDirty = true;
                console.info(`[admin_map_editor] pendingChanges 누적: ${cat}#${prevPk} (P6-CDE [저장] 시 PATCH)`);
            }
        }

        // P4-2: 시각 효과 복원
        _setPlacingFade(false);
        _removeEditingBadge();
        _hideEditGuide();                // P5-A

        // P6-CDE (Q-i 다): isDirty 검사 → 누적 있으면 [전체 되돌리기]/[저장] 유지, 없으면 [편집] 복귀
        if (editorState.isDirty) {
            _showEditActionsBar();
        } else {
            _hideEditActionsBar();
        }

        console.info('[admin_map_editor] 편집 모드 종료');
    }

    // P4-2 (R2-E): 편집 모드 진입 시 객체 선택 패널 자동 숨김
    function closePanelForEdit() {
        const panel = document.getElementById('object-panel');
        if (panel && !panel.classList.contains('panel-hidden')) {
            // 직접 classList 토글 — IIFE click handler 의존 제거 (timing 안전)
            panel.classList.add('panel-hidden');
            const handle = document.getElementById('panel-toggle-handle');
            if (handle) handle.setAttribute('aria-expanded', 'false');
        }
    }

    // P4-2 (R2-G-8): 활성 마커에 "편집 중" 뱃지 추가
    function _addEditingBadge(marker) {
        if (!marker) return;
        const el = marker.getElement && marker.getElement();
        if (!el) return;
        // 기존 뱃지 제거 (안전)
        _removeEditingBadge();
        // 마커 카드의 position:relative 래퍼 안에 추가
        const wrap = el.querySelector('[style*="position:relative"]') || el;
        const badge = document.createElement('span');
        badge.className = 'editing-badge';
        badge.textContent = '편집 중';
        badge.setAttribute('data-editing-badge', '1');
        wrap.appendChild(badge);
    }

    function _removeEditingBadge() {
        document.querySelectorAll('[data-editing-badge="1"]').forEach(el => el.remove());
    }

    // P5-A (R2-S): 객체별 편집 안내 문구 — 사용자 요구사항 원문
    const EDIT_GUIDE_TEXTS = {
        facility: [
            ['위치 이동', '아이콘을 드래그하여 위치를 조정하세요.'],
            ['크기 조정', '모서리 핸들을 드래그해 설비 영역 크기를 조정하세요.'],
        ],
        zone: [
            ['위치 이동',         '아이콘을 드래그해 구역 위치를 이동하세요.'],
            ['원형 반경 조정',     '반경 핸들을 드래그해 구역 범위를 조정하세요.'],
            ['형태 편집 (폴리곤)', '꼭짓점을 드래그해 구역 형태를 수정하세요.'],
            ['점 추가 (폴리곤)',   '선분을 클릭해 꼭짓점을 추가하세요.'],
        ],
        gas:   [['위치 이동', '아이콘을 드래그하여 위치를 조정하세요.']],
        power: [['위치 이동', '아이콘을 드래그하여 위치를 조정하세요.']],
        node:  [['위치 이동', '아이콘을 드래그하여 위치를 조정하세요.']],
    };

    // P5-A (R2-N): 편집 방법 안내 박스 표시
    function _showEditGuide(type) {
        const wrap = document.getElementById('edit-guide-wrap');
        const list = document.getElementById('edit-guide-list');
        if (!wrap || !list) return;
        const items = EDIT_GUIDE_TEXTS[type] || [];
        list.innerHTML = items.map(([label, text]) => `<li><strong>${label}:</strong> ${text}</li>`).join('');
        wrap.style.display = '';
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    function _hideEditGuide() {
        const wrap = document.getElementById('edit-guide-wrap');
        if (wrap) wrap.style.display = 'none';
    }

    // P5-B (R2-K): gas/power/node 드래그 종료 — 로컬 갱신 + 편집 팝오버 동기화
    // PATCH 는 Phase 6 [완료] 흐름에서 일괄 처리 (Q1-나)
    function _onSensorNodeDragEnd(marker, type, data) {
        const ll = marker.getLatLng();
        data.x = ll.lng;
        data.y = ll.lat;
        _markDirty();

        // γ-2: drag 핸들러가 위치·정보 popover 좌표 텍스트를 이미 동기.
        // dragEnd 에서는 액션 popover 만 재렌더링 (현재 dirty 상태 반영용 — 향후 확장 여지).
        const editBuilder = getEditPopoverBuilder(type);
        if (editBuilder) {
            _safeSetTooltipContent(editCtx.popover, editBuilder(data));
        }

        console.info(`[admin_map_editor] ${type} dragend — data=(${ll.lng.toFixed(2)}, ${ll.lat.toFixed(2)}), dirty=${editCtx.dirty}, isDirty(글로벌)=${editorState.isDirty}`);
    }

    // P5-C-1 (R2-G-6): facility 드래그 종료 — 로컬 갱신 + 사각형 동기 + 팝오버 갱신
    function _onFacilityDragEnd(marker, eq) {
        const ll = marker.getLatLng();
        eq.center_x = ll.lng;
        eq.center_y = ll.lat;
        _markDirty();

        // 사각형 동기 (안전망 — drag.popoverSync 가 이미 setBounds 했지만 dragEnd 에서도 한 번 더)
        if (editCtx.rectShape) {
            const halfW = (eq.width  || 1.0) / 2;
            const halfH = (eq.height || 1.0) / 2;
            editCtx.rectShape.setBounds([
                [ll.lat - halfH, ll.lng - halfW],
                [ll.lat + halfH, ll.lng + halfW],
            ]);
        }

        // γ-2: 액션 popover 재렌더링 (dirty 반영). 정보 popover 는 drag 핸들러가 처리.
        _safeSetTooltipContent(editCtx.popover, buildEquipmentEditPopover(eq));

        console.info(`[admin_map_editor] facility dragend — eq=(cx=${eq.center_x.toFixed(2)},cy=${eq.center_y.toFixed(2)},w=${(eq.width||0).toFixed(2)},h=${(eq.height||0).toFixed(2)}), dirty=${editCtx.dirty}, isDirty(글로벌)=${editorState.isDirty}`);
    }

    // γ-3 (P5-C-3 / R2-J): [크기 편집] 클릭 → 4꼭짓점 핸들 활성 + 액션 popover [크기 편집]→[완료(회색)] 토글
    function _startFacilityResize() {
        if (!editCtx.active || editCtx.type !== 'facility') {
            console.warn('[admin_map_editor] [크기 편집] — facility 편집 모드 아님');
            return;
        }
        if (editCtx.resizing) return;
        if (!editCtx.rectShape || !editCtx.rectShape.editing) {
            console.warn('[admin_map_editor] [크기 편집] — rectShape.editing 미정의 (leaflet-draw 미로드?)');
            return;
        }

        editCtx.resizing = true;

        // 4꼭짓점 핸들 활성
        try { editCtx.rectShape.editing.enable(); } catch (e) {
            console.warn('[admin_map_editor] editing.enable 실패:', e);
            editCtx.resizing = false;
            return;
        }

        // γ-3: 액션 popover 재렌더링 — [크기 편집] 자리에 [완료(회색 비활성)] 표시
        // 핸들 dragend 시 _markDirty → buildEquipmentEditPopover 가 [완료] 파란 활성으로 자동 토글
        _safeSetTooltipContent(editCtx.popover, buildEquipmentEditPopover(editCtx.data));

        // edit 이벤트 → 데이터 갱신 + 마커/사각형/popover 동기 + dirty
        editCtx.rectShape.on('edit', function() {
            const bounds = this.getBounds();
            const center = bounds.getCenter();
            const newW   = Math.abs(bounds.getEast()  - bounds.getWest());
            const newH   = Math.abs(bounds.getNorth() - bounds.getSouth());
            const eq = editCtx.data;
            eq.center_x = center.lng;
            eq.center_y = center.lat;
            eq.width    = newW;
            eq.height   = newH;
            _markDirty();
            // 마커 위치 동기
            if (editCtx.marker && editCtx.marker.setLatLng) editCtx.marker.setLatLng(center);
            // 통합 popover 위치·내용 동기 (dirty 반영 → [완료] 파란 활성 + 좌표·크기 갱신)
            _safeSetTooltipLatLng(editCtx.popover, center);
            _safeSetTooltipContent(editCtx.popover, buildEquipmentEditPopover(eq));
            console.info(`[admin_map_editor] resize edit — eq=(cx=${eq.center_x.toFixed(2)},cy=${eq.center_y.toFixed(2)},w=${eq.width.toFixed(2)},h=${eq.height.toFixed(2)}), dirty=${editCtx.dirty}`);
        });

        console.info('[admin_map_editor] facility 크기 편집 모드 진입 — 4꼭짓점 핸들 활성, [크기 편집]→[완료] 토글');
    }

    // γ-3: [완료] 클릭 시 — 핸들 비활성 + 액션 popover [완료]→[크기 편집] 텍스트 복원. dirty 는 유지.
    // 편집 모드 자체는 종료하지 않음 (위치 이동/추가 [크기 편집] 가능). 종료는 다른 객체 클릭/우하단 [저장] 등.
    function _finishFacilityResize() {
        if (!editCtx.active || editCtx.type !== 'facility' || !editCtx.resizing) return;

        // 핸들 비활성
        if (editCtx.rectShape && editCtx.rectShape.editing && editCtx.rectShape.editing.disable) {
            try { editCtx.rectShape.editing.disable(); } catch (e) { /* ignore */ }
        }
        if (editCtx.rectShape && editCtx.rectShape.off) {
            editCtx.rectShape.off('edit');
        }
        editCtx.resizing = false;

        // 액션 popover 재렌더링 — [완료] 자리에 [크기 편집] 복원
        _safeSetTooltipContent(editCtx.popover, buildEquipmentEditPopover(editCtx.data));

        console.info(`[admin_map_editor] facility resize 종료 — eq=(w=${(editCtx.data.width||0).toFixed(2)},h=${(editCtx.data.height||0).toFixed(2)}), dirty=${editCtx.dirty}, isDirty(글로벌)=${editorState.isDirty}`);
    }

    // P5-D-A (R2-G-6): 위험구역 도형 자체 mousedown/map.mousemove/map.mouseup — 자체 draggable
    // 도형은 m 단위(CRS.Simple) — Leaflet 이 줌 변화 자동 추종, px·m 변환 불필요
    function _enableShapeDrag(shape, geofenceData) {
        let dragging = false;
        let dragPrev = null;

        shape.on('mousedown.p5dDrag', function(e) {
            if (!editCtx.active || editCtx.type !== 'zone') return;
            dragging = true;
            dragPrev = e.latlng;
            map.dragging.disable();    // 지도 팬 잠시 비활성
            if (e.originalEvent) L.DomEvent.preventDefault(e.originalEvent);
        });

        map.on('mousemove.p5dDrag', function(e) {
            if (!dragging) return;
            const dx = e.latlng.lng - dragPrev.lng;
            const dy = e.latlng.lat - dragPrev.lat;
            if (shape.getLatLng) {              // L.Circle
                const c = shape.getLatLng();
                shape.setLatLng(L.latLng(c.lat + dy, c.lng + dx));
                geofenceData.center_x = shape.getLatLng().lng;
                geofenceData.center_y = shape.getLatLng().lat;
            } else if (shape.getLatLngs) {      // L.Polygon
                const latlngs = shape.getLatLngs()[0];
                const moved = latlngs.map(ll => L.latLng(ll.lat + dy, ll.lng + dx));
                shape.setLatLngs([moved]);
                geofenceData.polygon_data = moved.map(ll => [ll.lng, ll.lat]);
                const c = shape.getBounds().getCenter();
                geofenceData.center_x = c.lng;
                geofenceData.center_y = c.lat;
            }
            dragPrev = e.latlng;
        });

        map.on('mouseup.p5dDrag', function() {
            if (!dragging) return;
            dragging = false;
            map.dragging.enable();
            _markDirty();
            // 편집 팝오버 좌표·크기 갱신
            if (editCtx.popover && editCtx.popover.setContent) {
                editCtx.popover.setContent(buildGeofenceEditPopover(geofenceData));
            }
        });
    }

    function _disableShapeDrag(shape) {
        if (shape && shape.off) shape.off('mousedown.p5dDrag');
        if (map && map.off) {
            map.off('mousemove.p5dDrag');
            map.off('mouseup.p5dDrag');
        }
        // 안전: 지도 팬 상태 복원 (드래그 중 _exitEditMode 호출 케이스)
        if (map && map.dragging && map.dragging.enable) map.dragging.enable();
    }

    // P5-D-B (R2-L + R2-M): 위험구역 [편집] 클릭 → 핸들 활성 (반경/꼭짓점) + 드래그 비활성
    function _startZoneHandlesEdit() {
        if (!editCtx.active || editCtx.type !== 'zone') {
            console.warn('[admin_map_editor] [편집] — zone 편집 모드 아님');
            return;
        }
        if (editCtx.zoneHandling) return;
        const shape = editCtx.marker;
        if (!shape || !shape.editing) {
            console.warn('[admin_map_editor] [편집] — shape.editing 미정의');
            return;
        }

        editCtx.zoneHandling = true;
        editCtx.resizing     = true;   // δ: 외부 action 의 [크기 편집]→[완료] 토글 조건

        // P5-D-A 드래그 비활성 (충돌 방지)
        _disableShapeDrag(shape);

        // 핸들 활성
        try { shape.editing.enable(); } catch (e) {
            console.warn('[admin_map_editor] zone editing.enable 실패:', e);
            editCtx.zoneHandling = false;
            editCtx.resizing     = false;
            return;
        }

        // δ: popover 재렌더링 — 외부 action [크기 편집] 자리에 [완료(회색)] 표시
        _safeSetTooltipContent(editCtx.popover, buildGeofenceEditPopover(editCtx.data));

        // edit 이벤트 → 데이터 갱신 + 팝오버 갱신
        shape.on('edit', function() {
            const g = editCtx.data;
            if (this.getLatLng && this.getRadius) {        // L.Circle
                const c = this.getLatLng();
                g.center_x = c.lng;
                g.center_y = c.lat;
                g.radius   = this.getRadius();
            } else if (this.getLatLngs) {                  // L.Polygon
                const latlngs = this.getLatLngs()[0];
                g.polygon_data = latlngs.map(ll => [ll.lng, ll.lat]);
                const c = this.getBounds().getCenter();
                g.center_x = c.lng;
                g.center_y = c.lat;
            }
            _markDirty();
            if (editCtx.popover) {
                _safeSetTooltipContent(editCtx.popover, buildGeofenceEditPopover(g));
            }
        });

        console.info('[admin_map_editor] zone 핸들 편집 모드 진입');
    }

    // δ: 위험구역 [위험도] 클릭 → severity 변경 + 도형 색상 + popover 갱신 + severityDirty=true
    // 일반 dirty(_markDirty)도 함께 — 우하단 [저장]은 모든 변경에 활성.
    // popover 내부 [완료]는 severityDirty 만 활성 조건으로 사용.
    function _onZoneSeverityChange(targetSev) {
        if (!editCtx.active || editCtx.type !== 'zone') return;
        if (!targetSev) return;
        const g = editCtx.data;
        if (!g) return;
        if (g.severity === targetSev) return;

        g.severity = targetSev;
        editCtx.severityDirty = true;   // δ: 위험구역 popover 내부 [완료] 활성 조건
        _markDirty();                    // 우하단 [저장] 활성 + pendingChanges 누적

        // 도형 색상 즉시 변경
        const colors = {
            danger:  { stroke: '#ef4444', fill: 'rgba(239,68,68,0.15)' },
            warning: { stroke: '#f59e0b', fill: 'rgba(245,158,11,0.12)' },
            safe:    { stroke: '#22c55e', fill: 'rgba(34,197,94,0.10)' },
        }[targetSev];
        if (colors && editCtx.marker && editCtx.marker.setStyle) {
            editCtx.marker.setStyle({ color: colors.stroke, fillColor: colors.fill });
        }

        // popover 갱신 (활성 버튼 + 내부 [완료] 활성)
        _safeSetTooltipContent(editCtx.popover, buildGeofenceEditPopover(g));

        console.info(`[admin_map_editor] zone severity 변경 → ${targetSev}, severityDirty=true`);
    }

    // δ: 위험구역 popover 내부 [완료] 클릭 → 위험도 결정 완료. severityDirty=false 로 리셋.
    // 편집 모드 자체는 종료하지 않음. dirty 는 유지 (우하단 [저장] 가능).
    function _finishZoneSeverityEdit() {
        if (!editCtx.active || editCtx.type !== 'zone') return;
        if (!editCtx.severityDirty) return;
        editCtx.severityDirty = false;
        // popover 재렌더링 — 내부 [완료] 회색 비활성 복원
        _safeSetTooltipContent(editCtx.popover, buildGeofenceEditPopover(editCtx.data));
        console.info('[admin_map_editor] zone severity 결정 완료 — severityDirty=false');
    }

    // P6-AB: dirty 설정 + 우하단 [완료] 버튼 활성 (개별 객체 변경 누적)
    // 모든 Phase 5 dirty=true 위치를 이 헬퍼 호출로 통합
    // γ: 편집 모드 *유지 중* 에도 우하단 [저장] 이 작동하도록, 변경 즉시 pendingChanges + editorState.isDirty 갱신.
    //     (_exitEditMode 의 누적 로직은 보존 — 중복 누적이어도 같은 update key 라 무해)
    function _markDirty() {
        editCtx['dirty'] = true;   // replace_all 회피용 표기
        if (editCtx.type && editCtx.pk != null && editCtx.data) {
            const cat = editCtx.type === 'facility'                       ? 'equipment'
                      : (editCtx.type === 'gas' || editCtx.type === 'power') ? 'sensor'
                      : editCtx.type === 'node'                            ? 'locationNode'
                      : editCtx.type === 'zone'                            ? 'geofence'
                      : null;
            if (cat && pendingChanges[cat]) {
                pendingChanges[cat].update[editCtx.pk] = editCtx.data;
                editorState.isDirty = true;
            }
        }
        const editBtn = document.getElementById('edit-mode-btn');
        if (editBtn) {
            editBtn.disabled = false;
            editBtn.style.opacity = '';
            editBtn.style.cursor  = '';
        }
        _showEditActionsBar();   // 우하단 [전체 되돌리기]/[저장] 즉시 표시
    }

    // P6-CDE: 우하단 [편집] ↔ [전체 되돌리기]/[저장] 토글 (Q-i 다)
    function _showEditActionsBar() {
        const editWrap    = document.getElementById('edit-mode-wrap');
        const actionsWrap = document.getElementById('edit-actions-wrap');
        if (editWrap)    editWrap.style.display = 'none';
        if (actionsWrap) actionsWrap.style.display = '';
    }

    function _hideEditActionsBar() {
        const editWrap    = document.getElementById('edit-mode-wrap');
        const actionsWrap = document.getElementById('edit-actions-wrap');
        if (editWrap)    editWrap.style.display = '';
        if (actionsWrap) actionsWrap.style.display = 'none';
    }

    // T1: 위험구역 생성 모드 진입 시 누적된 편집 세션을 폐기.
    function _resetEditState() {
        for (const cat of ['equipment', 'sensor', 'locationNode', 'geofence']) {
            if (pendingChanges[cat]) {
                pendingChanges[cat].update = {};
                pendingChanges[cat].add    = [];
                pendingChanges[cat].delete = [];
            }
        }
        editorState.isDirty = false;
        _hideEditActionsBar();
        console.info('[admin_map_editor] T1: 편집 세션 폐기 (위험구역 생성 모드 진입)');
    }

    // P6-CDE (Q-γ 나): [전체 되돌리기] — 변경 없으면 즉시 reload, 있으면 재확인
    function _handleEditUndoClick() {
        if (!editorState.isDirty) {
            window.location.reload();
            return;
        }
        Modal.confirm({
            title:   '변경 사항을 폐기하시겠습니까?',
            message: '저장하지 않은 모든 변경이 사라집니다.',
            onConfirm: () => window.location.reload(),
        });
    }

    // P6-CDE (Q-iv 나): [저장] — 재확인 + Promise.allSettled 일괄 PATCH + reload
    function _handleEditSaveClick() {
        if (!editorState.isDirty) {
            Modal.info({ title: '저장할 변경 사항이 없습니다.' });
            return;
        }
        Modal.confirm({
            title:   '저장하시겠습니까?',
            message: `변경된 객체 ${_countPendingChanges()}건을 저장합니다.`,
            onConfirm: () => _executeBulkSave(),
        });
    }

    function _countPendingChanges() {
        let n = 0;
        for (const cat of ['equipment', 'sensor', 'locationNode', 'geofence']) {
            n += Object.keys(pendingChanges[cat]?.update || {}).length;
        }
        return n;
    }

    // T1-ε: 단일 bulk endpoint 호출 — per-item 결과 상세 표시
    function _executeBulkSave() {
        const csrf = _getCsrfToken();
        // 각 카테고리 update payload 그대로 전송 (서버가 카테고리별 처리)
        const body = {
            equipment:    pendingChanges.equipment?.update    || {},
            locationNode: pendingChanges.locationNode?.update || {},
            sensor:       pendingChanges.sensor?.update       || {},
            geofence:     pendingChanges.geofence?.update     || {},
        };
        console.group('[admin_map_editor] bulk-save 요청');
        console.log('URL:', `${API_BASE}/map-editor/bulk-save/`);
        console.log('body (server-bound payload):', JSON.parse(JSON.stringify(body)));
        console.log('counts:', {
            equipment:    Object.keys(body.equipment).length,
            sensor:       Object.keys(body.sensor).length,
            locationNode: Object.keys(body.locationNode).length,
            geofence:     Object.keys(body.geofence).length,
        });
        console.groupEnd();

        fetch(`${API_BASE}/map-editor/bulk-save/`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body:    JSON.stringify(body),
        })
        .then(res => res.json().then(data => ({ ok: res.ok, status: res.status, data })))
        .then(({ ok, status, data }) => {
            console.group('[admin_map_editor] bulk-save 응답');
            console.log('HTTP', status, 'ok=', ok);
            console.log('data:', data);
            console.groupEnd();
            return { ok, data };
        })
        .then(({ ok, data }) => {
            if (!ok) {
                Modal.info({
                    title:   '저장 실패',
                    message: '서버 응답 오류',
                    onClose: () => window.location.reload(),
                });
                return;
            }
            const { success, failed, errors } = data;
            let message = `${success}건 저장 완료.`;
            if (failed > 0) {
                message += ` ${failed}건 실패:\n`;
                message += errors.map(e => `  - ${e.type}#${e.pk}: ${JSON.stringify(e.errors)}`).join('\n');
            }
            Modal.info({
                title:   failed > 0 ? '일부 저장 실패' : '저장되었습니다.',
                message,
                onClose: () => window.location.reload(),
            });
        })
        .catch(err => {
            console.error('[admin_map_editor] bulk-save 호출 실패:', err);
            Modal.info({
                title:   '저장 요청 실패',
                message: '네트워크 오류',
                onClose: () => window.location.reload(),
            });
        });
    }

    function _doPatch(url, payload, type, pk, csrf) {
        return fetch(url, {
            method:  'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body:    JSON.stringify(payload),
        })
        .then(res => ({ ok: res.ok, type, pk }))
        .catch(err => {
            console.error(`[admin_map_editor] PATCH 실패 ${type}#${pk}:`, err);
            return { ok: false, type, pk };
        });
    }

    // P6-CDE: 우하단 [전체 되돌리기]/[저장] click 핸들러 등록 (1회만)
    function setupEditActionsButtons() {
        if (window._editActionsBound) return;
        window._editActionsBound = true;
        const saveBtn = document.getElementById('edit-save-btn-floating');
        const undoBtn = document.getElementById('edit-undo-btn-floating');
        if (saveBtn) saveBtn.addEventListener('click', _handleEditSaveClick);
        if (undoBtn) undoBtn.addEventListener('click', _handleEditUndoClick);
    }

    // P5-E (R2-G-5): 편집 중 객체 [삭제] — 지도에서 제외(facility/node) 또는 진짜 DELETE(수동 zone)
    // "삭제" = 지도에서 안 보이게. DB 영구 삭제는 다른 페이지.
    function _confirmDeleteObject() {
        if (!editCtx.active) return;
        const { type, pk } = editCtx;
        if (!pk) {
            Modal.info({ title: '삭제 실패', message: 'DB PK 누락' });
            return;
        }

        // T1-β P1: gas/power 미배치 PATCH 활성화 (pk 는 SensorLocation.pk)
        if (type === 'gas' || type === 'power') {
            Modal.confirm({
                title:   '삭제하시겠습니까?',
                message: '지도에서 제외됩니다. 영구 삭제는 장비 관리 페이지에서 가능합니다.',
                onConfirm: () => _patchUnplacement(
                    `${API_BASE}/sensor-locations/${pk}/`,
                    {
                        floor:     null,
                        is_placed: false,
                        x:         null,    // T1-β Q1+B-2: 미배치 = 좌표 없음
                        y:         null,
                    },
                    type === 'gas' ? '유해가스 센서' : '스마트 전력 시스템',
                ),
            });
            return;
        }

        if (type === 'facility') {
            Modal.confirm({
                title:   '삭제하시겠습니까?',
                message: '지도에서 제외됩니다. 영구 삭제는 장비 관리 페이지에서 가능합니다.',
                onConfirm: () => _patchUnplacement(
                    `${API_BASE}/equipments/${pk}/`,
                    {
                        floor:     null,
                        is_placed: false,
                        center_x:  null,    // T1-γ B-2: 미배치 = 좌표 없음
                        center_y:  null,
                        width:     null,
                        height:    null,
                    },
                    '설비',
                ),
            });
        } else if (type === 'node') {
            Modal.confirm({
                title:   '삭제하시겠습니까?',
                message: '지도에서 제외됩니다. 영구 삭제는 장비 관리 페이지에서 가능합니다.',
                onConfirm: () => _patchUnplacement(
                    `${API_BASE}/location-nodes/${pk}/`,
                    {
                        floor:     null,
                        is_placed: false,
                        x:         null,    // T1-α X3+B-2: 미배치 = 좌표 없음
                        y:         null,
                    },
                    '위치 노드',
                ),
            });
        } else if (type === 'zone') {
            // 자동 위험구역은 buildGeofenceEditPopover 가 [삭제] 버튼 미표시 — 여기 도달 시 수동만
            Modal.confirm({
                title:   '삭제하시겠습니까?',
                message: '이 작업은 되돌릴 수 없습니다.',
                onConfirm: () => _deleteGeofence(`${API_BASE}/geofences/${pk}/`),
            });
        }
    }

    // P5-E: facility/node 지도에서 제외 (PATCH floor=null)
    function _patchUnplacement(url, payload, label) {
        const csrf = _getCsrfToken();
        console.info(`[admin_map_editor] PATCH (지도 제외) ${url}`, payload);
        fetch(url, {
            method:  'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body:    JSON.stringify(payload),
        })
        .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
        .then(() => Modal.info({
            title:   '삭제되었습니다.',
            onClose: () => window.location.reload(),
        }))
        .catch(err => {
            console.error(`[admin_map_editor] ${label} 처리 실패:`, err);
            Modal.info({ title: `${label} 처리 실패`, message: err.message || '서버 통신 오류' });
        });
    }

    // P5-E: 위험구역(수동) 진짜 DELETE
    function _deleteGeofence(url) {
        const csrf = _getCsrfToken();
        console.info(`[admin_map_editor] DELETE ${url}`);
        fetch(url, { method: 'DELETE', headers: { 'X-CSRFToken': csrf } })
        .then(res => {
            if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
            Modal.info({
                title:   '삭제되었습니다.',
                onClose: () => window.location.reload(),
            });
        })
        .catch(err => {
            console.error('[admin_map_editor] 위험구역 삭제 실패:', err);
            Modal.info({ title: '위험구역 삭제 실패', message: err.message || '서버 통신 오류' });
        });
    }

    // 디버깅 노출
    window._mapEditor.placeCtx = placeCtx;
    window._mapEditor.cancelPlaceMode = _cancelPlaceMode;
    // ─── 상단 캔버스 필터 (단계 3-G.1) ────────────────────────────

    /**
     * applyCanvasFilter
     * 상단 필터 탭 클릭 시 호출.
     * 선택된 타입만 지도에 표시, 나머지는 숨김 (opacity 0).
     *
     * 입력:
     *   filter — 'all' | 'facility' | 'gas' | 'power' | 'node' | 'zone'
     */

    /**
     * _completePlacement
     * 배치 완료 처리 (단계 3-Z.3).
     *
     * 동작:
     *   1. placeCtx 에서 정보 수집
     *   2. payload 구성 (타입별 다름)
     *   3. console.log (Stub 검증)
     *   4. (선택) 실제 PATCH/POST 호출 — 현재는 Stub 만
     *   5. 모드 종료 (_cancelPlaceMode 와 유사)
     *
     * Stub 모드 (사용자 결정):
     *   - 모든 타입 console.log 만 (DB 영향 0)
     *   - 실제 API 활성화는 R12 마이그레이션 후
     */
    function _completePlacement() {
        if (!placeCtx.active) {
            console.warn('[admin_map_editor] 배치 모드 아님 — 완료 처리 건너뜀');
            return;
        }

        if (!placeCtx.latlng) {
            console.warn('[admin_map_editor] 좌표 없음 — 지도를 클릭해서 위치를 결정하세요');
            return;
        }

        // P3-3 (R2-G-7): 충돌 상태면 저장 차단
        if (placeCtx._colliding) {
            Modal.info({
                title:   '다른 설비와 겹쳐 배치할 수 없습니다',
                message: '위치를 조정한 후 다시 시도하세요.',
            });
            return;
        }

        const { type, code, name, pk, latlng } = placeCtx;
        const floorId =
            (typeof currentFloorId   !== 'undefined' && currentFloorId)   ||
            (typeof MAP_AUTO_FLOOR_ID !== 'undefined' && MAP_AUTO_FLOOR_ID);

        if (!pk) {
            Modal.info({
                title:   '저장 실패',
                message: 'DB PK 매핑 실패 — data-pk 누락',
            });
            return;
        }

        // 타입별 payload + PATCH 함수
        let payload, patchFn;
        if (type === 'facility') {
            // P3-2c 의 사각형 bounds 에서 width/height 재계산
            let widthM = 1.0, heightM = 1.0;
            if (placeCtx.rectShape && placeCtx.rectShape.getBounds) {
                const b = placeCtx.rectShape.getBounds();
                widthM  = Math.abs(b.getEast()  - b.getWest());
                heightM = Math.abs(b.getNorth() - b.getSouth());
            }
            payload = {
                center_x:  latlng.lng,
                center_y:  latlng.lat,
                width:     widthM,
                height:    heightM,
                floor:     floorId,
                is_placed: true,
            };
            patchFn = () => _patchEquipment(pk, payload);
        } else if (type === 'node') {
            payload = {
                x:         latlng.lng,
                y:         latlng.lat,
                floor:     floorId,
                is_placed: true,
            };
            patchFn = () => _patchLocationNode(pk, payload);
        } else if (type === 'gas' || type === 'power') {
            // T1-β: gas/power 배치 — SensorLocation.pk 사용. 동일 endpoint 에 reverse PATCH.
            payload = {
                x:         latlng.lng,
                y:         latlng.lat,
                floor:     floorId,
                is_placed: true,
            };
            patchFn = () => _patchSensorLocation(pk, payload, type);
        } else {
            console.warn(`[admin_map_editor] 지원하지 않는 type: ${type}`);
            _cancelPlaceMode();
            return;
        }

        // P3-7 (R4-F 패턴): 재확인 → PATCH → 완료 팝업 → reload
        Modal.confirm({
            title: '저장하시겠습니까?',
            onConfirm: patchFn,
        });
    }

    // P3-7: 객체별 PATCH 헬퍼 (R4-F 와 동일 패턴 — 완료 시 reload)
    function _patchEquipment(pkId, payload) {
        _patchObject(`${API_BASE}/equipments/${pkId}/`, payload, '설비');
    }
    function _patchLocationNode(pkId, payload) {
        _patchObject(`${API_BASE}/location-nodes/${pkId}/`, payload, '위치 노드');
    }
    // T1-β: gas/power 배치 PATCH — SensorLocation 동일 endpoint 사용 (unplacement 와 동일)
    function _patchSensorLocation(pkId, payload, type) {
        const label = type === 'gas' ? '유해가스 센서' : '스마트 전력 시스템';
        _patchObject(`${API_BASE}/sensor-locations/${pkId}/`, payload, label);
    }

    // 공통 PATCH — 성공 시 reload, 실패 시 Modal.info
    function _patchObject(url, payload, label) {
        const csrf = _getCsrfToken();
        console.info(`[admin_map_editor] PATCH ${url}`, payload);
        fetch(url, {
            method:  'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken':  csrf,
            },
            body: JSON.stringify(payload),
        })
        .then(response => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        })
        .then(data => {
            console.info(`[admin_map_editor] ${label} 저장 성공:`, data);
            Modal.info({
                title:   '저장되었습니다.',
                onClose: () => window.location.reload(),
            });
        })
        .catch(err => {
            console.error(`[admin_map_editor] ${label} 저장 실패:`, err);
            Modal.info({
                title:   `${label} 저장 실패`,
                message: err.message || '서버와 통신 중 오류가 발생했습니다.',
            });
        });
    }

    // 디버깅 노출
    window._mapEditor.completePlacement = _completePlacement;
    window._mapEditor.pendingChanges    = pendingChanges;

    function applyCanvasFilter(filter) {
        console.info(`[admin_map_editor] 캔버스 필터 적용: ${filter}`);

        // 1) Equipment 마커
        Object.values(markerRefs.equipment).forEach(marker => {
            _setMarkerVisible(marker, filter === 'all' || filter === 'facility');
        });

        // 2) Sensor 마커 (gas + power 분리 필요)
        Object.entries(markerRefs.sensor).forEach(([id, marker]) => {
            const sensor = dataCache.sensor.find(s => s.id === parseInt(id));
            if (!sensor) return;
            let show = false;
            if (filter === 'all') show = true;
            else if (filter === 'gas' && sensor.sensor_type === 'gas') show = true;
            else if (filter === 'power' && sensor.sensor_type === 'power') show = true;
            _setMarkerVisible(marker, show);
        });

        // 3) LocationNode 마커
        Object.values(markerRefs.locationNode).forEach(marker => {
            _setMarkerVisible(marker, filter === 'all' || filter === 'node');
        });

        // 4) Geofence 도형 + 라벨
        if (typeof geofenceState !== 'undefined') {
            Object.values(geofenceState).forEach(state => {
                const show = filter === 'all' || filter === 'zone';
                _setShapeVisible(state.shape, show);
                _setMarkerVisible(state.labelMarker, show);
            });
        }
    }

    /**
     * _setMarkerVisible
     * divIcon 마커의 표시/숨김 — setOpacity 사용.
     */
    function _setMarkerVisible(marker, visible) {
        if (!marker) return;
        if (typeof marker.setOpacity === 'function') {
            marker.setOpacity(visible ? 1 : 0);
            // 클릭 차단도 함께 (숨겼는데 클릭되면 이상함)
            const el = marker.getElement && marker.getElement();
            if (el) el.style.pointerEvents = visible ? '' : 'none';
        }
    }

    /**
     * _setShapeVisible
     * Geofence 도형 (Circle/Polygon) 의 표시/숨김 — setStyle 사용.
     */
    function _setShapeVisible(shape, visible) {
        if (!shape) return;
        try {
            if (visible) {
                shape.setStyle({ opacity: 1, fillOpacity: undefined });  // 원래대로
                // 자동/수동 잠금 재적용 (필요 시)
                // (setupAutoGeofenceLock 의 다음 호출에서 자동 처리됨)
            } else {
                shape.setStyle({ opacity: 0, fillOpacity: 0 });
                shape._path && (shape._path.style.pointerEvents = 'none');
            }
        } catch (e) {
            console.warn('[admin_map_editor] shape 가시성 변경 실패:', e);
        }
    }

    /**
     * setupCanvasFilterTabs
     * 상단의 .tab-btn[data-canvas-filter] 클릭 이벤트 등록.
     * 멱등성 보장.
     */
    function setupCanvasFilterTabs() {
        if (window._canvasFilterRegistered) {
            return;
        }
        window._canvasFilterRegistered = true;

        document.querySelectorAll('[data-canvas-filter]').forEach(btn => {
            btn.addEventListener('click', function() {
                // 모든 탭의 aria-selected 초기화
                document.querySelectorAll('[data-canvas-filter]').forEach(b => {
                    b.setAttribute('aria-selected', 'false');
                });
                // 이 탭만 선택 상태로
                this.setAttribute('aria-selected', 'true');

                const filter = this.dataset.canvasFilter;
                applyCanvasFilter(filter);
            });
        });

        console.info('[admin_map_editor] 캔버스 필터 탭 활성화');
    }

    // 디버깅 노출
    window._mapEditor.applyCanvasFilter = applyCanvasFilter;

    // ─── 줌 컨트롤 (단계 3-V) ────────────────────────────────────────

    /**
     * setupZoomControls
     * 우상단 줌 컨트롤 박스의 버튼 활성화.
     * - 확대/축소 → map.zoomIn/zoomOut()
     * - 되돌리기 → 초기 줌으로 (그리고 fitBounds 로 도면 전체 보기)
     *
     * 멱등성 보장.
     */
    function setupZoomControls() {
        if (window._zoomControlsRegistered) {
            return;
        }
        window._zoomControlsRegistered = true;

        const zoomInBtn    = document.getElementById('zoom-in-btn');
        const zoomOutBtn   = document.getElementById('zoom-out-btn');
        const zoomResetBtn = document.getElementById('zoom-reset-btn');
        const zoomResetBox = document.getElementById('zoom-reset-box');

        if (!map) {
            console.warn('[admin_map_editor] map 미준비 — 줌 컨트롤 등록 보류');
            return;
        }

        // 초기 줌·중심 저장 (되돌리기용)
        const initialZoom   = map.getZoom();
        const initialCenter = map.getCenter();

        // 확대
        zoomInBtn?.addEventListener('click', () => {
            map.zoomIn();
        });

        // 축소
        zoomOutBtn?.addEventListener('click', () => {
            map.zoomOut();
        });

        // 되돌리기 — 초기 상태로
        zoomResetBtn?.addEventListener('click', () => {
            map.setView(initialCenter, initialZoom, { animate: true });
        });

        // 줌 변경 시 되돌리기 박스 표시/숨김
        map.on('zoomend', () => {
            if (!zoomResetBox) return;
            const isInitial = map.getZoom() === initialZoom;
            zoomResetBox.style.display = isInitial ? 'none' : 'flex';
        });

        console.info('[admin_map_editor] 줌 컨트롤 활성화');
    }

    // ─── 편집 모드 토글 (단계 3-V) ──────────────────────────────────

    /**
     * setupEditModeButton
     * 우하단 [편집] 버튼 클릭 시 편집/뷰 모드 전환.
     *
     * 편집 모드 진입 시:
     *   - editorState.mode = 'edit'
     *   - 버튼 텍스트 "완료", 색상 파란색
     *   - #mode-badge 표시
     *   - (단계 3-Y 에서) 마커 드래그 활성
     *
     * 뷰 모드 복귀:
     *   - editorState.mode = 'view'
     *   - 버튼 텍스트 "편집", 색상 어두운 회색
     *   - #mode-badge 숨김
     *
     * 멱등성 보장.
     */
    function setupEditModeButton() {
        if (window._editModeRegistered) {
            return;
        }
        window._editModeRegistered = true;

        const editBtn   = document.getElementById('edit-mode-btn');
        const modeBadge = document.getElementById('mode-badge');

        if (!editBtn) {
            console.warn('[admin_map_editor] #edit-mode-btn 미발견 — 편집 모드 등록 보류');
            return;
        }

editBtn.addEventListener('click', () => {
            const currentMode = editorState.mode;

            if (currentMode === 'create') {
                // 단계 3-Z.3: 배치 완료 처리
                _completePlacement();
                return;
            }

            if (currentMode === 'view') {
                // 편집 모드 진입
                editorState.mode = 'edit';
                editBtn.setAttribute('aria-pressed', 'true');
                editBtn.innerHTML = '<i data-lucide="check" class="w-4 h-4"></i> 완료';
                editBtn.classList.replace('bg-slate-800', 'bg-blue-600');
                editBtn.classList.replace('hover:bg-slate-700', 'hover:bg-blue-700');
                modeBadge?.classList.remove('hidden');
                modeBadge?.classList.add('flex');

                console.info('[admin_map_editor] 편집 모드 진입');
                // TODO: 단계 3-Y 에서 마커 드래그 활성화 추가 예정
            } else {
                // 뷰 모드 복귀 (edit 모드에서)
                editorState.mode = 'view';
                editBtn.setAttribute('aria-pressed', 'false');
                editBtn.innerHTML = '<i data-lucide="pencil" class="w-4 h-4"></i> 편집';
                editBtn.classList.replace('bg-blue-600', 'bg-slate-800');
                editBtn.classList.replace('hover:bg-blue-700', 'hover:bg-slate-700');
                modeBadge?.classList.add('hidden');
                modeBadge?.classList.remove('flex');

                console.info('[admin_map_editor] 뷰 모드 복귀');
                // TODO: 단계 3-Y 에서 [저장] 호출 (pendingChanges 처리)
            }

            // lucide 아이콘 재렌더
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        });

        console.info('[admin_map_editor] 편집 모드 버튼 활성화');
    }

    // ─── 위험구역 추가 흐름 (단계 3-W) ──────────────────────────────

    /**
     * Zone Create 상태 — 모듈 스코프 변수
     */
    const zoneCreateCtx = {
        active:        false,        // 위험구역 생성 모드 진입 여부
        severity:      null,         // 'danger' | 'warning'
        shape:         null,         // 'circle' | 'polygon'
        drawData:      null,         // 그리기 완료 후 데이터
        drawer:        null,         // L.Draw.Circle / L.Draw.Polygon 인스턴스
        previousMode:  'view',       // 진입 전 editorState.mode
        _circleCenter: null,         // P2-4: 원형 그리는 중 중심 좌표 추적용
        popover:       null,         // P2-5a: 위험구역 생성 팝오버(L.Tooltip permanent) 인스턴스
    };

    /**
     * setupZoneCreateButton
     * 우상단 [위험 구역 추가] 버튼 + 위험구역 생성 패널 의 컨트롤 활성화.
     *
     * 하위 단계 분할:
     *   - 3-W.1: 패널 전환 + 위험도/모양 선택 (현재)
     *   - 3-W.2: 그리기
     *   - 3-W.3: 저장/취소/다시 그리기
     */
    function setupZoneCreateButton() {
        if (window._zoneCreateRegistered) {
            return;
        }
        window._zoneCreateRegistered = true;

        const addZoneBtn      = document.getElementById('add-zone-btn');
        const objectPanel     = document.getElementById('object-panel');
        const zoneCreatePanel = document.getElementById('zone-create-panel');

        if (!addZoneBtn || !zoneCreatePanel || !objectPanel) {
            console.warn('[admin_map_editor] 위험구역 추가 UI 미발견 — 등록 보류');
            return;
        }

        // [위험 구역 추가] / [생성 취소] 토글
        addZoneBtn.addEventListener('click', function(e) {
            e.preventDefault();

            // (1) 이미 위험구역 생성 모드 진행 중 → [생성 취소] 흐름 (R4-B)
            if (zoneCreateCtx.active) {
                // P2-2 (R4-B): 생성 데이터 유무에 따라 분기
                // 옵션 (c): 어떤 입력(도형/위험도/모양/구역명)이라도 있으면 의사가 있는 것으로 판단
                const zoneNameInput = document.getElementById('zone-name-input');
                const hasName = zoneNameInput && zoneNameInput.value.trim() !== '';
                const hasData = !!zoneCreateCtx.drawData
                    || !!zoneCreateCtx.severity
                    || !!zoneCreateCtx.shape
                    || hasName;

                if (!hasData) {
                    // 데이터 없음 → 팝업 없이 바로 종료
                    exitZoneCreateMode();
                    return;
                }

                // 데이터 있음 → 재확인
                Modal.confirm({
                    title:   '생성을 중단하시겠습니까?',
                    message: '그린 도형과 입력 정보가 사라집니다.',
                    onConfirm: () => exitZoneCreateMode(),
                    // onCancel — 생성 화면 유지 (Modal 닫힘만)
                });
                return;
            }

            // (2) R1-K (P2-1): 다른 작업 진행 중이면 재확인
            const otherWorkActive =
                editorState.mode === 'edit' ||
                editorState.mode === 'create' ||
                placeCtx.active ||
                editorState.isDirty;

            if (otherWorkActive) {
                Modal.confirm({
                    title:   '수행하던 작업을 중지하고 위험 구역을 추가하시겠습니까?',
                    message: '진행 중인 편집/배치 작업이 취소됩니다.',
                    onConfirm: () => {
                        // 진행 중 작업 정리 후 위험구역 생성 모드 진입
                        if (placeCtx.active) _cancelPlaceMode();
                        if (editCtx.active)  _exitEditMode();   // T1: editCtx 정리
                        _resetEditState();                       // T1: pendingChanges 폐기 + 우하단 토글
                        editorState.mode = 'view';
                        enterZoneCreateMode();
                    },
                    // onCancel — 그대로 작업 중 화면 유지 (Modal 닫힘 처리만)
                });
                return;
            }

            // (3) 아무 작업 없음 → 바로 생성 모드
            enterZoneCreateMode();
        });

        // 위험도 선택 (.severity-btn)
        document.querySelectorAll('.severity-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.severity-btn').forEach(b => {
                    b.style.outline = '';
                    b.style.outlineOffset = '';
                });
                this.style.outline = '3px solid #3b82f6';
                this.style.outlineOffset = '2px';
                zoneCreateCtx.severity = this.dataset.severity;
                console.info(`[admin_map_editor] 위험도 선택: ${zoneCreateCtx.severity}`);
                _updateZoneCreateState();
            });
        });

        // 생성 방법 선택 (.shape-btn)
        document.querySelectorAll('.shape-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.shape-btn').forEach(b => {
                    b.style.borderColor = '';
                    b.style.color = '';
                    b.style.background = '';
                    b.style.outline = '';
                });
                this.style.borderColor = '#3b82f6';
                this.style.color = '#2563eb';
                this.style.background = '#eff6ff';
                this.style.outline = '3px solid #93c5fd';
                this.style.outlineOffset = '2px';
                zoneCreateCtx.shape = this.dataset.shape;
                console.info(`[admin_map_editor] 모양 선택: ${zoneCreateCtx.shape}`);

                // 모양 변경 시 기존 미리보기·드로어 정리
                _clearDrawPreview();
                _updateZoneCreateState();
            });
        });

        // [다시 그리기] 버튼
        const zoneResetBtn = document.getElementById('zone-reset-btn');
        zoneResetBtn?.addEventListener('click', function() {
            console.info('[admin_map_editor] 다시 그리기');
            _clearDrawPreview();
            _updateZoneCreateState();  // 그리기 다시 시작
        });

        // [저장] 버튼
        const zoneSaveBtn = document.getElementById('zone-save-btn-floating');
        zoneSaveBtn?.addEventListener('click', function() {
            if (this.disabled) return;
            _handleZoneSave();
        });

        console.info('[admin_map_editor] 위험구역 추가 기능 활성화');
    }

    /**
     * enterZoneCreateMode
     * 위험구역 생성 모드 진입.
     */
    function enterZoneCreateMode() {
        const addZoneBtn      = document.getElementById('add-zone-btn');
        const objectPanel     = document.getElementById('object-panel');
        const zoneCreatePanel = document.getElementById('zone-create-panel');

        zoneCreateCtx.active = true;
        zoneCreateCtx.previousMode = editorState.mode;
        editorState.mode = 'zone-create';

        // 버튼 텍스트/색상 변경
        addZoneBtn.innerHTML = '<i data-lucide="x" class="w-4 h-4"></i> 생성 취소';
        addZoneBtn.classList.replace('bg-blue-600', 'bg-red-500');
        addZoneBtn.classList.replace('hover:bg-blue-700', 'hover:bg-slate-600');

        // 패널 전환
        objectPanel.style.display = 'none';
        zoneCreatePanel.style.display = 'flex';
        zoneCreatePanel.style.flexDirection = 'column';

        // P2-5d: [편집] 버튼 숨김, [저장 floating] 표시
        const editBtnWrap = document.getElementById('edit-mode-wrap');
        if (editBtnWrap) editBtnWrap.style.display = 'none';
        const floatingSaveWrap = document.getElementById('zone-save-floating-wrap');
        if (floatingSaveWrap) floatingSaveWrap.style.display = '';

        _hideEditActionsBar();   // T1: [전체 되돌리기]/[저장] 바 잔존 방지

        if (typeof lucide !== 'undefined') lucide.createIcons();

        console.info('[admin_map_editor] 위험구역 생성 모드 진입');
    }

    /**
     * exitZoneCreateMode
     * 위험구역 생성 모드 종료 — 모든 상태 초기화.
     */
    function exitZoneCreateMode() {
        const addZoneBtn      = document.getElementById('add-zone-btn');
        const objectPanel     = document.getElementById('object-panel');
        const zoneCreatePanel = document.getElementById('zone-create-panel');
        const zoneGuide       = document.getElementById('zone-guide');
        const zoneInfo        = document.getElementById('zone-info');
        const zoneResetBtn    = document.getElementById('zone-reset-btn');
        const zoneSaveBtn     = document.getElementById('zone-save-btn-floating');
        const zoneNameInput   = document.getElementById('zone-name-input');

        // 컨텍스트 초기화
        zoneCreateCtx.active   = false;
        zoneCreateCtx.severity = null;
        zoneCreateCtx.shape    = null;
        zoneCreateCtx.drawData = null;
        zoneCreateCtx._circleCenter = null;  // P2-4

        // P2-5a: 팝오버 닫기
        closeZoneCreatePopover();

        // 그리기 중이면 취소
        if (zoneCreateCtx.drawer) {
            try { zoneCreateCtx.drawer.disable(); } catch (e) { /* ignore */ }
            zoneCreateCtx.drawer = null;
        }

        // 미리보기 도형 제거
        if (zoneCreateCtx.drawData && zoneCreateCtx.drawData.preview) {
            try { map.removeLayer(zoneCreateCtx.drawData.preview); } catch (e) { /* ignore */ }
        }
        zoneCreateCtx.drawData = null;

        editorState.mode = zoneCreateCtx.previousMode || 'view';

        // 버튼 복원
        addZoneBtn.innerHTML = '<i data-lucide="plus" class="w-4 h-4"></i> 위험 구역 추가';
        addZoneBtn.classList.replace('bg-slate-500', 'bg-blue-600');
        addZoneBtn.classList.replace('hover:bg-slate-600', 'hover:bg-blue-700');

        // 패널 복원
        zoneCreatePanel.style.display = 'none';
        objectPanel.style.display = '';

        // 위험도/모양 버튼 선택 상태 초기화
        document.querySelectorAll('.severity-btn').forEach(b => {
            b.style.outline = '';
            b.style.outlineOffset = '';
        });
        document.querySelectorAll('.shape-btn').forEach(b => {
            b.style.borderColor = '';
            b.style.color = '';
            b.style.background = '';
            b.style.outline = '';
        });

        // 안내·정보·저장 UI 초기화
        zoneGuide?.classList.add('hidden');
        zoneInfo?.classList.add('hidden');
        zoneResetBtn?.classList.add('hidden');
        if (zoneSaveBtn) {
            zoneSaveBtn.disabled = true;
            zoneSaveBtn.classList.add('opacity-40', 'cursor-not-allowed');
        }
        if (zoneNameInput) {
            zoneNameInput.value = '';
        }

        // P2-5d: [편집] 버튼 복귀, [저장 floating] 숨김
        const editBtnWrap = document.getElementById('edit-mode-wrap');
        if (editBtnWrap) editBtnWrap.style.display = '';
        const floatingSaveWrap = document.getElementById('zone-save-floating-wrap');
        if (floatingSaveWrap) floatingSaveWrap.style.display = 'none';

        if (typeof lucide !== 'undefined') lucide.createIcons();

        console.info('[admin_map_editor] 위험구역 생성 모드 종료');
    }

    /**
     * _updateZoneCreateState
     * 위험도 + 모양 둘 다 선택되면 다음 단계 (그리기) 안내 표시.
     * 그리기 자체는 단계 3-W.2 에서 활성화.
     */
function _updateZoneCreateState() {
        const zoneGuide     = document.getElementById('zone-guide');
        const zoneGuideText = document.getElementById('zone-guide-text');

        if (zoneCreateCtx.severity && zoneCreateCtx.shape) {
            zoneGuide?.classList.remove('hidden');
            zoneGuideText.textContent = zoneCreateCtx.shape === 'circle'
                ? '지도를 클릭·드래그하여 원형 구역을 그리세요.'
                : '지도를 클릭하여 꼭짓점을 찍고, 마지막 점을 더블클릭하여 완성하세요.';

            // 단계 3-W.2: 그리기 모드 활성화
            _startDrawing();
        }
    }

    /**
     * _startDrawing
     * L.Draw.Circle 또는 L.Draw.Polygon 활성화.
     *
     * 동작:
     *   1. 기존 drawer 가 있으면 disable
     *   2. 새 drawer 생성 + enable
     *   3. CREATED 이벤트 1회 청취 → _handleDrawCreated
     *
     * 위험도에 따른 색상:
     *   - danger:  빨강
     *   - warning: 주황
     */
    function _startDrawing() {
        if (!map) {
            console.warn('[admin_map_editor] map 미준비 — 그리기 시작 불가');
            return;
        }
        if (typeof L.Draw === 'undefined') {
            console.warn('[admin_map_editor] Leaflet.Draw 미로드 — 그리기 시작 불가');
            return;
        }

        // 기존 drawer 정리
        if (zoneCreateCtx.drawer) {
            try { zoneCreateCtx.drawer.disable(); } catch (e) { /* ignore */ }
            zoneCreateCtx.drawer = null;
        }

        // 위험도별 색상
        const colors = zoneCreateCtx.severity === 'warning'
            ? { color: '#f59e0b', fillColor: 'rgba(245,158,11,0.15)' }
            : { color: '#ef4444', fillColor: 'rgba(239,68,68,0.15)' };

        const options = {
            shapeOptions: {
                color:       colors.color,
                fillColor:   colors.fillColor,
                fillOpacity: 1,
                weight:      2,
                dashArray:   '4,3',
            },
        };

        // Drawer 생성
        if (zoneCreateCtx.shape === 'circle') {
            zoneCreateCtx.drawer = new L.Draw.Circle(map, {
                ...options,
                showRadius: true,
                metric:     true,
            });
        } else if (zoneCreateCtx.shape === 'polygon') {
            zoneCreateCtx.drawer = new L.Draw.Polygon(map, {
                ...options,
                showArea: false,
                allowIntersection: false,  // 자기 교차 방지
            });
        }

        if (!zoneCreateCtx.drawer) {
            console.warn('[admin_map_editor] 지원하지 않는 shape:', zoneCreateCtx.shape);
            return;
        }

        zoneCreateCtx.drawer.enable();

        // CREATED 이벤트 1회 청취
        map.once(L.Draw.Event.CREATED, _handleDrawCreated);

        // P2-4 (R4-D-4/E-4): 그리는 중 좌표 실시간 표시
        if (zoneCreateCtx.shape === 'polygon') {
            map.on('draw:drawvertex', _onPolygonVertex);
        } else if (zoneCreateCtx.shape === 'circle') {
            map.on('draw:drawstart', _onCircleDrawStart);
        }

        console.info(`[admin_map_editor] 그리기 시작: shape=${zoneCreateCtx.shape}, severity=${zoneCreateCtx.severity}`);
    }

    // P2-4 (R4-D-4): 폴리곤 그리는 중 — 마지막 꼭짓점 좌표 표시
    function _onPolygonVertex(e) {
        const layers = e.layers && e.layers.getLayers ? e.layers.getLayers() : [];
        const last = layers[layers.length - 1];
        if (!last || !last.getLatLng) return;
        const ll = last.getLatLng();
        _showDrawingInfoText(
            `꼭짓점: (${metersToCmDisplay(ll.lng)}cm, ${metersToCmDisplay(ll.lat)}cm)`,
            '크기: — (그리는 중)'
        );
        // P2-5c: 팝오버 — 첫 꼭짓점 위치에 고정, 이후 내용만 갱신
        const vertexCount = layers.length;
        showDrawingPopover(layers[0].getLatLng(), _drawingPopoverHtml(
            `꼭짓점: (${metersToCmDisplay(ll.lng)}cm, ${metersToCmDisplay(ll.lat)}cm)`,
            `꼭짓점 ${vertexCount}개 (3개 이상 + 더블클릭으로 완료)`
        ));
    }

    // P2-4 (R4-E-4) — 원형: 중심 클릭 후 마우스 이동에 따라 중심 + 반경 실시간 표시
    function _onCircleDrawStart() {
        zoneCreateCtx._circleCenter = null;
        map.on('mousedown', _onCircleCenterDown);
        map.on('mousemove', _onCircleDrawing);
    }

    function _onCircleCenterDown(e) {
        zoneCreateCtx._circleCenter = e.latlng;
        // 중심은 한 번만 — 캐치 후 해제
        map.off('mousedown', _onCircleCenterDown);
        // P2-5c: 중심 위치에 팝오버 띄우기
        const cxCm = metersToCmDisplay(e.latlng.lng);
        const cyCm = metersToCmDisplay(e.latlng.lat);
        showDrawingPopover(e.latlng, _drawingPopoverHtml(
            `중심: (${cxCm}cm, ${cyCm}cm)`,
            '반경: — (드래그 중)'
        ));
    }

    function _onCircleDrawing(e) {
        const ll = e.latlng;
        if (!ll) return;
        const center = zoneCreateCtx._circleCenter;
        if (!center) {
            _showDrawingInfoText(
                `중심: (${metersToCmDisplay(ll.lng)}cm, ${metersToCmDisplay(ll.lat)}cm) (클릭으로 중심 설정)`,
                '크기: — (그리는 중)'
            );
        } else {
            const radius = center.distanceTo(ll);
            _showDrawingInfoText(
                `중심: (${metersToCmDisplay(center.lng)}cm, ${metersToCmDisplay(center.lat)}cm)`,
                `반경: ${metersToCmDisplay(radius)}cm`
            );
            // P2-5c: 팝오버 — 그리는 중 내용만 갱신 (위치는 중심에 고정됨)
            if (zoneCreateCtx.popover) {
                zoneCreateCtx.popover.setContent(_drawingPopoverHtml(
                    `중심: (${metersToCmDisplay(center.lng)}cm, ${metersToCmDisplay(center.lat)}cm)`,
                    `반경: ${metersToCmDisplay(radius)}cm`
                ));
            }
        }
    }

    // P2-4 공통 — 그리는 중 안내 텍스트 갱신
    function _showDrawingInfoText(coordText, sizeText) {
        const zoneInfo      = document.getElementById('zone-info');
        const zoneCoordText = document.getElementById('zone-coord-text');
        const zoneSizeText  = document.getElementById('zone-size-text');
        if (zoneCoordText) zoneCoordText.textContent = coordText;
        if (zoneSizeText)  zoneSizeText.textContent  = sizeText;
        zoneInfo?.classList.remove('hidden');
    }

    // P2-5a: 위험구역 생성 팝오버 카드 표시 (그리기 완료 시 1회) — L.Tooltip(permanent)
    function showZoneCreatePopover(drawData) {
        if (!drawData) return;
        closeZoneCreatePopover();  // 이전 인스턴스 정리

        const latlng = L.latLng(drawData.center_y, drawData.center_x);

        const cxCm = metersToCmDisplay(drawData.center_x);
        const cyCm = metersToCmDisplay(drawData.center_y);
        let sizeText;
        if (drawData.geofence_type === 'circle') {
            sizeText = `반경: ${metersToCmDisplay(drawData.radius)}cm`;
        } else {
            sizeText = `꼭짓점: ${drawData.polygon_data.length}개`;
        }

        const isCircle  = drawData.geofence_type === 'circle';
        const nameValue = (document.getElementById('zone-name-input')?.value || '').trim();
        const html = `
            <div class="popover-section-title">생성 유형</div>
            <div class="popover-shape-toggle">
                <button data-popover-shape="circle"  aria-selected="${isCircle}">원형</button>
                <button data-popover-shape="polygon" aria-selected="${!isCircle}">폴리곤</button>
            </div>
            <div class="popover-section-title">원형: 중심점 + 반경 / 폴리곤: 꼭짓점 3개 이상 추가</div>
            <div class="popover-section-title" style="margin-top:10px;">구역명</div>
            <input type="text" class="popover-name-input" data-popover-field="name"
                   placeholder="신규 위험 구역" value="${nameValue.replace(/"/g, '&quot;')}">
            <div class="popover-info-label">현재 좌표 및 크기</div>
            <div class="popover-info-value">X ${cxCm} / Y ${cyCm} · ${sizeText}</div>
        `;

        zoneCreateCtx.popover = L.tooltip({
            className:   'zone-create-popover',
            permanent:   true,
            direction:   'right',
            interactive: true,
            opacity:     1,
            offset:      [20, 0],
        })
        .setLatLng(latlng)
        .setContent(html)
        .addTo(map);

        // P2-5b: 팝오버 이벤트 위임 등록 (map 단위 1회만)
        _bindZonePopoverEvents();

        console.info('[admin_map_editor] 위험구역 생성 팝오버 표시');
    }

    function closeZoneCreatePopover() {
        if (zoneCreateCtx.popover) {
            try { map.removeLayer(zoneCreateCtx.popover); } catch (e) { /* ignore */ }
            zoneCreateCtx.popover = null;
        }
        // P2-5b: 위임 이벤트 해제 (위험구역 모드 외에는 불필요)
        if (map && map._zonePopoverEventsBound) {
            const container = map.getContainer();
            container.removeEventListener('click', _zonePopoverClickHandler, true);
            container.removeEventListener('input', _zonePopoverInputHandler, true);
            map._zonePopoverEventsBound = false;
        }
    }

    // P2-5b: 팝오버 내부 이벤트 위임 (map 단위 1회만 등록)
    // setContent 로 HTML 이 갱신돼도 위임이라 살아 있음
    function _bindZonePopoverEvents() {
        if (map._zonePopoverEventsBound) return;
        map._zonePopoverEventsBound = true;

        const container = map.getContainer();
        container.addEventListener('click', _zonePopoverClickHandler, true);
        container.addEventListener('input', _zonePopoverInputHandler, true);
    }

    function _zonePopoverClickHandler(e) {
        if (!zoneCreateCtx.popover) return;
        const btn = e.target.closest('.zone-create-popover [data-popover-shape]');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const targetShape = btn.dataset.popoverShape;
        _onPopoverShapeToggle(targetShape);
    }

    function _zonePopoverInputHandler(e) {
        if (!zoneCreateCtx.popover) return;
        const input = e.target.closest('.zone-create-popover [data-popover-field="name"]');
        if (!input) return;
        // P2-5b: 팝오버 → 좌측 패널 #zone-name-input 단방향 동기화
        const panelInput = document.getElementById('zone-name-input');
        if (panelInput && panelInput.value !== input.value) {
            panelInput.value = input.value;
        }
    }

    // P2-5b: 팝오버에서 모양 토글 → 좌측 패널의 .shape-btn 클릭과 동일 효과
    // 완료 후만 동작 — 현재 drawData 가 있는 상태에서 호출됨
    function _onPopoverShapeToggle(targetShape) {
        if (!targetShape) return;
        if (zoneCreateCtx.shape === targetShape) return;  // 같은 모양은 무시

        // 좌측 패널의 .shape-btn 클릭을 시뮬레이션 — 기존 _clearDrawPreview + _updateZoneCreateState 흐름 재사용
        const panelBtn = document.querySelector(`.shape-btn[data-shape="${targetShape}"]`);
        if (panelBtn) {
            panelBtn.click();
        } else {
            console.warn('[admin_map_editor] 팝오버 모양 토글 — 좌측 패널 버튼 미발견', targetShape);
        }
    }

    // P2-5c: 그리는 중 팝오버 표시 (정보 텍스트만 — 모양 토글·구역명 input 은 완료 후)
    // 첫 꼭짓점/중심 시점에 위치 설정 → 그 후 setContent 로 내용만 갱신
    function showDrawingPopover(latlng, infoHtml) {
        if (zoneCreateCtx.popover) {
            // 이미 표시 중이면 위치 유지 + 내용만 갱신
            zoneCreateCtx.popover.setContent(infoHtml);
            return;
        }
        zoneCreateCtx.popover = L.tooltip({
            className:   'zone-create-popover',
            permanent:   true,
            direction:   'right',
            interactive: false,   // 그리는 중에는 인터랙션 불가
            opacity:     1,
            offset:      [20, 0],
        })
        .setLatLng(latlng)
        .setContent(infoHtml)
        .addTo(map);
    }

    // P2-5c: 그리는 중 팝오버 콘텐츠 HTML 생성
    function _drawingPopoverHtml(coordText, sizeText) {
        return `
            <div class="popover-section-title">생성 중</div>
            <div class="popover-info-label">${coordText}</div>
            <div class="popover-info-value">${sizeText}</div>
        `;
    }

    /**
     * _handleDrawCreated
     * 그리기 완료 이벤트 핸들러.
     *
     * 동작:
     *   1. 도형 데이터 추출 → zoneCreateCtx.drawData
     *   2. 도형을 지도에 임시로 추가 (사용자 확인용)
     *   3. UI 갱신 — 좌표 정보, [저장] 버튼 활성화, [다시 그리기] 표시
     */
    function _handleDrawCreated(e) {
        const layer = e.layer;

        if (zoneCreateCtx.shape === 'circle') {
            const center = layer.getLatLng();
            const radius = layer.getRadius();
            zoneCreateCtx.drawData = {
                geofence_type: 'circle',
                center_x: center.lng,
                center_y: center.lat,
                radius:   radius,
                preview:  layer,
            };
        } else if (zoneCreateCtx.shape === 'polygon') {
            const latlngs = layer.getLatLngs()[0];
            const polygon_data = latlngs.map(ll => [ll.lng, ll.lat]);
            const cx = polygon_data.reduce((s, p) => s + p[0], 0) / polygon_data.length;
            const cy = polygon_data.reduce((s, p) => s + p[1], 0) / polygon_data.length;
            zoneCreateCtx.drawData = {
                geofence_type: 'polygon',
                polygon_data,
                center_x: cx,
                center_y: cy,
                preview:  layer,
            };
        }

        // 미리보기 — 지도에 임시 추가 (사용자가 확인 가능)
        layer.addTo(map);

        // UI 갱신
        _showDrawInfo();
        _enableSaveButton();

        // P2-4: 진행 이벤트 청취 해제 (완료됨)
        map.off('draw:drawvertex', _onPolygonVertex);
        map.off('draw:drawstart',  _onCircleDrawStart);
        map.off('mousedown',       _onCircleCenterDown);
        map.off('mousemove',       _onCircleDrawing);

        // P2-5a: 위험구역 생성 팝오버 카드 표시
        showZoneCreatePopover(zoneCreateCtx.drawData);

        console.info('[admin_map_editor] 그리기 완료:', zoneCreateCtx.drawData);
    }

    /**
     * _showDrawInfo
     * 좌측 패널의 좌표/크기 정보 표시.
     */
    function _showDrawInfo() {
        const zoneInfo      = document.getElementById('zone-info');
        const zoneCoordText = document.getElementById('zone-coord-text');
        const zoneSizeText  = document.getElementById('zone-size-text');
        const zoneResetBtn  = document.getElementById('zone-reset-btn');

        if (!zoneCreateCtx.drawData) return;

        const d = zoneCreateCtx.drawData;
        const cxCm = metersToCmDisplay(d.center_x);
        const cyCm = metersToCmDisplay(d.center_y);

        if (zoneCoordText) {
            zoneCoordText.textContent = `중심: (${cxCm}cm, ${cyCm}cm)`;
        }
        if (zoneSizeText) {
            if (d.geofence_type === 'circle') {
                const rCm = metersToCmDisplay(d.radius);
                zoneSizeText.textContent = `반경: ${rCm}cm (${d.radius.toFixed(2)}m)`;
            } else {
                zoneSizeText.textContent = `꼭짓점: ${d.polygon_data.length}개`;
            }
        }

        zoneInfo?.classList.remove('hidden');
        zoneResetBtn?.classList.remove('hidden');
    }

    /**
     * _enableSaveButton
     * [저장] 버튼 활성화.
     */
    function _enableSaveButton() {
        const zoneSaveBtn = document.getElementById('zone-save-btn-floating');
        if (!zoneSaveBtn) return;
        zoneSaveBtn.disabled = false;
        zoneSaveBtn.classList.remove('opacity-40', 'cursor-not-allowed');
    }
    /**
     * _clearDrawPreview
     * 기존 미리보기 도형 + drawer 정리.
     * (모양 변경, 다시 그리기 등에서 호출)
     */
    function _clearDrawPreview() {
        // 미리보기 도형 제거
        if (zoneCreateCtx.drawData && zoneCreateCtx.drawData.preview) {
            try { map.removeLayer(zoneCreateCtx.drawData.preview); } catch (e) { /* ignore */ }
        }
        zoneCreateCtx.drawData = null;

        // drawer 정리
        if (zoneCreateCtx.drawer) {
            try { zoneCreateCtx.drawer.disable(); } catch (e) { /* ignore */ }
            zoneCreateCtx.drawer = null;
        }

        // P2-4: 진행 이벤트 청취 해제 (다시 그리기·취소 시 잔존 이벤트 방지)
        try {
            map.off('draw:drawvertex', _onPolygonVertex);
            map.off('draw:drawstart',  _onCircleDrawStart);
            map.off('mousedown',       _onCircleCenterDown);
            map.off('mousemove',       _onCircleDrawing);
        } catch (e) { /* ignore */ }
        zoneCreateCtx._circleCenter = null;

        // P2-5a: 팝오버 닫기
        closeZoneCreatePopover();

        // UI 초기화
        const zoneInfo     = document.getElementById('zone-info');
        const zoneResetBtn = document.getElementById('zone-reset-btn');
        const zoneSaveBtn  = document.getElementById('zone-save-btn-floating');

        zoneInfo?.classList.add('hidden');
        zoneResetBtn?.classList.add('hidden');
        if (zoneSaveBtn) {
            zoneSaveBtn.disabled = true;
            zoneSaveBtn.classList.add('opacity-40', 'cursor-not-allowed');
        }
    }
    /**
     * _handleZoneSave
     * [저장] 버튼 클릭 처리.
     *
     * 동작:
     *   1. payload 구성 (백엔드 API 형식)
     *   2. console.log 로 데이터 확인 (Stub 검증)
     *   3. fetch POST /facilities/api/geofences/
     *   4. 성공 시 — 생성 모드 종료 + 페이지 갱신 (또는 geofence.js 가 WebSocket 으로 자동 반영)
     *   5. 실패 시 — 에러 메시지 표시 (콘솔)
     *
     * payload 형식 (geofence.js 의 _showGeofenceForm 참조):
     *   - circle:  { name, severity, floor, geofence_type:'circle', center_x, center_y, radius, is_active }
     *   - polygon: { name, severity, floor, geofence_type:'polygon', polygon_data, center_x, center_y, is_active }
     */
    function _handleZoneSave() {
        if (!zoneCreateCtx.drawData) {
            console.warn('[admin_map_editor] 저장 시도 — 그린 데이터 없음');
            return;
        }
        if (!zoneCreateCtx.severity) {
            console.warn('[admin_map_editor] 저장 시도 — 위험도 미선택');
            return;
        }

        // 구역명 — 없으면 자동 생성
        const zoneNameInput = document.getElementById('zone-name-input');
        const name = (zoneNameInput?.value || '').trim() || '새 위험구역';

        // floor — currentFloorId 사용
        const floorId =
            (typeof currentFloorId   !== 'undefined' && currentFloorId)   ||
            (typeof MAP_AUTO_FLOOR_ID !== 'undefined' && MAP_AUTO_FLOOR_ID);

        const d = zoneCreateCtx.drawData;

        // payload 구성
        const payload = {
            name,
            severity:      zoneCreateCtx.severity,
            floor:         floorId,
            geofence_type: d.geofence_type,
            center_x:      d.center_x,
            center_y:      d.center_y,
            is_active:     true,
        };

        if (d.geofence_type === 'circle') {
            payload.radius = d.radius;
        } else if (d.geofence_type === 'polygon') {
            payload.polygon_data = d.polygon_data;
        }

        // Stub 검증 — 데이터 형태 콘솔 출력
        console.info('[admin_map_editor] 위험구역 저장 payload:', payload);

        // P2-3 (R4-F-1): 저장 재확인
        Modal.confirm({
            title: '저장하시겠습니까?',
            onConfirm: () => _postGeofence(payload),
            // onCancel — 팝업만 닫고 생성 화면 유지
        });
    }

    /**
     * _postGeofence
     * POST /facilities/api/geofences/ 호출.
     */
    function _postGeofence(payload) {
        const csrf = _getCsrfToken();
        const url = `${API_BASE}/geofences/`;

        console.info(`[admin_map_editor] POST ${url}`);

        fetch(url, {
            method:  'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken':  csrf,
            },
            body: JSON.stringify(payload),
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.info('[admin_map_editor] 위험구역 저장 성공:', data);

            // P2-3 (R4-F-3): 완료 팝업 → [확인] → 진입 화면 reload (Q1 결정)
            // reload 가 모든 상태를 초기화하므로 exitZoneCreateMode 별도 호출 불필요
            Modal.info({
                title:   '저장되었습니다.',
                onClose: () => window.location.reload(),
            });
        })
        .catch(err => {
            console.error('[admin_map_editor] 위험구역 저장 실패:', err);
            // P2-3: 실패 시도 공용 모달로 통일 (alert 제거)
            Modal.info({
                title:   '위험구역 저장 실패',
                message: err.message || '서버와 통신 중 오류가 발생했습니다.',
            });
        });
    }

    /**
     * _safeSetTooltipContent
     * L.Tooltip.setContent 안전망.
     * leaflet 의 standalone tooltip(L.tooltip().addTo(map))은 _source 가 null 인 상태인데,
     * setContent 호출 시 일부 경로(특히 interactive:true)에서 _source null 참조로
     * 'Cannot set properties of null (setting _source)' 발생 가능.
     * - 1차: setContent 시도
     * - 실패 시: _contentNode.innerHTML 직접 갱신 (DOM fallback). 위치는 setLatLng 별도 호출.
     */
    function _safeSetTooltipContent(tooltip, html) {
        if (!tooltip) return false;
        try {
            tooltip.setContent(html);
            return true;
        } catch (e) {
            console.warn('[admin_map_editor] tooltip.setContent 실패 — DOM fallback', e);
            try {
                if (tooltip._contentNode) {
                    tooltip._contentNode.innerHTML = html;
                    return true;
                }
            } catch (e2) {
                console.error('[admin_map_editor] tooltip DOM fallback 실패', e2);
            }
            return false;
        }
    }

    /**
     * _safeSetTooltipLatLng
     * setLatLng 도 동일 안전망. _setPosition 직접 호출 fallback.
     */
    function _safeSetTooltipLatLng(tooltip, latlng) {
        if (!tooltip || !latlng) return false;
        try {
            tooltip.setLatLng(latlng);
            return true;
        } catch (e) {
            console.warn('[admin_map_editor] tooltip.setLatLng 실패', e);
            return false;
        }
    }

    /**
     * _getCsrfToken
     * Django CSRF 토큰 추출 (cookie 에서).
     */
    function _getCsrfToken() {
        const name = 'csrftoken';
        const cookies = document.cookie.split(';');
        for (const c of cookies) {
            const [k, v] = c.trim().split('=');
            if (k === name) return decodeURIComponent(v);
        }
        return '';
    }

    /**
     * clearMarkerHighlight
     * 현재 강조된 마커가 있으면 강조 해제
     */
    function clearMarkerHighlight() {
        if (window._highlightTimer) {
            clearTimeout(window._highlightTimer);
            window._highlightTimer = null;
        }

        const last = window._lastHighlightedMarker;
        if (!last) return;
        const { marker, type } = last;

        if (type === 'zone') {
            // Geofence — 원래 스타일 복원 (잠금 적용)
            try {
                const id = Object.entries(geofenceState).find(([_, s]) => s.shape === marker)?.[0];
                if (id) {
                    const g = _geofenceCache[id];
                    if (g) {
                        if (g.name && g.name.startsWith('[자동]')) {
                            _lockAutoShape(marker, g);
                        } else {
                            _restoreManualShape(marker, g);
                        }
                    }
                }
            } catch (e) { /* ignore */ }
        } else {
            // divIcon — outline 제거
            const el = marker.getElement && marker.getElement();
            if (el) {
                const card = el.querySelector('[data-obj-type]');
                if (card) {
                    card.style.outline = '';
                    card.style.outlineOffset = '';
                    card.style.boxShadow = '';
                    card.style.zIndex = '';
                }
            }
        }

        window._lastHighlightedMarker = null;
    }

    // 디버깅 노출
    window._mapEditor.resolveMarkerByPanelCode = resolveMarkerByPanelCode;
    window._mapEditor.focusMarker              = focusMarker;

    /**
     * _addPanelHover
     * 좌측 패널 호버 시 지도 마커에 .panel-hover 클래스 추가.
     * 클릭 강조와 다른 색상으로 시각적 구분 (CSS: 주황색).
     */
    function _addPanelHover(resolved) {
        if (!resolved) return;
        const { marker, type } = resolved;

        if (type === 'zone') {
            // Geofence — setStyle 로 옅은 강조 (호버용)
            if (marker && marker.setStyle) {
                try {
                    marker.setStyle({ weight: 4, color: '#f59e0b' });
                } catch (e) { /* ignore */ }
            }
        } else {
            // divIcon — DOM 의 카드에 .panel-hover 클래스
            if (!marker) return;
            const el = marker.getElement && marker.getElement();
            if (!el) return;
            const card = el.querySelector('[data-obj-type]');
            if (card) {
                card.classList.add('panel-hover');
            }
        }
    }

    /**
     * _removePanelHover
     * 좌측 패널 호버 해제 시 강조 제거.
     * 단, 클릭으로 인한 강조 (3초 outline) 가 진행 중이면 그것은 유지.
     */
    function _removePanelHover(resolved) {
        if (!resolved) return;
        const { marker, type } = resolved;

        if (type === 'zone') {
            // Geofence — 원래 스타일 (잠금 상태) 복원
            // 클릭 강조 중이 아니면 자동/수동 잠금 재적용
            if (window._lastHighlightedMarker && window._lastHighlightedMarker.marker === marker) {
                return;  // 클릭 강조 중 — 유지
            }
            try {
                const id = Object.entries(geofenceState).find(([_, s]) => s.shape === marker)?.[0];
                if (id) {
                    const g = _geofenceCache[id];
                    if (g) {
                        if (g.name && g.name.startsWith('[자동]')) {
                            _lockAutoShape(marker, g);
                        } else {
                            _restoreManualShape(marker, g);
                        }
                    }
                }
            } catch (e) { /* ignore */ }
        } else {
            // divIcon — .panel-hover 클래스 제거
            if (!marker) return;
            const el = marker.getElement && marker.getElement();
            if (!el) return;
            const card = el.querySelector('[data-obj-type]');
            if (card) {
                card.classList.remove('panel-hover');
            }
        }
    }


    /**
     * formatCode
     * 객체의 코드를 일관된 형식으로 반환.
     * API serializer 가 코드 필드를 누락한 경우 폴백 적용.
     *
     * - equipment_code 있으면 그대로 (예: 'EQ-001')
     * - device_code 있으면 그대로
     * - node_code 있으면 그대로
     * - 없으면 형식화 (예: 'GAS-001', 'PWR-001', 'LOC-001')
     */
    function formatCode(obj, type) {
        if (type === 'facility') {
            return obj.equipment_code || `EQ-${String(obj.id).padStart(3, '0')}`;
        }
        if (type === 'gas') {
            return obj.device_code || `GAS-${String(obj.device_id || obj.id).padStart(3, '0')}`;
        }
        if (type === 'power') {
            return obj.device_code || `PWR-${String(obj.device_id || obj.id).padStart(3, '0')}`;
        }
        if (type === 'node') {
            return obj.node_code || `LOC-${String(obj.id).padStart(3, '0')}`;
        }
        return String(obj.id);
    }

    // ─── divIcon 빌더 디버깅 노출 ────────────────────────────────────
    //
    // 콘솔에서 테스트:
    //   window._mapEditor.buildEquipmentIcon(eq, 'view')
    window._mapEditor.buildEquipmentIcon = buildEquipmentIcon;
    window._mapEditor.buildGasIcon       = buildGasIcon;
    window._mapEditor.buildPowerIcon     = buildPowerIcon;
    window._mapEditor.buildNodeIcon      = buildNodeIcon;

    // ─── 후처리 훅 ────────────────────────────────────────────────

    /**
     * applyPendingFocus
     * map_event.js 의 loadFloorData() 가 moveend 콜백 마지막에서 호출.
     * 우리 페이지에서는 이 시점이 Leaflet 렌더링 완료 시점이므로
     * API 호출 + 마커 렌더링 + 자동 위험구역 잠금 등을 실행.
     *
     * monitoring.js 도 같은 훅을 사용하지만, 우리 페이지에서는
     * monitoring.js 가 로드되지 않으므로 우리 정의가 유효.
     */
    window.applyPendingFocus = function() {
        // currentFloorId 는 map_config.js 의 let 변수 (window 자동 부착 안 됨)
        // MAP_AUTO_FLOOR_ID 는 map.html 의 const 변수 (window 자동 부착 안 됨)
        // typeof 체크로 안전하게 접근
        const floorId =
            (typeof currentFloorId   !== 'undefined' && currentFloorId)   ||
            (typeof MAP_AUTO_FLOOR_ID !== 'undefined' && MAP_AUTO_FLOOR_ID);

        if (!floorId) {
            console.warn('[admin_map_editor] floor id 미설정 — API 호출 건너뜀');
            return;
        }

        // 단계 3-B: Equipment + Sensor + LocationNode 병렬 호출
        // Geofence 는 geofence.js 가 이미 처리 (별도 호출 불필요)
        // Worker 는 편집 화면에서 사용 안 함
        Promise.all([
            fetchEquipments(floorId),
            fetchSensors(floorId),
            fetchLocationNodes(floorId),
        ]).then(() => {
            console.info('[admin_map_editor] 모든 API 호출 완료. 캐시 상태:', {
                equipment:    dataCache.equipment.length,
                sensor:       dataCache.sensor.length,
                locationNode: dataCache.locationNode.length,
            });

            // 단계 3-E: 마커 렌더링
            renderAllMarkers();

            // 단계 3-F: 좌측 패널 ↔ 지도 연동
            setupPanelMarkerLinking();

            // 단계 3-G.1: 상단 캔버스 필터 탭 활성화
            setupCanvasFilterTabs();

            // 단계 3-V: 줌 컨트롤 + 편집 버튼 활성화
            setupZoomControls();
            setupEditModeButton();
             // 단계 3-W: 위험구역 추가 흐름
            setupZoneCreateButton();

            // P6-CDE: 우하단 [전체 되돌리기]/[저장] 핸들러 등록
            setupEditActionsButtons();

            // 단계 3-C: 자동 위험구역 잠금 (geofenceState 직접 순회)
            // P1-4b: 호버 팝오버 덮어쓰기도 같은 타이밍에 적용 (geofenceState 준비 완료 시점)
            setTimeout(() => {
                setupAutoGeofenceLock();
                overrideGeofenceHoverPopover();
            }, 500);
        });
    };
})();