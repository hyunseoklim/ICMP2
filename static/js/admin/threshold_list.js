// 임계치 기준 관리 페이지

function getCsrf() {
  return document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('csrftoken='))?.split('=')[1] || '';
}
function showModal(id) { const m = document.getElementById(id); m.classList.remove('hidden'); m.classList.add('flex'); }
function hideModal(id) { const m = document.getElementById(id); m.classList.add('hidden'); m.classList.remove('flex'); }

// ── confirm / done ──────────────────────────────────────────────
function showConfirm(msg, onOk, onCancel) {
  document.getElementById('confirmMsg').textContent = msg;
  const okBtn     = document.getElementById('confirmOkBtn');
  const cancelBtn = document.getElementById('confirmCancelBtn');
  okBtn.onclick = () => {
    hideModal('confirmModal');
    if (onOk) onOk();
  };
  cancelBtn.onclick = () => {
    hideModal('confirmModal');
    if (onCancel) onCancel();
  };
  showModal('confirmModal');
}
function showDone(msg, callback) {
  document.getElementById('doneMsg').textContent = msg;
  const btn = document.getElementById('doneOkBtn');
  btn.onclick = () => { hideModal('doneModal'); if (callback) callback(); };
  showModal('doneModal');
}

// ── 정렬 ──────────────────────────────────────────────────────
function applySort(val) {
  const url = new URL(location.href);
  url.searchParams.set('sort', val);
  location.href = url.toString();
}

// ── 삭제 버튼 ─────────────────────────────────────────────────
function updateDeleteBtn() {
  const checks  = document.querySelectorAll('.row-check:checked');
  const countEl = document.getElementById('selectedCount');
  const delBtn  = document.getElementById('deleteBtn');
  if (!delBtn) return;
  if (checks.length > 0) {
    countEl.textContent = `${checks.length}건 선택`;
    delBtn.disabled = false;
    delBtn.className = 'ml-2 px-3.5 py-1.5 text-sm text-red-600 bg-red-50 border border-red-100 rounded-md hover:bg-red-100 cursor-pointer whitespace-nowrap';
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
    delBtn.className = 'ml-2 px-3.5 py-1.5 text-sm text-slate-400 bg-slate-50 border border-slate-100 rounded-md cursor-not-allowed whitespace-nowrap';
  }
}

function confirmDelete() {
  const checks = document.querySelectorAll('.row-check:checked');
  if (!checks.length) return;
  showConfirm(`${checks.length}건을 삭제하시겠습니까?`, _doDelete);
}
function _doDelete() {
  const form = document.getElementById('deleteForm');
  const data = new FormData(form);
  fetch(DELETE_URL, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body: data,
  }).then(r => r.json()).then(res => {
    if (res.ok) showDone('삭제되었습니다.', () => location.reload());
  });
}

// ── 공통: 스코프 토글 헬퍼 ────────────────────────────────────
const SCOPE_LABELS = { '실시간 관제': 'cc_scope_실시간관제', 'AI 예측': 'cc_scope_AI예측', '알림': 'cc_scope_알림' };
const ESCOPE_LABELS = { '실시간 관제': 'e_scope_실시간관제', 'AI 예측': 'e_scope_AI예측', '알림': 'e_scope_알림' };

function _updateScopeBtn(btnId, active) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.className = 'px-4 py-1.5 text-sm rounded-full border transition-colors ' +
    (active ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium' : 'border-slate-200 bg-white text-slate-600 hover:border-blue-400');
}

// ── 임계치 기준 등록 모달 ─────────────────────────────────────
let _ccScopes = new Set();

