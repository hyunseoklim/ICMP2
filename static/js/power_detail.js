/**
 * power_detail.js — 전력 관리 세부 페이지 실시간 업데이트
 */
document.addEventListener('DOMContentLoaded', function () {

    let powerHistoryChart = null;
    let powerPredictChart = null;
    let equipments        = [];
    let currentEquipIdx   = 0;

    // ── 전력 현황 로드 ────────────────────────────────────
    async function loadPowerStatus() {
        try {
            const res  = await SafetyAPI.getPowerStatus();
            const data = res.data;

            // 총 전력 갱신
            const totalEl = document.getElementById('power-total-mw');
            if (totalEl) {
                totalEl.innerHTML = `${data.total_mw.toLocaleString()} <span class="power-unit">MW</span>`;
            }
            const totalCardEl = document.getElementById('power-total');
            if (totalCardEl) totalCardEl.textContent = data.total_mw + ' MW';

            // 설비 테이블 갱신
            const tbody = document.getElementById('power-tbody');
            if (tbody && data.equipment_list) {
                tbody.innerHTML = data.equipment_list.map(function (eq) {
                    return `
                    <tr class="row--${eq.latest_reading?.level || 'normal'}">
                        <td>${eq.name}</td>
                        <td class="mono">${eq.latest_reading?.power_mwh ?? '—'} MWh</td>
                        <td class="mono">${eq.latest_reading?.temperature ?? '—'}°C</td>
                        <td><span class="level-badge level--${eq.latest_reading?.level || 'normal'}">
                            ${eq.latest_reading?.level_display || '—'}
                        </span></td>
                    </tr>`;
                }).join('');
            }

            equipments = data.equipment_list || [];
        } catch (e) {
            console.error('전력 현황 로드 실패', e);
        }
    }

    // ── 전력 히스토리 차트 ────────────────────────────────
    async function loadPowerHistory(hours) {
        try {
            const res  = await SafetyAPI.getPowerHistory({ hours });
            const rows = res.data;

            // 시간대별 집계
            const buckets = {};
            rows.forEach(function (r) {
                const h = new Date(r.measured_at).getHours();
                buckets[h] = (buckets[h] || 0) + r.power_kw;
            });

            const now    = new Date();
            const labels = [];
            const values = [];
            for (let i = hours - 1; i >= 0; i--) {
                const h = (now.getHours() - i + 24) % 24;
                labels.push(String(h).padStart(2, '0') + ':00');
                values.push(Math.round((buckets[h] || 0) / 1000 * 10) / 10); // MW
            }

            const ctx = document.getElementById('power-history-chart');
            if (!ctx) return;

            if (powerHistoryChart) powerHistoryChart.destroy();

            powerHistoryChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: '전력 사용량 (MW)',
                        data: values,
                        borderColor: '#63b3ed',
                        backgroundColor: 'rgba(99,179,237,0.08)',
                        borderWidth: 1.5,
                        pointRadius: 2,
                        pointBackgroundColor: '#63b3ed',
                        tension: 0.4,
                        fill: true,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: 'rgba(22,27,34,0.95)',
                            borderColor: '#2a3448',
                            borderWidth: 1,
                            titleColor: '#e2e8f0',
                            bodyColor: '#94a3b8',
                            callbacks: {
                                label: function (ctx) {
                                    return ` ${ctx.parsed.y} MW`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.04)' },
                            ticks: { color: '#4b5563', font: { size: 10 }, maxTicksLimit: 8 },
                        },
                        y: {
                            grid: { color: 'rgba(255,255,255,0.04)' },
                            ticks: {
                                color: '#4b5563', font: { size: 10 },
                                callback: function (v) { return v + ' MW'; },
                            },
                        },
                    },
                },
            });
        } catch (e) {
            console.error('전력 히스토리 로드 실패', e);
        }
    }

    // ── AI 전력 예측 차트 ─────────────────────────────────
    async function loadPowerPredict(equipId) {
        try {
            const res = await SafetyAPI.getPowerPredict(equipId);
            const d   = res.data;

            const etaEl  = document.getElementById('power-predict-time');
            const maxEl  = document.getElementById('power-predict-max');
            if (etaEl) etaEl.textContent = d.danger_eta_min + '분 뒤';
            if (maxEl) maxEl.innerHTML   =
                `${d.predicted_max.toLocaleString()} kW <span class="predict-diff">(정상 대비 ${d.predicted_max_pct}%)</span>`;

            const ctx = document.getElementById('powerPredictFullChart');
            if (!ctx) return;

            if (powerPredictChart) powerPredictChart.destroy();

            powerPredictChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: d.labels,
                    datasets: [
                        {
                            label: '실제 부하',
                            data: d.actual,
                            borderColor: '#63b3ed',
                            backgroundColor: 'rgba(99,179,237,0.08)',
                            borderWidth: 1.5,
                            pointRadius: 0,
                            tension: 0.4,
                        },
                        {
                            label: 'AI 예측',
                            data: d.predicted,
                            borderColor: '#fc8181',
                            backgroundColor: 'rgba(252,129,129,0.06)',
                            borderWidth: 1.5,
                            borderDash: [4, 3],
                            pointRadius: 0,
                            tension: 0.4,
                        },
                        {
                            label: '위험 임계값',
                            data: d.labels.map(function () { return d.threshold; }),
                            borderColor: 'rgba(239,68,68,0.4)',
                            borderWidth: 1,
                            borderDash: [3, 3],
                            pointRadius: 0,
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
                            ticks: {
                                color: '#4b5563', font: { size: 10 },
                                callback: function (v) { return (v / 1000).toFixed(1) + ' MW'; },
                            },
                        },
                    },
                },
            });
        } catch (e) {
            console.error('AI 전력 예측 로드 실패', e);
        }
    }

    // ── 시간 범위 선택 ────────────────────────────────────
    document.getElementById('power-range')?.addEventListener('change', function () {
        loadPowerHistory(parseInt(this.value));
    });

    // ── AI 예측 설비 네비게이션 ───────────────────────────
    document.getElementById('ai-power-prev')?.addEventListener('click', function () {
        if (!equipments.length) return;
        currentEquipIdx = (currentEquipIdx - 1 + equipments.length) % equipments.length;
        refreshAIPowerNav();
    });

    document.getElementById('ai-power-next')?.addEventListener('click', function () {
        if (!equipments.length) return;
        currentEquipIdx = (currentEquipIdx + 1) % equipments.length;
        refreshAIPowerNav();
    });

    function refreshAIPowerNav() {
        const eq    = equipments[currentEquipIdx];
        if (!eq) return;
        const label = document.getElementById('ai-power-label');
        const page  = document.getElementById('ai-power-page');
        if (label) label.textContent = eq.name;
        if (page)  page.textContent  = `${currentEquipIdx + 1} / ${equipments.length}`;
        loadPowerPredict(eq.id);
    }

    // ── WebSocket 전력 실시간 업데이트 ────────────────────
    if (window.SafetyWS) {
        SafetyWS.on('power_update', function (payload) {
            if (!payload.reading) return;
            const r = payload.reading;

            // 테이블 행 갱신
            document.querySelectorAll('#power-tbody tr').forEach(function (row) {
                if (row.cells[0]?.textContent.trim() === r.name) {
                    row.className = 'row--' + r.level;
                    row.cells[1].textContent = (r.power_kw / 1000).toFixed(1) + ' MWh';
                    row.cells[2].textContent = r.temperature + '°C';
                    const badge = row.cells[3].querySelector('.level-badge');
                    if (badge) {
                        badge.className  = 'level-badge level--' + r.level;
                        badge.textContent = r.level_display;
                    }
                }
            });

            // 위험 설비 카운트 갱신
            const dangerCount = document.getElementById('power-danger-count');
            if (dangerCount) {
                const cnt = document.querySelectorAll('#power-tbody tr.row--danger').length;
                dangerCount.textContent = cnt;
            }
        });
    }

    // ── 5분마다 AI 예측 자동 갱신 ────────────────────────
    function scheduleAIRefresh() {
        setTimeout(function () {
            if (equipments[currentEquipIdx]) loadPowerPredict(equipments[currentEquipIdx].id);
            scheduleAIRefresh();
        }, 5 * 60 * 1000);
    }

    // ── 초기화 ───────────────────────────────────────────
    async function init() {
        await loadPowerStatus();
        await loadPowerHistory(6);
        if (equipments.length) {
            await loadPowerPredict(equipments[0].id);
            refreshAIPowerNav();
        }
        scheduleAIRefresh();
    }

    init();

    // 30초마다 전력 현황 폴링 (WebSocket 보완)
    setInterval(loadPowerStatus, 30 * 1000);
});
