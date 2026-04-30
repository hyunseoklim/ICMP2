/**
 * gas_detail.js — 유해가스 위젯 및 세부 페이지
 * GAS_META, LEVEL_CLASS는 monitoring.js에서 전역 정의
 */

const GAS_THRESHOLDS = {
    co:  { warn: 25,   danger: 200,  max: 300,  reverse: false },
    h2s: { warn: 10,   danger: 15,   max: 25,   reverse: false },
    co2: { warn: 1000, danger: 5000, max: 6000, reverse: false },
    o2:  { warn: 18,   danger: 16,   max: 25,   reverse: true, high: 23.5 }, // 23.5 초과 주의
    no2: { warn: 3,    danger: 5,    max: 10,   reverse: false },
    so2: { warn: 2,    danger: 5,    max: 10,   reverse: false },
    o3:  { warn: 0.06, danger: 0.12, max: 0.2,  reverse: false },
    nh3: { warn: 25,   danger: 35,   max: 50,   reverse: false },
    voc: { warn: 0.5,  danger: 1.0,  max: 1.5,  reverse: false },
};

const LEVEL_COLOR = {
    danger:  'rgba(239,68,68,0.85)',
    warning: 'rgba(245,158,11,0.85)',
    normal:  'rgba(16,185,129,0.85)',
};

let gasSensors      = [];
let gasCurrentIndex = 0;
let gasCharts       = {};
let currentReading  = null;
let selectedGas     = null;


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
            const warnY   = clamp(t.warn);
            const highY   = t.high ? clamp(t.high) : area.top;

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
            const warnY   = clamp(t.warn);
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
            levels[gas] = value < t.danger        ? 'danger'  :
                          value < t.warn          ? 'warning' :
                          (t.high && value > t.high) ? 'warning' : 'normal';
        } else {
            levels[gas] = value >= t.danger ? 'danger'  :
                          value >= t.warn   ? 'warning' : 'normal';
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
                    grid:  { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#4b5563', font: { size: 9 }, maxTicksLimit: 6 },
                    border: { color: 'rgba(255,255,255,0.1)' },
                }
            }
        }
    });

    chart.config._gasKey = gas;
    gasCharts[gas] = chart;
}

function updateGasCharts(reading, gasLevels) {
    if (!reading) return;

    Object.keys(GAS_META).forEach(gas => {
        const card  = document.getElementById(`card-${gas}`);
        const badge = document.getElementById(`badge-${gas}`);

        const value   = reading[gas];
        const level   = (gasLevels && gasLevels[gas]) || 'normal';
        const levelKo = level === 'danger' ? '위험' : level === 'warning' ? '주의' : '정상';

        if (gasCharts[gas]) {
            gasCharts[gas].destroy();
            delete gasCharts[gas];
        }
        createGasChart(gas);

        const chart = gasCharts[gas];
        if (!chart) return;

        chart.data.datasets[0].data            = [value ?? 0];
        chart.data.datasets[0].backgroundColor = LEVEL_COLOR[level];
        chart.update();

        if (card)  card.className  = `gas-chart-card gas-chart-card--${level}`;
        if (badge) {
            badge.textContent = levelKo;
            badge.className   = `gas-chart-card__badge level-badge level--${level}`;
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
        return;
    }

    currentReading = reading;

    const gasLevels = (reading.gas_levels && Object.keys(reading.gas_levels).length > 0)
        ? reading.gas_levels
        : calcPerGasLevels(reading);

    reading._gasLevels = gasLevels;

    tbody.innerHTML = Object.keys(GAS_META).map(gas => {
        const meta    = GAS_META[gas];
        const value   = reading[gas];
        const level   = gasLevels[gas] || 'normal';
        const levelKo = level === 'danger' ? '위험' : level === 'warning' ? '주의' : '정상';
        const dv      = (value !== null && value !== undefined) ? value : '-';

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
        const res    = await DeviceAPI.getLatestGas(sensor.id);
        const data   = res.data;

        const levels = (data.gas_levels && Object.keys(data.gas_levels).length > 0)
            ? data.gas_levels
            : calcPerGasLevels(data);

        const dangerGases  = Object.entries(levels).filter(([, v]) => v === 'danger');
        const warningGases = Object.entries(levels).filter(([, v]) => v === 'warning');
        const mainGasEl    = document.getElementById(`main-gas-${sensor.id}`);
        const badgeEl      = document.getElementById(`level-badge-${sensor.id}`);

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
        const badgeEl   = document.getElementById(`level-badge-${sensor.id}`);
        if (e.response?.status === 404) {
            if (mainGasEl) mainGasEl.textContent = '-';
            if (badgeEl)   badgeEl.innerHTML =
                '<span class="level-badge level--normal">-</span>';
        } else {
            if (mainGasEl) mainGasEl.textContent = '-';
            if (badgeEl)   badgeEl.innerHTML =
                '<span class="conn-status conn-status--err">수신 오류</span>';
        }
    }
}

function updateGasSummaryBadges() {
    const rows = document.querySelectorAll('#sensor-list .sensor-list__item');
    let danger = 0, warning = 0, normal = 0;
    rows.forEach(row => {
        const id    = row.dataset.id;
        const badge = document.querySelector(`#level-badge-${id} .level-badge`);
        if (!badge) return;
        if (badge.classList.contains('level--danger'))       danger++;
        else if (badge.classList.contains('level--warning')) warning++;
        else                                                  normal++;
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
        const res       = await DeviceAPI.getLatestGas(deviceId);
        const data      = res.data;
        renderGasTable(data);

        const device    = gasSensors[gasCurrentIndex];
        const gasLevels = data._gasLevels || calcPerGasLevels(data);
        const level     = data.danger_level;

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
    const bar      = document.getElementById('alert-bar');
    const sensorEl = document.getElementById('alert-sensor');
    const msgEl    = document.getElementById('alert-msg');
    const actionEl = document.getElementById('alert-action');
    const timeEl   = document.getElementById('alert-time');

    if (!bar) return;
    if (!level || level === '정상') { bar.style.display = 'none'; return; }

    bar.style.display = 'flex';
    bar.className     = `alert-bar alert-bar--${level === '위험' ? 'danger' : 'warning'}`;
    if (sensorEl) sensorEl.textContent = sensorId;
    if (msgEl)    msgEl.textContent    = msg;
    if (actionEl) actionEl.textContent = action;
    if (timeEl)   timeEl.textContent   = time;
}


// ══════════════════════════════════════════════════════════
// 네비게이션
// ══════════════════════════════════════════════════════════
function updateGasNav() {
    const device = gasSensors[gasCurrentIndex];
    if (!device) return;

    const nameEl    = document.getElementById('gas-sensor-name');
    const pageEl    = document.getElementById('gas-page');
    const currentEl = document.getElementById('current-sensor-name');
    if (nameEl)    nameEl.textContent    = device.device_name;
    if (pageEl)    pageEl.textContent    = `${gasCurrentIndex + 1} / ${gasSensors.length}`;
    if (currentEl) currentEl.textContent = device.device_uid;

    loadLatestGas(device.id);
}


// ══════════════════════════════════════════════════════════
// 초기화
// ══════════════════════════════════════════════════════════
window.initGasWidget = async function () {
    initGasChartGrid();

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

    } catch (e) {
        console.error('가스 위젯 초기화 실패:', e);
    }
};


// ══════════════════════════════════════════════════════════
// 상세 페이지 전용 이벤트
// ══════════════════════════════════════════════════════════
document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn[data-tab]').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`tab-${btn.dataset.tab}`)?.classList.add('active');
    });
});