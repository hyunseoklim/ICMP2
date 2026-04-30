document.addEventListener('DOMContentLoaded', function() {

    /* ── 작업자 도넛 차트 업데이트 ── */
    SafetyWS.on('worker_update', function(payload) {
        document.getElementById('worker-danger').textContent  = payload.danger  + '명';
        document.getElementById('worker-warning').textContent = payload.warning + '명';
        document.getElementById('worker-normal').textContent  = payload.normal  + '명';

        const chart = Chart.getChart('workerDonut');
        if (chart) {
            chart.data.datasets[0].data = [payload.danger, payload.warning, payload.normal];
            chart.update('none');
        }
    });

    /* ── 이벤트 목록 실시간 추가 (WebSocket) ── */
    SafetyWS.on('event_new', function(payload) {
        renderEventList();
    });

    /* ── 유해가스 테이블 갱신 ── */
    SafetyWS.on('gas_update', function(data) {
        if (typeof gasSensors === 'undefined' || !gasSensors.length) return;

        const device = gasSensors.find(s => s.device_uid === data.device_uid);
        if (!device) return;

        if (gasSensors[gasCurrentIndex]?.device_uid === data.device_uid) {
            loadLatestGas(device.id);
        }
        loadSensorSummary(device);
    });

    /* ── 전력 현황 갱신 ── */
    SafetyWS.on('power_update', function(data) {
        if (typeof powerDevices === 'undefined' || !powerDevices.length) return;
        loadLatestPower(powerDevices[powerCurrentIndex]?.id);
    });

    /* ── 마지막 갱신 시각 자동 업데이트 ── */
    document.addEventListener('wsConnected', function() {
        const el = document.getElementById('last-refresh');
        if (el) {
            const now = new Date();
            el.textContent = `${now.toLocaleDateString('ko-KR')} ${now.toLocaleTimeString('ko-KR')}`;
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

    /* ── 이벤트 목록 렌더링 ─────────────────────────────── */
    function buildWorkerItem() {
        if (!window.CURRENT_WORKER_NAME) return '';
        const done       = window.SAFETY_DONE;
        const stateText  = done ? '작업 전 안전 확인 완료' : '작업 전 안전 확인 미완료';
        const stateClass = done ? 'safety-done' : 'safety-undone';
        const iconColor  = done ? 'var(--accent-green)' : 'var(--danger)';
        return `
        <li class="event-item event-item--worker event--${done ? 'normal' : 'danger'}">
            <div class="event-icon event-icon--worker" style="color:${iconColor}">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
                </svg>
            </div>
            <div class="event-body">
                <p class="event-title">${window.CURRENT_WORKER_NAME} 작업자</p>
                <p class="event-desc ${stateClass}">${stateText}</p>
            </div>
            <span class="event-time">-</span>
        </li>`;
    }

    async function renderEventList() {
        const list = document.getElementById('event-list');
        if (!list) return;

        try {
            const res    = await axios.get('/alerts/api/recent/?mine=true&minutes=1440&limit=20');
            const alarms = Array.isArray(res.data) ? res.data : [];

            const alarmItems = alarms.map(a => {
                const icon = a.severity === 'danger'
                    ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L1 21h22L12 2zm0 3.5l8.7 15H3.3L12 5.5zM11 10v4h2v-4h-2zm0 6v2h2v-2h-2z"/></svg>`
                    : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
                return `
                <li class="event-item event--${a.severity}" data-id="${a.id}">
                    <div class="event-icon">${icon}</div>
                    <div class="event-body">
                        <p class="event-title">${a.title}</p>
                        <p class="event-desc">${a.message || ''}</p>
                    </div>
                    <span class="event-time" data-start="${a.occurred_at}">00:00</span>
                </li>`;
            });

            list.innerHTML = buildWorkerItem() + alarmItems.join('') || '<li class="event-empty">현재 이벤트가 없습니다.</li>';

        } catch (e) {
            console.error('[EventList] 로딩 실패:', e);
        }
    }

    renderEventList();
    setInterval(renderEventList, 10000);

});


/* ── 유해가스 위젯 초기화 (gas_detail.js에서 정의) ── */
document.addEventListener('DOMContentLoaded', function () {
    if (typeof initGasWidget === 'function') initGasWidget();
});

/* ── 전력 위젯 초기화 (power_detail.js에서 정의) ── */
document.addEventListener('DOMContentLoaded', function () {
    if (typeof initPowerWidget === 'function') initPowerWidget();
});
