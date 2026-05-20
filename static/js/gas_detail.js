/**
 * gas_detail.js — 유해가스 위젯 및 세부 페이지
 * GAS_META, LEVEL_CLASS는 monitoring.js에서 전역 정의
 */

const GAS_THRESHOLDS = {
    co: { warn: 25, danger: 200, max: 300, reverse: false },
    h2s: { warn: 10, danger: 15, max: 25, reverse: false },
    co2: { warn: 1000, danger: 5000, max: 6000, reverse: false },
    o2: { warn: 18, danger: 16, max: 25, reverse: true, high: 23.5 }, // 23.5 초과 주의
    no2: { warn: 3, danger: 5, max: 10, reverse: false },
    so2: { warn: 2, danger: 5, max: 10, reverse: false },
    o3: { warn: 0.06, danger: 0.12, max: 0.2, reverse: false },
    nh3: { warn: 25, danger: 35, max: 50, reverse: false },
    voc: { warn: 0.5, danger: 1.0, max: 1.5, reverse: false },
};

const LEVEL_COLOR = {
    danger: 'rgba(239,68,68,0.85)',
    warning: 'rgba(245,158,11,0.85)',
    normal: 'rgba(16,185,129,0.85)',
};

let gasSensors = [];
let gasCurrentIndex = 0;
let gasCharts = {};
let aiCharts = {};
let currentReading = null;
let selectedGas = null;


// ══════════════════════════════════════════════════════════
// Chart.js 커스텀 플러그인 — 배경 구역 레이어
// ══════════════════════════════════════════════════════════
const zoneBackgroundPlugin = {
    id: 'zoneBackground',
    beforeDraw(chart) {
        const { ctx, chartArea: area, scales: { y } } = chart;
        const gas = chart.config._gasKey;
        if (!gas || !area) return;
        const t = GAS_THRESHOLDS[gas];
        if (!t) return;

        const clamp = v => Math.max(area.top, Math.min(area.bottom, y.getPixelForValue(v)));

        if (t.reverse) {
            const dangerY = clamp(t.danger);
            const warnY = clamp(t.warn);
            const highY = t.high ? clamp(t.high) : area.top;

            // 23.5 초과 주의 구역 (기준 미정)
            if (t.high) {
                ctx.fillStyle = 'rgba(245,158,11,0.15)';
                ctx.fillRect(area.left, area.top, area.right - area.left, highY - area.top);
            }
            // 정상 구역
            ctx.fillStyle = 'rgba(16,185,129,0.05)';
            ctx.fillRect(area.left, highY, area.right - area.left, warnY - highY);
            // 주의 구역
            ctx.fillStyle = 'rgba(245,158,11,0.2)';
            ctx.fillRect(area.left, warnY, area.right - area.left, dangerY - warnY);
            // 위험 구역
            ctx.fillStyle = 'rgba(239,68,68,0.25)';
            ctx.fillRect(area.left, dangerY, area.right - area.left, area.bottom - dangerY);
        } else {
            const warnY = clamp(t.warn);
            const dangerY = clamp(t.danger);
            ctx.fillStyle = 'rgba(239,68,68,0.25)';
            ctx.fillRect(area.left, area.top, area.right - area.left, dangerY - area.top);
            ctx.fillStyle = 'rgba(245,158,11,0.2)';
            ctx.fillRect(area.left, dangerY, area.right - area.left, warnY - dangerY);
            ctx.fillStyle = 'rgba(16,185,129,0.05)';
            ctx.fillRect(area.left, warnY, area.right - area.left, area.bottom - warnY);
        }
    }
};
Chart.register(zoneBackgroundPlugin);


// ══════════════════════════════════════════════════════════
// Chart.js 커스텀 플러그인 — 예측 구간 수직 분리선
// ══════════════════════════════════════════════════════════
const forecastSeparatorPlugin = {
    id: 'forecastSeparator',
    afterDraw(chart) {
        const splitIdx = chart.config._splitIdx;
        if (splitIdx == null) return;
        const { ctx, chartArea: area, scales: { x } } = chart;
        if (!area || !x) return;

        const xPos = x.getPixelForValue(splitIdx - 0.5);
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(xPos, area.top);
        ctx.lineTo(xPos, area.bottom);
        ctx.strokeStyle = 'rgba(255,255,255,0.18)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.restore();

        ctx.save();
        ctx.fillStyle = 'rgba(251,146,60,0.55)';
        ctx.font = '9px monospace';
        ctx.textAlign = 'left';
        ctx.fillText('예측 →', xPos + 4, area.top + 11);
        ctx.restore();
    },
};
Chart.register(forecastSeparatorPlugin);


