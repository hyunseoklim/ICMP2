// 위험 유형 관리 페이지

/* ── 모달 open/close ── */
function showModal(id) {
  const m = document.getElementById(id);
  m.classList.remove('hidden'); m.classList.add('flex');
}
function closeModal(id) {
  const m = document.getElementById(id);
  m.classList.add('hidden'); m.classList.remove('flex');
}

/* ── CSRF ── */
function getCsrf() {
  return document.querySelector('[name=csrfmiddlewaretoken]').value;
}

/* ── 재확인 모달 ── */
function showConfirm(msg, onOk) {
  document.getElementById('confirmMsg').textContent = msg;
  showModal('confirmModal');
  const ok  = document.getElementById('confirmOk');
  const can = document.getElementById('confirmCancel');
  const cleanup = () => { ok.onclick = null; can.onclick = null; };
  ok.onclick  = () => { cleanup(); closeModal('confirmModal'); onOk(); };
  can.onclick = () => { cleanup(); closeModal('confirmModal'); };
}

/* ── 완료 모달 ── */
function showDone(msg, onOk) {
  document.getElementById('doneMsg').textContent = msg;
  showModal('doneModal');
  const btn = document.getElementById('doneOk');
  btn.onclick = () => { closeModal('doneModal'); if (onOk) onOk(); };
}

/* ════════ 위험 유형 등록 ════════ */
let _rcActiveSet = false;

function setRCActive(isActive) {
  _rcActiveSet = true;
  document.getElementById('rc_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('rc_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('rc_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
  document.getElementById('rc_active_err').classList.add('hidden');
}

function openRiskCreateModal() {
  document.getElementById('rc_code').value      = '';
  document.getElementById('rc_code_name').value = '';
  document.getElementById('rc_desc').value      = '';
  document.getElementById('rc_desc_count').textContent = '0/100자';
  document.getElementById('rc_map_reflect').value = '';
  document.getElementById('rc_is_active').value = '';
  _rcActiveSet = false;
  // 버튼 초기화 (비선택 상태)
  document.getElementById('rc_btn_active').className   = 'px-6 py-1.5 text-sm rounded text-slate-600 hover:bg-white';
  document.getElementById('rc_btn_inactive').className = 'px-6 py-1.5 text-sm rounded text-slate-600 hover:bg-white';
  ['rc_code_err','rc_name_err','rc_map_err','rc_active_err'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.add('hidden'); el.textContent = ''; }
  });
  showModal('riskCreateModal');
}

function validateRiskCreate() {
  const code     = document.getElementById('rc_code').value.trim();
  const codeName = document.getElementById('rc_code_name').value.trim();
  const mapVal   = document.getElementById('rc_map_reflect').value;
  const isActive = document.getElementById('rc_is_active').value;
  let ok = true;
  const setErr = (id, msg) => {
    const el = document.getElementById(id);
    el.textContent = msg; el.classList.toggle('hidden', !msg);
    if (msg) ok = false;
  };

  if (!code) {
    setErr('rc_code_err', '사용할 코드를 입력해 주세요.');
  } else if (/\s/.test(code)) {
    setErr('rc_code_err', '코드는 공백 없이 입력해 주세요.');
  } else if (!/^[A-Z0-9_]+$/.test(code)) {
    setErr('rc_code_err', '코드는 영문 대문자, 숫자, 밑줄(_)만 사용할 수 있습니다.');
  } else {
    setErr('rc_code_err', '');
  }

  if (!codeName) {
    setErr('rc_name_err', '유형명을 입력해 주세요.');
  } else if (!codeName.replace(/\s/g, '')) {
    setErr('rc_name_err', '유형명은 공백만 입력할 수 없습니다.');
  } else {
    setErr('rc_name_err', '');
  }

  setErr('rc_map_err',    mapVal   === '' ? '지도 반영 여부를 선택해 주세요.' : '');
  setErr('rc_active_err', !_rcActiveSet   ? '사용 상태를 선택해 주세요.'    : '');

  return ok;
}

