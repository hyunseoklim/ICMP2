/**
 * power_detail.js — 전력 위젯 및 세부 페이지
 * 부하율 = 현재 전력 / rated_power_w × 100
 * 위험 판단 임시 기준: 부하율 50% 초과 → 주의, 75% 초과 → 위험
 * 시간대별 평균 기반 위험도는 4차에서 구현 예정
 */

// ── 상수 ─────────────────────────────────────────────────────
const POWER_LEVEL_COLOR = {
    danger:  'rgba(239,68,68,0.85)',
    warning: 'rgba(245,158,11,0.85)',
    normal:  'rgba(16,185,129,0.85)',
    error:   'rgba(100,100,100,0.3)',
    off:     'rgba(100,100,100,0.3)',
};

const DEFAULT_RATED_W = 1000; // 카탈로그 기준 채널 최대 전력 (W)
const WARN_LOAD       = 50;   // 주의 임계 부하율 % (화면설계 추정)
const DANGER_LOAD     = 75;   // 위험 임계 부하율 % (화면설계 추정)

// ── 상태 ─────────────────────────────────────────────────────
let powerDevices      = [];
let powerCurrentIndex = 0;
let powerCharts       = {};
let currentChannels   = [];
let selectedChannels  = new Set();


// ══════════════════════════════════════════════════════════
// Chart.js 커스텀 플러그인 — 배경 구역 레이어
// ══════════════════════════════════════════════════════════
const powerZonePlugin = {
    id: 'powerZoneBackground',
    beforeDraw(chart) {
    const { ctx, chartArea: area, scales: { y } } = chart;
        if (!area || !y) return;   // ← !y 추가

        const clamp = v => Math.max(area.top, Math.min(area.bottom, y.getPixelForValue(v)));

        const dangerY = clamp(DANGER_LOAD);
        const warnY   = clamp(WARN_LOAD);

        ctx.fillStyle = 'rgba(239,68,68,0.2)';
        ctx.fillRect(area.left, area.top, area.right - area.left, dangerY - area.top);

        ctx.fillStyle = 'rgba(245,158,11,0.15)';
        ctx.fillRect(area.left, dangerY, area.right - area.left, warnY - dangerY);

        ctx.fillStyle = 'rgba(16,185,129,0.05)';
        ctx.fillRect(area.left, warnY, area.right - area.left, area.bottom - warnY);
    }
};
Chart.register(powerZonePlugin);


// ══════════════════════════════════════════════════════════
// 채널 상태 계산
// ══════════════════════════════════════════════════════════
function calcChannelLevel(r) {
    if (r.current_a === -1 && r.voltage_v === -1 && r.power_w === -1) return 'error';
    if (r.current_a === -1 || r.voltage_v === -1 || r.power_w === -1) return 'warning';
    if (r.current_a === 0  && r.voltage_v === 0  && r.power_w === 0)  return 'off';
    const load = calcLoadRate(r.power_w, r.channel_rated_power);
    if (load > DANGER_LOAD) return 'danger';
    if (load > WARN_LOAD)   return 'warning';
    return 'normal';
}

function calcLoadRate(power_w, rated_w) {
    if (!power_w || power_w <= 0) return 0;
    const base = rated_w || DEFAULT_RATED_W;
    return Math.round((power_w / base) * 100);
}

// 연결 상태 텍스트
function connStatusText(level) {
    return level === 'error' ? '오류' :
           level === 'off'   ? 'OFF'  : '정상';
}

// 연결 상태 CSS 클래스
function connStatusClass(level) {
    return level === 'error' ? 'conn-status--err' :
           level === 'off'   ? 'conn-status--off' : 'conn-status--ok';
}

// 위험도 텍스트
function dangerLevelText(level) {
    return level === 'danger'  ? '위험'    :
           level === 'warning' ? '주의'    :
           level === 'error'   ? '통신불능' :
           level === 'off'     ? 'OFF'     : '정상';
}

// 위험도 배지 CSS 클래스
function levelToBadgeClass(level) {
    return level === 'error' ? 'level--error-comm' :
           `level--${level}`;
}