// ══════════════════════════════════════════════════════════
// 가스별 개별 위험도 계산
// ══════════════════════════════════════════════════════════
function calcPerGasLevels(reading) {
    const levels = {};
    Object.keys(GAS_META).forEach(gas => {
        const value = reading[gas];
        if (value === null || value === undefined) {
            levels[gas] = 'normal';
            return;
        }
        const t = GAS_THRESHOLDS[gas];
        if (!t) { levels[gas] = 'normal'; return; }

        if (t.reverse) {
            // O2: 낮을수록 위험, 23.5 초과도 주의(기준 미정)
            levels[gas] = value < t.danger ? 'danger' :
                value < t.warn ? 'warning' :
                    (t.high && value > t.high) ? 'warning' : 'normal';
        } else {
            levels[gas] = value >= t.danger ? 'danger' :
                value >= t.warn ? 'warning' : 'normal';
        }
    });
    return levels;
}


// ══════════════════════════════════════════════════════════
// 차트 초기화
// ══════════════════════════════════════════════════════════
function initGasChartGrid() {
    const grid = document.getElementById('gas-chart-grid');
    if (!grid) return;

    grid.innerHTML = Object.keys(GAS_META).map(gas => `
        <div class="gas-chart-card" id="card-${gas}" data-gas="${gas}">
            <div class="gas-chart-card__header">
                <span class="gas-chart-card__name">• ${GAS_META[gas].formula}(${GAS_META[gas].name})</span>
                <span class="gas-chart-card__badge level-badge" id="badge-${gas}">-</span>
            </div>
            <div class="gas-chart-card__canvas-wrap">
                <canvas id="chart-${gas}"></canvas>
            </div>
        </div>`
    ).join('');

    Object.keys(GAS_META).forEach(gas => createGasChart(gas));
}

function createGasChart(gas) {
    const ctx = document.getElementById(`chart-${gas}`);
    if (!ctx) return;

    const t = GAS_THRESHOLDS[gas];

    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [GAS_META[gas].name],
            datasets: [{
                data: [0],
                backgroundColor: LEVEL_COLOR.normal,
                borderColor: 'transparent',
                borderWidth: 0,
                borderRadius: { topLeft: 3, topRight: 3 },
                barPercentage: 0.5,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            hover: { mode: null },
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        title: () => new Date().toLocaleString('ko-KR'),
                        label: ctx => `현재 ${GAS_META[gas].name} 농도  ${ctx.parsed.y} ${GAS_META[gas].unit}`,
                    },
                    backgroundColor: 'rgba(22,27,34,0.95)',
                    borderColor: '#2a3448',
                    borderWidth: 1,
                    titleColor: '#94a3b8',
                    bodyColor: '#e2e8f0',
                    titleFont: { size: 10 },
                    bodyFont: { size: 12, weight: 'bold' },
                    padding: 10,
                }
            },
            scales: {
                x: { display: false },
                y: {
                    min: 0,
                    max: t?.max ?? 100,
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#4b5563', font: { size: 9 }, maxTicksLimit: 6 },
                    border: { color: 'rgba(255,255,255,0.1)' },
                }
            }
        }
    });

    chart.config._gasKey = gas;
    gasCharts[gas] = chart;
}

function clearGasCharts() {
    Object.keys(GAS_META).forEach(gas => {
        const chart = gasCharts[gas];
        if (chart) {
            chart.data.datasets[0].data = [0];
            chart.data.datasets[0].backgroundColor = LEVEL_COLOR['normal'];
            chart.update();
        }
        const card  = document.getElementById(`card-${gas}`);
        const badge = document.getElementById(`badge-${gas}`);
        if (card)  card.className  = 'gas-chart-card gas-chart-card--normal';
        if (badge) { badge.textContent = '-'; badge.className = 'gas-chart-card__badge level-badge level--normal'; }
    });
}