function submitRiskCreate() {
  if (!validateRiskCreate()) return;
  showConfirm('해당 코드를 등록하시겠습니까?', _doRiskCreate);
}

function _doRiskCreate() {
  const body = new FormData(document.getElementById('riskCreateForm'));
  fetch('/manager/risks/create/', {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        closeModal('riskCreateModal');
        showDone('등록되었습니다.', () => location.reload());
      } else if (res.field === 'code') {
        const el = document.getElementById('rc_code_err');
        el.textContent = res.error; el.classList.remove('hidden');
      } else if (res.field === 'code_name') {
        const el = document.getElementById('rc_name_err');
        el.textContent = res.error; el.classList.remove('hidden');
      } else {
        alert(res.error || '등록에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ════════ 위험 유형 수정 ════════ */
let _reOriginal = {};
let _reActiveSet = false;

function setREActive(isActive) {
  _reActiveSet = true;
  document.getElementById('re_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('re_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('re_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
  document.getElementById('re_active_err').classList.add('hidden');
  markREDirty();
}

function openRiskEditModal(pk) {
  fetch(`/manager/risks/${pk}/edit/`, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
    .then(r => r.json())
    .then(data => {
      document.getElementById('re_pk').value           = data.pk;
      document.getElementById('re_group_display').value = data.group_code;
      document.getElementById('re_code').value          = data.code;
      document.getElementById('re_code_name').value     = data.code_name;
      document.getElementById('re_desc').value          = data.description || '';
      document.getElementById('re_desc_count').textContent = `${(data.description || '').length}/100자`;
      document.getElementById('re_map_reflect').value   = data.map_reflect ? 'true' : 'false';
      setREActive(data.is_active);
      _reActiveSet = true;

      _reOriginal = {
        code_name:   data.code_name,
        description: data.description || '',
        map_reflect: data.map_reflect ? 'true' : 'false',
        is_active:   data.is_active ? 'true' : 'false',
      };

      ['re_name_err','re_map_err','re_active_err'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.classList.add('hidden'); el.textContent = ''; }
      });
      _setREBtnState(false);
      showModal('riskEditModal');
    });
}

function markREDirty() {
  if (!Object.keys(_reOriginal).length) return;
  const cur = {
    code_name:   document.getElementById('re_code_name').value,
    description: document.getElementById('re_desc').value,
    map_reflect: document.getElementById('re_map_reflect').value,
    is_active:   document.getElementById('re_is_active').value,
  };
  const dirty = Object.keys(_reOriginal).some(k => _reOriginal[k] !== cur[k]);
  _setREBtnState(dirty);
}

function _setREBtnState(enabled) {
  const btn = document.getElementById('re_submit_btn');
  if (enabled) {
    btn.disabled = false;
    btn.className = 'px-7 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700';
  } else {
    btn.disabled = true;
    btn.className = 'px-7 py-2.5 bg-slate-300 text-slate-500 text-sm font-medium rounded-md cursor-not-allowed';
  }
}

function validateRiskEdit() {
  const codeName = document.getElementById('re_code_name').value.trim();
  const mapVal   = document.getElementById('re_map_reflect').value;
  let ok = true;
  const setErr = (id, msg) => {
    const el = document.getElementById(id);
    el.textContent = msg; el.classList.toggle('hidden', !msg);
    if (msg) ok = false;
  };
  if (!codeName) {
    setErr('re_name_err', '유형명을 입력해 주세요.');
  } else if (!codeName.replace(/\s/g, '')) {
    setErr('re_name_err', '유형명은 공백만 입력할 수 없습니다.');
  } else {
    setErr('re_name_err', '');
  }
  setErr('re_map_err', mapVal === '' ? '지도 반영 여부를 선택해 주세요.' : '');
  return ok;
}

function submitRiskEdit() {
  if (!validateRiskEdit()) return;
  showConfirm('해당 코드를 수정하시겠습니까?', _doRiskEdit);
}

function _doRiskEdit() {
  const pk   = document.getElementById('re_pk').value;
  const body = new FormData();
  body.append('code_name',   document.getElementById('re_code_name').value.trim());
  body.append('description', document.getElementById('re_desc').value.trim());
  body.append('map_reflect', document.getElementById('re_map_reflect').value);
  body.append('is_active',   document.getElementById('re_is_active').value);
  fetch(`/manager/risks/${pk}/edit/`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        closeModal('riskEditModal');
        showDone('수정되었습니다.', () => location.reload());
      } else if (res.field === 'code_name') {
        const el = document.getElementById('re_name_err');
        el.textContent = res.error; el.classList.remove('hidden');
      } else {
        alert(res.error || '수정에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ════════ 위험 분류 등록 ════════ */
const _gcScopes = new Set();
let _gcActiveSet = false;

function toggleGCScope(btn, val) {
  if (_gcScopes.has(val)) {
    _gcScopes.delete(val);
    btn.className = 'gc-scope-btn px-4 py-2 text-sm border border-slate-200 rounded-md text-slate-600 hover:bg-slate-50';
  } else {
    _gcScopes.add(val);
    btn.className = 'gc-scope-btn px-4 py-2 text-sm border border-blue-400 rounded-md bg-blue-50 text-blue-700 font-medium';
  }
  document.getElementById('gc_scope_hidden').value = Array.from(_gcScopes).join(',');
  document.getElementById('gc_scope_err').classList.add('hidden');
}

function setGCActive(isActive) {
  _gcActiveSet = true;
  document.getElementById('gc_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('gc_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('gc_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
  document.getElementById('gc_active_err').classList.add('hidden');
}

function openGroupCreateModal() {
  document.getElementById('gc_code').value  = '';
  document.getElementById('gc_name').value  = '';
  document.getElementById('gc_desc').value  = '';
  document.getElementById('gc_desc_count').textContent = '0/100자';
  document.getElementById('gc_scope_hidden').value = '';
  document.getElementById('gc_is_active').value = '';
  _gcScopes.clear();
  _gcActiveSet = false;
  // 스코프 버튼 초기화
  document.querySelectorAll('.gc-scope-btn').forEach(btn => {
    btn.className = 'gc-scope-btn px-4 py-2 text-sm border border-slate-200 rounded-md text-slate-600 hover:bg-slate-50';
  });
  // 사용여부 버튼 초기화
  document.getElementById('gc_btn_active').className   = 'px-6 py-1.5 text-sm rounded text-slate-600 hover:bg-white';
  document.getElementById('gc_btn_inactive').className = 'px-6 py-1.5 text-sm rounded text-slate-600 hover:bg-white';
  // 최근 수정일 자동
  const now = new Date();
  const pad = n => String(n).padStart(2,'0');
  document.getElementById('gc_updated_at').value =
    `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
  ['gc_code_err','gc_name_err','gc_scope_err','gc_active_err'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.add('hidden'); el.textContent = ''; }
  });
  showModal('groupCreateModal');
}

function validateGroupCreate() {
  const code   = document.getElementById('gc_code').value.trim();
  const name   = document.getElementById('gc_name').value.trim();
  const scopes = document.getElementById('gc_scope_hidden').value;
  let ok = true;
  const setErr = (id, msg) => {
    const el = document.getElementById(id);
    el.textContent = msg; el.classList.toggle('hidden', !msg);
    if (msg) ok = false;
  };
  setErr('gc_code_err',   !code   ? '분류 코드를 입력하세요.' : !/^[A-Z0-9_]+$/.test(code) ? '영문 대문자, 숫자, 밑줄(_)만 사용할 수 있습니다.' : '');
  setErr('gc_name_err',   !name   ? '분류명을 입력하세요.' : '');
  setErr('gc_scope_err',  !scopes ? '반영 범위를 하나 이상 선택하세요.' : '');
  setErr('gc_active_err', !_gcActiveSet ? '사용 여부를 선택하세요.' : '');
  return ok;
}

function submitGroupCreate() {
  if (!validateGroupCreate()) return;
  showConfirm('등록하시겠습니까?', _doGroupCreate);
}

function _doGroupCreate() {
  const body = new FormData(document.getElementById('groupCreateForm'));
  fetch('/manager/risks/group/create/', {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        closeModal('groupCreateModal');
        showDone('등록이 완료되었습니다.', () => {
          location.href = `/manager/risks/?group=${res.group_code}`;
        });
      } else {
        alert(res.error || '등록에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ════════ 위험 분류 수정 ════════ */
const _geScopes = new Set();
let _geOriginal = {};

function toggleGEScope(btn, val) {
  if (_geScopes.has(val)) {
    _geScopes.delete(val);
    btn.className = 'ge-scope-btn px-4 py-2 text-sm border border-slate-200 rounded-md text-slate-600 hover:bg-slate-50';
  } else {
    _geScopes.add(val);
    btn.className = 'ge-scope-btn px-4 py-2 text-sm border border-blue-400 rounded-md bg-blue-50 text-blue-700 font-medium';
  }
  document.getElementById('ge_scope_hidden').value = Array.from(_geScopes).join(',');
  document.getElementById('ge_scope_err').classList.add('hidden');
  markGEDirty();
}

function setGEActive(isActive) {
  document.getElementById('ge_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('ge_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('ge_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
  markGEDirty();
}

function openGroupEditModal(groupCode) {
  fetch(`/manager/risks/group/${groupCode}/edit/`, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
    .then(r => r.json())
    .then(data => {
      document.getElementById('ge_group_code').value    = data.group_code;
      document.getElementById('ge_code_display').value  = data.group_code;
      document.getElementById('ge_name').value           = data.group_name;
      document.getElementById('ge_updated_at').value    = data.updated_at || '-';
      document.getElementById('ge_updated_by').value    = data.updated_by || '-';
      document.getElementById('ge_type_count').value    = (data.type_count ?? 0) + '건';
      document.getElementById('ge_desc').value           = data.description || '';
      document.getElementById('ge_desc_count').textContent = `${(data.description || '').length}/100자`;

      // 스코프 복원
      _geScopes.clear();
      const savedScopes = data.scope ? data.scope.split(',').map(s => s.trim()).filter(Boolean) : [];
      document.querySelectorAll('.ge-scope-btn').forEach(btn => {
        const val = btn.textContent.trim();
        if (savedScopes.includes(val)) {
          _geScopes.add(val);
          btn.className = 'ge-scope-btn px-4 py-2 text-sm border border-blue-400 rounded-md bg-blue-50 text-blue-700 font-medium';
        } else {
          btn.className = 'ge-scope-btn px-4 py-2 text-sm border border-slate-200 rounded-md text-slate-600 hover:bg-slate-50';
        }
      });
      document.getElementById('ge_scope_hidden').value = Array.from(_geScopes).join(',');

      // 사용여부 복원
      setGEActive(data.is_active);

      _geOriginal = {
        group_name:  data.group_name,
        scope:       Array.from(_geScopes).sort().join(','),
        is_active:   data.is_active ? 'true' : 'false',
        description: data.description || '',
      };

      ['ge_name_err','ge_scope_err'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.classList.add('hidden'); el.textContent = ''; }
      });
      _setGEBtnState(false);
      showModal('groupEditModal');
    });
}

function markGEDirty() {
  if (!Object.keys(_geOriginal).length) return;
  const cur = {
    group_name:  document.getElementById('ge_name').value,
    scope:       Array.from(_geScopes).sort().join(','),
    is_active:   document.getElementById('ge_is_active').value,
    description: document.getElementById('ge_desc').value,
  };
  const dirty = Object.keys(_geOriginal).some(k => _geOriginal[k] !== cur[k]);
  _setGEBtnState(dirty);
}

function _setGEBtnState(enabled) {
  const btn = document.getElementById('ge_submit_btn');
  if (enabled) {
    btn.disabled = false;
    btn.className = 'px-7 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700';
  } else {
    btn.disabled = true;
    btn.className = 'px-7 py-2.5 bg-slate-300 text-slate-500 text-sm font-medium rounded-md cursor-not-allowed';
  }
}

function validateGroupEdit() {
  const name  = document.getElementById('ge_name').value.trim();
  const scope = document.getElementById('ge_scope_hidden').value;
  let ok = true;
  const setErr = (id, msg) => {
    const el = document.getElementById(id);
    el.textContent = msg; el.classList.toggle('hidden', !msg);
    if (msg) ok = false;
  };
  setErr('ge_name_err',  !name  ? '분류명을 입력하세요.' : '');
  setErr('ge_scope_err', !scope ? '반영 범위를 하나 이상 선택하세요.' : '');
  return ok;
}

function submitGroupEdit() {
  if (!validateGroupEdit()) return;
  showConfirm('해당 그룹을 수정하시겠습니까?', _doGroupEdit);
}

function _doGroupEdit() {
  const groupCode = document.getElementById('ge_group_code').value;
  const body = new FormData();
  body.append('group_name',  document.getElementById('ge_name').value.trim());
  body.append('scope',       document.getElementById('ge_scope_hidden').value);
  body.append('is_active',   document.getElementById('ge_is_active').value);
  body.append('description', document.getElementById('ge_desc').value.trim());
  fetch(`/manager/risks/group/${groupCode}/edit/`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        closeModal('groupEditModal');
        showDone('수정되었습니다.', () => location.reload());
      } else {
        alert(res.error || '수정에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ════════ 삭제 확인 ════════ */
function confirmDelete() {
  const checks = document.querySelectorAll('.row-check:checked');
  if (!checks.length) return;
  showConfirm(`${checks.length}건을 삭제하시겠습니까?`, _doDelete);
}

function _doDelete() {
  const form = document.getElementById('deleteForm');
  const data = new FormData(form);
  fetch(form.action, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body: data,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        showDone('삭제되었습니다.', () => location.reload());
      } else {
        alert('삭제에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ════════ 삭제 버튼 ════════ */
function updateDeleteBtn() {
  const checks  = document.querySelectorAll('.row-check:checked');
  const countEl = document.getElementById('selectedCount');
  const delBtn  = document.getElementById('deleteBtn');
  if (!delBtn) return;

  if (checks.length > 0) {
    countEl.textContent = `${checks.length}건 선택`;
    delBtn.disabled = false;
    delBtn.classList.remove('text-slate-400','bg-slate-50','border-slate-100','cursor-not-allowed');
    delBtn.classList.add('text-rose-600','bg-red-50','border-red-100','hover:bg-red-100','cursor-pointer');
    const form = document.getElementById('deleteForm');
    form.querySelectorAll('input[name="pks"]').forEach(el => el.remove());
    checks.forEach(cb => {
      const inp = document.createElement('input');
      inp.type = 'hidden'; inp.name = 'pks'; inp.value = cb.dataset.pk;
      form.appendChild(inp);
    });
  } else {
    countEl.textContent = '- 건 선택';
    delBtn.disabled = true;
    delBtn.classList.add('text-slate-400','bg-slate-50','border-slate-100','cursor-not-allowed');
    delBtn.classList.remove('text-rose-600','bg-red-50','border-red-100','hover:bg-red-100','cursor-pointer');
  }
}

/* ════════ 클라이언트 정렬 ════════ */
function getCellValue(row, colIdx) {
  const cells = row.querySelectorAll('td');
  return cells[colIdx] ? cells[colIdx].textContent.trim() : '';
}

function sortTable(value) {
  const tbody = document.getElementById('risk-tbody');
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll('tr[onclick]'));
  if (!rows.length) return;

  rows.sort((a, b) => {
    let va, vb;
    switch (value) {
      case 'code_asc':    return getCellValue(a,1).localeCompare(getCellValue(b,1));
      case 'code_desc':   return getCellValue(b,1).localeCompare(getCellValue(a,1));
      case 'name_asc':    return getCellValue(a,2).localeCompare(getCellValue(b,2),'ko');
      case 'name_desc':   return getCellValue(b,2).localeCompare(getCellValue(a,2),'ko');
      case 'map_reflect':
        va = getCellValue(a,3).includes('반영') && !getCellValue(a,3).includes('미반영') ? 0 : 1;
        vb = getCellValue(b,3).includes('반영') && !getCellValue(b,3).includes('미반영') ? 0 : 1;
        return va - vb;
      case 'active':
        va = getCellValue(a,4).includes('사용') && !getCellValue(a,4).includes('미사용') ? 0 : 1;
        vb = getCellValue(b,4).includes('사용') && !getCellValue(b,4).includes('미사용') ? 0 : 1;
        return va - vb;
      case 'updated_new': return getCellValue(b,5).localeCompare(getCellValue(a,5));
      case 'updated_old': return getCellValue(a,5).localeCompare(getCellValue(b,5));
      default: return 0;
    }
  });
  rows.forEach(r => tbody.appendChild(r));
}

/* ════════ DOMContentLoaded ════════ */
document.addEventListener('DOMContentLoaded', () => {
  function updateRowHighlight(cb) {
    const row = cb.closest('tr');
    if (!row) return;
    if (cb.checked) { row.classList.add('row-selected'); }
    else { row.classList.remove('row-selected'); }
  }
  document.querySelectorAll('.row-check').forEach(cb => cb.addEventListener('change', () => { updateRowHighlight(cb); updateDeleteBtn(); }));

  /* 수정 모달 dirty tracking */
  ['re_code_name','re_desc'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', markREDirty);
  });
  document.getElementById('re_map_reflect')?.addEventListener('change', markREDirty);

  /* 설명 카운터 */
  [['rc_desc','rc_desc_count'],['re_desc','re_desc_count'],['gc_desc','gc_desc_count'],['ge_desc','ge_desc_count']].forEach(([tid, cid]) => {
    const ta = document.getElementById(tid);
    const ct = document.getElementById(cid);
    if (ta && ct) ta.addEventListener('input', () => { ct.textContent = `${ta.value.length}/100자`; });
  });

  /* 분류 수정 dirty tracking */
  document.getElementById('ge_name')?.addEventListener('input', markGEDirty);
  document.getElementById('ge_desc')?.addEventListener('input', markGEDirty);

  /* 정렬 드롭다운 */
  const sortToggle  = document.getElementById('sort-toggle');
  const sortMenu    = document.getElementById('sort-menu');
  const sortChevron = document.getElementById('sort-chevron');

  sortToggle?.addEventListener('click', e => {
    e.stopPropagation();
    const open = !sortMenu.classList.contains('hidden');
    sortMenu.classList.toggle('hidden', open);
    if (sortChevron) sortChevron.style.transform = open ? '' : 'rotate(180deg)';
  });

  document.querySelectorAll('.sort-opt').forEach(opt => {
    opt.addEventListener('click', e => {
      e.stopPropagation();
      document.querySelectorAll('.sort-opt').forEach(o => {
        o.classList.remove('bg-blue-50','text-slate-900');
        o.classList.add('text-slate-700','pl-8');
        const ic = o.querySelector('i[data-lucide="check"]');
        if (ic) ic.style.display = 'none';
      });
      opt.classList.add('bg-blue-50','text-slate-900');
      opt.classList.remove('text-slate-700','pl-8');
      const ic = opt.querySelector('i[data-lucide="check"]');
      if (ic) ic.style.display = '';
      document.getElementById('sort-label').textContent = opt.dataset.label;
      sortTable(opt.dataset.value);
      sortMenu.classList.add('hidden');
      if (sortChevron) sortChevron.style.transform = '';
    });
  });

  document.addEventListener('click', () => {
    sortMenu?.classList.add('hidden');
    if (sortChevron) sortChevron.style.transform = '';
  });

  /* ESC 닫기 */
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      ['riskCreateModal','riskEditModal','groupCreateModal','groupEditModal','confirmModal','doneModal'].forEach(closeModal);
    }
  });
});
