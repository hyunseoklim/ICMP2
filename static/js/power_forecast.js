/**
 * power_forecast.js — 전력 'AI 예측' 탭 (power_detail 페이지)
 *
 * Phase D M2-5 (2026-05-23) — gas_forecast.js 패턴 미러.
 * gas는 1 device × 9 sensor 고정. power는 1 channel × 3 sensor 단위라
 * *채널 페이저*로 채널 선택 후 3 sensor 카드 그리드 표시.
 *
 * 데이터 흐름:
 *   ChannelAPI.getForecast(channelId) → /channels/{id}/forecast/
 *   응답: { device_uid, channel_code, channel_name, rated_power_w,
 *           interval_seconds, sensors: [...3개] }
 *
 * 의존:
 *   - POWER_META (monitoring.js 전역) — sensor 메타 (name/unit/formula)
 *   - computePowerThresholds (ai_power_predict.js에서 window 노출)
 *   - power_detail.js의 currentChannels 전역 (활성 채널 리스트)
 */
(function () {
    'use strict';

    const POLL_MS = 60000;
    const POWER_ORDER = ['voltage', 'current', 'power'];

    let aiGridInitialized = false;
    let forecastCharts = {};      // sensor_type → Chart 인스턴스
    let pollTimer = null;
    let channelIndex = 0;          // 현재 선택된 채널 (currentChannels 배열 인덱스)

    // ══════════════════════════════════════════════════════
    // Chart.js 플러그인 — 임계 수평선 + '현재' 경계선
    // ══════════════════════════════════════════════════════
    const powerForecastOverlayPlugin = {
        id: 'powerForecastOverlay',
        afterDatasetsDraw(chart) {
            if (!chart.config._isForecast) return;
            const area = chart.chartArea;
            const x = chart.scales.x, y = chart.scales.y;
            if (!area || !x || !y) return;
            const ctx = chart.ctx;
            const t = chart.config._thresholds;

            // 임계 수평선
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
                if (t.both) {
                    hline(t.warn_high, 'rgba(245,158,11,0.85)');
                    hline(t.danger_high, 'rgba(239,68,68,0.85)');
                    hline(t.warn_low, 'rgba(245,158,11,0.85)');
                    hline(t.danger_low, 'rgba(239,68,68,0.85)');
                }
            }

            // '현재' 정적 경계선 — 실측/예측 경계
            const nowIndex = chart.config._nowIndex;
            if (nowIndex != null) {
                const px = x.getPixelForValue(nowIndex);
                if (px >= area.left && px <= area.right) {
                    ctx.save();
                    ctx.strokeStyle = 'rgba(255,255,255,0.18)';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([2, 3]);
                    ctx.beginPath();
                    ctx.moveTo(px, area.top);
                    ctx.lineTo(px, area.bottom);
                    ctx.stroke();
                    ctx.restore();
                }
            }
        },
    };

    // ── 배경 구역 (위험/주의) 플러그인 ──
    // 정상 구간은 fill 없음 (배경 그대로 노출). 양방향(voltage)도 위/아래 모두 fill.
    const powerForecastZonePlugin = {
        id: 'powerForecastZone',
        beforeDraw(chart) {
            if (!chart.config._isForecast) return;
            const t = chart.config._thresholds;
            if (!t) return;
            const { ctx, chartArea: area, scales: { y } } = chart;
            if (!area || !y) return;

            const clamp = v => Math.max(area.top, Math.min(area.bottom, y.getPixelForValue(v)));
            const W = area.right - area.left;
            const DANGER_FILL = 'rgba(239,68,68,0.22)';
            const WARN_FILL = 'rgba(245,158,11,0.18)';

            if (t.both) {
                // 양방향: 상단 위험/주의 + 하단 주의/위험
                const dHi = clamp(t.danger_high);
                const wHi = clamp(t.warn_high);
                const wLo = clamp(t.warn_low);
                const dLo = clamp(t.danger_low);
                ctx.fillStyle = DANGER_FILL;
                ctx.fillRect(area.left, area.top, W, dHi - area.top);
                ctx.fillRect(area.left, dLo, W, area.bottom - dLo);
                ctx.fillStyle = WARN_FILL;
                ctx.fillRect(area.left, dHi, W, wHi - dHi);
                ctx.fillRect(area.left, wLo, W, dLo - wLo);
            } else {
                // 단방향: 상단 위험 + 그 아래 주의 (정상은 fill 없음)
                const dangerY = t.danger != null ? clamp(t.danger) : area.top;
                const warnY = t.warn != null ? clamp(t.warn) : area.top;
                ctx.fillStyle = DANGER_FILL;
                ctx.fillRect(area.left, area.top, W, dangerY - area.top);
                ctx.fillStyle = WARN_FILL;
                ctx.fillRect(area.left, dangerY, W, warnY - dangerY);
            }
        },
    };

    // ── Hover 수직 가이드 막대 플러그인 ──
    // tooltip 활성 시 마우스 X 위치에 흰 세로선 그림 (Chart.js 기본은 점 호버만).
    const powerForecastHoverPlugin = {
        id: 'powerForecastHover',
        afterDatasetsDraw(chart) {
            if (!chart.config._isForecast) return;
            const tip = chart.tooltip;
            if (!tip || !tip._active || tip._active.length === 0) return;
            const x = tip._active[0].element.x;
            const area = chart.chartArea;
            if (x < area.left || x > area.right) return;
            const ctx = chart.ctx;
            ctx.save();
            ctx.strokeStyle = 'rgba(255,255,255,0.55)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, area.top);
            ctx.lineTo(x, area.bottom);
            ctx.stroke();
            ctx.restore();
        },
    };

    if (typeof Chart !== 'undefined') {
        Chart.register(powerForecastOverlayPlugin);
        Chart.register(powerForecastZonePlugin);
        Chart.register(powerForecastHoverPlugin);
    }

    // ── 센서별 '정상' 기준점 — 정상대비% 계산용 ──
    // voltage: 220V nominal / current: 정격 부하 전류 / power: 정격 부하
    function normalReference(sensorType, rated_w) {
        if (sensorType === 'voltage') return 220;
        if (sensorType === 'current') return rated_w / 220;
        return rated_w;  // power
    }

    // ── y 값의 zone 분류 (양방향/단방향 공용) ──
    function zoneOf(val, t) {
        if (val == null || !t) return 'normal';
        if (t.both) {
            if (val >= t.danger_high || val <= t.danger_low) return 'danger';
            if (val >= t.warn_high || val <= t.warn_low) return 'warning';
            return 'normal';
        }
        if (val >= t.danger) return 'danger';
        if (val >= t.warn) return 'warning';
        return 'normal';
    }

    // ── 분 단위 ETA 포맷 — null/0 가드 ──
    function fmtEtaMinutes(eta_step, intervalSec) {
        if (eta_step == null) return '—';
        const mins = Math.max(0, Math.round(eta_step * intervalSec / 60));
        return `${mins} 분 뒤`;
    }

    // ── HH:MM 포맷 (X축 라벨용) ──
    function fmtHM(d) {
        const dt = (d instanceof Date) ? d : new Date(d);
        const pad = n => String(n).padStart(2, '0');
        return `${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
    }

    // ── 외부 HTML 툴팁 핸들러 ──
    // Chart.js 기본 툴팁을 끄고 .pfc-tooltip-card 를 동적으로 띄운다.
    // 카드별로 하나의 div를 canvas 부모에 lazy 생성·재사용.
    function externalTooltipHandler(ctx) {
        const { chart, tooltip } = ctx;
        const parent = chart.canvas.parentNode;
        if (!parent) return;
        let tipEl = parent.querySelector(':scope > .pfc-tooltip-card');
        if (!tipEl) {
            parent.style.position = parent.style.position || 'relative';
            tipEl = document.createElement('div');
            tipEl.className = 'pfc-tooltip-card';
            parent.appendChild(tipEl);
        }
        if (!tooltip || tooltip.opacity === 0) {
            tipEl.style.opacity = '0';
            return;
        }
        const meta = chart._tooltipMeta || {};
        const dp = tooltip.dataPoints && tooltip.dataPoints[0];
        const i = dp ? dp.dataIndex : meta.nowIndex;
        const ts = (meta.times && meta.times[i]) ? fmtDateTime(meta.times[i]) : '';
        const maxStr = (meta.maxForecast != null)
            ? `${meta.maxForecast.toFixed(2)} ${meta.unit}`
                + (meta.normalRatio != null ? ` (정상 대비 ${meta.normalRatio}%)` : '')
            : '—';
        tipEl.innerHTML = `
            <div class="pfc-tooltip-card__ts">${ts}</div>
            <div class="pfc-tooltip-card__row">
                <span class="pfc-tooltip-card__label">위험 도달 예상 시간</span>
                <span class="pfc-tooltip-card__value">${meta.etaText}</span>
            </div>
            <div class="pfc-tooltip-card__row">
                <span class="pfc-tooltip-card__label">예측 구간 내 예상 최대</span>
                <span class="pfc-tooltip-card__value">${maxStr}</span>
            </div>
        `;
        // 위치 — 차트 오른쪽 절반에 마우스가 있으면 좌측에 표시 (겹침 방지)
        const cw = chart.width || chart.canvas.clientWidth;
        const tx = tooltip.caretX, ty = tooltip.caretY;
        const placeLeft = tx > cw * 0.5;
        tipEl.style.opacity = '1';
        tipEl.style.left = (placeLeft ? Math.max(8, tx - tipEl.offsetWidth - 14) : tx + 14) + 'px';
        tipEl.style.top = Math.max(8, ty - tipEl.offsetHeight / 2) + 'px';
    }

    function fmtDateTime(d) {
        const dt = (d instanceof Date) ? d : new Date(d);
        const pad = n => String(n).padStart(2, '0');
        return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ` +
               `${pad(dt.getHours())}:${pad(dt.getMinutes())}:${pad(dt.getSeconds())}`;
    }

    // ── 등급 — value 기준 (위젯과 일치) ──
    function levelForValue(sensorType, val, thresholds) {
        if (val == null) return 'normal';
        const t = thresholds[sensorType];
        if (!t) return 'normal';
        if (t.both) {
            if (val >= t.danger_high || val <= t.danger_low) return 'danger';
            if (val >= t.warn_high || val <= t.warn_low) return 'warning';
            return 'normal';
        }
        if (val >= t.danger) return 'danger';
        if (val >= t.warn) return 'warning';
        return 'normal';
    }

    // ── 채널별 sensor 차트 렌더 ──
    function renderSensorChart(sensorType, s, intervalSec, rated_w) {
        const canvas = document.getElementById(`pfc-chart-${sensorType}`);
        if (!canvas) return;

        const meta = (typeof POWER_META !== 'undefined') ? POWER_META[sensorType] : null;
        const unit = meta ? meta.unit : '';
        const thresholds = window.computePowerThresholds(rated_w);
        const t = thresholds[sensorType] || {};

        const past = Array.isArray(s.past) ? s.past : [];
        const fmean = Array.isArray(s.forecast_mean) ? s.forecast_mean : [];
        // CI(신뢰구간)는 디자인 사양 외 요소 — 차트에서 제거 (API 응답은 유지).
        // 표시했을 때 ci_upper가 yMax를 부풀려 zone 밴드가 차트 좁은 구역에 압축됐다.
        const N = past.length, H = fmean.length, total = N + H;
        if (total === 0) return;
        const nowIndex = N > 0 ? N - 1 : 0;

        // 시간 배열 (툴팁용)
        const baseMs = N > 0 ? new Date(past[N - 1].t).getTime() : Date.now();
        const times = [];
        for (let i = 0; i < total; i++) {
            times.push(i < N ? new Date(past[i].t)
                             : new Date(baseMs + (i - nowIndex) * intervalSec * 1000));
        }

        // 데이터셋 — 측정/예측 두 라인만
        const actual = [], forecast = [];
        for (let i = 0; i < total; i++) {
            actual.push(i < N ? past[i].v : null);
            if (i < nowIndex) {
                forecast.push(null);
            } else if (i === nowIndex) {
                forecast.push(N > 0 ? past[nowIndex].v : null);
            } else {
                forecast.push(fmean[i - N] != null ? fmean[i - N] : null);
            }
        }

        // y축 — 임계 밴드가 차트 절반 이상을 차지하도록 산정.
        // 측정·예측 평균만 dataMax에 반영 (CI 제거).
        const all = [];
        actual.concat(forecast).forEach(v => { if (v != null) all.push(v); });
        const dataMax = all.length ? Math.max(...all) : 1;
        let yMin, yMax;
        if (t.both) {
            // 양방향 (voltage): 위/아래 위험 임계 모두 보이도록 ±15 마진
            yMin = Math.max(0, (t.danger_low ?? 170) - 15);
            yMax = (t.danger_high ?? 270) + 15;
        } else {
            // 단방향 (current/power): 위험 임계가 항상 차트 상단의 80~90% 지점에 오도록
            yMin = 0;
            yMax = Math.max(dataMax * 1.10, (t.danger || 0) * 1.15);
        }

        const datasets = [];
        datasets.push({
            label: '측정', data: actual, order: 1,
            borderColor: '#e2e8f0', borderWidth: 1.6, tension: 0.25, fill: false,
            pointRadius: 0, pointHoverRadius: 5,
            pointHoverBackgroundColor: '#22d3ee',
            pointHoverBorderColor: '#ffffff',
            pointHoverBorderWidth: 2,
        });
        // 예측 라인 — segment.borderColor로 구간별 색 분기.
        // 두 endpoint의 y 평균으로 zone 판정 (정상=흰, 주의=주황, 위험=빨강).
        const ZONE_COLOR = { normal: '#e2e8f0', warning: '#f59e0b', danger: '#ef4444' };
        datasets.push({
            label: 'AI 예측', data: forecast, order: 2,
            borderColor: ZONE_COLOR.normal,  // 기본값 — segment 콜백이 우선 적용
            borderWidth: 1.8, borderDash: [5, 4],
            tension: 0.25, fill: false, pointRadius: 0, pointHoverRadius: 5,
            pointHoverBackgroundColor: '#22d3ee',
            pointHoverBorderColor: '#ffffff',
            pointHoverBorderWidth: 2,
            segment: {
                borderColor: ctx => {
                    const y0 = ctx.p0.parsed.y, y1 = ctx.p1.parsed.y;
                    if (y0 == null || y1 == null) return ZONE_COLOR.normal;
                    const mid = (y0 + y1) / 2;
                    return ZONE_COLOR[zoneOf(mid, t)] || ZONE_COLOR.normal;
                },
            },
        });

        if (forecastCharts[sensorType]) forecastCharts[sensorType].destroy();

        // 예측 구간 내 최대값 (정상대비% 계산용) — null 안전
        const fmeanClean = fmean.filter(v => v != null);
        const forecastMax = fmeanClean.length ? Math.max(...fmeanClean) : null;
        const normalRef = normalReference(sensorType, rated_w);
        const normalRatio = (forecastMax != null && normalRef > 0)
            ? Math.round(forecastMax / normalRef * 100) : null;

        const config = {
            type: 'line',
            data: { labels: times.map((_, i) => i), datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                animation: { duration: 250 },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    // 기본 tooltip 비활성화 — external HTML 카드로 대체 (S5).
                    tooltip: {
                        enabled: false,
                        external: externalTooltipHandler,
                    },
                },
                scales: {
                    x: {
                        display: true,
                        grid: { display: false },
                        ticks: {
                            color: '#4b5563', font: { size: 9 }, maxTicksLimit: 6,
                            autoSkip: true,
                            callback: function (val) {
                                // labels가 숫자 인덱스이므로 times[i]에서 HH:MM 포맷
                                const i = typeof val === 'number' ? val : Number(this.getLabelForValue(val));
                                return Number.isFinite(i) && times[i] ? fmtHM(times[i]) : '';
                            },
                        },
                        border: { color: 'rgba(255,255,255,0.1)' },
                    },
                    y: {
                        min: yMin, max: yMax,
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { color: '#4b5563', font: { size: 9 }, maxTicksLimit: 6 },
                        border: { color: 'rgba(255,255,255,0.1)' },
                    },
                },
            },
        };
        config._isForecast = true;
        config._nowIndex = nowIndex;
        // plugin에서 sensor별 임계 lookup이 어려우니 직접 sensor 임계 객체 부착
        config._thresholds = t;

        // 외부 툴팁은 Chart.js v4의 config 래퍼 통과 문제를 피하기 위해
        // chart 인스턴스 자체에 메타 부착 (config가 아닌 인스턴스 프로퍼티).
        const chart = new Chart(canvas, config);
        chart._tooltipMeta = {
            times, unit, intervalSec,
            etaText: fmtEtaMinutes(s.danger_eta_step, intervalSec),
            maxForecast: forecastMax,
            normalRatio,
            sensorType,
            nowIndex,
        };
        forecastCharts[sensorType] = chart;

        // '현재 값' 배지 + 카드 테두리
        const cur = N > 0 ? past[N - 1].v : null;
        const lvl = levelForValue(sensorType, cur, thresholds);
        const badge = document.getElementById(`pfc-badge-${sensorType}`);
        if (badge) {
            badge.textContent = `현재 : ${cur != null ? cur.toFixed(2) : '—'} ${unit}`;
            badge.className = `pfc-current-badge pfc-current-badge--${lvl}`;
        }
        const card = document.getElementById(`pfc-card-${sensorType}`);
        if (card) card.className = `power-chart-card forecast-card power-chart-card--${lvl}`;
    }

    // ── 카드 골격 생성 (최초 1회) — 3 카드 ──
    function initAiForecastGrid() {
        if (aiGridInitialized) return;
        const grid = document.getElementById('power-ai-forecast-grid');
        if (!grid || typeof POWER_META === 'undefined') return;

        grid.innerHTML = POWER_ORDER.map(st => {
            const m = POWER_META[st] || {};
            return `
            <div class="power-chart-card forecast-card" id="pfc-card-${st}" data-sensor="${st}">
                <div class="power-chart-card__header">
                    <span class="power-chart-card__name">• ${m.formula || ''}(${m.name || st})</span>
                    <span class="pfc-current-badge" id="pfc-badge-${st}">현재 : —</span>
                </div>
                <div class="power-chart-card__canvas-wrap">
                    <canvas id="pfc-chart-${st}"></canvas>
                </div>
            </div>`;
        }).join('');

        aiGridInitialized = true;
        if (!pollTimer) pollTimer = setInterval(loadForecast, POLL_MS);
    }

    // ── 채널 페이저 ──
    function renderChannelPager() {
        const wrap = document.getElementById('power-ai-channel-pager');
        if (!wrap) return;
        if (typeof currentChannels === 'undefined' || !currentChannels.length) {
            wrap.innerHTML = '<span class="muted">활성 채널 없음</span>';
            return;
        }
        const ch = currentChannels[channelIndex] || currentChannels[0];
        wrap.innerHTML = `
            <button type="button" id="power-ai-ch-prev" class="ai-pager-btn">&#8249;</button>
            <span class="ai-pager-label">${ch.channel_name || ch.channel_code} · 정격 ${ch.rated_power_w}W</span>
            <span class="ai-pager-page">${channelIndex + 1} / ${currentChannels.length}</span>
            <button type="button" id="power-ai-ch-next" class="ai-pager-btn">&#8250;</button>
        `;
        document.getElementById('power-ai-ch-prev')?.addEventListener('click', () => {
            channelIndex = (channelIndex - 1 + currentChannels.length) % currentChannels.length;
            renderChannelPager();
            loadForecast();
        });
        document.getElementById('power-ai-ch-next')?.addEventListener('click', () => {
            channelIndex = (channelIndex + 1) % currentChannels.length;
            renderChannelPager();
            loadForecast();
        });
    }

    // ── 데이터 로드 ──
    async function loadForecast() {
        const tab = document.getElementById('tab-ai');
        if (!tab || !tab.classList.contains('active')) return;
        if (typeof currentChannels === 'undefined' || !currentChannels.length) return;

        const ch = currentChannels[channelIndex] || currentChannels[0];
        if (!ch || !ch.id) {
            // currentChannels에 id가 없으면 channel_code로 ChannelAPI 조회 필요 — 후속 보강
            console.warn('[power_forecast] channel id 없음 — currentChannels 구조 확인');
            return;
        }

        try {
            const res = await ChannelAPI.getForecast(ch.id);
            const data = res.data || {};
            const intervalSec = data.interval_seconds || 60;
            const ratedW = data.rated_power_w || ch.rated_power_w || window.DEFAULT_RATED_W || 1000;

            const byType = {};
            (data.sensors || []).forEach(s => { byType[s.sensor_type] = s; });
            POWER_ORDER.forEach(st => {
                if (byType[st]) renderSensorChart(st, byType[st], intervalSec, ratedW);
            });
        } catch (e) {
            console.error('전력 AI 예측 로드 실패:', e);
        }
    }

    // ── 탭 전환 핸들러 ──
    function onTabClick(tab) {
        const legend = document.querySelector('.chart-legend');
        if (tab === 'ai') {
            initAiForecastGrid();
            renderChannelPager();
            if (legend) legend.classList.add('show-forecast');
            loadForecast();
        } else if (legend) {
            legend.classList.remove('show-forecast');
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!document.getElementById('power-ai-forecast-grid')) return;

        document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
            btn.addEventListener('click', () => onTabClick(btn.dataset.tab));
        });
    });
})();