// 행 배경 CSS 클래스
function getRowClass(level) {
    return level === 'danger'  ? 'row--danger'  :
           level === 'warning' ? 'row--warning' : '';
}

// 위험도 셀 렌더링
function renderDangerCell(level) {
    if (level === 'off') {
        // OFF: 테두리 없이 회색 글씨
        return '<span class="power-danger-off">OFF</span>';
    }
    return `<span class="level-badge ${levelToBadgeClass(level)}">${dangerLevelText(level)}</span>`;
}


// ══════════════════════════════════════════════════════════
// 차트 초기화
// ══════════════════════════════════════════════════════════
function initPowerChartGrid(channels) {
    const grid = document.getElementById('power-chart-grid');
    if (!grid) return;

    // 기존 차트 전부 파괴
    Object.keys(powerCharts).forEach(code => {
        if (powerCharts[code]) {
            powerCharts[code].destroy();
            delete powerCharts[code];
        }
    });
    powerCharts = {};

    if (!channels || channels.length === 0) {
        grid.innerHTML = '<p class="text-center text-muted">채널 데이터 없음</p>';
        powerCharts = {};
        return;
    }

    grid.innerHTML = channels.map(ch => {
        const isOff   = ch.level === 'off';
        const isError = ch.level === 'error';

        return `
            <div class="power-chart-card power-chart-card--${ch.level}"
                 id="pcard-${ch.channel_code}" data-code="${ch.channel_code}">
                <div class="power-chart-card__header">
                    <span class="power-chart-card__name">• ${ch.channel_name || ch.channel_code}</span>
                    <span class="power-chart-card__badge level-badge ${levelToBadgeClass(ch.level)}"
                          id="pbadge-${ch.channel_code}">
                        ${dangerLevelText(ch.level)}
                    </span>
                </div>
                <div class="power-chart-card__canvas-wrap">
                    ${isOff   ? '<div class="power-state-label power-state-label--off">OFF</div>'       :
                      isError ? '<div class="power-state-label power-state-label--error">통신불능</div>' :
                                `<canvas id="pchart-${ch.channel_code}"></canvas>`}
                </div>
            </div>`;
    }).join('');

    // DOM 완전히 렌더링 후 차트 생성
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            channels.forEach(ch => createPowerChart(ch));
        });
    });
}

function createPowerChart(ch) {
    if (ch.level === 'off' || ch.level === 'error') return;

    const ctx = document.getElementById(`pchart-${ch.channel_code}`);
    if (!ctx) return;

    const color    = POWER_LEVEL_COLOR[ch.level] || POWER_LEVEL_COLOR.normal;
    const loadRate = calcLoadRate(ch.power_w, ch.rated_power_w);

    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [ch.channel_name || ch.channel_code],
            datasets: [{
                data: [loadRate],
                backgroundColor: color,
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
                powerZoneBackground: {},
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        title: () => new Date().toLocaleString('ko-KR'),
                        label: ctx => [
                            `부하율: ${ctx.parsed.y}%`,
                            `현재 전력: ${ch.power_w} W`,
                        ],
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
                    max: 110,
                    grid:  { color: 'rgba(255,255,255,0.04)' },
                    ticks: {
                        color: '#4b5563',
                        font: { size: 9 },
                        maxTicksLimit: 6,
                        callback: v => `${v}%`,
                    },
                    border: { color: 'rgba(255,255,255,0.1)' },
                }
            }
        }
    });

    powerCharts[ch.channel_code] = chart;
}