function updateGasCharts(reading, gasLevels) {
    if (!reading) return;

    Object.keys(GAS_META).forEach(gas => {
        const card = document.getElementById(`card-${gas}`);
        const badge = document.getElementById(`badge-${gas}`);

        const value = reading[gas];
        const level = (gasLevels && gasLevels[gas]) || 'normal';
        const levelKo = level === 'danger' ? '위험' : level === 'warning' ? '주의' : '정상';

        if (gasCharts[gas]) {
            gasCharts[gas].destroy();
            delete gasCharts[gas];
        }
        createGasChart(gas);

        const chart = gasCharts[gas];
        if (!chart) return;

        chart.data.datasets[0].data = [value ?? 0];
        chart.data.datasets[0].backgroundColor = LEVEL_COLOR[level];
        chart.update();

        if (card) card.className = `gas-chart-card gas-chart-card--${level}`;
        if (badge) {
            badge.textContent = levelKo;
            badge.className = `gas-chart-card__badge level-badge level--${level}`;
        }
    });
}


// ══════════════════════════════════════════════════════════
// 테이블 렌더링
// ══════════════════════════════════════════════════════════
function renderGasTable(reading) {
    const tbody = document.getElementById('gas-tbody');
    if (!tbody) return;

    if (!reading) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center">데이터 없음</td></tr>';
        clearGasCharts();
        return;
    }

    currentReading = reading;

    const gasLevels = (reading.gas_levels && Object.keys(reading.gas_levels).length > 0)
        ? reading.gas_levels
        : calcPerGasLevels(reading);

    reading._gasLevels = gasLevels;

    tbody.innerHTML = Object.keys(GAS_META).map(gas => {
        const meta = GAS_META[gas];
        const value = reading[gas];
        const level = gasLevels[gas] || 'normal';
        const levelKo = level === 'danger' ? '위험' : level === 'warning' ? '주의' : '정상';
        const dv = (value !== null && value !== undefined) ? value : '-';

        return `
            <tr class="row--${level} gas-table-row" data-gas="${gas}">
                <td>${meta.name}(${meta.formula})</td>
                <td class="mono">${dv}</td>
                <td class="mono">${meta.unit}</td>
                <td><span class="level-badge level--${level}">${levelKo}</span></td>
            </tr>`;
    }).join('');

    tbody.querySelectorAll('.gas-table-row').forEach(row => {
        row.addEventListener('click', () => {
            tbody.querySelectorAll('.gas-table-row').forEach(r => r.classList.remove('selected'));
            row.classList.add('selected');
            selectedGas = row.dataset.gas;
            if (currentReading) updateGasCharts(currentReading, currentReading._gasLevels);
        });
    });

    const updateEl = document.getElementById('gas-last-update');
    if (updateEl) updateEl.textContent = new Date().toLocaleTimeString('ko-KR');

    updateGasCharts(reading, gasLevels);
}


// ══════════════════════════════════════════════════════════
// 센서 리스트 렌더링
// ══════════════════════════════════════════════════════════
function renderSensorList(sensors) {
    const tbody = document.getElementById('sensor-list');
    if (!tbody) return;

    if (sensors.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center">등록된 센서 없음</td></tr>';
        return;
    }

    tbody.innerHTML = sensors.map((s, idx) => `
        <tr class="sensor-list__item ${idx === gasCurrentIndex ? 'sensor-list__item--active' : ''}"
            data-idx="${idx}" data-id="${s.id}">
            <td class="mono">${s.device_uid}</td>
            <td class="text-muted" id="main-gas-${s.id}">-</td>
            <td>
                <span class="conn-status conn-status--${s.status === 'active' ? 'ok' : 'err'}">
                    ${s.status === 'active' ? '정상' : '수신 오류'}
                </span>
            </td>
            <td id="level-badge-${s.id}">
                <span class="level-badge level--normal">-</span>
            </td>
        </tr>`
    ).join('');

    tbody.querySelectorAll('.sensor-list__item').forEach(item => {
        item.addEventListener('click', () => {
            tbody.querySelectorAll('.sensor-list__item')
                .forEach(i => i.classList.remove('sensor-list__item--active'));
            item.classList.add('sensor-list__item--active');
            gasCurrentIndex = parseInt(item.dataset.idx);
            updateGasNav();
        });
    });

    sensors.forEach(s => loadSensorSummary(s));
}

