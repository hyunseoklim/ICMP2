/**
 * ai_gas_predict.js — 메인 대시보드 'AI 예측 - 내 근처 유해가스 위험' 위젯
 *
 * gas_detail 'AI 예측' 탭의 압축·캐러셀 버전. Slice 1의 forecast 엔드포인트와
 * 전역 GAS_META·GAS_THRESHOLDS·zoneBackgroundPlugin(gas_detail.js 등록)을
 * 그대로 재사용한다 — 신규 백엔드 없음.
 */
(function () {
    'use strict';

    const POLL_MS = 60000;
    const GAS_ORDER = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc'];

    let selectedDevice = null;   // '내 근처' 장비 (1회 선택 후 캐시)
    let channels = [];           // forecast 응답 channels (GAS_ORDER 정렬)
    let deviceName = '';
    let intervalSec = 60;
    let page = 0;
    let chart = null;

    // ── '내 근처' 장비 선택 ───────────────────────────────────────────
    // TODO(내 근처): 작업자 위치 ↔ 센서 위치를 비교해 가장 가까운 가스
    //   센서를 고르도록 교체한다. 현재는 첫 가스 장비를 사용(자리표시).
    async function pickNearbyGasDevice() {
        const res = await DeviceAPI.getList({ device_type: 'gas', is_active: true });
        const list = res.data.results || res.data || [];
        list.sort((a, b) => a.device_uid.localeCompare(b.device_uid));
        return list[0] || null;
    }

    // ── 예측 호라이즌 → 라벨 (시간 범위를 데이터에서 파생) ─────────────
    // 엔진 예측 수평(forecast_mean 길이)이 바뀌면 라벨이 자동 갱신된다.
    // 12시간 예측이 가능해지면 여기 손대지 않아도 '12시간 내'로 표기됨.
    function horizonLabel(steps, sec) {
        const totalMin = Math.round((steps || 0) * (sec || 0) / 60);
        if (totalMin <= 0) return '최대 예상 농도';
        const span = totalMin >= 60 ? `${Math.round(totalMin / 60)}시간` : `${totalMin}분`;
        return `${span} 내 최대 예상 농도`;
    }

    function setText(id, txt) {
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
    }

    // ── 현재 페이지(채널) 렌더 ────────────────────────────────────────
    function renderPage() {
        const ch = channels[page];
        if (!ch) return;
        const gas = ch.sensor_type;
        const meta = (typeof GAS_META !== 'undefined') ? GAS_META[gas] : null;
        const unit = meta ? meta.unit : '';

        setText('aigw-channel', meta ? `${meta.formula}(${meta.name})` : gas.toUpperCase());
        setText('aigw-device', `📡 ${deviceName}`);
        setText('aigw-page', `${page + 1} / ${channels.length}`);

        const past = Array.isArray(ch.past) ? ch.past : [];
        const fmean = Array.isArray(ch.forecast_mean) ? ch.forecast_mean : [];
        const cur = past.length ? past[past.length - 1].v : null;
        const fvals = fmean.filter(v => v != null);
        const maxF = fvals.length ? Math.max(...fvals) : null;

        setText('aigw-current', cur != null ? `${cur.toFixed(1)} ${unit}` : '—');
        setText('aigw-max', maxF != null ? `${maxF.toFixed(1)} ${unit}` : '—');
        setText('aigw-max-label', horizonLabel(fmean.length, intervalSec));

        renderDots();
        renderChart(gas, ch);
    }

    function renderDots() {
        const wrap = document.getElementById('aigw-dots');
        if (!wrap) return;
        wrap.innerHTML = channels.map((_, i) =>
            `<span class="ai-gas-widget__dot${i === page ? ' ai-gas-widget__dot--active' : ''}" data-i="${i}"></span>`
        ).join('');
        wrap.querySelectorAll('.ai-gas-widget__dot').forEach(d => {
            d.addEventListener('click', () => { page = +d.dataset.i; renderPage(); });
        });
    }

    function renderChart(gas, ch) {
        const canvas = document.getElementById('aigw-chart');
        if (!canvas) return;
        const t = (typeof GAS_THRESHOLDS !== 'undefined') ? (GAS_THRESHOLDS[gas] || {}) : {};

        const past = Array.isArray(ch.past) ? ch.past : [];
        const fmean = Array.isArray(ch.forecast_mean) ? ch.forecast_mean : [];
        const N = past.length, H = fmean.length, total = N + H;
        if (total === 0) return;
        const nowIndex = N > 0 ? N - 1 : 0;

        // 측정/예측 — nowIndex 한 점 공유로 끊김 없이 연결
        const actual = [], forecast = [];
        for (let i = 0; i < total; i++) {
            actual.push(i < N ? past[i].v : null);
            if (i < nowIndex) forecast.push(null);
            else if (i === nowIndex) forecast.push(N > 0 ? past[nowIndex].v : null);
            else forecast.push(fmean[i - N] != null ? fmean[i - N] : null);
        }

        const all = actual.concat(forecast).filter(v => v != null);
        const dataMax = all.length ? Math.max(...all) : (t.danger || 100);
        const yMax = t.reverse
            ? Math.max(t.max || 26, dataMax * 1.1)
            : Math.max((t.danger || 0) * 1.2, dataMax * 1.12);

        if (chart) chart.destroy();
        const config = {
            type: 'line',
            data: {
                labels: actual.map((_, i) => i),
                datasets: [
                    {
                        label: '측정', data: actual,
                        borderColor: '#e2e8f0', borderWidth: 1.5,
                        pointRadius: 0, tension: 0.25, fill: false,
                    },
                    {
                        label: '예측', data: forecast,
                        borderColor: '#f59e0b', borderWidth: 1.8, borderDash: [5, 4],
                        pointRadius: 0, tension: 0.25, fill: false,
                        // 예측선: 위험 구역 진입 시 빨강, 그 외 주황
                        segment: {
                            borderColor: seg => {
                                const y = seg.p1.parsed.y;
                                const danger = t.reverse
                                    ? (t.danger != null && y <= t.danger)
                                    : (t.danger != null && y >= t.danger);
                                return danger ? '#ef4444' : '#f59e0b';
                            },
                        },
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 200 },
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: {
                    x: { display: false },
                    y: {
                        min: 0, max: yMax,
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { color: '#4b5563', font: { size: 8 }, maxTicksLimit: 5 },
                        border: { color: 'rgba(255,255,255,0.1)' },
                    },
                },
            },
        };
        chart = new Chart(canvas, config);
        // Chart.js v4: 생성 후 chart.config 에 부착해야 zoneBackgroundPlugin이 읽음
        // (생성 전 config._gasKey 는 chart.config._config 로 들어가 플러그인에서 안 보임)
        chart.config._gasKey = gas;   // zoneBackgroundPlugin 재사용 (정상/주의/위험 배경)
        chart.update('none');
    }

    // ── 데이터 로드 ───────────────────────────────────────────────────
    async function load() {
        if (typeof DeviceAPI === 'undefined') return;
        try {
            if (!selectedDevice) selectedDevice = await pickNearbyGasDevice();
            if (!selectedDevice) return;
            deviceName = selectedDevice.device_name || selectedDevice.device_uid;

            const res = await DeviceAPI.getForecast(selectedDevice.id);
            const data = res.data || {};
            intervalSec = data.interval_seconds || 60;

            const byType = {};
            (data.channels || []).forEach(c => { byType[c.sensor_type] = c; });
            channels = GAS_ORDER.filter(g => byType[g]).map(g => byType[g]);
            if (!channels.length) return;
            if (page >= channels.length) page = 0;
            renderPage();
        } catch (e) {
            console.error('AI 예측 위젯 로드 실패:', e);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!document.getElementById('ai-gas-widget')) return;  // 위젯 없는 페이지

        document.getElementById('aigw-prev')?.addEventListener('click', () => {
            if (!channels.length) return;
            page = (page - 1 + channels.length) % channels.length;
            renderPage();
        });
        document.getElementById('aigw-next')?.addEventListener('click', () => {
            if (!channels.length) return;
            page = (page + 1) % channels.length;
            renderPage();
        });

        load();
        setInterval(load, POLL_MS);
    });
})();
