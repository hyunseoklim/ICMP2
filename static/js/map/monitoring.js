/**
 * monitoring.js  (map_monitoring.html 전용)
 * 셀렉트박스 연동 + 탭 필터
 *
 * [수정] 각 getElementById에 null 체크 추가
 *        → worker_list 등 해당 DOM이 없는 페이지에서 로드되어도 에러 없음
 *        (base.html이 전역으로 로드하는 js/monitoring.js 와 다른 파일임에 주의)
 */

// ─── URL 파라미터 파싱 ─────────────────────────────────────────
const params       = new URLSearchParams(location.search);
const focusType    = params.get('type');
const focusId      = params.get('id');
const focusFloorId = params.get('floor_id');

// ─── 초기화 함수 ───────────────────────────────────────────────
function _initMonitoring() {

    // URL 파라미터로 층 자동 로드
    if (focusFloorId) {
        window._PENDING_FOCUS = { type: focusType, id: focusId };
        loadFloorData(focusFloorId);
    }

    // ─── 셀렉트박스 연동 ──────────────────────────────────────
    const selFacility = document.getElementById('sel-facility');
    const selBuilding = document.getElementById('sel-building');
    const selFloor    = document.getElementById('sel-floor');

    if (selFacility) {
        selFacility.addEventListener('change', function () {
            const fid = this.value;
            selBuilding.innerHTML = '<option value="">건물 선택</option>';
            selFloor.innerHTML    = '<option value="">층 선택</option>';
            if (!fid) return;

            fetch(`${API_BASE}/buildings/?facility_id=${fid}`)
                .then(r => r.json())
                .then(data => {
                    data.results.forEach(b => {
                        const opt = document.createElement('option');
                        opt.value = b.id;
                        opt.textContent = b.building_name;
                        selBuilding.appendChild(opt);
                    });
                });
        });
    }

    if (selBuilding) {
        selBuilding.addEventListener('change', function () {
            const bid = this.value;
            selFloor.innerHTML = '<option value="">층 선택</option>';
            if (!bid) return;

            fetch(`${API_BASE}/floors/?building_id=${bid}`)
                .then(r => r.json())
                .then(data => {
                    data.results.forEach(f => {
                        const opt = document.createElement('option');
                        opt.value = f.id;
                        opt.textContent = f.floor_name;
                        selFloor.appendChild(opt);
                    });
                });
        });
    }

    if (selFloor) {
        selFloor.addEventListener('change', function () {
            const fid = this.value;
            if (!fid) return;
            loadFloorData(fid);
        });
    }

    // ─── 탭 필터 ──────────────────────────────────────────────
    document.querySelectorAll('.tab-btn-map').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.tab-btn-map').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            applyTabFilter(this.dataset.filter);
        });
    });
}

// ─── 실행 시점 제어 ────────────────────────────────────────────
// DOMContentLoaded가 이미 지난 경우(readyState: complete) 즉시 실행
// 아직 로딩 중이면 이벤트 대기
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initMonitoring);
} else {
    _initMonitoring();
}

// ─── 포커스 처리 ──────────────────────────────────────────────
// map_event.js의 moveend 콜백 마지막에서 호출됨

window.applyPendingFocus = function() {
    const focus = window._PENDING_FOCUS;
    if (!focus || !focus.type || !focus.id) return;
    window._PENDING_FOCUS = null;

    const id   = String(focus.id);
    const type = focus.type;

    setTimeout(() => {
        if      (type === 'worker')    _focusWorker(id);
        else if (type === 'sensor')    _focusSensor(id);
        else if (type === 'equipment') _focusEquipment(id);
        else if (type === 'geofence')  _focusGeofence(id);
    }, 300);
};

function _focusSensor(id) {
    const marker = sensorMarkers[id];
    if (!marker) {
        if (!_focusSensor._retry) _focusSensor._retry = 0;
        if (_focusSensor._retry < 10) {
            _focusSensor._retry++;
            setTimeout(() => _focusSensor(id), 500);
        } else {
            _focusSensor._retry = 0;
            console.warn('[focus] sensor 마커 대기 초과:', id);
        }
        return;
    }
    _focusSensor._retry = 0;
    map.setView(marker.getLatLng(), 2, { animate: true });
    setTimeout(() => marker.fire('click'), 400);
}

function _focusEquipment(id) {
    const state = equipmentMarkers[id];
    if (!state) {
        if (!_focusEquipment._retry) _focusEquipment._retry = 0;
        if (_focusEquipment._retry < 10) {
            _focusEquipment._retry++;
            setTimeout(() => _focusEquipment(id), 500);
        } else {
            _focusEquipment._retry = 0;
            console.warn('[focus] equipment 마커 대기 초과:', id);
        }
        return;
    }
    _focusEquipment._retry = 0;
    map.setView(state.rect.getBounds().getCenter(), 2, { animate: true });
    setTimeout(() => state.rect.fire('click'), 400);
}

function _focusGeofence(id) {
    const state = geofenceState[id];
    if (!state) {
        if (!_focusGeofence._retry) _focusGeofence._retry = 0;
        if (_focusGeofence._retry < 10) {
            _focusGeofence._retry++;
            setTimeout(() => _focusGeofence(id), 500);
        } else {
            _focusGeofence._retry = 0;
            console.warn('[focus] geofence 마커 대기 초과:', id);
        }
        return;
    }
    _focusGeofence._retry = 0;
    const center = state.shape.getBounds
        ? state.shape.getBounds().getCenter()
        : state.shape.getLatLng();
    map.setView(center, 2, { animate: true });
    setTimeout(() => state.shape.fire('click'), 400);
}