async function loadSensorSummary(sensor) {
    try {
        const res = await DeviceAPI.getLatestGas(sensor.id);
        const data = res.data;

        const levels = (data.gas_levels && Object.keys(data.gas_levels).length > 0)
            ? data.gas_levels
            : calcPerGasLevels(data);

        const dangerGases = Object.entries(levels).filter(([, v]) => v === 'danger');
        const warningGases = Object.entries(levels).filter(([, v]) => v === 'warning');
        const mainGasEl = document.getElementById(`main-gas-${sensor.id}`);
        const badgeEl = document.getElementById(`level-badge-${sensor.id}`);

        if (dangerGases.length > 0) {
            const gas = dangerGases[0][0];
            if (mainGasEl) mainGasEl.textContent =
                `${GAS_META[gas]?.formula} - ${data[gas]} ${GAS_META[gas]?.unit}`;
            if (badgeEl) badgeEl.innerHTML =
                '<span class="level-badge level--danger">위험</span>';
        } else if (warningGases.length > 0) {
            const gas = warningGases[0][0];
            if (mainGasEl) mainGasEl.textContent =
                `${GAS_META[gas]?.formula} - ${data[gas]} ${GAS_META[gas]?.unit}`;
            if (badgeEl) badgeEl.innerHTML =
                '<span class="level-badge level--warning">주의</span>';
        } else {
            if (mainGasEl) mainGasEl.textContent = '-';
            if (badgeEl) badgeEl.innerHTML =
                '<span class="level-badge level--normal">정상</span>';
        }

        updateGasSummaryBadges();

    } catch (e) {
        const mainGasEl = document.getElementById(`main-gas-${sensor.id}`);
        const badgeEl = document.getElementById(`level-badge-${sensor.id}`);
        if (e.response?.status === 404) {
            if (mainGasEl) mainGasEl.textContent = '-';
            if (badgeEl) badgeEl.innerHTML =
                '<span class="level-badge level--normal">-</span>';
        } else {
            if (mainGasEl) mainGasEl.textContent = '-';
            if (badgeEl) badgeEl.innerHTML =
                '<span class="conn-status conn-status--err">수신 오류</span>';
        }
    }
}

function updateGasSummaryBadges() {
    const rows = document.querySelectorAll('#sensor-list .sensor-list__item');
    let danger = 0, warning = 0, normal = 0;
    rows.forEach(row => {
        const id = row.dataset.id;
        const badge = document.querySelector(`#level-badge-${id} .level-badge`);
        if (!badge) return;
        if (badge.classList.contains('level--danger')) danger++;
        else if (badge.classList.contains('level--warning')) warning++;
        else normal++;
    });
    const dEl = document.getElementById('summary-danger');
    const wEl = document.getElementById('summary-warning');
    const nEl = document.getElementById('summary-normal');
    if (dEl) dEl.textContent = danger;
    if (wEl) wEl.textContent = warning;
    if (nEl) nEl.textContent = normal;
}


// ══════════════════════════════════════════════════════════
// 데이터 로드
// ══════════════════════════════════════════════════════════
async function loadLatestGas(deviceId) {
    if (!deviceId) return;
    try {
        const res = await DeviceAPI.getLatestGas(deviceId);
        const data = res.data;
        renderGasTable(data);

        const device = gasSensors[gasCurrentIndex];
        const gasLevels = data._gasLevels || calcPerGasLevels(data);
        const level = data.danger_level;

        if (device && (level === '위험' || level === '주의')) {
            const affectedGases = Object.entries(gasLevels)
                .filter(([, v]) => v === 'danger' || v === 'warning')
                .map(([g]) => GAS_META[g]?.formula)
                .join(', ');
            const action = level === '위험'
                ? '즉시 대피 및 관리자 연락 필요'
                : '환기 조치 및 현장 확인 필요';
            updateAlertBar(device.device_uid, `${affectedGases} 농도 ${level} 수준 감지`, action, new Date().toLocaleTimeString('ko-KR'), level);
        } else {
            updateAlertBar(null, null, null, null, '정상');
        }

    } catch (e) {
        if (e.response?.status === 404) renderGasTable(null);
        else console.error('가스 데이터 로드 실패:', e);
    }
}

