import http from 'k6/http';
import { check, sleep } from 'k6';

// 부하 단계: 실행 시 --vus, --duration 으로 덮어쓸 수 있음
export const options = {
  vus: 5,
  duration: '30s',
};

const BASE = 'http://localhost:8000';

export default function () {
  // 1) 디바이스 목록 조회 (가장 많이 쓰이는 API)
  const devices = http.get(`${BASE}/monitoring/api/devices/`);
  check(devices, { 'devices 200': (r) => r.status === 200 });

  // 2) 알람 이벤트 목록 조회
  const events = http.get(`${BASE}/alerts/api/events/`);
  check(events, { 'events 200': (r) => r.status === 200 });

  // 3) metrics 엔드포인트 (Prometheus 스크랩과 동일한 부하)
  const metrics = http.get(`${BASE}/metrics`);
  check(metrics, { 'metrics 200': (r) => r.status === 200 });

  sleep(1);
}
