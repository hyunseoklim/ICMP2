/**
 * gas_forecast.js — 유해가스 'AI 예측' 탭 (gas_detail 페이지)
 *
 * 실시간 탭(gas_detail.js)과 그리드·카드 껍데기(.gas-chart-grid /
 * .gas-chart-card)는 공유하되, 예측 차트 로직만 본 파일에 분리한다.
 * 상수(GAS_META·GAS_THRESHOLDS)·플러그인(zoneBackgroundPlugin)·선택 장비
 * 상태(gasSensors·gasCurrentIndex)는 페이지 전역 정의를 그대로 읽어 쓴다.
 *
 * 카드 구성:
 *  - 헤더 배지 '현재 농도 : N 단위' — 현재 측정값 기준 위험/주의/정상 3색.
 *  - 차트(line) — 과거 실측(흰 실선) + AI 예측(주황 점선) + 신뢰구간(음영),
 *    배경 3구역(zoneBackgroundPlugin), 임계 수평선 + '현재' 경계선 +
 *    커서 추종 수직선(forecastOverlayPlugin).
 *  - 툴팁 — 「yyyy-MM-DD HH:mm:ss」 + 「해당 시간 예상/측정 농도 N 단위」.
 */
(function () {
    'use strict';

    const POLL_MS = 60000;

    let aiGridInitialized = false;
    let forecastCharts = {};   // gas → Chart 인스턴스
    let pollTimer = null;

    // ══════════════════════════════════════════════════════
    // Chart.js 플러그인 — 임계 수평선 + '현재' 경계선 + 커서 추종 수직선
    //   _isForecast 플래그로 게이트 → 실시간 막대 차트엔 적용 안 됨
    // ══════════════════════════════════════════════════════
    const forecastOverlayPlugin = {
        id: 'forecastOverlay',
        afterDatasetsDraw(chart) {
            if (!chart.config._isForecast) return;
            const area = chart.chartArea;
            const x = chart.scales.x, y = chart.scales.y;
            if (!area || !x || !y) return;
            const ctx = chart.ctx;

            // 임계 수평선 (주의=주황 / 위험=빨강)
            const t = (typeof GAS_THRESHOLDS !== 'undefined')
                ? GAS_THRESHOLDS[chart.config._gasKey] : null;
            if (t) {
                const hline = (val, color) => {
                    if (val == null) return;
                    const py = y.getPixelForValue(val);
                    if (py < area.top || py > area.bottom) return;
                    ctx.save();
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 1;
                    ctx.setLineDash([4, 3]);
                    ctx.beginPath();
                    ctx.moveTo(area.left, py);
                    ctx.lineTo(area.right, py);
                    ctx.stroke();
                    ctx.restore();
                };
                hline(t.warn, 'rgba(245,158,11,0.85)');
                hline(t.danger, 'rgba(239,68,68,0.85)');
            }

            // '현재' 정적 경계선 — 실측/예측 분기 인덱스 (옅게)
            const ni = chart.config._nowIndex;
            if (ni != null) {
                const px = x.getPixelForValue(ni);
                ctx.save();
                ctx.strokeStyle = 'rgba(148,163,184,0.45)';
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(px, area.top);
                ctx.lineTo(px, area.bottom);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = 'rgba(148,163,184,0.7)';
                ctx.font = '9px sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText('현재', px, area.top + 9);
                ctx.restore();
            }

            // 커서 추종 수직선 — 호버 시, 잘 보이게 흰 실선
            const act = (chart.tooltip && chart.tooltip.getActiveElements)
                ? chart.tooltip.getActiveElements() : [];
            if (act.length) {
                const px = act[0].element.x;
                ctx.save();
                ctx.strokeStyle = 'rgba(255,255,255,0.92)';
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(px, area.top);
                ctx.lineTo(px, area.bottom);
                ctx.stroke();
                ctx.restore();
            }
        },
    };
    if (typeof Chart !== 'undefined') Chart.register(forecastOverlayPlugin);

    // ══════════════════════════════════════════════════════
    // 헬퍼
    // ══════════════════════════════════════════════════════
    // 현재 측정값의 위험도 — 임계치 기준 danger/warning/normal
    function levelForValue(gas, v) {
        const t = (typeof GAS_THRESHOLDS !== 'undefined') ? GAS_THRESHOLDS[gas] : null;
        if (v == null || !t) return 'normal';
        if (t.reverse) {
            return v < t.danger ? 'danger'
                 : v < t.warn ? 'warning'
                 : (t.high && v > t.high) ? 'warning' : 'normal';
        }
        return v >= t.danger ? 'danger' : v >= t.warn ? 'warning' : 'normal';
    }

    // Date → 'yyyy-MM-DD HH:mm:ss'
    function fmtDateTime(d) {
        const p = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
             + `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
    }

    // ══════════════════════════════════════════════════════
    // 채널 1개 예측 차트 렌더 (destroy 후 재생성)
    // ══════════════════════════════════════════════════════
    function renderChannelChart(gas, ch, intervalSec) {
        const canvas = document.getElementById(`fc-chart-${gas}`);
        if (!canvas) return;
        const t = (typeof GAS_THRESHOLDS !== 'undefined') ? (GAS_THRESHOLDS[gas] || {}) : {};
        const unit = (typeof GAS_META !== 'undefined' && GAS_META[gas]) ? GAS_META[gas].unit : '';

        const past = Array.isArray(ch.past) ? ch.past : [];
        const fmean = Array.isArray(ch.forecast_mean) ? ch.forecast_mean : [];
        const clo = Array.isArray(ch.ci_lower) ? ch.ci_lower : [];
        const chi = Array.isArray(ch.ci_upper) ? ch.ci_upper : [];
        const N = past.length, H = fmean.length, total = N + H;
        if (total === 0) return;
        const nowIndex = N > 0 ? N - 1 : 0;
        const hasCI = H > 0 && clo.length === H && chi.length === H;

        // 절대 시각 배열 (툴팁 제목용) — 과거는 실측 t, 미래는 케이던스 외삽
        const baseMs = N > 0 ? new Date(past[N - 1].t).getTime() : Date.now();
        const times = [];
        for (let i = 0; i < total; i++) {
            times.push(i < N ? new Date(past[i].t)
                             : new Date(baseMs + (i - nowIndex) * intervalSec * 1000));
        }

        // 데이터셋 값 — 측정/예측은 nowIndex에서 한 점을 공유해 시각적으로 이어짐
        const actual = [], forecast = [], ciUp = [], ciLo = [];
        for (let i = 0; i < total; i++) {
            actual.push(i < N ? past[i].v : null);
            if (i < nowIndex) {
                forecast.push(null); ciUp.push(null); ciLo.push(null);
            } else if (i === nowIndex) {
                const v = N > 0 ? past[nowIndex].v : null;
                forecast.push(v); ciUp.push(v); ciLo.push(v);
            } else {
                const k = i - N;
                forecast.push(fmean[k] != null ? fmean[k] : null);
                ciUp.push(hasCI && chi[k] != null ? chi[k] : null);
                ciLo.push(hasCI && clo[k] != null ? clo[k] : null);
            }
        }

        // y축 — 임계치 기준 프레이밍: 정상/주의/위험 3구역이 항상 보이게
        const all = [];
        actual.concat(forecast).forEach(v => { if (v != null) all.push(v); });
        const dataMax = all.length ? Math.max(...all) : (t.warn || 100);
        // 값 기준(가스별 상대) 프레이밍 — 정상값이면 초록 위주(+상단 주의 띠),
        // 값이 임계에 가까워질수록 노랑·빨강 구역이 확대돼 현재 위험도를 반영.
        // reverse(O2)는 저농도가 위험이라 max(정상상한) 기준을 유지.
        const cap = (t.max || (t.danger || 100) * 1.5) * 1.1;
        const yMax = t.reverse
            ? Math.max(t.max || 26, Math.min(dataMax * 1.1, cap))
            : Math.max(dataMax * 1.25, (t.warn || t.danger || 100) * 1.4);

        // 데이터셋 구성 (측정 실선 → 예측 점선) — 신뢰구간(CI) 밴드는 표시 안 함
        const HOVER_PT = {
            pointHoverBackgroundColor: '#3b82f6',
            pointHoverBorderColor: '#ffffff',
            pointHoverBorderWidth: 2,
        };
        const datasets = [];
        datasets.push(Object.assign({
            label: '측정 농도', data: actual, order: 1,
            borderColor: '#e2e8f0', borderWidth: 1.6, tension: 0.25, fill: false,
            pointRadius: 0, pointHoverRadius: 5,
        }, HOVER_PT));
        datasets.push(Object.assign({
            label: 'AI 예측', data: forecast, order: 2,
            // 과거(실측)는 실선, nowIndex 이후 예측 구간은 점선
            borderColor: '#f59e0b', borderWidth: 1.8, borderDash: [5, 4],
            tension: 0.25, fill: false, pointRadius: 0, pointHoverRadius: 5,
        }, HOVER_PT));

        if (forecastCharts[gas]) forecastCharts[gas].destroy();

        const config = {
            type: 'line',
            data: { labels: times.map((_, i) => i), datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 250 },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        filter: it => it.dataset.label === '측정 농도'
                                   || it.dataset.label === 'AI 예측',
                        callbacks: {
                            title: items => items.length ? fmtDateTime(times[items[0].dataIndex]) : '',
                            label: c => {
                                if (c.parsed.y == null) return null;
                                // nowIndex의 예측 연결점은 중복이므로 제외
                                if (c.dataset.label === 'AI 예측' && c.dataIndex <= nowIndex) return null;
                                const kind = c.dataIndex > nowIndex ? '예상' : '측정';
                                return `해당 시간 ${kind} 농도   ${c.parsed.y.toFixed(2)} ${unit}`;
                            },
                        },
                        backgroundColor: 'rgba(22,27,34,0.95)',
                        borderColor: '#2a3448', borderWidth: 1,
                        titleColor: '#94a3b8', bodyColor: '#e2e8f0',
                        titleFont: { size: 10 }, bodyFont: { size: 11, weight: 'bold' },
                        padding: 10, displayColors: false,
                    },
                },
                scales: {
                    x: { display: false },
                    y: {
                        min: 0, max: yMax,
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { color: '#4b5563', font: { size: 9 }, maxTicksLimit: 6 },
                        border: { color: 'rgba(255,255,255,0.1)' },
                    },
                },
            },
        };
        // 플러그인용 메타 — Chart.js v4는 config를 Config 래퍼로 감싼다. 생성 '전'에
        // config._X 를 넣으면 chart.config._config 로 들어가 플러그인(chart.config._X)에서
        // 안 보여 zone·임계선이 그려지지 않는다. 반드시 생성 '후' chart.config 에 부착 + redraw.
        const chart = new Chart(canvas, config);
        chart.config._gasKey = gas;            // zoneBackgroundPlugin / 임계선
        chart.config._isForecast = true;       // forecastOverlayPlugin 게이트
        chart.config._nowIndex = nowIndex;     // '현재' 경계선 = 실측/예측 분기 인덱스
        chart.update('none');
        forecastCharts[gas] = chart;

        // '현재 농도' 배지 + 카드 테두리 — 현재 측정값 기준 3색
        const cur = N > 0 ? past[N - 1].v : null;
        const lvl = levelForValue(gas, cur);
        const badge = document.getElementById(`fc-badge-${gas}`);
        if (badge) {
            badge.textContent = `현재 농도 : ${cur != null ? cur.toFixed(2) : '—'} ${unit}`;
            badge.className = `fc-current-badge fc-current-badge--${lvl}`;
        }
        const card = document.getElementById(`fc-card-${gas}`);
        if (card) card.className = `gas-chart-card forecast-card gas-chart-card--${lvl}`;
    }

    // ══════════════════════════════════════════════════════
    // 데이터 로드 — 현재 선택된 가스 장비의 예측 조회
    // ══════════════════════════════════════════════════════
    async function loadForecast() {
        const tab = document.getElementById('tab-ai');
        if (!tab || !tab.classList.contains('active')) return;  // 보이는 동안만 렌더
        if (typeof gasSensors === 'undefined' || !gasSensors.length) return;
        const device = gasSensors[gasCurrentIndex];
        if (!device || typeof DeviceAPI === 'undefined') return;

        try {
            const res = await DeviceAPI.getForecast(device.id);
            const data = res.data || {};
            const intervalSec = data.interval_seconds || 60;
            const byType = {};
            (data.channels || []).forEach(c => { byType[c.sensor_type] = c; });
            Object.keys(GAS_META).forEach(gas => {
                if (byType[gas]) renderChannelChart(gas, byType[gas], intervalSec);
            });
        } catch (e) {
            console.error('AI 예측 로드 실패:', e);
        }
    }

    // ══════════════════════════════════════════════════════
    // 카드 골격 (최초 1회) — canvas 9개 생성
    // ══════════════════════════════════════════════════════
    function initAiForecastGrid() {
        if (aiGridInitialized) return;
        const grid = document.getElementById('ai-forecast-grid');
        if (!grid || typeof GAS_META === 'undefined') return;

        grid.innerHTML = Object.keys(GAS_META).map(gas => `
            <div class="gas-chart-card forecast-card" id="fc-card-${gas}" data-gas="${gas}">
                <div class="gas-chart-card__header">
                    <span class="gas-chart-card__name">• ${GAS_META[gas].formula}(${GAS_META[gas].name})</span>
                    <span class="fc-current-badge" id="fc-badge-${gas}">현재 농도 : —</span>
                </div>
                <div class="gas-chart-card__canvas-wrap">
                    <canvas id="fc-chart-${gas}"></canvas>
                </div>
            </div>`
        ).join('');

        aiGridInitialized = true;
        if (!pollTimer) pollTimer = setInterval(loadForecast, POLL_MS);
    }

    // 탭 전환 — AI 탭이면 그리드 lazy-init + 범례 노출 + 즉시 로드
    function onTabClick(tab) {
        const legend = document.querySelector('.chart-legend');
        if (tab === 'ai') {
            initAiForecastGrid();
            if (legend) legend.classList.add('show-forecast');
            loadForecast();
        } else if (legend) {
            legend.classList.remove('show-forecast');
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        // gas_detail 페이지에만 존재 — 없으면 무시
        if (!document.getElementById('ai-forecast-grid')) return;

        document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
            btn.addEventListener('click', () => onTabClick(btn.dataset.tab));
        });
    });
})();
