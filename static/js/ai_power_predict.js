/**
 * ai_power_predict.js — 메인 대시보드 'AI 예측 — 스마트 전력 시스템 위험' 위젯
 *
 * Phase D M2-4 (2026-05-23) — gas의 ai_gas_predict.js 패턴 미러.
 * 단 power는 channel × 3 sensor 단위라 *1 channel 3 sensor 캐러셀* 구조.
 *
 * 데이터 흐름:
 *   ChannelAPI.getForecast(channelId) → /channels/{id}/forecast/
 *   응답: { device_uid, channel_code, channel_name, rated_power_w,
 *           interval_seconds, sensors: [{sensor_type, past, forecast_mean, ...}] }
 *
 * 채널 선택 (TODO: 가장 위험한 채널 자동):
 *   현재는 첫 active power 채널을 선택 (자리표시).
 */
(function () {
    'use strict';

    const POLL_MS = 60000;
    const POWER_ORDER = ['voltage', 'current', 'power'];

    let selectedDevice = null;
    let selectedChannel = null;
    let sensors = [];
    let deviceName = '';
    let channelName = '';
    let intervalSec = 60;
    let ratedW = 1000;
    let page = 0;
    let chart = null;

    // ── POWER_THRESHOLDS 동적 계산 (rated_w 기반) — power_forecast.js와 공유 ──
    function computePowerThresholds(rated_w) {
        return {
            voltage: {
                warn_high: 240, danger_high: 260,
                warn_low: 200, danger_low: 180,
                max: 270, min: 170, reverse: false, both: true,
            },
            current: {
                warn: rated_w / 220 * 0.5,
                danger: rated_w / 220 * 0.75,
                max: rated_w / 220 * 1.2,
                reverse: false,
            },
            power: {
                warn: rated_w * 0.5,
                danger: rated_w * 0.75,
                max: rated_w * 1.2,
                reverse: false,
            },
        };
    }
    window.computePowerThresholds = computePowerThresholds;

    // ── 첫 활성 power 채널 선택 (자리표시 — 향후 '가장 위험' 채널) ──
    async function pickNearbyPowerChannel() {
        const dev_res = await DeviceAPI.getList({ device_type: 'power', is_active: true });
        const devices = dev_res.data.results || dev_res.data || [];
        if (!devices.length) return null;
        devices.sort((a, b) => a.device_uid.localeCompare(b.device_uid));
        const device = devices[0];

        const ch_res = await ChannelAPI.getList({ device: device.id, is_active: true });
        const channels = ch_res.data.results || ch_res.data || [];
        if (!channels.length) return null;
        // 첫 활성 채널 — 향후 부하율 기반 정렬로 교체 가능
        return { device, channel: channels[0] };
    }

    // ── 예측 호라이즌 → 라벨 ──
    function horizonLabel(steps, sec) {
        const totalMin = Math.round((steps || 0) * (sec || 0) / 60);
        if (totalMin <= 0) return '최대 예상 값';
        const span = totalMin >= 60 ? `${Math.round(totalMin / 60)}시간` : `${totalMin}분`;
        return `${span} 내 최대 예상 값`;
    }

    function setText(id, txt) {
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
    }

    // ── 페이지 렌더 ──
    function renderPage() {
        const s = sensors[page];
        if (!s) return;
        const meta = (typeof POWER_META !== 'undefined') ? POWER_META[s.sensor_type] : null;
        const unit = meta ? meta.unit : '';
        const name = meta ? meta.name : s.sensor_type.toUpperCase();

        setText('aipw-channel', `${name} (${channelName})`);
        setText('aipw-device', `📡 ${deviceName} · 정격 ${ratedW}W`);
        setText('aipw-page', `${page + 1} / ${sensors.length}`);

        const past = Array.isArray(s.past) ? s.past : [];
        const fmean = Array.isArray(s.forecast_mean) ? s.forecast_mean : [];
        const cur = past.length ? past[past.length - 1].v : null;
        const fvals = fmean.filter(v => v != null);
        const maxF = fvals.length ? Math.max(...fvals) : null;

        setText('aipw-current', cur != null ? `${cur.toFixed(1)} ${unit}` : '—');
        setText('aipw-max', maxF != null ? `${maxF.toFixed(1)} ${unit}` : '—');
        setText('aipw-max-label', horizonLabel(fmean.length, intervalSec));

        renderDots();
        renderChart(s.sensor_type, s);
    }

    function renderDots() {
        const wrap = document.getElementById('aipw-dots');
        if (!wrap) return;
        wrap.innerHTML = sensors.map((_, i) =>
            `<span class="ai-power-widget__dot${i === page ? ' ai-power-widget__dot--active' : ''}" data-i="${i}"></span>`
        ).join('');
        wrap.querySelectorAll('.ai-power-widget__dot').forEach(d => {
            d.addEventListener('click', () => { page = +d.dataset.i; renderPage(); });
        });
    }

    // ── 차트 렌더 — gas 패턴 단순 미러 (CI 음영 생략 — 위젯 컴팩트) ──
    function renderChart(sensorType, s) {
        const canvas = document.getElementById('aipw-chart');
        if (!canvas) return;

        const past = Array.isArray(s.past) ? s.past : [];
        const fmean = Array.isArray(s.forecast_mean) ? s.forecast_mean : [];
        const N = past.length, H = fmean.length, total = N + H;
        if (total === 0) return;
        const nowIndex = N > 0 ? N - 1 : 0;

        const baseMs = N > 0 ? new Date(past[N - 1].t).getTime() : Date.now();
        const times = [];
        for (let i = 0; i < total; i++) {
            times.push(i < N ? new Date(past[i].t)
                             : new Date(baseMs + (i - nowIndex) * intervalSec * 1000));
        }

        const actual = [], forecast = [];
        for (let i = 0; i < total; i++) {
            actual.push(i < N ? past[i].v : null);
            if (i < nowIndex) forecast.push(null);
            else if (i === nowIndex) forecast.push(N > 0 ? past[nowIndex].v : null);
            else forecast.push(fmean[i - N] != null ? fmean[i - N] : null);
        }

        const all = actual.concat(forecast).filter(v => v != null);
        const dataMax = all.length ? Math.max(...all) : 1;
        const t = computePowerThresholds(ratedW)[sensorType] || {};
        const yMax = t.danger ? Math.max(t.danger * 1.2, dataMax * 1.12) : dataMax * 1.15;

        if (chart) chart.destroy();
        chart = new Chart(canvas, {
            type: 'line',
            data: {
                labels: times.map((_, i) => i),
                datasets: [
                    {
                        label: '측정', data: actual,
                        borderColor: '#e2e8f0', borderWidth: 1.5, tension: 0.25, fill: false,
                        pointRadius: 0, pointHoverRadius: 4,
                    },
                    {
                        label: '예측', data: forecast,
                        borderColor: '#f59e0b', borderWidth: 1.6, borderDash: [5, 4],
                        tension: 0.25, fill: false, pointRadius: 0, pointHoverRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { display: false },
                    y: { min: 0, max: yMax },
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    // ── 폴링 ──
    async function poll() {
        if (!selectedChannel) {
            const picked = await pickNearbyPowerChannel();
            if (!picked) return;
            selectedDevice = picked.device;
            selectedChannel = picked.channel;
            deviceName = picked.device.device_name || picked.device.device_uid;
            channelName = picked.channel.channel_name || picked.channel.channel_code;
            ratedW = picked.channel.rated_power_w || 1000;
        }
        try {
            const res = await ChannelAPI.getForecast(selectedChannel.id);
            const data = res.data;
            intervalSec = data.interval_seconds || 60;
            sensors = POWER_ORDER
                .map(st => (data.sensors || []).find(s => s.sensor_type === st))
                .filter(Boolean);
            if (page >= sensors.length) page = 0;
            renderPage();
        } catch (e) {
            console.error('[ai_power_predict] poll error:', e);
        }
    }

    function init() {
        const widget = document.getElementById('ai-power-widget');
        if (!widget) return;

        document.getElementById('aipw-prev')?.addEventListener('click', () => {
            if (!sensors.length) return;
            page = (page - 1 + sensors.length) % sensors.length;
            renderPage();
        });
        document.getElementById('aipw-next')?.addEventListener('click', () => {
            if (!sensors.length) return;
            page = (page + 1) % sensors.length;
            renderPage();
        });

        poll();
        setInterval(poll, POLL_MS);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
