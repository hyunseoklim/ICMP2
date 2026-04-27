/**
 * api.js — 공통 Axios 인스턴스 및 API 헬퍼
 * Django CSRF 토큰 자동 첨부, 에러 인터셉터 포함
 */

// Django CSRF 쿠키에서 토큰 추출
function getCsrfToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (const c of cookies) {
        const [k, v] = c.trim().split('=');
        if (k === name) return decodeURIComponent(v);
    }
    return '';
}

const API = axios.create({
    baseURL: '/monitoring/api',
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
    },
});

// 요청 인터셉터: CSRF 토큰 자동 첨부
API.interceptors.request.use(config => {
    const method = config.method?.toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        config.headers['X-CSRFToken'] = getCsrfToken();
    }
    return config;
});

// 응답 인터셉터: 공통 에러 처리
API.interceptors.response.use(
    res => res,
    err => {
        const status = err.response?.status;
        if (status === 401) { window.location.href = '/accounts/login/'; }
        if (status === 403) { console.error('권한 없음'); }
        if (status >= 500)  { console.error('서버 오류:', err.response?.data); }
        return Promise.reject(err);
    }
);


/* ── monitoring: 장비 (Device) ─────────────────── */
const DeviceAPI = {
    getList:        (params)   => API.get('/devices/', { params }),
    getDetail:      (id)       => API.get(`/devices/${id}/`),
    create:         (data)     => API.post('/devices/', data),
    update:         (id, data) => API.put(`/devices/${id}/`, data),
    delete:         (id)       => API.delete(`/devices/${id}/`),
    getChannels:    (id)       => API.get(`/devices/${id}/channels/`),
    getLatestGas:   (id)       => API.get(`/devices/${id}/latest_gas/`),
    getLatestPower: (id)       => API.get(`/devices/${id}/latest_power/`),
    getStatusLogs:  (id)       => API.get(`/devices/${id}/status_logs/`),
    getInspections: (id)       => API.get(`/devices/${id}/inspections/`),
};

/* ── monitoring: 채널 (DeviceChannel) ──────────── */
const ChannelAPI = {
    getList: (params)    => API.get('/channels/', { params }),
    update:  (id, data)  => API.put(`/channels/${id}/`, data),
    patch:   (id, data)  => API.patch(`/channels/${id}/`, data),
};

/* ── monitoring: 유해가스 측정값 (GasReading) ───── */
const GasReadingAPI = {
    getList: (params) => API.get('/gas-readings/', { params }),
};

/* ── monitoring: 전력 측정값 (PowerReading) ─────── */
const PowerReadingAPI = {
    getList: (params) => API.get('/power-readings/', { params }),
};

/* ── monitoring: 전력 ON/OFF 상태 ───────────────── */
const PowerStatusAPI = {
    getList: (params) => API.get('/power-status-readings/', { params }),
};

/* ── monitoring: 임계치 정책 (ThresholdPolicy) ───── */
const ThresholdAPI = {
    getList: (params)    => API.get('/threshold-policies/', { params }),
    update:  (id, data)  => API.put(`/threshold-policies/${id}/`, data),
};

/* ── monitoring: 점검 이력 (InspectionLog) ─────── */
const InspectionAPI = {
    getList:   (params)   => API.get('/inspections/', { params }),
    create:    (data)     => API.post('/inspections/', data),
    update:    (id, data) => API.put(`/inspections/${id}/`, data),
    getAction: (id)       => API.get(`/inspections/${id}/action_log/`),
};

/* ── monitoring: 조치 이력 (ActionLog) ─────────── */
const ActionAPI = {
    create: (data)     => API.post('/actions/', data),
    update: (id, data) => API.put(`/actions/${id}/`, data),
};

/* ── 다른 앱 API (각 담당자가 baseURL 별도 설정 필요) ── */
// 아래는 기존 SafetyAPI 유지 (accounts/facilities/alerts/safety 담당자용)
// baseURL이 /monitoring/api라서 실제로는 각 담당자가 axios 인스턴스를 별도로 만들어야 함

const SafetyAPI = {
    // 작업자 (facilities 담당)
    getWorkerStats:  ()       => axios.get('/facilities/api/workers/stats/'),
    getWorkers:      (params) => axios.get('/facilities/api/workers/', { params }),
    getWorkerDetail: (id)     => axios.get(`/facilities/api/workers/${id}/`),

    // 이벤트/알림 (alerts 담당)
    getRecentEvents:  (limit=20) => axios.get('/alerts/api/events/', { params: { limit } }),
    acknowledgeEvent: (id)       => axios.post(`/alerts/api/events/${id}/ack/`),

    // 나의 안전 확인 (safety 담당)
    getMySafety:      ()     => axios.get('/safety/api/my/'),
    updateSafetyItem: (data) => axios.patch('/safety/api/my/', data),
};


/* ── 전역 노출 ──────────────────────────────────── */
window.API             = API;
window.DeviceAPI       = DeviceAPI;
window.ChannelAPI      = ChannelAPI;
window.GasReadingAPI   = GasReadingAPI;
window.PowerReadingAPI = PowerReadingAPI;
window.PowerStatusAPI  = PowerStatusAPI;
window.ThresholdAPI    = ThresholdAPI;
window.InspectionAPI   = InspectionAPI;
window.ActionAPI       = ActionAPI;
window.SafetyAPI       = SafetyAPI;