function updateAlertBar(sensorId, msg, action, time, level) {
    const bar = document.getElementById('alert-bar');
    const sensorEl = document.getElementById('alert-sensor');
    const msgEl = document.getElementById('alert-msg');
    const actionEl = document.getElementById('alert-action');
    const timeEl = document.getElementById('alert-time');

    if (!bar) return;
    if (!level || level === '정상') { bar.style.display = 'none'; return; }

    bar.style.display = 'flex';
    bar.className = `alert-bar alert-bar--${level === '위험' ? 'danger' : 'warning'}`;
    if (sensorEl) sensorEl.textContent = sensorId;
    if (msgEl) msgEl.textContent = msg;
    if (actionEl) actionEl.textContent = action;
    if (timeEl) timeEl.textContent = time;
}


// ══════════════════════════════════════════════════════════
// 네비게이션
// ══════════════════════════════════════════════════════════
function updateGasNav() {
    const device = gasSensors[gasCurrentIndex];
    if (!device) return;

    const nameEl = document.getElementById('gas-sensor-name');
    const pageEl = document.getElementById('gas-page');
    const currentEl = document.getElementById('current-sensor-name');
    if (nameEl) nameEl.textContent = device.device_name;
    if (pageEl) pageEl.textContent = `${gasCurrentIndex + 1} / ${gasSensors.length}`;
    if (currentEl) currentEl.textContent = device.device_uid;

    loadLatestGas(device.id);

    // AI 예측 탭이 활성화 상태면 해당 장비로 AI 차트도 갱신
    const aiTabActive = document.getElementById('tab-ai')?.classList.contains('active');
    if (aiTabActive) loadAICharts(device.id, device.device_uid);
}


// ══════════════════════════════════════════════════════════
// 초기화
// ══════════════════════════════════════════════════════════
window.initGasWidget = async function () {
    initGasChartGrid();
    initAITab();

    try {
        const res = await DeviceAPI.getList({ device_type: 'gas', is_active: true });
        gasSensors = res.data.results || res.data;

        if (gasSensors.length === 0) {
            const tbody = document.getElementById('gas-tbody');
            if (tbody) tbody.innerHTML =
                '<tr><td colspan="4" class="text-center">등록된 센서 없음</td></tr>';
            return;
        }

        gasSensors.sort((a, b) => a.device_uid.localeCompare(b.device_uid));
        renderSensorList(gasSensors);
        updateGasNav();

        document.getElementById('gas-prev')?.addEventListener('click', () => {
            gasCurrentIndex = (gasCurrentIndex - 1 + gasSensors.length) % gasSensors.length;
            renderSensorList(gasSensors);
            updateGasNav();
        });
        document.getElementById('gas-next')?.addEventListener('click', () => {
            gasCurrentIndex = (gasCurrentIndex + 1) % gasSensors.length;
            renderSensorList(gasSensors);
            updateGasNav();
        });

        setInterval(() => {
            loadLatestGas(gasSensors[gasCurrentIndex]?.id);
            gasSensors.forEach(s => loadSensorSummary(s));
        }, 60000);

        if (window.SafetyWS) {
            SafetyWS.on('gas_update', function(data) {
                if (!gasSensors.length) return;
                const device = gasSensors.find(s => s.device_uid === data.device_uid);
                if (!device) return;
                if (gasSensors[gasCurrentIndex]?.device_uid === data.device_uid) {
                    loadLatestGas(device.id);
                }
                loadSensorSummary(device);
            });
        }

    } catch (e) {
        console.error('가스 위젯 초기화 실패:', e);
    }
};


// ══════════════════════════════════════════════════════════
// AI 예측 탭 — 가스별 라인 차트
// ══════════════════════════════════════════════════════════

function calcSingleGasLevel(gas, value) {
    const t = GAS_THRESHOLDS[gas];
    if (!t || value === null || value === undefined) return 'normal';
    if (t.reverse) {
        return value < t.danger ? 'danger'
             : value < t.warn   ? 'warning'
             : (t.high && value > t.high) ? 'warning'
             : 'normal';
    }
    return value >= t.danger ? 'danger' : value >= t.warn ? 'warning' : 'normal';
}

