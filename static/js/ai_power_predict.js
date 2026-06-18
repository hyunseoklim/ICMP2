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
    let ratedW = window.DEFAULT_RATED_W ?? 1000;
    let page = 0;
    let chart = null;

    // ── POWER_THRESHOLDS 동적 계산 (rated_w 기반) — power_forecast.js와 공유 ──
    // 부하율 임계치는 window.POWER_LOAD_WARN / POWER_LOAD_DANGER 사용 (관리자 설정 반영)
    function computePowerThresholds(rated_w) {
        const warnPct   = (window.POWER_LOAD_WARN   ?? 50)  / 100;
        const dangerPct = (window.POWER_LOAD_DANGER ?? 75) / 100;
        return {
            voltage: {
                warn_high: 240, danger_high: 260,
                warn_low: 200, danger_low: 180,
                max: 270, min: 170, reverse: false, both: true,
            },
            current: {
                warn:    rated_w / 220 * warnPct,
                danger:  rated_w / 220 * dangerPct,
                max:     rated_w / 220 * 1.2,
                reverse: false,
            },
            power: {
                warn:    rated_w * warnPct,
                danger:  rated_w * dangerPct,
                max:     rated_w * 1.2,
                reverse: false,
            },
        };
    }
    window.computePowerThresholds = computePowerThresholds;

    // ── 최근 데이터가 있는 power 채널 선택 ──
    // 과거: channels[0](DB 삽입순 = slave01 압연기A)을 고정 선택 → 스토리 데이터가
    // 들어오는 slave61(충전스테이션A)이 아닌 무데이터 채널이 노출됐다.
    // 개선: 장비별 channel-latest reading 중 measured_at이 가장 최신인 채널을 선택.
    async function pickNearbyPowerChannel() {
        const dev_res = await DeviceAPI.getList({ device_type: 'power', is_active: true });
        const devices = dev_res.data.results || dev_res.data || [];
        if (!devices.length) return null;
        devices.sort((a, b) => a.device_uid.localeCompare(b.device_uid));

        // 모든 장비의 채널별 최신 reading 중 가장 최신인 (device, channel_code) 탐색
        let best = null; // { device, channelCode, ts }
        for (const device of devices) {
            let latest = [];
            try {
                const lp = await DeviceAPI.getLatestPower(device.id);
                latest = lp.data || [];
            } catch (e) { /* 무데이터 장비 — 건너뜀 */ }
            for (const r of latest) {
                const ts = r.measured_at ? new Date(r.measured_at).getTime() : 0;
                if (!best || ts > best.ts) best = { device, channelCode: r.channel_code, ts };
            }
        }

        const device = best ? best.device : devices[0];
        const ch_res = await ChannelAPI.getList({ device: device.id, is_active: true });
        const channels = ch_res.data.results || ch_res.data || [];
        if (!channels.length) return null;
        // 최신 데이터 채널 매칭 — 없으면 첫 채널로 폴백
        const channel = (best && channels.find(c => c.channel_code === best.channelCode))
                        || channels[0];
        return { device, channel };
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

        // 부하율(%) — 채널 단위 지표(캐러셀 페이지와 무관). power 센서 현재값 / 정격.
        // power_detail의 calcLoadRate(power_w / rated_w * 100)와 동일 정의.
        const pwr = sensors.find(x => x.sensor_type === 'power');
        const pwrPast = pwr && Array.isArray(pwr.past) ? pwr.past : [];
        const curW = pwrPast.length ? pwrPast[pwrPast.length - 1].v : null;
        const loadPct = (curW != null && ratedW) ? (curW / ratedW * 100) : null;
        setText('aipw-load', loadPct != null ? `${loadPct.toFixed(1)}%` : '—');

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
