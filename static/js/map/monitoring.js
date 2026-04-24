
  // ─── 셀렉트박스 연동 ───
  document.getElementById('sel-facility').addEventListener('change', function () {
    const fid = this.value;
    const bSel = document.getElementById('sel-building');
    bSel.innerHTML = '<option value="">건물 선택</option>';
    document.getElementById('sel-floor').innerHTML = '<option value="">층 선택</option>';
    if (!fid) return;
    fetch(`${API_BASE}/buildings/?facility_id=${fid}`)
      .then(r => r.json())
      .then(data => {
        data.forEach(b => {
          const opt = document.createElement('option');
          opt.value = b.id; opt.textContent = b.building_name;
          bSel.appendChild(opt);
        });
      });
  });

  document.getElementById('sel-building').addEventListener('change', function () {
    const bid = this.value;
    const fSel = document.getElementById('sel-floor');
    fSel.innerHTML = '<option value="">층 선택</option>';
    if (!bid) return;
    fetch(`${API_BASE}/floors/?building_id=${bid}`)
      .then(r => r.json())
      .then(data => {
        data.forEach(f => {
          const opt = document.createElement('option');
          opt.value = f.id; opt.textContent = f.floor_name;
          fSel.appendChild(opt);
        });
      });
  });

  document.getElementById('sel-floor').addEventListener('change', function () {
    const fid = this.value;
    if (!fid) return;
    loadFloorData(fid);
  });

  // ─── 탭 필터 ───
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      applyTabFilter(this.dataset.filter);
    });
  });