// ══════════════════════════════════════════════════════════
// 설비 리스트 렌더링
// ══════════════════════════════════════════════════════════
function renderEquipList(channels) {
    const detailTbody    = document.getElementById('power-equip-list');
    const dashboardTbody = document.getElementById('power-tbody');

    // ── 대시보드 위젯 (4컬럼) ──
    if (dashboardTbody) {
        if (!channels || channels.length === 0) {
            dashboardTbody.innerHTML =
                '<tr><td colspan="4" class="text-center">데이터 없음</td></tr>';
        } else {
            dashboardTbody.innerHTML = channels.map(ch => {
                const level    = ch.level || 'normal';
                const powerStr = ch.power_w > 0 ? `${ch.power_w.toLocaleString()} W` : '-';

                return `
                    <tr class="${getRowClass(level)}">
                        <td>${ch.channel_name || ch.channel_code}</td>
                        <td class="mono">${powerStr}</td>
                        <td style="text-align:center;">-</td>
                        <td style="text-align:center;">${renderDangerCell(level)}</td>
                    </tr>`;
            }).join('');
        }

        // 기준 대비 계산 (활성 채널 평균 부하율 대비)
        updateBaselineDisplay(channels);
    }

    // ── 상세 페이지 (6컬럼) ──
    if (detailTbody) {
        if (!channels || channels.length === 0) {
            detailTbody.innerHTML =
                '<tr><td colspan="6" class="text-center">데이터 없음</td></tr>';
        } else {
            detailTbody.innerHTML = channels.map(ch => {
                const level    = ch.level || 'normal';
                const loadRate = calcLoadRate(ch.power_w, ch.rated_power_w);
                const loadStr  = loadRate > 0 ? `${loadRate}%` : '-';

                return `
                    <tr class="power-equip-item ${getRowClass(level)}" data-code="${ch.channel_code}">
                        <td style="text-align:center;">
                            <input type="checkbox" class="equip-checkbox" data-code="${ch.channel_code}">
                        </td>
                        <td>${ch.channel_name || ch.channel_code}</td>
                        <td class="mono" style="text-align:center;">${loadStr}</td>
                        <td style="text-align:center;">
                            <span class="conn-status ${connStatusClass(level)}">${connStatusText(level)}</span>
                        </td>
                        <td style="text-align:center;">-</td>
                        <td style="text-align:center;">${renderDangerCell(level)}</td>
                    </tr>`;
            }).join('');

            detailTbody.querySelectorAll('.equip-checkbox').forEach(cb => {
                cb.addEventListener('change', () => {
                    const code = cb.dataset.code;
                    if (cb.checked) selectedChannels.add(code);
                    else            selectedChannels.delete(code);
                    updateRestartBtn();
                });
            });
        }
    }

    updatePowerSummaryBadges(channels || []);
}

// ── 기준 대비 표시 (활성 채널 평균 부하율 기준) ──────────────
function updateBaselineDisplay(channels) {
    const baselineEl = document.getElementById('power-baseline');
    if (!baselineEl) return;

    // OFF, 통신불능 제외한 활성 채널만
    const activeChannels = channels.filter(ch =>
        ch.level !== 'off' && ch.level !== 'error' && ch.power_w > 0
    );

    if (activeChannels.length === 0) {
        baselineEl.textContent = '-';
        baselineEl.className   = 'baseline-val';
        return;
    }

    const avgLoad = activeChannels.reduce((sum, ch) =>
        sum + calcLoadRate(ch.power_w, ch.rated_power_w), 0
    ) / activeChannels.length;

    const totalLoad = calcLoadRate(
        channels.reduce((s, ch) => s + (ch.power_w > 0 ? ch.power_w : 0), 0),
        DEFAULT_RATED_W * channels.length
    );

    const diff = Math.round(totalLoad - avgLoad);
    const sign = diff >= 0 ? '▲' : '▼';
    const cls  = diff > 0 ? 'val--up' : diff < 0 ? 'val--down' : '';

    baselineEl.textContent = `${sign}${Math.abs(diff)}%`;
    baselineEl.className   = `baseline-val ${cls}`;
}

function updatePowerSummaryBadges(channels) {
    let danger = 0, warning = 0, normal = 0;
    channels.forEach(ch => {
        if (ch.level === 'danger' || ch.level === 'error') danger++;
        else if (ch.level === 'warning')                   warning++;
        else                                               normal++;
    });
    const dEl = document.getElementById('summary-danger');
    const wEl = document.getElementById('summary-warning');
    const nEl = document.getElementById('summary-normal');
    if (dEl) dEl.textContent = danger;
    if (wEl) wEl.textContent = warning;
    if (nEl) nEl.textContent = normal;
}

function updateRestartBtn() {
    const btn = document.getElementById('power-restart-btn');
    if (btn) btn.disabled = selectedChannels.size === 0;
}