function initAITab() {
    const grid = document.getElementById('ai-chart-grid');
    if (!grid) return;

    grid.innerHTML = Object.keys(GAS_META).map(gas => `
        <div class="ai-chart-card" id="ai-card-${gas}">
            <div class="ai-chart-card__header">
                <span class="ai-chart-card__name">• ${GAS_META[gas].formula}(${GAS_META[gas].name})</span>
                <span class="ai-chart-card__badge level-badge" id="ai-badge-${gas}">-</span>
            </div>
            <div class="ai-chart-insight" id="ai-insight-${gas}">
                <span class="ai-insight-muted">데이터 로딩 중...</span>
            </div>
            <div class="ai-chart-card__canvas-wrap">
                <canvas id="ai-chart-${gas}"></canvas>
            </div>
        </div>`
    ).join('');
}

async function loadAICharts(deviceId, deviceUid) {
    if (!deviceId) return;

    Object.values(aiCharts).forEach(c => { try { c.destroy(); } catch (_) {} });
    aiCharts = {};

    Object.keys(GAS_META).forEach(gas => {
        const insight = document.getElementById(`ai-insight-${gas}`);
        if (insight) insight.innerHTML = '<span class="ai-insight-muted">로딩 중...</span>';
    });

    try {
        const [histData, aiData] = await Promise.all([
            fetch(`/monitoring/api/gas-history/?device_id=${deviceId}&limit=30`).then(r => r.json()),
            fetch('/monitoring/api/ai-status/').then(r => r.json()),
        ]);

        const history = Array.isArray(histData) ? histData : [];
        const deviceAI = (aiData.devices || []).find(d => d.device_uid === deviceUid);

        // Isolation Forest 상태 카드 업데이트
        const ifCard  = document.getElementById('if-status-card');
        const ifBadge = document.getElementById('if-status-badge');
        const ifScore = document.getElementById('if-status-score');
        if (ifCard && deviceAI?.isolation) {
            const iso = deviceAI.isolation;
            const isAnomaly = iso.is_anomaly;
            ifBadge.textContent  = isAnomaly ? '이상 감지' : '정상';
            ifBadge.style.background    = isAnomaly ? '#ef4444' : '#22c55e';
            ifBadge.style.color         = '#fff';
            ifScore.textContent  = iso.score != null ? `score: ${iso.score}` : '(실시간 데이터 대기 중)';
            ifCard.style.display = 'flex';
        }

        Object.keys(GAS_META).forEach(gas => {
            const histValues = history.map(r => r[gas] ?? null);
            const histLabels = history.map(r => {
                const t = new Date(r.measured_at);
                return t.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            });

            // ARIMA 예측값: forecasts(전체) → predictions(임계 초과) 순서로 탐색
            let forecastValues = null;
            let firstExceedStep = null;
            if (deviceAI?.arima) {
                if (deviceAI.arima.forecasts?.[gas]) {
                    forecastValues = deviceAI.arima.forecasts[gas];
                }
                const pred = deviceAI.arima.predictions?.find(p => p.metric === gas);
                if (pred) {
                    if (!forecastValues) forecastValues = pred.forecast;
                    firstExceedStep = pred.first_exceed_step;
                }
            }

            const currentValue = histValues.length > 0 ? histValues[histValues.length - 1] : null;
            const level = currentValue !== null ? calcSingleGasLevel(gas, currentValue) : 'normal';

            createAILineChart(gas, histLabels, histValues, forecastValues, firstExceedStep, currentValue, level);
        });

    } catch (e) {
        console.error('AI 차트 로드 실패:', e);
        Object.keys(GAS_META).forEach(gas => {
            const insight = document.getElementById(`ai-insight-${gas}`);
            if (insight) insight.innerHTML = '<span class="ai-insight-muted">로드 실패</span>';
        });
    }
}