function openCreateModal() {
  document.getElementById('cc_category_name').value = typeof CATEGORY_NAME !== 'undefined' ? CATEGORY_NAME : '';
  document.getElementById('cc_metric').value  = '';
  document.getElementById('cc_unit').value    = '';
  document.getElementById('cc_warning').value = '';
  document.getElementById('cc_danger').value  = '';
  document.getElementById('cc_desc').value    = '';
  document.getElementById('cc_desc_count').textContent = '0/100자';
  document.getElementById('cc_condition').value = '';
  document.getElementById('cc_is_active').value = '';
  ['cc_metric_err','cc_unit_err','cc_cond_err','cc_warning_err','cc_danger_err','cc_active_err','cc_scope_err']
    .forEach(id => { const el = document.getElementById(id); if (el) el.classList.add('hidden'); });
  // condition 버튼 초기화
  ['cc_btn_gte','cc_btn_lte'].forEach(id => {
    document.getElementById(id).className = 'px-6 py-1.5 text-sm rounded text-slate-600 hover:bg-white';
  });
  // active 버튼 초기화
  ['cc_btn_active','cc_btn_inactive'].forEach(id => {
    document.getElementById(id).className = 'px-6 py-1.5 text-sm rounded text-slate-600 hover:bg-white';
  });
  // scope 초기화
  _ccScopes = new Set();
  Object.values(SCOPE_LABELS).forEach(id => _updateScopeBtn(id, false));
  document.getElementById('cc_scope_hidden').value = '';
  showModal('createModal');
}
function closeCreateModal() { hideModal('createModal'); }