// ══════════════════════════════════════════════════════════
// 데이터 로드
// ══════════════════════════════════════════════════════════
async function loadLatestPower(deviceId) {
    if (!deviceId) return;
    try {
        const res      = await DeviceAPI.getLatestPower(deviceId);
        const readings = res.data;

        const channels = readings.map(r => ({
            channel_code:    r.channel_code || r.channel,
            channel_name:    r.channel_name || r.channel_code || r.channel,
            rated_power_w:   r.channel_rated_power || DEFAULT_RATED_W,
            current_a:       r.current_a,
            voltage_v:       r.voltage_v,
            power_w:         r.power_w,
            level:           calcChannelLevel(r),
        }));

        currentChannels = channels;
        renderEquipList(channels);
        initPowerChartGrid(channels);

        // 총 전력 갱신
        const totalW  = channels.reduce((s, ch) => s + (ch.power_w > 0 ? ch.power_w : 0), 0);
        const totalEl = document.getElementById('power-total');
        if (totalEl) totalEl.textContent = totalW.toLocaleString();

        // 경보바
        const device    = powerDevices[powerCurrentIndex];
        const hasError  = channels.some(ch => ch.level === 'error');
        const hasDanger = channels.some(ch => ch.level === 'danger');
        const hasWarn   = channels.some(ch => ch.level === 'warning');

        if (device && (hasError || hasDanger)) {
            updatePowerAlertBar(
                device.device_uid,
                hasError ? '통신불능 채널 감지' : '전력 과부하 감지',
                '즉시 점검 및 차단 필요',
                new Date().toLocaleTimeString('ko-KR'),
                '위험'
            );
        } else if (device && hasWarn) {
            updatePowerAlertBar(
                device.device_uid,
                '부분 통신 오류 감지',
                '해당 설비 연결 상태 확인 필요',
                new Date().toLocaleTimeString('ko-KR'),
                '주의'
            );
        } else {
            updatePowerAlertBar(null, null, null, null, '정상');
        }

    } catch (e) {
        if (e.response?.status === 404) renderEquipList(null);
        else console.error('전력 데이터 로드 실패:', e.response?.status, e.message);
    }
}

function updatePowerAlertBar(deviceId, msg, action, time, level) {
    const bar      = document.getElementById('power-alert-bar');
    const sensorEl = document.getElementById('power-alert-sensor');
    const msgEl    = document.getElementById('power-alert-msg');
    const actionEl = document.getElementById('power-alert-action');
    const timeEl   = document.getElementById('power-alert-time');

    if (!bar) return;
    if (!level || level === '정상') { bar.style.display = 'none'; return; }

    bar.style.display = 'flex';
    bar.className     = `alert-bar alert-bar--${level === '위험' ? 'danger' : 'warning'}`;
    if (sensorEl) sensorEl.textContent = deviceId;
    if (msgEl)    msgEl.textContent    = msg;
    if (actionEl) actionEl.textContent = action;
    if (timeEl)   timeEl.textContent   = time;
}


// ══════════════════════════════════════════════════════════
// 네비게이션
// ══════════════════════════════════════════════════════════
function updatePowerNav() {
    const device = powerDevices[powerCurrentIndex];
    if (!device) return;

    const nameEl = document.getElementById('power-device-name');
    const pageEl = document.getElementById('power-page');
    if (nameEl) nameEl.textContent = device.device_name;
    if (pageEl) pageEl.textContent = `${powerCurrentIndex + 1} / ${powerDevices.length}`;

    loadLatestPower(device.id);

    // AI 예측 탭이 활성화 상태면 해당 장비로 AI 차트도 갱신
    const aiTabActive = document.getElementById('tab-ai')?.classList.contains('active');
    if (aiTabActive) loadPowerAICharts(device.id, device.device_uid);
}


