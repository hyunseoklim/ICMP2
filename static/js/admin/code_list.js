// 공통 코드 관리 페이지

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

/* ═══════════ 사용 여부 토글 ═══════════ */
function setCCActive(isActive) {
  document.getElementById('cc_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('cc_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('cc_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
}

function setCEActive(isActive) {
  document.getElementById('ce_is_active').value = isActive ? 'true' : 'false';
  document.getElementById('ce_btn_active').className   = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'font-medium bg-blue-600 text-white' : 'text-slate-600 hover:bg-white');
  document.getElementById('ce_btn_inactive').className = 'px-6 py-1.5 text-sm rounded ' + (isActive ? 'text-slate-600 hover:bg-white' : 'font-medium bg-blue-600 text-white');
  markCEDirty();
}

/* ═══════════ 공통 코드 등록 ═══════════ */
function openCodeCreateModal() {
  document.getElementById('cc_code').value      = '';
  document.getElementById('cc_code_name').value = '';
  document.getElementById('cc_desc').value      = '';
  document.getElementById('cc_sort').value      = '0';
  setCCActive(true);
  ['cc_code_err','cc_name_err','cc_desc_err','cc_sort_err'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.add('hidden'); el.textContent = ''; }
  });
  showModal('codeCreateModal');
}

function validateCodeCreate() {
  const code     = document.getElementById('cc_code').value.trim();
  const codeName = document.getElementById('cc_code_name').value.trim();
  const desc     = document.getElementById('cc_desc').value.trim();
  const sort     = document.getElementById('cc_sort').value;
  let ok = true;
  const setErr = (id, msg) => {
    const el = document.getElementById(id);
    el.textContent = msg; el.classList.toggle('hidden', !msg);
    if (msg) ok = false;
  };
  setErr('cc_code_err',  !code     ? '코드를 입력하세요.'
                        : !/^[A-Z0-9_]+$/.test(code) ? '영문 대문자, 숫자, 언더바(_)만 허용됩니다.'
                        : code.length > 50 ? '최대 50자까지 입력 가능합니다.' : '');
  if (!codeName) {
    setErr('cc_name_err', '코드명을 입력해 주세요.');
  } else if (!codeName.replace(/\s/g, '')) {
    setErr('cc_name_err', '코드명은 공백만 입력할 수 없습니다.');
  } else {
    setErr('cc_name_err', '');
  }
  setErr('cc_desc_err',  !desc     ? '설명을 입력하세요.'
                        : desc.length > 100 ? '최대 100자까지 입력 가능합니다.' : '');
  setErr('cc_sort_err',  sort === '' ? '정렬 순서를 입력하세요.'
                        : isNaN(parseInt(sort)) || parseInt(sort) < 0 ? '0 이상의 정수를 입력하세요.' : '');
  return ok;
}

function submitCodeCreate() {
  if (!validateCodeCreate()) return;
  showConfirm('등록하시겠습니까?', _doCodeCreate);
}