function setCCCondition(val) {
  document.getElementById('cc_condition').value = val;
  document.getElementById('cc_btn_gte').className = 'px-6 py-1.5 text-sm rounded ' + (val === '이상' ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('cc_btn_lte').className = 'px-6 py-1.5 text-sm rounded ' + (val === '이하' ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
}
function setCCActive(isActive) {
  document.getElementById('cc_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('cc_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('cc_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
}
function toggleCCScope(val) {
  if (_ccScopes.has(val)) _ccScopes.delete(val); else _ccScopes.add(val);
  _updateScopeBtn(SCOPE_LABELS[val], _ccScopes.has(val));
  document.getElementById('cc_scope_hidden').value = [..._ccScopes].join(',');
}

function _setErr(id, msg) {
  const el = document.getElementById(id);
  if (!el) return false;
  el.textContent = msg;
  el.classList.toggle('hidden', !msg);
  return !!msg;
}

function _crossValidate(cond, warning, danger, warnErrId, dangErrId) {
  // 이상: 주의 < 위험  /  이하: 주의 > 위험
  let hasErr = false;
  if (warning !== '' && danger !== '' && !isNaN(parseFloat(warning)) && !isNaN(parseFloat(danger))) {
    const w = parseFloat(warning), d = parseFloat(danger);
    if (cond === '이하') {
      if (w <= d) hasErr |= _setErr(warnErrId, '주의값은 위험값보다 큰 값으로 입력해 주세요. (이하 조건)');
      if (d >= w) hasErr |= _setErr(dangErrId, '위험값은 주의값보다 작은 값으로 입력해 주세요. (이하 조건)');
    } else {
      if (w >= d) hasErr |= _setErr(warnErrId, '주의값은 위험값보다 작은 값으로 입력해 주세요.');
      if (d <= w) hasErr |= _setErr(dangErrId, '위험값은 주의값보다 큰 값으로 입력해 주세요.');
    }
  }
  return hasErr;
}

function _validateCreate() {
  const metric  = document.getElementById('cc_metric').value.trim().toLowerCase();
  const unit    = document.getElementById('cc_unit').value.trim();
  const cond    = document.getElementById('cc_condition').value;
  const warning = document.getElementById('cc_warning').value.trim();
  const danger  = document.getElementById('cc_danger').value.trim();
  const active  = document.getElementById('cc_is_active').value;
  const scope   = document.getElementById('cc_scope_hidden').value;
  let hasErr = false;

  hasErr |= _setErr('cc_metric_err', !metric ? '측정 항목을 입력해 주세요.' : '');
  hasErr |= _setErr('cc_unit_err',   !unit   ? '단위를 입력해 주세요.'     : '');
  hasErr |= _setErr('cc_cond_err',   !cond   ? '판단 조건을 선택해 주세요.' : '');

  if (!warning) {
    hasErr |= _setErr('cc_warning_err', '주의값을 입력해 주세요.');
  } else if (isNaN(parseFloat(warning))) {
    hasErr |= _setErr('cc_warning_err', '주의값은 숫자만 입력할 수 있습니다.');
  } else { _setErr('cc_warning_err', ''); }

  if (!danger) {
    hasErr |= _setErr('cc_danger_err', '위험값을 입력해 주세요.');
  } else if (isNaN(parseFloat(danger))) {
    hasErr |= _setErr('cc_danger_err', '위험값은 숫자만 입력할 수 있습니다.');
  } else { _setErr('cc_danger_err', ''); }

  if (warning && danger && !isNaN(parseFloat(warning)) && !isNaN(parseFloat(danger))) {
    hasErr |= _crossValidate(cond, warning, danger, 'cc_warning_err', 'cc_danger_err');
  }

  hasErr |= _setErr('cc_active_err', !active ? '사용 여부를 선택해 주세요.' : '');
  hasErr |= _setErr('cc_scope_err',  !scope  ? '반영 범위를 하나 이상 선택해 주세요.' : '');

  return !hasErr;
}

function submitCreate() {
  if (!_validateCreate()) return;
  hideModal('createModal');
  showConfirm('해당 코드를 등록하시겠습니까?', _doCreate, () => showModal('createModal'));
}

function _doCreate() {
  const data = new FormData();
  data.append('category',    SELECTED_CATEGORY);
  data.append('metric_code', document.getElementById('cc_metric').value.trim().toLowerCase());
  data.append('unit',        document.getElementById('cc_unit').value.trim());
  data.append('condition',   document.getElementById('cc_condition').value);
  data.append('warning_val', document.getElementById('cc_warning').value.trim());
  data.append('danger_val',  document.getElementById('cc_danger').value.trim());
  data.append('is_active',   document.getElementById('cc_is_active').value);
  data.append('scope',       document.getElementById('cc_scope_hidden').value);
  data.append('description', document.getElementById('cc_desc').value.trim());

  fetch(CREATE_URL, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body: data,
  })
  .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .then(res => {
    if (res.ok) {
      showDone('등록되었습니다.', () => location.reload());
    } else {
      showModal('createModal');
      if (res.field === 'metric_code') {
        _setErr('cc_metric_err', res.error || '동일한 기준 분류에 같은 측정 항목이 이미 등록되어 있습니다.');
      } else {
        alert(res.error || '등록에 실패했습니다.');
      }
    }
  })
  .catch(err => {
    showModal('createModal');
    console.error('등록 오류:', err);
    alert('서버 오류가 발생했습니다. 다시 시도해 주세요.');
  });
}

// ── 임계치 기준 수정 모달 ─────────────────────────────────────
let _editPk = null;
let _editOriginal = {};
let _eScopes = new Set();

function openEditModal(pk) {
  _editPk = pk;
  fetch(`/manager/thresholds/${pk}/edit/`)
    .then(r => r.json())
    .then(data => {
      document.getElementById('e_category_name').value = CATEGORY_NAME;
      document.getElementById('e_item').value       = data.metric_code.toUpperCase();
      document.getElementById('e_unit').value       = data.unit || '';
      document.getElementById('e_warning').value    = data.warning_val ?? '';
      document.getElementById('e_danger').value     = data.danger_val  ?? '';
      document.getElementById('e_desc').value       = data.description || '';
      document.getElementById('e_desc_count').textContent = `${(data.description || '').length}/100자`;
      setECondition(data.condition || '이상');
      setEActive(data.is_active);
      // scope
      _eScopes = new Set((data.scope || '').split(',').map(s => s.trim()).filter(Boolean));
      Object.entries(ESCOPE_LABELS).forEach(([val, id]) => _updateScopeBtn(id, _eScopes.has(val)));
      document.getElementById('e_scope_hidden').value = [..._eScopes].join(',');

      _editOriginal = {
        unit:    data.unit || '',
        cond:    data.condition || '이상',
        warning: String(data.warning_val ?? ''),
        danger:  String(data.danger_val  ?? ''),
        active:  data.is_active,
        scope:   data.scope || '',
        desc:    data.description || '',
      };
      _checkEditDirty();
      showModal('editModal');
    });
}
function closeEditModal() { hideModal('editModal'); }

function setECondition(val) {
  document.getElementById('e_condition').value = val;
  document.getElementById('e_btn_gte').className = 'px-6 py-1.5 text-sm rounded ' + (val === '이상' ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('e_btn_lte').className = 'px-6 py-1.5 text-sm rounded ' + (val === '이하' ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  _checkEditDirty();
}
function setEActive(isActive) {
  document.getElementById('e_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('e_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('e_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
  _checkEditDirty();
}
function toggleEScope(val) {
  if (_eScopes.has(val)) _eScopes.delete(val); else _eScopes.add(val);
  _updateScopeBtn(ESCOPE_LABELS[val], _eScopes.has(val));
  document.getElementById('e_scope_hidden').value = [..._eScopes].join(',');
  _checkEditDirty();
}

function _checkEditDirty() {
  const cur = {
    unit:    document.getElementById('e_unit').value.trim(),
    cond:    document.getElementById('e_condition').value,
    warning: document.getElementById('e_warning').value,
    danger:  document.getElementById('e_danger').value,
    active:  document.getElementById('e_is_active').value === 'true',
    scope:   document.getElementById('e_scope_hidden').value,
    desc:    document.getElementById('e_desc').value.trim(),
  };
  const dirty = cur.unit    !== _editOriginal.unit    ||
                cur.cond    !== _editOriginal.cond    ||
                cur.warning !== _editOriginal.warning ||
                cur.danger  !== _editOriginal.danger  ||
                cur.active  !== _editOriginal.active  ||
                cur.scope   !== _editOriginal.scope   ||
                cur.desc    !== _editOriginal.desc;
  const btn = document.getElementById('editSubmitBtn');
  btn.disabled = !dirty;
  btn.className = 'px-7 py-2.5 text-sm font-medium rounded-md ' +
    (dirty ? 'bg-blue-600 text-white hover:bg-blue-700 cursor-pointer' : 'bg-slate-300 text-white cursor-not-allowed');
}

function _validateEdit() {
  const unit    = document.getElementById('e_unit').value.trim();
  const warning = document.getElementById('e_warning').value.trim();
  const danger  = document.getElementById('e_danger').value.trim();
  const cond    = document.getElementById('e_condition').value;
  const active  = document.getElementById('e_is_active').value;
  const scope   = document.getElementById('e_scope_hidden').value;
  let hasErr = false;

  hasErr |= _setErr('e_unit_err', !unit ? '단위를 입력해 주세요.' : '');
  hasErr |= _setErr('e_cond_err', !cond ? '판단 조건을 선택해 주세요.' : '');

  if (!warning) {
    hasErr |= _setErr('e_warning_err', '주의값을 입력해 주세요.');
  } else if (isNaN(parseFloat(warning))) {
    hasErr |= _setErr('e_warning_err', '주의값은 숫자만 입력할 수 있습니다.');
  } else { _setErr('e_warning_err', ''); }

  if (!danger) {
    hasErr |= _setErr('e_danger_err', '위험값을 입력해 주세요.');
  } else if (isNaN(parseFloat(danger))) {
    hasErr |= _setErr('e_danger_err', '위험값은 숫자만 입력할 수 있습니다.');
  } else { _setErr('e_danger_err', ''); }

  if (warning && danger && !isNaN(parseFloat(warning)) && !isNaN(parseFloat(danger))) {
    hasErr |= _crossValidate(cond, warning, danger, 'e_warning_err', 'e_danger_err');
  }

  hasErr |= _setErr('e_active_err', !active ? '사용 여부를 선택해 주세요.' : '');
  hasErr |= _setErr('e_scope_err',  !scope  ? '반영 범위를 하나 이상 선택해 주세요.' : '');

  return !hasErr;
}

function submitEdit() {
  if (!_validateEdit()) return;
  hideModal('editModal');
  showConfirm('해당 코드를 수정하시겠습니까?', _doEdit, () => showModal('editModal'));
}

function _doEdit() {
  const data = new FormData();
  data.append('unit',        document.getElementById('e_unit').value.trim());
  data.append('condition',   document.getElementById('e_condition').value);
  data.append('warning_val', document.getElementById('e_warning').value.trim());
  data.append('danger_val',  document.getElementById('e_danger').value.trim());
  data.append('is_active',   document.getElementById('e_is_active').value);
  data.append('scope',       document.getElementById('e_scope_hidden').value);
  data.append('description', document.getElementById('e_desc').value.trim());

  fetch(`/manager/thresholds/${_editPk}/edit/`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body: data,
  })
  .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .then(res => {
    if (res.ok) {
      showDone('수정되었습니다.', () => location.reload());
    } else {
      showModal('editModal');
      alert(res.error || '수정에 실패했습니다.');
    }
  })
  .catch(err => {
    showModal('editModal');
    console.error('수정 오류:', err);
    alert('서버 오류가 발생했습니다. 다시 시도해 주세요.');
  });
}

// ── 기준 분류 등록 모달 ───────────────────────────────────────
let _gcScopes = new Set();
const GC_SCOPE_IDS = { '실시간 관제': 'gc_scope_실시간관제', 'AI 예측': 'gc_scope_AI예측', '알림': 'gc_scope_알림' };

function openGroupCreateModal() {
  document.getElementById('gc_code').value = '';
  document.getElementById('gc_name').value = '';
  document.getElementById('gc_desc').value = '';
  document.getElementById('gc_desc_count').textContent = '0/100자';
  document.getElementById('gc_is_active').value = '';
  // 자동 고정 필드
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const nowStr = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  document.getElementById('gc_updated_at').value = nowStr;
  document.getElementById('gc_updated_by').value = typeof CURRENT_USER_NAME !== 'undefined' ? CURRENT_USER_NAME : '-';
  document.getElementById('gc_code_count').value = '0건';
  ['gc_code_err','gc_name_err','gc_scope_err','gc_active_err'].forEach(id => {
    const el = document.getElementById(id); if (el) el.classList.add('hidden');
  });
  ['gc_btn_active','gc_btn_inactive'].forEach(id => {
    document.getElementById(id).className = 'px-6 py-1.5 text-sm rounded text-slate-600 hover:bg-white';
  });
  _gcScopes = new Set();
  Object.values(GC_SCOPE_IDS).forEach(id => _updateScopeBtn(id, false));
  document.getElementById('gc_scope_hidden').value = '';
  showModal('groupCreateModal');
}
function closeGroupCreateModal() { hideModal('groupCreateModal'); }

function toggleGCScope(val) {
  if (_gcScopes.has(val)) _gcScopes.delete(val); else _gcScopes.add(val);
  _updateScopeBtn(GC_SCOPE_IDS[val], _gcScopes.has(val));
  document.getElementById('gc_scope_hidden').value = [..._gcScopes].join(',');
}
function setGCActive(isActive) {
  document.getElementById('gc_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('gc_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('gc_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
}
function submitGroupCreate() {
  const code   = document.getElementById('gc_code').value.trim().toUpperCase();
  const name   = document.getElementById('gc_name').value.trim();
  const scope  = document.getElementById('gc_scope_hidden').value;
  const active = document.getElementById('gc_is_active').value;
  let hasErr = false;
  hasErr |= _setErr('gc_code_err',  !code   ? '분류코드는 필수입니다.' : '');
  hasErr |= _setErr('gc_name_err',  !name   ? '분류명은 필수입니다.'   : '');
  if (!scope)  { document.getElementById('gc_scope_err').classList.remove('hidden');  hasErr = true; }
  else           document.getElementById('gc_scope_err').classList.add('hidden');
  if (!active) { document.getElementById('gc_active_err').classList.remove('hidden'); hasErr = true; }
  else           document.getElementById('gc_active_err').classList.add('hidden');
  if (hasErr) return;
  hideModal('groupCreateModal');
  showConfirm('해당 그룹을 등록하시겠습니까?', _doGroupCreate, () => showModal('groupCreateModal'));
}

function _doGroupCreate() {
  const code   = document.getElementById('gc_code').value.trim().toUpperCase();
  const name   = document.getElementById('gc_name').value.trim();
  const scope  = document.getElementById('gc_scope_hidden').value;
  const active = document.getElementById('gc_is_active').value;
  const data = new FormData();
  data.append('code', code); data.append('code_name', name);
  data.append('scope', scope); data.append('is_active', active);
  data.append('description', document.getElementById('gc_desc').value.trim());
  fetch(GROUP_CREATE_URL, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body: data,
  }).then(r => r.json()).then(res => {
    if (res.ok) { showDone('등록되었습니다.', () => location.reload()); }
    else if (res.field === 'code') { showModal('groupCreateModal'); _setErr('gc_code_err', res.error); }
  });
}

// ── 기준 분류 수정 모달 ───────────────────────────────────────
let _geCatCode = null;
let _geOriginal = {};
let _geScopes = new Set();
const GE_SCOPE_IDS = { '실시간 관제': 'ge_scope_실시간관제', 'AI 예측': 'ge_scope_AI예측', '알림': 'ge_scope_알림' };

function openGroupEditModal(catCode) {
  _geCatCode = catCode;
  fetch(`/manager/thresholds/group/${catCode}/edit/`, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  }).then(r => r.json()).then(data => {
    document.getElementById('ge_code').value       = data.code;
    document.getElementById('ge_name').value       = data.code_name;
    document.getElementById('ge_updated_at').value = data.updated_at;
    document.getElementById('ge_updated_by').value = data.updated_by;
    document.getElementById('ge_type_count').value = data.type_count + '건';
    document.getElementById('ge_desc').value       = data.description || '';
    document.getElementById('ge_desc_count').textContent = `${(data.description || '').length}/100자`;
    setGEActive(data.is_active);
    _geScopes = new Set((data.scope || '').split(',').map(s => s.trim()).filter(Boolean));
    Object.entries(GE_SCOPE_IDS).forEach(([val, id]) => _updateScopeBtn(id, _geScopes.has(val)));
    document.getElementById('ge_scope_hidden').value = [..._geScopes].join(',');
    _geOriginal = { code: data.code, name: data.code_name, scope: data.scope || '', active: data.is_active, desc: data.description || '' };
    _checkGEDirty();
    showModal('groupEditModal');
  });
}
function closeGroupEditModal() { hideModal('groupEditModal'); }

function toggleGEScope(val) {
  if (_geScopes.has(val)) _geScopes.delete(val); else _geScopes.add(val);
  _updateScopeBtn(GE_SCOPE_IDS[val], _geScopes.has(val));
  document.getElementById('ge_scope_hidden').value = [..._geScopes].join(',');
  _checkGEDirty();
}
function setGEActive(isActive) {
  document.getElementById('ge_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('ge_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('ge_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
  _checkGEDirty();
}
function _checkGEDirty() {
  const cur = {
    code:   document.getElementById('ge_code').value.trim().toUpperCase(),
    name:   document.getElementById('ge_name').value.trim(),
    scope:  document.getElementById('ge_scope_hidden').value,
    active: document.getElementById('ge_is_active').value === 'true',
    desc:   document.getElementById('ge_desc').value.trim(),
  };
  const dirty = cur.code !== _geOriginal.code || cur.name !== _geOriginal.name ||
                cur.scope !== _geOriginal.scope || cur.active !== _geOriginal.active ||
                cur.desc !== _geOriginal.desc;
  const btn = document.getElementById('geSubmitBtn');
  btn.disabled = !dirty;
  btn.className = 'px-7 py-2.5 text-sm font-medium rounded-md ' +
    (dirty ? 'bg-blue-600 text-white hover:bg-blue-700 cursor-pointer' : 'bg-slate-300 text-white cursor-not-allowed');
}
function submitGroupEdit() {
  const code  = document.getElementById('ge_code').value.trim().toUpperCase();
  const name  = document.getElementById('ge_name').value.trim();
  const scope = document.getElementById('ge_scope_hidden').value;
  const active = document.getElementById('ge_is_active').value;
  let hasErr = false;
  hasErr |= _setErr('ge_code_err', !code ? '분류 코드는 필수입니다.' : '');
  hasErr |= _setErr('ge_name_err', !name ? '분류명은 필수입니다.' : '');
  if (!scope)  { document.getElementById('ge_scope_err').classList.remove('hidden');  hasErr = true; }
  else           document.getElementById('ge_scope_err').classList.add('hidden');
  if (!active) { document.getElementById('ge_active_err').classList.remove('hidden'); hasErr = true; }
  else           document.getElementById('ge_active_err').classList.add('hidden');
  if (hasErr) return;

  hideModal('groupEditModal');
  showConfirm('해당 그룹을 수정하시겠습니까?', _doGroupEdit, () => showModal('groupEditModal'));
}

function _doGroupEdit() {
  const data = new FormData();
  data.append('code',        document.getElementById('ge_code').value.trim().toUpperCase());
  data.append('code_name',   document.getElementById('ge_name').value.trim());
  data.append('scope',       document.getElementById('ge_scope_hidden').value);
  data.append('is_active',   document.getElementById('ge_is_active').value);
  data.append('description', document.getElementById('ge_desc').value.trim());
  fetch(`/manager/thresholds/group/${_geCatCode}/edit/`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body: data,
  }).then(r => r.json()).then(res => {
    if (res.ok) { showDone('수정되었습니다.', () => location.reload()); }
    else if (res.error) { showModal('groupEditModal'); _setErr('ge_code_err', res.error); }
  });
}

// ── DOMContentLoaded ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  function updateRowHighlight(cb) {
    const row = cb.closest('tr');
    if (!row) return;
    if (cb.checked) { row.classList.add('row-selected'); }
    else { row.classList.remove('row-selected'); }
  }
  document.querySelectorAll('.row-check').forEach(cb => cb.addEventListener('change', () => { updateRowHighlight(cb); updateDeleteBtn(); }));
  const checkAll = document.getElementById('checkAll');
  if (checkAll) {
    checkAll.addEventListener('change', e => {
      document.querySelectorAll('.row-check').forEach(cb => { cb.checked = e.target.checked; updateRowHighlight(cb); });
      updateDeleteBtn();
    });
  }

  // 글자수 카운터
  [['cc_desc','cc_desc_count'],['e_desc','e_desc_count'],['gc_desc','gc_desc_count'],['ge_desc','ge_desc_count']].forEach(([tid, cid]) => {
    const ta = document.getElementById(tid); const ct = document.getElementById(cid);
    if (ta && ct) ta.addEventListener('input', () => { ct.textContent = `${ta.value.length}/100자`; });
  });

  // 수정 모달 dirty tracking
  ['e_unit','e_warning','e_danger','e_desc'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', _checkEditDirty);
  });
  ['ge_code','ge_name','ge_desc'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', _checkGEDirty);
  });

  // ESC 닫기
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      ['createModal','editModal','groupCreateModal','groupEditModal','confirmModal','doneModal'].forEach(hideModal);
    }
  });
});
