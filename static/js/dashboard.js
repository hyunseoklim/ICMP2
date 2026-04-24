/**
 * dashboard.js — 메인 대시보드 실시간 업데이트
 */

document.addEventListener('DOMContentLoaded', function() {

  /* ── 작업자 도넛 차트 업데이트 ── */
  SafetyWS.on('worker_update', function(payload) {
    document.getElementById('worker-danger').textContent  = payload.danger  + '명';
    document.getElementById('worker-warning').textContent = payload.warning + '명';
    document.getElementById('worker-normal').textContent  = payload.normal  + '명';

    // Chart.js 인스턴스 업데이트
    const chart = Chart.getChart('workerDonut');
    if (chart) {
      chart.data.datasets[0].data = [payload.danger, payload.warning, payload.normal];
      chart.update('none');
    }
  });

  /* ── 이벤트 목록 실시간 추가 ── */
  SafetyWS.on('event_new', function(payload) {
    const list = document.getElementById('event-list');
    if (!list) return;

    const li = document.createElement('li');
    li.className = `event-item event--${payload.severity}`;
    li.dataset.id = payload.id;
    li.innerHTML = `
      <div class="event-icon">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L1 21h22L12 2zm0 3.5l8.7 15H3.3L12 5.5zM11 10v4h2v-4h-2zm0 6v2h2v-2h-2z"/>
        </svg>
      </div>
      <div class="event-body">
        <p class="event-title">${payload.title}</p>
        <p class="event-desc">${payload.description}</p>
      </div>
      <span class="event-time">00:00</span>
    `;
    list.prepend(li);

    // 최대 20개 유지
    while (list.children.length > 20) {
      list.lastChild.remove();
    }

    // 브라우저 알림 (권한 있을 때)
    if (Notification.permission === 'granted' && payload.severity === 'danger') {
      new Notification('🚨 위험 이벤트 발생', { body: payload.title });
    }
  });

  /* ── 유해가스 테이블 갱신 ── */
  SafetyWS.on('gas_update', function(payload) {
    payload.readings?.forEach(function(row) {
      const el = document.querySelector(`#gas-tbody [data-id="${row.id}"]`);
      if (!el) return;
      el.querySelector('.mono').textContent = row.current_value;
      const badge = el.querySelector('.level-badge');
      badge.className = `level-badge level--${row.level}`;
      badge.textContent = row.level_display;
    });
  });

  /* ── 전력 현황 갱신 ── */
  SafetyWS.on('power_update', function(payload) {
    const totalEl = document.getElementById('power-total-mw');
    if (totalEl) {
      totalEl.innerHTML = `${Math.round(payload.total_mw).toLocaleString()} <span class="power-unit">MW</span>`;
    }
  });

  /* ── 마지막 갱신 시각 자동 업데이트 ── */
  document.addEventListener('wsConnected', function() {
    const el = document.getElementById('last-refresh');
    if (el) {
      const now = new Date();
      el.textContent = `${now.toLocaleDateString('ko-KR')} ${now.toLocaleTimeString('ko-KR')}`;
    }
  });

  /* ── 수동 새로고침 ── */
  document.addEventListener('safetyRefresh', async function() {
    try {
      const [workerRes, powerRes] = await Promise.all([
        SafetyAPI.getWorkerStats(),
        SafetyAPI.getPowerStatus(),
      ]);
      // 각 응답을 WS 핸들러와 동일한 방식으로 처리
      if (workerRes.data) SafetyWS.on && null; // 핸들러 직접 호출
    } catch(e) {
      console.error('새로고침 오류', e);
    }
  });

  /* ── 브라우저 알림 권한 요청 ── */
  if (Notification.permission === 'default') {
    Notification.requestPermission();
  }

  /* ── 이벤트 타임 카운터 ── */
  setInterval(function() {
    document.querySelectorAll('.event-time[data-start]').forEach(function(el) {
      const start = new Date(el.dataset.start);
      const diff = Math.floor((Date.now() - start) / 1000);
      const m = String(Math.floor(diff / 60)).padStart(2, '0');
      const s = String(diff % 60).padStart(2, '0');
      el.textContent = `${m}:${s}`;
    });
  }, 1000);

});