// ══════════════════════════════════════════════════════════
// 초기화
// ══════════════════════════════════════════════════════════
window.initPowerWidget = async function () {
    initPowerAITab();
    try {
        const res = await DeviceAPI.getList({ device_type: 'power', is_active: true });
        powerDevices = res.data.results || res.data;

        if (powerDevices.length === 0) {
            const tbody = document.getElementById('power-equip-list')
                       || document.getElementById('power-tbody');
            if (tbody) tbody.innerHTML =
                '<tr><td colspan="6" class="text-center">등록된 전력 장비 없음</td></tr>';
            return;
        }

        updatePowerNav();

        document.getElementById('power-prev')?.addEventListener('click', () => {
            powerCurrentIndex = (powerCurrentIndex - 1 + powerDevices.length) % powerDevices.length;
            updatePowerNav();
        });
        document.getElementById('power-next')?.addEventListener('click', () => {
            powerCurrentIndex = (powerCurrentIndex + 1) % powerDevices.length;
            updatePowerNav();
        });

        setInterval(() => loadLatestPower(powerDevices[powerCurrentIndex]?.id), 60000);

    } catch (e) {
        console.error('전력 위젯 초기화 실패:', e);
    }
};


// ══════════════════════════════════════════════════════════
// AI 예측 탭 — 채널별 부하율 라인차트
// ══════════════════════════════════════════════════════════

// 현재 시점 수직 파란선 플러그인
const powerForecastSeparatorPlugin = {
    id: 'powerForecastSeparator',
    afterDraw(chart) {
        const splitIdx = chart.config._splitIdx;
        if (splitIdx == null) return;
        const { ctx, chartArea: area, scales: { x } } = chart;
        if (!area || !x) return;

        const xPos = x.getPixelForValue(splitIdx - 0.5);

        // 파란 실선
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(xPos, area.top);
        ctx.lineTo(xPos, area.bottom);
        ctx.strokeStyle = 'rgba(56,189,248,0.7)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        ctx.stroke();
        ctx.restore();

        // "현재" 레이블
        ctx.save();
        ctx.fillStyle = '#38bdf8';
        ctx.font = 'bold 9px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('현재', xPos, area.top + 10);
        ctx.restore();
    },
};
Chart.register(powerForecastSeparatorPlugin);

let powerAICharts = {};

// 최근 트렌드 기반 예측 (최근 5개 포인트의 변화율을 미래로 연장)
function trendForecast(values, steps) {
    const clean = values.filter(v => v !== null && v !== undefined);
    if (clean.length === 0) return Array(steps).fill(0);
    if (clean.length === 1) return Array(steps).fill(clean[0]);

    // 최근 최대 5개 포인트로 트렌드 계산
    const recent = clean.slice(Math.max(0, clean.length - 5));
    const trend  = (recent[recent.length - 1] - recent[0]) / Math.max(1, recent.length - 1);
    const last   = clean[clean.length - 1];

    return Array.from({ length: steps }, (_, i) => {
        const v = last + trend * (i + 1);
        return Math.round(Math.max(0, Math.min(150, v)) * 10) / 10;
    });
}