function _doCodeCreate() {
  const form = document.getElementById('codeCreateForm');
  const data = new FormData(form);
  fetch('/manager/codes/value/create/', {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body: data,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        closeModal('codeCreateModal');
        showDone('등록이 완료되었습니다.', () => location.reload());
      } else if (res.field === 'code_name') {
        const el = document.getElementById('cc_name_err');
        el.textContent = res.error; el.classList.remove('hidden');
      } else {
        alert(res.error || '등록에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ═══════════ 공통 코드 수정 ═══════════ */
let _ceOriginal = {};

function openCodeEditModal(pk) {
  fetch(`/manager/codes/value/${pk}/edit/`, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
    .then(r => r.json())
    .then(data => {
      document.getElementById('ce_pk').value          = data.pk;
      document.getElementById('ce_group_name').value  = data.group_code;
      document.getElementById('ce_updated_by').value  = data.updated_by || '-';
      document.getElementById('ce_code').value        = data.code;
      document.getElementById('ce_code_name').value   = data.code_name;
      document.getElementById('ce_desc').value        = data.description || '';
      document.getElementById('ce_sort').value        = data.sort_order;
      const ceDescCount = document.getElementById('ce_desc_count');
      if (ceDescCount) ceDescCount.textContent = `${(data.description || '').length}/100자`;
      setCEActive(data.is_active);

      _ceOriginal = {
        code_name:   data.code_name,
        description: data.description || '',
        sort_order:  String(data.sort_order),
        is_active:   data.is_active ? 'true' : 'false',
      };

      ['ce_name_err','ce_desc_err','ce_sort_err'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.classList.add('hidden'); el.textContent = ''; }
      });
      _setEditBtnState(false);
      showModal('codeEditModal');
    });
}

function markCEDirty() {
  if (!Object.keys(_ceOriginal).length) return;
  const cur = {
    code_name:   document.getElementById('ce_code_name').value,
    description: document.getElementById('ce_desc').value,
    sort_order:  document.getElementById('ce_sort').value,
    is_active:   document.getElementById('ce_is_active').value,
  };
  const dirty = Object.keys(_ceOriginal).some(k => _ceOriginal[k] !== cur[k]);
  _setEditBtnState(dirty);
}

function _setEditBtnState(enabled) {
  const btn = document.getElementById('ce_submit_btn');
  if (enabled) {
    btn.disabled = false;
    btn.className = 'px-7 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700';
  } else {
    btn.disabled = true;
    btn.className = 'px-7 py-2.5 bg-slate-300 text-slate-500 text-sm font-medium rounded-md cursor-not-allowed';
  }
}

function validateCodeEdit() {
  const codeName = document.getElementById('ce_code_name').value.trim();
  const desc     = document.getElementById('ce_desc').value.trim();
  const sort     = document.getElementById('ce_sort').value;
  let ok = true;
  const setErr = (id, msg) => {
    const el = document.getElementById(id);
    el.textContent = msg; el.classList.toggle('hidden', !msg);
    if (msg) ok = false;
  };
  if (!codeName) {
    setErr('ce_name_err', '코드명을 입력해 주세요.');
  } else if (!codeName.replace(/\s/g, '')) {
    setErr('ce_name_err', '코드명은 공백만 입력할 수 없습니다.');
  } else {
    setErr('ce_name_err', '');
  }
  setErr('ce_desc_err', !desc ? '설명을 입력하세요.' : desc.length > 100 ? '최대 100자까지 입력 가능합니다.' : '');
  setErr('ce_sort_err', sort === '' ? '정렬 순서를 입력하세요.' : isNaN(parseInt(sort)) || parseInt(sort) < 0 ? '0 이상의 정수를 입력하세요.' : '');
  return ok;
}

function submitCodeEdit() {
  if (!validateCodeEdit()) return;
  showConfirm('수정하시겠습니까?', _doCodeEdit);
}

function _doCodeEdit() {
  const pk   = document.getElementById('ce_pk').value;
  const body = new FormData();
  body.append('code_name',   document.getElementById('ce_code_name').value.trim());
  body.append('description', document.getElementById('ce_desc').value.trim());
  body.append('sort_order',  document.getElementById('ce_sort').value);
  body.append('is_active',   document.getElementById('ce_is_active').value);
  fetch(`/manager/codes/value/${pk}/edit/`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        closeModal('codeEditModal');
        showDone('수정이 완료되었습니다.', () => location.reload());
      } else if (res.field === 'code_name') {
        const el = document.getElementById('ce_name_err');
        el.textContent = res.error; el.classList.remove('hidden');
      } else {
        alert(res.error || '수정에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ═══════════ 코드 그룹 등록 ═══════════ */
function openGroupCreateModal() {
  document.getElementById('gc_name').value  = '';
  document.getElementById('gc_code').value  = '';
  document.getElementById('gc_scope').value = '';
  document.getElementById('gc_desc').value  = '';
  ['gc_name_err','gc_code_err','gc_scope_err'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.add('hidden'); el.textContent = ''; }
  });
  const dtEl = document.getElementById('gc_now_datetime');
  if (dtEl) {
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    dtEl.value = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
  }
  showModal('groupCreateModal');
}

function validateGroupCreate() {
  const name  = document.getElementById('gc_name').value.trim();
  const code  = document.getElementById('gc_code').value.trim();
  const scope = document.getElementById('gc_scope').value.trim();
  let ok = true;
  const setErr = (id, msg) => {
    const el = document.getElementById(id);
    el.textContent = msg; el.classList.toggle('hidden', !msg);
    if (msg) ok = false;
  };
  setErr('gc_name_err',  !name  ? '그룹명을 입력하세요.' : name.length > 50 ? '최대 50자까지 입력 가능합니다.' : '');
  setErr('gc_code_err',  !code  ? '그룹 코드를 입력하세요.'
                        : !/^[A-Z0-9_]+$/.test(code) ? '영문 대문자, 숫자, 언더바(_)만 허용됩니다.'
                        : code.length > 50 ? '최대 50자까지 입력 가능합니다.' : '');
  setErr('gc_scope_err', !scope ? '관리 범위를 입력하세요.' : scope.length > 50 ? '최대 50자까지 입력 가능합니다.' : '');
  return ok;
}

function submitGroupCreate() {
  if (!validateGroupCreate()) return;
  showConfirm('등록하시겠습니까?', _doGroupCreate);
}

function _doGroupCreate() {
  const body = new FormData();
  body.append('group_name',  document.getElementById('gc_name').value.trim());
  body.append('group_code',  document.getElementById('gc_code').value.trim());
  body.append('scope',       document.getElementById('gc_scope').value.trim());
  body.append('description', document.getElementById('gc_desc').value.trim());
  fetch('/manager/codes/group/create/', {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        closeModal('groupCreateModal');
        showDone('등록이 완료되었습니다.', () => location.reload());
      } else {
        alert(res.error || '등록에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ═══════════ 코드 그룹 수정 ═══════════ */
let _geOriginal = {};

function openGroupEditModal(groupCode) {
  fetch(`/manager/codes/group/${groupCode}/edit/`, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
    .then(r => r.json())
    .then(data => {
      document.getElementById('ge_group_code').value   = data.group_code;
      document.getElementById('ge_name').value          = data.group_name;
      document.getElementById('ge_code_display').value  = data.group_code;
      document.getElementById('ge_scope').value         = data.scope || '';
      document.getElementById('ge_updated_at').value    = data.updated_at || '-';
      document.getElementById('ge_updated_by').value    = data.updated_by || '-';
      document.getElementById('ge_desc').value          = data.description || '';
      document.getElementById('ge_code_count').value    = (data.code_count ?? 0) + '건';
      const geDescCount = document.getElementById('ge_desc_count');
      if (geDescCount) geDescCount.textContent = `${(data.description || '').length}/100자`;

      _geOriginal = {
        group_name:  data.group_name,
        scope:       data.scope || '',
        description: data.description || '',
      };

      ['ge_name_err','ge_scope_err'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.classList.add('hidden'); el.textContent = ''; }
      });
      _setGroupEditBtnState(false);
      showModal('groupEditModal');
    });
}

function markGEDirty() {
  if (!Object.keys(_geOriginal).length) return;
  const cur = {
    group_name:  document.getElementById('ge_name').value,
    scope:       document.getElementById('ge_scope').value,
    description: document.getElementById('ge_desc').value,
  };
  const dirty = Object.keys(_geOriginal).some(k => _geOriginal[k] !== cur[k]);
  _setGroupEditBtnState(dirty);
}

function _setGroupEditBtnState(enabled) {
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
  const scope = document.getElementById('ge_scope').value.trim();
  let ok = true;
  const setErr = (id, msg) => {
    const el = document.getElementById(id);
    el.textContent = msg; el.classList.toggle('hidden', !msg);
    if (msg) ok = false;
  };
  setErr('ge_name_err',  !name  ? '그룹명을 입력하세요.' : name.length > 50 ? '최대 50자까지 입력 가능합니다.' : '');
  setErr('ge_scope_err', !scope ? '관리 범위를 입력하세요.' : scope.length > 50 ? '최대 50자까지 입력 가능합니다.' : '');
  return ok;
}

function submitGroupEdit() {
  if (!validateGroupEdit()) return;
  showConfirm('수정하시겠습니까?', _doGroupEdit);
}

function _doGroupEdit() {
  const groupCode = document.getElementById('ge_group_code').value;
  const body = new FormData();
  body.append('group_name',  document.getElementById('ge_name').value.trim());
  body.append('scope',       document.getElementById('ge_scope').value.trim());
  body.append('description', document.getElementById('ge_desc').value.trim());
  fetch(`/manager/codes/group/${groupCode}/edit/`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
    body,
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        closeModal('groupEditModal');
        showDone('수정이 완료되었습니다.', () => location.reload());
      } else {
        alert(res.error || '수정에 실패했습니다.');
      }
    })
    .catch(() => alert('서버 오류가 발생했습니다.'));
}

/* ═══════════ 삭제 확인 ═══════════ */
function confirmDelete() {
  const checks = document.querySelectorAll('.row-check:checked');
  if (!checks.length) return;
  const count = checks.length;
  showConfirm(`${count}건을 삭제하시겠습니까?`, _doDelete);
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

/* ═══════════ 삭제 버튼 ═══════════ */
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

/* ═══════════ 클라이언트 정렬 ═══════════ */
function getCellValue(row, colIdx) {
  const cells = row.querySelectorAll('td');
  return cells[colIdx] ? cells[colIdx].textContent.trim() : '';
}

function sortTable(value) {
  const tbody = document.getElementById('code-tbody');
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
      case 'order_asc':
        return (parseInt(getCellValue(a,4))||0) - (parseInt(getCellValue(b,4))||0);
      case 'order_desc':
        return (parseInt(getCellValue(b,4))||0) - (parseInt(getCellValue(a,4))||0);
      case 'active':
        va = getCellValue(a,5).includes('사용') && !getCellValue(a,5).includes('미사용') ? 0 : 1;
        vb = getCellValue(b,5).includes('사용') && !getCellValue(b,5).includes('미사용') ? 0 : 1;
        return va - vb;
      case 'updated_new': return getCellValue(b,6).localeCompare(getCellValue(a,6));
      case 'updated_old': return getCellValue(a,6).localeCompare(getCellValue(b,6));
      default: return 0;
    }
  });
  rows.forEach(r => tbody.appendChild(r));
}

/* ═══════════ DOMContentLoaded ═══════════ */
document.addEventListener('DOMContentLoaded', () => {
  /* 체크박스 */
  document.querySelectorAll('.row-check').forEach(cb => cb.addEventListener('change', updateDeleteBtn));

  /* 글자 수 카운터 */
  [
    ['cc_desc', 'cc_desc_count'],
    ['ce_desc', 'ce_desc_count'],
    ['gc_desc', 'gc_desc_count'],
    ['ge_desc', 'ge_desc_count'],
  ].forEach(([textareaId, countId]) => {
    const ta = document.getElementById(textareaId);
    const ct = document.getElementById(countId);
    if (ta && ct) {
      ta.addEventListener('input', () => { ct.textContent = `${ta.value.length}/100자`; });
    }
  });

  /* 코드 수정 모달 dirty tracking */
  ['ce_code_name','ce_desc','ce_sort'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', markCEDirty);
  });

  /* 그룹 수정 모달 dirty tracking */
  ['ge_name','ge_scope','ge_desc'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', markGEDirty);
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
      ['codeCreateModal','codeEditModal','groupCreateModal','groupEditModal','confirmModal','doneModal']
        .forEach(closeModal);
    }
  });
});
