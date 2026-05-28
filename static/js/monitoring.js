/**
 * monitoring.js — monitoring 앱 공통 상수 및 유틸리티
 * gas_detail.js, power_detail.js, dashboard.js에서 공통으로 사용
 */

window.GAS_META = {
    co:  { name: "일산화탄소", formula: "CO",  unit: "ppm" },
    h2s: { name: "황화수소",   formula: "H₂S", unit: "ppm" },
    co2: { name: "이산화탄소", formula: "CO₂", unit: "ppm" },
    o2:  { name: "산소",       formula: "O₂",  unit: "%"   },
    no2: { name: "이산화질소", formula: "NO₂", unit: "ppm" },
    so2: { name: "이산화황",   formula: "SO₂", unit: "ppm" },
    o3:  { name: "오존",       formula: "O₃",  unit: "ppm" },
    nh3: { name: "암모니아",   formula: "NH₃", unit: "ppm" },
    voc: { name: "VOC",        formula: "VOC", unit: "ppm" },
};

// Phase D M2-8 — 전력 3 sensor 메타 (ai_power_predict.js / power_forecast.js 공유)
window.POWER_META = {
    voltage: { name: "전압", formula: "V", unit: "V" },
    current: { name: "전류", formula: "A", unit: "A" },
    power:   { name: "전력", formula: "W", unit: "W" },
};

// 위험도 → CSS 클래스명
window.LEVEL_CLASS = {
    "위험": "danger",
    "주의": "warning",
    "정상": "normal",
};

// ── 임계치 전역 (기본값 — DB 로드 전 fallback) ─────────────────────
window._DEFAULT_GAS_THRESHOLDS = {
    co:  { warn: 25,    danger: 200,   max: 300,   reverse: false },
    h2s: { warn: 10,    danger: 15,    max: 25,    reverse: false },
    co2: { warn: 1000,  danger: 5000,  max: 6000,  reverse: false },
    o2:  { warn: 18,    danger: 16,    max: 25,    reverse: true, high: 23.5 },
    no2: { warn: 3,     danger: 5,     max: 10,    reverse: false },
    so2: { warn: 2,     danger: 5,     max: 10,    reverse: false },
    o3:  { warn: 0.06,  danger: 0.12,  max: 0.2,   reverse: false },
    nh3: { warn: 25,    danger: 35,    max: 50,    reverse: false },
    voc: { warn: 0.5,   danger: 1.0,   max: 1.5,   reverse: false },
};

// 페이지 로드 즉시 기본값으로 초기화 (DB 로드 완료 전에도 차트가 깨지지 않도록)
window.GAS_THRESHOLDS    = { ...window._DEFAULT_GAS_THRESHOLDS };
window.POWER_LOAD_WARN   = 50;   // 전력 부하율 주의 임계치 (%)
window.POWER_LOAD_DANGER = 75;   // 전력 부하율 위험 임계치 (%)

/**
 * DB에서 활성 임계치 정책을 조회하여 전역 변수 갱신
 *  - gas_detail.js → initGasWidget() 진입 시 호출
 *  - power_detail.js → initPowerWidget() 진입 시 호출
 * DB 조회 실패 시 기본값(_DEFAULT_GAS_THRESHOLDS / POWER_LOAD_*) 유지
 */
window.loadThresholdsFromDB = async function () {
    try {
        const res = await fetch('/monitoring/api/threshold-policies/?is_active=true&limit=200');
        if (!res.ok) return;
        const json = await res.json();
        const policies = json.results ?? json;

        const gas = { ...window._DEFAULT_GAS_THRESHOLDS };
        let warnLoad   = 50;
        let dangerLoad = 75;

        policies.forEach(p => {
            const mc    = (p.metric_code || '').toLowerCase();
            const scope = p.scope || '';

            // scope가 비어있으면 전체 적용 (폴백), 아니면 '실시간 관제' 포함 여부 확인
            if (scope !== '' && !scope.includes('실시간 관제')) return;

            // ── 유해가스 임계치 ──────────────────────────────────────
            if (p.category === 'TH_GAS' && mc in gas) {
                const prev = gas[mc];
                if (p.condition === '이하' || p.condition === '미만') {
                    // O2 등 역방향: warning_min / danger_min 사용
                    gas[mc] = {
                        ...prev,
                        ...(p.warning_min != null ? { warn:   p.warning_min } : {}),
                        ...(p.danger_min  != null ? { danger: p.danger_min  } : {}),
                    };
                } else {
                    // 일반 가스 (이상/초과): warning_max / danger_max 사용
                    const newDanger = p.danger_max  ?? prev.danger;
                    const newWarn   = p.warning_max ?? prev.warn;
                    gas[mc] = {
                        ...prev,
                        warn:   newWarn,
                        danger: newDanger,
                        max:    Math.max(newDanger * 1.5, prev.max ?? 0),
                    };
                }
            }

            // ── 전력 부하율 임계치 (metric_code = 'load_rate') ──────
            if (p.category === 'TH_POWER' && mc === 'load_rate') {
                if (p.warning_max != null) warnLoad   = p.warning_max;
                if (p.danger_max  != null) dangerLoad = p.danger_max;
            }
        });

        window.GAS_THRESHOLDS    = gas;
        window.POWER_LOAD_WARN   = warnLoad;
        window.POWER_LOAD_DANGER = dangerLoad;
        console.log('[Thresholds] DB 임계치 로드 완료 ✓');
    } catch (e) {
        console.warn('[Thresholds] DB 임계치 로드 실패 → 기본값 사용:', e);
    }
};