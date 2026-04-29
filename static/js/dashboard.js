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

        while (list.children.length > 20) {
            list.lastChild.remove();
        }

        if (Notification.permission === 'granted' && payload.severity === 'danger') {
            new Notification('🚨 위험 이벤트 발생', { body: payload.title });
        }
    });

    /* ── 유해가스 테이블 갱신 ── */
    SafetyWS.on('gas_update', function(data) {
        if (typeof gasSensors === 'undefined' || !gasSensors.length) return;

        const deviceUid = data.device_uid;
        const device = gasSensors.find(s => s.device_uid === deviceUid);

        if (device && gasSensors[gasCurrentIndex]?.device_uid === deviceUid) {
            renderGasTable(data);
        }
        if (device) loadSensorSummary(device);
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

    /* ── 알람 폴링 (5초마다) ── */
    async function pollAlarms() {
        try {
            const res    = await axios.get('/alerts/api/recent/');
            const alarms = res.data;
            if (!Array.isArray(alarms) || alarms.length === 0) return;

            const list = document.getElementById('event-list');
            if (!list) return;

            list.innerHTML = alarms.map(a => `
                <li class="event-item event--${a.severity}">
                    <div class="event-icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2L1 21h22L12 2zm0 3.5l8.7 15H3.3L12 5.5zM11 10v4h2v-4h-2zm0 6v2h2v-2h-2z"/>
                        </svg>
                    </div>
                    <div class="event-body">
                        <p class="event-title">${a.title}</p>
                        <p class="event-desc">${a.message || ''}</p>
                    </div>
                    <span class="event-time">${new Date(a.occurred_at).toLocaleTimeString('ko-KR')}</span>
                </li>`
            ).join('');

        } catch (e) {
            console.error('알람 폴링 실패:', e);
        }
    }

    pollAlarms();
    setInterval(pollAlarms, 5000);

});


/* ── 유해가스 위젯 초기화 (gas_detail.js에서 정의) ── */
document.addEventListener('DOMContentLoaded', function () {
    if (typeof initGasWidget === 'function') initGasWidget();
});

/* ── 전력 위젯 초기화 (power_detail.js에서 정의) ── */
document.addEventListener('DOMContentLoaded', function () {
    if (typeof initPowerWidget === 'function') initPowerWidget();
});