function createAILineChart(gas, histLabels, histValues, forecastValues, firstExceedStep, currentValue, level) {
    const ctx = document.getElementById(`ai-chart-${gas}`);
    if (!ctx) return;

    const meta = GAS_META[gas];
    const t = GAS_THRESHOLDS[gas];

    // Badge
    const badge = document.getElementById(`ai-badge-${gas}`);
    if (badge) {
        const levelKo = level === 'danger' ? '위험' : level === 'warning' ? '주의' : '정상';
        badge.textContent = levelKo;
        badge.className = `ai-chart-card__badge level-badge level--${level}`;
    }

    // Insight row
    const insight = document.getElementById(`ai-insight-${gas}`);
    if (insight) {
        const valStr = currentValue !== null ? `${currentValue} ${meta.unit}` : '-';
        let warn = '';
        if (forecastValues && firstExceedStep) {
            warn = `<span class="ai-insight-warn">⚠ ${firstExceedStep}분 후 임계치 초과 예상</span>`;
        } else if (forecastValues) {
            warn = `<span class="ai-insight-ok">예측 범위 정상</span>`;
        } else {
            warn = `<span class="ai-insight-muted">예측 데이터 부족</span>`;
        }
        insight.innerHTML = `<span class="ai-insight-val">현재: <b>${valStr}</b></span>${warn}`;
    }

    const N_HIST = histValues.length;
    const N_FORE = forecastValues ? forecastValues.length : 0;

    const forecastLabels = forecastValues ? forecastValues.map((_, i) => `+${i + 1}분`) : [];
    const allLabels = [...histLabels, ...forecastLabels];

    // History: values + nulls for forecast region
    const histDataset = [...histValues, ...Array(N_FORE).fill(null)];

    // Forecast: bridge from last history point + forecast values
    let forecastDataset = null;
    if (forecastValues && N_HIST > 0) {
        forecastDataset = [
            ...Array(N_HIST - 1).fill(null),
            histValues[N_HIST - 1],
            ...forecastValues,
        ];
    }

    const datasets = [
        {
            label: '실측',
            data: histDataset,
            borderColor: '#38bdf8',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            pointRadius: 0,
            pointHoverRadius: 3,
            spanGaps: false,
            tension: 0.2,
        },
    ];
    if (forecastDataset) {
        datasets.push({
            label: '예측',
            data: forecastDataset,
            borderColor: '#fb923c',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            borderDash: [5, 4],
            pointRadius: 2,
            pointHoverRadius: 4,
            pointBackgroundColor: '#fb923c',
            spanGaps: false,
            tension: 0.2,
        });
    }

    const yMin = gas === 'o2' ? 10 : 0;
    const yMax = t?.max ?? 100;

    const chart = new Chart(ctx, {
        type: 'line',
        data: { labels: allLabels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(22,27,34,0.95)',
                    borderColor: '#2a3448',
                    borderWidth: 1,
                    titleColor: '#94a3b8',
                    bodyColor: '#e2e8f0',
                    titleFont: { size: 10 },
                    bodyFont: { size: 11 },
                    padding: 8,
                    filter: item => item.parsed.y !== null,
                    callbacks: {
                        label: ctx => {
                            const v = ctx.parsed.y;
                            if (v === null) return null;
                            return `${ctx.dataset.label}: ${v} ${meta.unit}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: {
                        color: '#4b5563',
                        font: { size: 8 },
                        maxTicksLimit: 7,
                        maxRotation: 0,
                    },
                    border: { color: 'rgba(255,255,255,0.08)' },
                },
                y: {
                    min: yMin,
                    max: yMax,
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#4b5563', font: { size: 8 }, maxTicksLimit: 5 },
                    border: { color: 'rgba(255,255,255,0.08)' },
                },
            },
        },
    });

    chart.config._gasKey  = gas;
    chart.config._splitIdx = N_HIST;
    aiCharts[gas] = chart;
}


// ══════════════════════════════════════════════════════════
// 상세 페이지 전용 이벤트
// ══════════════════════════════════════════════════════════
document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn[data-tab]').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`tab-${btn.dataset.tab}`)?.classList.add('active');

        const isAI = btn.dataset.tab === 'ai';
        document.getElementById('legend-realtime').style.display = isAI ? 'none' : '';
        document.getElementById('legend-ai').style.display       = isAI ? ''     : 'none';

        if (isAI) {
            const device = gasSensors[gasCurrentIndex];
            if (device) loadAICharts(device.id, device.device_uid);
        }
    });
});

document.addEventListener('DOMContentLoaded', initGasWidget);