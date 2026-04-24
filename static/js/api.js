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
  baseURL: '/api/v1',
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

/* ── 엔드포인트 헬퍼 ───────────────────────────── */

const SafetyAPI = {
  // 작업자
  getWorkerStats:  ()       => API.get('/workers/stats/'),
  getWorkers:      (params) => API.get('/workers/', { params }),
  getWorkerDetail: (id)     => API.get(`/workers/${id}/`),

  // 유해가스
  getGasReadings:  (sensorId) => API.get('/gas/readings/', { params: { sensor: sensorId } }),
  getGasPredict:   (sensorId) => API.get('/gas/predict/', { params: { sensor: sensorId } }),
  getGasSensors:   ()         => API.get('/gas/sensors/'),

  // 전력
  getPowerStatus:  ()         => API.get('/power/status/'),
  getPowerPredict: (equipId)  => API.get('/power/predict/', { params: { equipment: equipId } }),
  getPowerHistory: (params)   => API.get('/power/history/', { params }),

  // 이벤트 / 알림
  getRecentEvents: (limit=20) => API.get('/events/', { params: { limit } }),
  acknowledgeEvent:(id)       => API.post(`/events/${id}/ack/`),

  // 나의 안전 확인
  getMySafety:     ()         => API.get('/safety/my/'),
  updateSafetyItem:(data)     => API.patch('/safety/my/', data),
};

// 전역 노출
window.SafetyAPI = SafetyAPI;
window.API = API;
