/**
 * gas_detail.js — 유해가스 세부 페이지 실시간 업데이트
 */
document.addEventListener('DOMContentLoaded', function () {

    let currentSensorIdx = 0;
    let sensors = [];

    // ── 센서 목록 로드 ────────────────────────────────────
    async function loadSensors() {
        try {
            const res = await SafetyAPI.getGasSensors();
            sensors = res.data;
            if (sensors.length) renderGasTable(sensors[currentSensorIdx]);
        } catch (e) {
            console.error('센서 로드 실패', e);
        }
    }

    // ── 가스 테이블 렌더링 ────────────────────────────────
    function renderGasTable(sensor) {
        if (!sensor?.latest_reading) return;
        const tbody = document.getElementById('gas-tbody');
        if (!tbody) return;

        tbody.innerHTML = sensor.latest_reading.map(function (r) {
            return `
            <tr class="row--${r.level}">
                <td>${r.gas_name}<br><small class="text-muted">${r.gas_formula}</small></td>
                <td class="mono">${r.value}</td>
                <td class="mono">${r.unit}</td>
                <td><span class="level-badge level--${r.level}">${r.level_display}</span></td>
            </tr>`;
        }).join('');

        // 요약 카드 갱신
        const counts = { danger: 0, warning: 0, normal: 0 };
        sensor.latest_reading.forEach(function (r) { counts[r.level] = (counts[r.level] || 0) + 1; });
        const dangerEl  = document.getElementById('gas-danger-count');
        const warningEl = document.getElementById('gas-warning-count');
        const normalEl  = document.getElementById('gas-normal-count');
        if (dangerEl)  dangerEl.textContent  = counts.danger;
        if (warningEl) warningEl.textContent = counts.warning;
        if (normalEl)  normalEl.textContent  = counts.normal;
    }

    // ── 센서 네비게이션 ──────────────────────────────────
    document.getElementById('gas-prev')?.addEventListener('click', function () {
        if (!sensors.length) return;
        currentSensorIdx = (currentSensorIdx - 1 + sensors.length) % sensors.length;
        renderGasTable(sensors[currentSensorIdx]);
        updateSensorNav();
    });

    document.getElementById('gas-next')?.addEventListener('click', function () {
        if (!sensors.length) return;
        currentSensorIdx = (currentSensorIdx + 1) % sensors.length;
        renderGasTable(sensors[currentSensorIdx]);
        updateSensorNav();
    });

    function updateSensorNav() {
        const label = document.querySelector('.sensor-nav-label');
        const page  = document.getElementById('gas-page');
        if (label && sensors[currentSensorIdx]) label.textContent = sensors[currentSensorIdx].name;
        if (page) page.textContent = `${currentSensorIdx + 1} / ${sensors.length}`;
    }

    // ── AI 예측 차트 (Full View) ──────────────────────────
    let gasPredictChart = null;

    async function loadGasPredict(sensorId) {
        try {
            const res = await SafetyAPI.getGasPredict(sensorId);
            const d   = res.data;

            const currentEl = document.getElementById('gas-predict-current');
            const maxEl     = document.getElementById('gas-predict-max');
            if (currentEl) currentEl.textContent = d.current_pct + '%';
            if (maxEl)     maxEl.textContent      = d.predicted_max_pct + '%';

            const ctx = document.getElementById('gasPredictFullChart');
            if (!ctx) return;

            if (gasPredictChart) gasPredictChart.destroy();

            gasPredictChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: d.labels,
                    datasets: [
                        {
                            label: '실제 농도',
                            data: d.actual,
                            borderColor: '#f6ad55',
                            backgroundColor: 'rgba(246,173,85,0.08)',
                            borderWidth: 1.5,
                            pointRadius: 0,
                            tension: 0.4,
                        },
                        {
                            label: 'AI 예측',
                            data: d.predicted,
                            borderColor: '#fc8181',
                            backgroundColor: 'rgba(252,129,129,0.08)',
                            borderWidth: 1.5,
                            borderDash: [4, 3],
                            pointRadius: 0,
                            tension: 0.4,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 10 },
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: 'rgba(22,27,34,0.95)',
                            borderColor: '#2a3448',
                            borderWidth: 1,
                            titleColor: '#e2e8f0',
                            bodyColor: '#94a3b8',
                        },
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.04)' },
                            ticks: { color: '#4b5563', font: { size: 10 }, maxTicksLimit: 8 },
                        },
                        y: {
                            grid: { color: 'rgba(255,255,255,0.04)' },
                            ticks: { color: '#4b5563', font: { size: 10 } },
                        },
                    },
                },
            });
        } catch (e) {
            console.error('AI 예측 로드 실패', e);
        }
    }

    // ── 센서 필터 ─────────────────────────────────────────
    document.getElementById('sensor-filter')?.addEventListener('change', function () {
        const val = this.value;
        document.querySelectorAll('#gas-tbody tr').forEach(function (tr) {
            const badge = tr.querySelector('.level-badge');
            if (!badge) return;
            tr.style.display = (!val || val === 'all' || badge.classList.contains('level--' + val)) ? '' : 'none';
        });
    });

    // ── 마지막 갱신 시각 ──────────────────────────────────
    function updateLastUpdate() {
        const el = document.getElementById('gas-last-update');
        if (el) el.textContent = new Date().toLocaleTimeString('ko-KR');
    }

    // ── WebSocket 실시간 가스 업데이트 ────────────────────
    if (window.SafetyWS) {
        SafetyWS.on('gas_update', function (payload) {
            if (!payload.readings) return;
            payload.readings.forEach(function (r) {
                const rows = document.querySelectorAll('#gas-tbody tr');
                rows.forEach(function (row) {
                    const formula = row.querySelector('small');
                    if (formula && formula.textContent === r.gas_formula) {
                        row.className      = 'row--' + r.level;
                        const cells        = row.querySelectorAll('td');
                        cells[1].textContent = r.value;
                        const badge        = cells[3].querySelector('.level-badge');
                        if (badge) {
                            badge.className  = 'level-badge level--' + r.level;
                            badge.textContent = r.level_display;
                        }
                    }
                });
            });
            updateLastUpdate();
        });
    }

    // ── AI 예측 센서 네비게이션 ───────────────────────────
    document.getElementById('ai-gas-prev')?.addEventListener('click', function () {
        if (!sensors.length) return;
        currentSensorIdx = (currentSensorIdx - 1 + sensors.length) % sensors.length;
        loadGasPredict(sensors[currentSensorIdx].id);
        const label = document.getElementById('ai-gas-label');
        const page  = document.getElementById('ai-gas-page');
        if (label) label.textContent = sensors[currentSensorIdx].name;
        if (page)  page.textContent  = `${currentSensorIdx + 1} / ${sensors.length}`;
    });

    document.getElementById('ai-gas-next')?.addEventListener('click', function () {
        if (!sensors.length) return;
        currentSensorIdx = (currentSensorIdx + 1) % sensors.length;
        loadGasPredict(sensors[currentSensorIdx].id);
        const label = document.getElementById('ai-gas-label');
        const page  = document.getElementById('ai-gas-page');
        if (label) label.textContent = sensors[currentSensorIdx].name;
        if (page)  page.textContent  = `${currentSensorIdx + 1} / ${sensors.length}`;
    });

    // ── 5분마다 AI 예측 자동 갱신 ────────────────────────
    function scheduleAIRefresh() {
        setTimeout(function () {
            if (sensors[currentSensorIdx]) loadGasPredict(sensors[currentSensorIdx].id);
            scheduleAIRefresh();
        }, 5 * 60 * 1000);
    }

    // ── 초기화 ───────────────────────────────────────────
    loadSensors().then(function () {
        if (sensors.length) loadGasPredict(sensors[0].id);
        scheduleAIRefresh();
    });
    updateLastUpdate();
});