function initPowerAITab() {
    const grid = document.getElementById('power-ai-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="ai-loading-msg">채널 데이터 로딩 중...</div>';
}

async function loadPowerAICharts(deviceId, deviceUid) {
    if (!deviceId) return;

    Object.values(powerAICharts).forEach(c => { try { c.destroy(); } catch (_) {} });
    powerAICharts = {};

    const grid = document.getElementById('power-ai-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="ai-loading-msg">로딩 중...</div>';

    try {
        const [histData, aiData] = await Promise.all([
            fetch(`/monitoring/api/power-history/?device_id=${deviceId}&limit=30`).then(r => r.json()),
            fetch('/monitoring/api/ai-power-status/').then(r => r.json()),
        ]);

        const entries = Object.entries(histData);
        if (entries.length === 0) {
            grid.innerHTML = '<div class="ai-loading-msg">채널 데이터 없음</div>';
            return;
        }

        // 현재 device의 채널별 ARIMA 결과 추출
        const deviceAI = (aiData.devices || []).find(d => d.device_uid === deviceUid);
        const arimaMap = {};
        if (deviceAI) {
            (deviceAI.channels || []).forEach(ch => {
                arimaMap[ch.channel_code] = ch.arima;
            });
        }

        grid.innerHTML = entries.map(([code, ch]) => {
            const readings     = ch.readings || [];
            const histValues   = readings.map(r => r.load_ratio);
            const currentLoad  = histValues.length > 0 ? histValues[histValues.length - 1] : null;
            const cardLevel    = currentLoad === null ? 'normal'
                               : currentLoad > DANGER_LOAD ? 'danger'
                               : currentLoad > WARN_LOAD   ? 'warning' : 'normal';
            return `
            <div class="power-ai-card power-ai-card--${cardLevel}" id="pai-card-${code}">
                <div class="power-ai-card__header">
                    <span class="power-ai-card__name">• ${ch.channel_name}</span>
                    <span class="level-badge" id="pai-badge-${code}">-</span>
                </div>
                <div class="power-ai-insight" id="pai-insight-${code}">
                    <span class="ai-insight-muted">로딩 중...</span>
                </div>
                <div class="power-ai-card__canvas-wrap">
                    <canvas id="pai-chart-${code}"></canvas>
                </div>
            </div>`;
        }).join('');

        requestAnimationFrame(() => {
            entries.forEach(([code, ch]) => {
                const readings   = ch.readings || [];
                const histLabels = readings.map(r => {
                    const t = new Date(r.measured_at);
                    return t.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
                });
                const histValues   = readings.map(r => r.load_ratio);
                const arima        = arimaMap[code] || null;
                // 백엔드 ARIMA 결과가 있으면 사용, 없으면 단순 트렌드로 폴백
                const forecastValues = (arima && arima.forecast) ? arima.forecast : trendForecast(histValues, 12);
                const currentLoad  = histValues.length > 0 ? histValues[histValues.length - 1] : null;
                const level = currentLoad === null ? 'normal'
                            : currentLoad > DANGER_LOAD ? 'danger'
                            : currentLoad > WARN_LOAD   ? 'warning' : 'normal';

                createPowerAILineChart(code, ch.channel_name, histLabels, histValues, forecastValues, currentLoad, level, arima);
            });
        });

    } catch (e) {
        console.error('전력 AI 차트 로드 실패:', e);
        grid.innerHTML = '<div class="ai-loading-msg">로드 실패</div>';
    }
}

function createPowerAILineChart(code, name, histLabels, histValues, forecastValues, currentLoad, level, arima = null) {
    const ctx = document.getElementById(`pai-chart-${code}`);
    if (!ctx) return;

    // Badge
    const badge = document.getElementById(`pai-badge-${code}`);
    if (badge) {
        const ko = level === 'danger' ? '위험' : level === 'warning' ? '주의' : '정상';
        badge.textContent = ko;
        badge.className = `level-badge level--${level}`;
    }

    // Insight — 백엔드 ARIMA 결과 우선, 없으면 프론트 트렌드 폴백
    const insight = document.getElementById(`pai-insight-${code}`);
    if (insight) {
        const valStr = currentLoad !== null ? `${currentLoad}%` : '-';

        let etaStr = '';
        if (arima) {
            // 백엔드 ARIMA 결과 사용
            if (currentLoad !== null && currentLoad >= DANGER_LOAD) {
                etaStr = `<span class="ai-insight-danger">현재 위험 초과</span>`;
            } else if (arima.eta_danger !== null && arima.eta_danger !== undefined) {
                etaStr = `<span class="ai-insight-warn">위험 도달 예상: ${arima.eta_danger}분 후</span>`;
            } else if (arima.eta_warn !== null && arima.eta_warn !== undefined) {
                etaStr = `<span class="ai-insight-warn">주의 도달 예상: ${arima.eta_warn}분 후</span>`;
            }
        } else {
            // 폴백: 단순 트렌드 직선 계산
            if (currentLoad !== null && currentLoad >= DANGER_LOAD) {
                etaStr = `<span class="ai-insight-danger">현재 위험 초과</span>`;
            } else if (currentLoad !== null) {
                const recent = histValues.slice(Math.max(0, histValues.length - 5)).filter(v => v != null);
                if (recent.length >= 2) {
                    const trend = (recent[recent.length - 1] - recent[0]) / Math.max(1, recent.length - 1);
                    if (trend > 0) {
                        const eta = Math.ceil((DANGER_LOAD - currentLoad) / trend);
                        if (eta <= 1440) etaStr = `<span class="ai-insight-warn">위험 도달 예상: ${eta}분 후</span>`;
                    }
                }
            }
        }

        let maxStr = '';
        const maxLoad = arima ? arima.max_load : null;
        if (maxLoad !== null && maxLoad !== undefined) {
            const cls = maxLoad > DANGER_LOAD ? 'ai-insight-danger'
                      : maxLoad > WARN_LOAD   ? 'ai-insight-warn' : 'ai-insight-ok';
            maxStr = `<span class="${cls}">예측 최대: ${maxLoad}%</span>`;
        }

        insight.innerHTML = `<span class="ai-insight-val">현재: <b>${valStr}</b></span>${etaStr}${maxStr}`;
    }

    const N_HIST = histValues.length;
    const N_FORE = forecastValues.length;
    const forecastLabels = forecastValues.map((_, i) => `+${i + 1}분`);
    const allLabels      = [...histLabels, ...forecastLabels];

    const histDataset = [...histValues, ...Array(N_FORE).fill(null)];
    const foreDataset = N_HIST > 0
        ? [...Array(N_HIST - 1).fill(null), histValues[N_HIST - 1], ...forecastValues]
        : null;

    const datasets = [{
        label: '실측',
        data: histDataset,
        borderColor: '#38bdf8',
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 3,
        spanGaps: false,
        tension: 0.2,
    }];
    if (foreDataset) {
        datasets.push({
            label: 'AI 예측',
            data: foreDataset,
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
                powerZoneBackground: {},
                tooltip: {
                    backgroundColor: 'rgba(22,27,34,0.95)',
                    borderColor: '#2a3448',
                    borderWidth: 1,
                    titleColor: '#94a3b8',
                    bodyColor: '#e2e8f0',
                    titleFont: { size: 10 },
                    bodyFont:  { size: 11 },
                    padding: 8,
                    filter: item => item.parsed.y !== null,
                    callbacks: {
                        label: ctx => {
                            const v = ctx.parsed.y;
                            return v === null ? null : `${ctx.dataset.label}: ${v}%`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid:   { color: 'rgba(255,255,255,0.04)' },
                    ticks:  { color: '#4b5563', font: { size: 8 }, maxTicksLimit: 7, maxRotation: 0 },
                    border: { color: 'rgba(255,255,255,0.08)' },
                },
                y: (() => {
                    const allVals = [...histValues, ...forecastValues].filter(v => v !== null);
                    const yMin = allVals.length ? Math.max(0,   Math.floor(Math.min(...allVals) / 10) * 10 - 10) : 0;
                    const yMax = allVals.length ? Math.min(120, Math.ceil(Math.max(...allVals)  / 10) * 10 + 10) : 110;
                    return {
                        min: yMin,
                        max: yMax,
                        grid:   { color: 'rgba(255,255,255,0.04)' },
                        ticks:  { color: '#4b5563', font: { size: 8 }, maxTicksLimit: 5, callback: v => `${v}%` },
                        border: { color: 'rgba(255,255,255,0.08)' },
                    };
                })(),
            },
        },
    });

    chart.config._splitIdx = N_HIST;
    powerAICharts[code] = chart;
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
        const legendRT = document.getElementById('power-legend-realtime');
        const legendAI = document.getElementById('power-legend-ai');
        if (legendRT) legendRT.style.display = isAI ? 'none' : '';
        if (legendAI) legendAI.style.display = isAI ? '' : 'none';

        if (isAI) {
            const device = powerDevices[powerCurrentIndex];
            if (device) loadPowerAICharts(device.id, device.device_uid);
        }
    });
});

document.getElementById('power-restart-btn')?.addEventListener('click', () => {
    if (selectedChannels.size === 0) return;
    const names = [...selectedChannels].join(', ');
    alert(`[미구현] ${names} 재가동 요청 — 4차에서 구현 예정`);
});

document.addEventListener('DOMContentLoaded', initPowerWidget);