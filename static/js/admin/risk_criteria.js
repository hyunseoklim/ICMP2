// 위험 기준 관리 페이지
function showModal(id) {
  const m = document.getElementById(id);
  m.classList.remove('hidden'); m.classList.add('flex');
}
function hideModal(id) {
  const m = document.getElementById(id);
  m.classList.add('hidden'); m.classList.remove('flex');
}

function showConfirm(msg, onOk, onCancel) {
  document.getElementById('confirmMsg').textContent = msg;
  const okBtn     = document.getElementById('confirmOkBtn');
  const cancelBtn = document.getElementById('confirmCancelBtn');
  okBtn.onclick     = () => { hideModal('confirmModal'); if (onOk) onOk(); };
  cancelBtn.onclick = () => { hideModal('confirmModal'); if (onCancel) onCancel(); };
  showModal('confirmModal');
}

function showDone(msg) {
  document.getElementById('doneMsg').textContent = msg;
  showModal('doneModal');
}

/* ── 사용 여부 토글 ── */
const _ACTIVE_ON  = 'px-6 py-1.5 text-sm rounded font-medium bg-blue-600 text-white';
const _ACTIVE_OFF = 'px-6 py-1.5 text-sm rounded text-slate-600 hover:bg-white';

function setCActive(isActive) {
  document.getElementById('c_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('c_btn_active').className   = isActive ? _ACTIVE_ON : _ACTIVE_OFF;
  document.getElementById('c_btn_inactive').className = isActive ? _ACTIVE_OFF : _ACTIVE_ON;
  _setErr('c_active_err', '');
}

function setEActive(isActive) {
  document.getElementById('e_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('e_btn_active').className   = isActive ? _ACTIVE_ON : _ACTIVE_OFF;
  document.getElementById('e_btn_inactive').className = isActive ? _ACTIVE_OFF : _ACTIVE_ON;
  _checkDirty();
}

/* ── 에러 표시 ── */
function _setErr(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
  else      { el.textContent = ''; el.classList.add('hidden'); }
}

function _clearCreateErrs() {
  ['c_code_err','c_name_err','c_color_err','c_emphasis_err','c_priority_err','c_active_err'].forEach(id => _setErr(id, ''));
}
function _clearEditErrs() {
  ['e_code_err','e_name_err','e_priority_err'].forEach(id => _setErr(id, ''));
}

/* ── 우선순위 값 파싱 ── */
function _parsePriority(val) {
  const s = val.trim();
  if (!s) return { empty: true };
  if (!/^\d+$/.test(s)) return { notNum: true };
  const n = parseInt(s, 10);
  if (n < 1) return { tooSmall: true };
  return { value: n };
}

/* ── 등록 검증 ── */
function _validateCreate() {
  _clearCreateErrs();
  let ok = true;

  const code   = document.getElementById('c_stage_code').value.trim();
  const name   = document.getElementById('c_stage_name').value.trim();
  const color  = document.getElementById('c_color_type').value;
  const emph   = document.getElementById('c_alert_emphasis').value;
  const prio   = document.getElementById('c_priority').value;
  const active = document.getElementById('c_is_active').value;

  if (!code) {
    _setErr('c_code_err', '단계 코드를 입력해 주세요.'); ok = false;
  } else if (!/^[A-Z0-9_]+$/.test(code)) {
    _setErr('c_code_err', '단계 코드는 영문 대문자, 숫자, _만 입력할 수 있습니다.'); ok = false;
  }

  if (!name) { _setErr('c_name_err', '단계명을 입력해 주세요.'); ok = false; }

  if (!color) { _setErr('c_color_err', '표시 색상을 선택해 주세요.'); ok = false; }

  if (!emph) { _setErr('c_emphasis_err', '알림 강조를 선택해 주세요.'); ok = false; }

  const pr = _parsePriority(prio);
  if (pr.empty)    { _setErr('c_priority_err', '이벤트 우선순위를 입력해 주세요.'); ok = false; }
  else if (pr.notNum)  { _setErr('c_priority_err', '이벤트 우선순위는 숫자만 입력할 수 있습니다.'); ok = false; }
  else if (pr.tooSmall){ _setErr('c_priority_err', '이벤트 우선순위는 1 이상의 값으로 입력해 주세요.'); ok = false; }

  if (!active) { _setErr('c_active_err', '사용 여부를 선택해 주세요.'); ok = false; }

  return ok;
}

/* ── 수정 검증 ── */
function _validateEdit() {
  _clearEditErrs();
  let ok = true;

  const code = document.getElementById('e_stage_code').value.trim();
  const name = document.getElementById('e_stage_name').value.trim();
  const prio = document.getElementById('e_priority').value;

  if (!code) {
    _setErr('e_code_err', '단계 코드를 입력해 주세요.'); ok = false;
  } else if (!/^[A-Z0-9_]+$/.test(code)) {
    _setErr('e_code_err', '단계 코드는 영문 대문자, 숫자, _만 입력할 수 있습니다.'); ok = false;
  }

  if (!name) { _setErr('e_name_err', '단계명을 입력해 주세요.'); ok = false; }

  const pr = _parsePriority(prio);
  if (pr.empty)    { _setErr('e_priority_err', '이벤트 우선순위를 입력해 주세요.'); ok = false; }
  else if (pr.notNum)  { _setErr('e_priority_err', '이벤트 우선순위는 숫자만 입력할 수 있습니다.'); ok = false; }
  else if (pr.tooSmall){ _setErr('e_priority_err', '이벤트 우선순위는 1 이상의 값으로 입력해 주세요.'); ok = false; }

  return ok;
}

/* ── 등록 ── */
function openCreateModal() {
  document.getElementById('c_stage_code').value       = '';
  document.getElementById('c_stage_name').value       = '';
  document.getElementById('c_color_type').value       = '';
  document.getElementById('c_alert_emphasis').value   = '';
  document.getElementById('c_priority').value         = '';
  document.getElementById('c_description').value      = '';
  document.getElementById('c_desc_count').textContent = '0';
  document.getElementById('c_is_active').value        = '';
  document.getElementById('c_btn_active').className   = _ACTIVE_OFF;
  document.getElementById('c_btn_inactive').className = _ACTIVE_OFF;
  _clearCreateErrs();
  showModal('createModal');
}

function closeCreateModal() { hideModal('createModal'); }

function submitCreate() {
  if (!_validateCreate()) return;
  hideModal('createModal');
  showConfirm('위험 기준을 등록하시겠습니까?', _doCreate, () => showModal('createModal'));
}

function _doCreate() {
  const body = new FormData();
  body.append('csrfmiddlewaretoken', CSRF_TOKEN);
  body.append('stage_code',     document.getElementById('c_stage_code').value.trim());
  body.append('stage_name',     document.getElementById('c_stage_name').value.trim());
  body.append('color_type',     document.getElementById('c_color_type').value);
  body.append('alert_emphasis', document.getElementById('c_alert_emphasis').value);
  body.append('priority',       document.getElementById('c_priority').value.trim());
  body.append('is_active',      document.getElementById('c_is_active').value);
  body.append('description',    document.getElementById('c_description').value.trim());

  fetch('/manager/risk-criteria/create/', { method: 'POST', body })
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(res => {
      if (res.ok) {
        showDone('위험 기준이 등록되었습니다.');
      } else {
        showModal('createModal');
        const fieldMap = { code: 'c_code_err', name: 'c_name_err', color: 'c_color_err', priority: 'c_priority_err' };
        if (res.field && fieldMap[res.field]) _setErr(fieldMap[res.field], res.error);
        else alert(res.error || '등록에 실패했습니다.');
      }
    })
    .catch(err => { showModal('createModal'); alert('오류가 발생했습니다: ' + err); });
}

/* ── 수정 ── */
let _original = {};

function openEditModal(pk) {
  fetch(`/manager/risk-criteria/${pk}/edit/`)
    .then(r => r.json())
    .then(data => {
      document.getElementById('e_pk').value             = data.id;
      document.getElementById('e_stage_code').value     = data.stage_code;
      document.getElementById('e_stage_name').value     = data.stage_name;
      document.getElementById('e_color_type').value     = data.color_type;
      document.getElementById('e_alert_emphasis').value = data.alert_emphasis || '정상';
      document.getElementById('e_priority').value       = data.priority;
      document.getElementById('e_description').value    = data.description || '';
      document.getElementById('e_desc_count').textContent = (data.description || '').length;
      setEActive(data.is_active);
      _clearEditErrs();
      _original = {
        stage_code:     data.stage_code,
        stage_name:     data.stage_name,
        color_type:     data.color_type,
        alert_emphasis: data.alert_emphasis || '정상',
        priority:       String(data.priority),
        is_active:      String(data.is_active),
        description:    data.description || '',
      };
      _setEditBtnState(false);
      showModal('editModal');
    });
}

function _setEditBtnState(dirty) {
  const btn = document.getElementById('editSubmitBtn');
  if (dirty) {
    btn.disabled = false;
    btn.className = 'px-7 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700';
    btn.style.cursor = 'pointer';
  } else {
    btn.disabled = true;
    btn.className = 'px-7 py-2.5 bg-slate-300 text-white text-sm font-medium rounded-md cursor-not-allowed';
    btn.style.cursor = '';
  }
}

function _checkDirty() {
  const cur = {
    stage_code:     document.getElementById('e_stage_code').value.trim(),
    stage_name:     document.getElementById('e_stage_name').value.trim(),
    color_type:     document.getElementById('e_color_type').value,
    alert_emphasis: document.getElementById('e_alert_emphasis').value,
    priority:       document.getElementById('e_priority').value.trim(),
    is_active:      document.getElementById('e_is_active').value,
    description:    document.getElementById('e_description').value.trim(),
  };
  const dirty = Object.keys(_original).some(k => cur[k] !== _original[k]);
  _setEditBtnState(dirty);
}

function closeEditModal() { hideModal('editModal'); }

function submitEdit() {
  if (!_validateEdit()) return;
  hideModal('editModal');
  showConfirm('위험 기준을 수정하시겠습니까?', _doEdit, () => showModal('editModal'));
}

function _doEdit() {
  const pk   = document.getElementById('e_pk').value;
  const body = new FormData();
  body.append('csrfmiddlewaretoken', CSRF_TOKEN);
  body.append('stage_code',     document.getElementById('e_stage_code').value.trim());
  body.append('stage_name',     document.getElementById('e_stage_name').value.trim());
  body.append('color_type',     document.getElementById('e_color_type').value);
  body.append('alert_emphasis', document.getElementById('e_alert_emphasis').value);
  body.append('priority',       document.getElementById('e_priority').value.trim());
  body.append('is_active',      document.getElementById('e_is_active').value);
  body.append('description',    document.getElementById('e_description').value.trim());

  fetch(`/manager/risk-criteria/${pk}/edit/`, { method: 'POST', body })
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(res => {
      if (res.ok) {
        showDone('위험 기준이 수정되었습니다.');
      } else {
        showModal('editModal');
        const fieldMap = { code: 'e_code_err', name: 'e_name_err', priority: 'e_priority_err' };
        if (res.field && fieldMap[res.field]) _setErr(fieldMap[res.field], res.error);
        else alert(res.error || '수정에 실패했습니다.');
      }
    })
    .catch(err => { showModal('editModal'); alert('오류가 발생했습니다: ' + err); });
}

/* ── 삭제 ── */
function confirmDelete() {
  const checks = document.querySelectorAll('.row-check:checked');
  if (checks.length === 0) return;
  showConfirm(`선택한 ${checks.length}건을 삭제하시겠습니까?`, () => {
    document.getElementById('deleteForm').submit();
  });
}

function updateDeleteBtn() {
  const checks  = document.querySelectorAll('.row-check:checked');
  const countEl = document.getElementById('selectedCount');
  const delBtn  = document.getElementById('deleteBtn');
  if (!delBtn) return;

  if (checks.length > 0) {
    countEl.textContent = `${checks.length}건 선택`;
    delBtn.disabled = false;
    delBtn.classList.remove('text-slate-400', 'bg-slate-50', 'border-slate-100', 'cursor-not-allowed');
    delBtn.classList.add('text-rose-600', 'bg-red-50', 'border-red-100', 'hover:bg-red-100', 'cursor-pointer');

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
    delBtn.classList.add('text-slate-400', 'bg-slate-50', 'border-slate-100', 'cursor-not-allowed');
    delBtn.classList.remove('text-rose-600', 'bg-red-50', 'border-red-100', 'hover:bg-red-100', 'cursor-pointer');
  }
}

/* ── 정렬 ── */
function getCellValue(row, colIdx) {
  const cells = row.querySelectorAll('td');
  return cells[colIdx] ? cells[colIdx].textContent.trim() : '';
}

function sortTable(value) {
  const tbody = document.getElementById('criteria-tbody');
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll('tr[onclick]'));
  if (rows.length === 0) return;

  rows.sort((a, b) => {
    let va, vb;
    switch (value) {
      case 'priority_desc':
        va = parseInt(getCellValue(a, 6)) || 99;
        vb = parseInt(getCellValue(b, 6)) || 99;
        return va - vb;
      case 'priority_low':
        va = parseInt(getCellValue(a, 6)) || 99;
        vb = parseInt(getCellValue(b, 6)) || 99;
        return vb - va;
      case 'name_asc':
        return getCellValue(a, 1).localeCompare(getCellValue(b, 1), 'ko');
      case 'priority_asc':
      case 'code_asc':
        return getCellValue(a, 2).localeCompare(getCellValue(b, 2));
      case 'code_desc':
        return getCellValue(b, 2).localeCompare(getCellValue(a, 2));
      case 'updated_new':
        return getCellValue(b, 5).localeCompare(getCellValue(a, 5));
      case 'updated_old':
        return getCellValue(a, 5).localeCompare(getCellValue(b, 5));
      case 'active_first':
        va = getCellValue(a, 3).includes('사용') ? 0 : 1;
        vb = getCellValue(b, 3).includes('사용') ? 0 : 1;
        return va - vb;
      case 'inactive_first':
        va = getCellValue(a, 3).includes('미사용') ? 0 : 1;
        vb = getCellValue(b, 3).includes('미사용') ? 0 : 1;
        return va - vb;
      default:
        return 0;
    }
  });

  rows.forEach(row => tbody.appendChild(row));
}

document.addEventListener('DOMContentLoaded', () => {
  function updateRowHighlight(cb) {
    const row = cb.closest('tr');
    if (!row) return;
    if (cb.checked) { row.classList.add('row-selected'); }
    else { row.classList.remove('row-selected'); }
  }
  document.querySelectorAll('.row-check').forEach(cb => cb.addEventListener('change', () => { updateRowHighlight(cb); updateDeleteBtn(); }));

  /* 설명 글자수 */
  document.getElementById('c_description')?.addEventListener('input', function() {
    document.getElementById('c_desc_count').textContent = this.value.length;
  });
  document.getElementById('e_description')?.addEventListener('input', function() {
    document.getElementById('e_desc_count').textContent = this.value.length;
    _checkDirty();
  });

  /* dirty 감지 */
  ['e_stage_code','e_stage_name','e_color_type','e_alert_emphasis','e_priority'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', _checkDirty);
    document.getElementById(id)?.addEventListener('change', _checkDirty);
  });

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
        o.classList.remove('bg-blue-50', 'text-slate-900');
        o.classList.add('text-slate-700', 'pl-8');
        const ic = o.querySelector('i[data-lucide="check"]');
        if (ic) ic.style.display = 'none';
      });
      opt.classList.add('bg-blue-50', 'text-slate-900');
      opt.classList.remove('text-slate-700', 'pl-8');
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
    if (e.key === 'Escape') ['createModal', 'editModal', 'confirmModal', 'doneModal'].forEach(hideModal);
  });
});
