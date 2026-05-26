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