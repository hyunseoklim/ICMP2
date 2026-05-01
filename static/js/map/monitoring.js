/**
 * monitoring.js  (map_monitoring.html 전용)
 * 셀렉트박스 연동 + 탭 필터
 *
 * [수정] 각 getElementById에 null 체크 추가
 *        → worker_list 등 해당 DOM이 없는 페이지에서 로드되어도 에러 없음
 *        (base.html이 전역으로 로드하는 js/monitoring.js 와 다른 파일임에 주의)
 */

document.addEventListener('DOMContentLoaded', () => {

    // ─── 셀렉트박스 연동 ───────────────────────────────────────
    // [수정] null 체크 — sel-facility가 없는 페이지에서는 전체 블록 skip

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

    // ─── 탭 필터 ───────────────────────────────────────────────
    document.querySelectorAll('.tab-btn-map').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.tab-btn-map').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            applyTabFilter(this.dataset.filter);
        });
    });
});
