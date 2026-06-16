# ICMP2 — 산업 현장 통합 관제 플랫폼

산업 현장의 가스 농도, 전력 상태, 작업자 위치를 실시간으로 수집·판단해 위험 상황을 사전에 감지하는 통합 안전 관제 시스템입니다.

---

## 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [기술 스택](#기술-스택)
3. [시스템 아키텍처](#시스템-아키텍처)
4. [디렉터리 구조](#디렉터리-구조)
5. [주요 기능](#주요-기능)
6. [데이터 흐름](#데이터-흐름)
7. [WebSocket 채널](#websocket-채널)
8. [API 엔드포인트](#api-엔드포인트)
9. [설치 및 실행](#설치-및-실행)
10. [테스트](#테스트)
11. [환경 설정](#환경-설정)
12. [앱별 설명](#앱별-설명)
13. [기술문서](./기술문서.pdf)

---

## 프로젝트 개요

현장에서 발생하는 가스 누출, 전력 이상, 작업자 위험 구역 진입은 **사고가 발생한 후에야 인지**되는 구조적 문제가 있습니다.

ICMP2는 센서 데이터, 위치 정보, 판단 로직을 하나의 화면에서 실시간으로 연결해 **사전 감지 → 알람 발생 → 알림 발송**까지의 흐름을 자동화하며, AI 기반 이상 탐지와 예측 경보로 임계값 초과 이전에 위험을 예고합니다.

| 항목 | 내용 |
|---|---|
| 언어 | Python 3.x |
| 백엔드 | Django 6.0.4 + Daphne (ASGI) |
| 데이터 생성 / AI 분석 | FastAPI 0.135.1 (독립 실행) |
| 실시간 통신 | Django Channels 4.3.2 + Redis |
| 비동기 처리 | Celery 5.6.2 + Celery Beat |
| 프론트엔드 | Django Templates + Leaflet.js + Chart.js |
| DB | PostgreSQL 15 (Docker) / SQLite (로컬 개발) |
| 모니터링 | Prometheus + Grafana + Alertmanager |
| 배포 | Docker Compose / Kubernetes (Minikube) |

---

## 기술 스택

```
Django 6.0.4        웹 프레임워크 (REST API + 비즈니스 로직)
Daphne 4.2.1        ASGI 서버 (HTTP + WebSocket 동시 처리)
Django Channels     WebSocket 그룹 관리
channels-redis      Redis 기반 Channel Layer
FastAPI 0.135.1     가짜 데이터 생성 및 AI 분석 전담 서버
Celery 5.6.2        비동기 태스크 (알람 발송, 누락 감지, 데이터 보존)
Redis 7.x           WebSocket 메시지 브로커 / Celery 브로커·캐시
PostgreSQL 15       운영 데이터베이스
scikit-learn 1.8    Isolation Forest 기반 이상 탐지
statsmodels         ARIMA 기반 예측 경보
ruptures            Change Point Detection
Prometheus          메트릭 수집 (django-prometheus + FastAPI instrumentator)
Grafana             메트릭 대시보드
Alertmanager        Prometheus 알림 라우팅
Pushgateway         단명(short-lived) Celery worker 메트릭 수집 (K8s)
Leaflet.js          공장 도면 기반 지도 + 지오펜스 렌더링
Chart.js            가스·전력 실시간 시계열 차트
DRF 3.16.0          REST API 프레임워크
```

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│               FastAPI 서버 (:8001)                            │
│  가짜 센서값 생성 (60초 간격)                                     │
│  가스 9종 / 전력 34채널 (장비 3대) / 작업자 위치 5명                 │
└──────────────────┬───────────────────────────────────────────┘
                   │ 가스: Celery 태스크 직접 큐잉 (ingest_gas_task → Redis)
                   │ 전력·위치·노드: HTTP POST (REST API)
                   ▼
┌──────────────────────────────────────────────────────────────┐
│     Django + Daphne ASGI (:8000) / Celery Worker (가스)       │
│  ① 데이터 수신 → DB 저장 (PostgreSQL)                           │
│  ② 임계값 비교 + 지오펜스 판단                                     │
│  ③ AI 분석: Isolation Forest(동기) / ARIMA(forecast 큐)         │
│  ④ AlarmEvent 생성 (5분 중복 방지)                               │
│  ⑤ channel_layer.group_send() → Redis                        │
│  ⑥ Celery 태스크 위임 (알람 발송 등)                              │
└──────────────────┬───────────────────────────────────────────┘
       ┌───────────┤────────────────────────────┐
       │           │                            │
  WebSocket    Redis :6379               Celery Workers
  (ws://)   (Channel Layer +          ┌─ worker (default)
       │     Pub/Sub + Broker)        ├─ forecast (AI 예측)
       ▼                              └─ events (Floor/FloorGrid 치수 변경, IndexGrid 재생성 시)
┌──────────────────┐          Celery Beat
│  프론트엔드         │            ├─ 누락 장비 감지 (1분)
│  Chart.js        │            └─ 데이터 보존 (매일 03:00)
│  Leaflet         │
│  WebSocket 수신   │
└──────────────────┘

┌──────────────────────────────────────────────────────────────┐
│            모니터링 스택                                        │
│  Prometheus (:9090) ← Django / FastAPI / Redis / PostgreSQL  │
│                     ← Pushgateway (Celery worker 메트릭, K8s)  │
│  Alertmanager (:9093) ← Prometheus 알림 라우팅                  │
│  Grafana (:3000) ← 메트릭 대시보드                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 디렉터리 구조

```
ICMP2/
├── config/                 # Django 프로젝트 설정
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py             # Daphne ASGI 진입점
│   ├── celery.py           # Celery 앱 + Beat 스케줄
│   └── wsgi.py
│
├── accounts/               # 사용자 인증 및 권한
├── facilities/             # 시설·층·지오펜스·작업자 위치
│   ├── services/           # geofence_checker, 그리드 생성·검증·좌표 변환
│   ├── repositories/       # IndexGrid 읽기/쓰기
│   ├── signals.py          # Floor/FloorGrid 변경 감지 → Celery 태스크 큐잉
│   └── tasks.py            # handle_floor_grid_changed / handle_floor_dimensions_changed (events 큐)
├── monitoring/             # 가스·전력 센서 및 임계값 관리
│   ├── ai/                 # Isolation Forest(이상 탐지) + ARIMA(예측) 모듈 (가스·전력)
│   └── anomaly/            # Z-Score / 슬라이딩 윈도우 / Change Point
├── alerts/                 # 알람 규칙 및 이벤트 라이프사이클
│   └── tasks.py            # 가스 인제스트(ingest_gas_task)·ARIMA 예측·알람 발송·누락 감지·보존 정책 (Celery)
├── dashboard/              # 관제 대시보드 위젯·레이아웃
├── safety/                 # 안전 체크리스트 및 VR 교육
├── manager/                # 보고서 및 관리 기능
├── core/                   # 공통 모델·유틸리티
│   └── management/commands/seed.py   # 통합 시드 데이터 생성 (--flush / --section)
│
├── fastapi_app/            # 가짜 데이터 생성 서버 (FastAPI)
│   ├── main.py             # FastAPI 앱 + 데이터 루프
│   ├── fake_data.py        # 가스·전력·위치 더미 데이터 생성 함수
│   ├── routers/            # gas / power 라우터 (Phase 5 placeholder, 미구현)
│   ├── ai_engine/          # AI 모델 학습·검증·시나리오 생성용 (라이브 파이프라인 미연동)
│   │   ├── common/         # 공통 모듈 (Z-Score, ARIMA, IForest, Change Point)
│   │   ├── gas/            # 가스 이상 탐지·예측 (학습 스크립트용)
│   │   ├── power/          # 전력 이상 탐지·예측 (학습 스크립트용)
│   │   └── generator/      # 시나리오 기반 데이터 생성기
│   ├── adapters/           # ORM ↔ 데이터 변환
│   └── sender.py           # Django REST API 비동기 POST 클라이언트 (httpx)
│
├── prometheus/             # Prometheus 설정 + 알림 규칙
├── alertmanager/           # Alertmanager 설정
├── grafana/                # Grafana 대시보드 프로비저닝
├── k8s/                    # Kubernetes 매니페스트
│
├── static/
│   ├── css/
│   │   ├── facility/       # 시설·지도 화면 스타일
│   │   └── map/
│   └── js/
│       ├── map/            # Leaflet 지도 관련 JS
│       ├── admin/          # 관리자 화면 JS
│       ├── common/         # 공통 유틸
│       └── websocket.js
│
├── templates/              # Django HTML 템플릿
├── media/                  # 업로드 파일 (도면 이미지 등)
├── docker-compose.yml      # 전체 스택 (DB, Redis, Django, FastAPI, Celery, 모니터링)
├── Dockerfile
├── Dockerfile.fastapi
├── entrypoint.sh
├── setup.sh                # 초기 환경 설정 스크립트
├── k6_icmp2_test.js        # k6 부하 테스트 스크립트
├── manage.py
└── requirements.txt
```

---

## 주요 기능

### 1. 실시간 가스 센서 모니터링

- 9종 가스 (CO, H₂S, CO₂, O₂, NO₂, SO₂, O₃, NH₃, VOC) 60초 주기 수신
- 임계값 초과 시 자동 알람 생성 (`ThresholdPolicy`(DB) 우선, 없으면 `DEFAULT_THRESHOLDS` 폴백)
- O₂는 역방향 판단 (낮을수록 위험: 16% 미만 → 위험, 16~18% → 경고, 23.5% 초과 → 경고·기준 미정 임시 처리)

| 가스 | 경고 임계값 | 위험 임계값 |
|---|---|---|
| CO | 25 ppm | 200 ppm |
| H₂S | 10 ppm | 15 ppm |
| CO₂ | 1,000 ppm | 5,000 ppm |
| O₂ | 16~18% 또는 23.5% 초과 | < 16% |

### 2. 전력 채널 모니터링

- 32개 채널 (PWR-001 16채널 / PWR-002 8채널 / PWR-003 8채널) 실시간 전류·전압·전력 수신
- 정격 대비 부하율로 위험 판단: 75% 이상 → 위험, 50~75% → 경고
- 통신 오류(-1) 및 OFF 상태 자동 감지

### 3. 작업자 위치 추적 + 지오펜스

- 5명 작업자 위치 60초 주기 업데이트 (±2m 상태 기반 이동)
- 지오펜스 판단:
  - **원형:** 거리 공식으로 내부 판단
  - **다각형:** 레이 캐스팅 알고리즘
  - 우선순위: 위험(danger) > 경고(warning) > 안전(safe)
- 오프듀티 작업자는 지오펜스 판단 생략

### 4. 자동 지오펜스 생성

- 가스 임계값 초과 시 해당 센서 주변에 원형 위험 구역 자동 생성
  - 위험 수준: 반경 5.0m
  - 경고 수준: 반경 3.0m
- 가스 정상화 시 자동 비활성화
- 이름 형식: `[자동] {센서명}`

### 5. 알람 이벤트 관리

알람 규칙 타입 5종:

| RuleType | 설명 |
|---|---|
| `threshold` | 임계값 초과 |
| `missing` | 데이터 누락 (1분 주기 감지) |
| `power` | 전력 이상 |
| `ai` | Isolation Forest 이상 탐지 |
| `forecast` | ARIMA 예측 경보 |

- 이벤트 상태 라이프사이클: `open → acknowledged → closed`
- **중복 방지:** 동일 디바이스 5분 이내 열린 이벤트 존재 시 신규 생성 안 함
- 이력 추적: 상태 변경마다 `EventHistory` 기록

### 6. AI 이상 탐지 · 예측 경보

- **Isolation Forest:** 가스 센서 9채널의 다변량 이상값 실시간 탐지 (전력 IF는 현재 비활성 — Phase D 결정)
- **ARIMA:** 가스·전력 시계열 기반 단기 예측 → 임계 도달 예상 시 예측 경보 발생 (forecast 전용 큐)
- **Z-Score / 슬라이딩 윈도우 / Change Point Detection:** 보조 이상 징후 판단
- AI 탐지 결과는 `AlarmEvent`(`severity: anomaly / predictive_warning`)로 생성

### 7. Celery 비동기 처리

| 태스크 | 큐 | 주기 |
|---|---|---|
| 가스 데이터 인제스트 (`ingest_gas_task`) | default | FastAPI 발행 (60초) |
| 알람 이벤트 발송 (Slack / Discord / WebSocket) | default | 이벤트 트리거 시 |
| AI ARIMA 예측 (가스 / 전력) | forecast | 데이터 수신 시 |
| 누락 장비 감지 | default | 60초 |
| 시설 이벤트 처리 (IndexGrid 재생성·캐시 무효화) | events | Floor/FloorGrid 변경 시 |
| 데이터 보존 정책 실행 | default | 매일 03:00 |

### 8. 알림 발송 (Slack / Discord)

- `AlarmPolicy` + `NotificationTemplate`으로 채널별 메시지 포맷 관리
- `AlarmSendHistory`에 발송 결과(성공/실패/지연) 기록
- 폴백 템플릿 내장 → DB 레코드 없어도 동작

### 9. 관제 대시보드

- WebSocket 수신으로 새로고침 없이 차트 실시간 갱신
- Leaflet 지도: 공장 도면 기반 커스텀 CRS (픽셀↔미터 직접 매핑)
- 레이어 분리: 작업자 / 장비 / 가스센서 / 전력장치 / 지오펜스 / 그리드

### 10. Prometheus + Grafana 모니터링

- Django / FastAPI 요청 메트릭 (`django-prometheus`, `prometheus-fastapi-instrumentator`)
- Redis 큐 적체 메트릭 (`redis-exporter`)
- PostgreSQL 메트릭 (`postgres-exporter`)
- 커스텀 메트릭: 알람 이벤트 건수, AI 예측 처리 시간, Celery 태스크 완료 건수
- Celery worker 메트릭: 단명 worker 프로세스라 직접 스크랩 대신 태스크 완료 시 **Pushgateway**로 push (`PUSHGATEWAY_URL` 설정 시 동작 — 현재 K8s 환경에만 배포)
- Alertmanager를 통한 임계 알림 라우팅 (시스템 장애 → Discord)

---

## 데이터 흐름

```
[FastAPI]
  가스 데이터 생성 (60초)
      │
      │ Celery send_task('alerts.tasks.ingest_gas_task')  ← Redis 브로커 직접 큐잉
      │ Payload: {device_uid, measured_at, co, h2s, co2, o2, no2, so2, o3, nh3, voc}
      ▼
[Celery Worker - alerts/tasks.py::ingest_gas_task]
  monitoring/services.py::process_gas_ingest() 실행
  GasReading DB 저장
  임계값 비교 (check_gas_thresholds)
      │
      ├─ 임계값 초과 → AlarmEvent 생성 (5분 중복 방지)
      │   └─ Celery 태스크 → Slack/Discord/WebSocket 발송
      ├─ 자동 지오펜스 업데이트 (update_geofence_from_gas)
      │
      └─ channel_layer.group_send("floor_{id}_sensor", {...})
              │
              │ Redis Channel Layer
              ▼
[WebSocket Consumer - facilities/consumers.py::SensorConsumer]
  ws://host/ws/floor/{floor_id}/sensor/
      │
      ▼
[프론트엔드]
  onmessage → Chart.js 차트 갱신

---

[Celery Worker - process_gas_ingest()] (이어서)
  STEP F: Isolation Forest 이상 탐지 (동기, monitoring/ai/gas_if.py)
      └─ 이상 시 AlarmEvent(severity=anomaly) 생성
  STEP G: forecast_gas_task.delay() → Celery forecast 큐
      └─ ARIMA 예측 → 임계 도달 예상 시 AlarmEvent(severity=predictive_warning) 생성

---

[FastAPI]
  작업자 위치 생성 (60초)
      │
      │ POST /facilities/api/worker-locations/dummy/
      │ Body: {worker_id, x, y, floor_id}
      ▼
[Django - facilities/views.py]
  WorkerLocation DB 저장
  sync_worker_status() 호출 → 지오펜스 판단
  Worker.safety_status 업데이트
      │
      └─ channel_layer.group_send("floor_{id}_worker", {...})
              │
              ▼
[프론트엔드]
  onmessage → Leaflet 마커 위치 갱신
```

---

## WebSocket 채널

층(floor) 단위 채널 3개와 전역 알람 채널 1개로 분리됩니다.

| 채널 그룹 | URL 패턴 | 전달 데이터 |
|---|---|---|
| `floor_{id}_sensor` | `ws/floor/<floor_id>/sensor/` | 가스·전력 수치, 위험 수준 |
| `floor_{id}_worker` | `ws/floor/<floor_id>/worker/` | 작업자 위치, 안전 상태 |
| `floor_{id}_geofence` | `ws/floor/<floor_id>/geofence/` | 지오펜스 생성·변경·삭제 |
| `alerts` / `system_alerts` | `ws/alerts/` | 전역 알람 팝업 (system_alerts는 관리자 전용) |

---

## API 엔드포인트

### 모니터링 (Monitoring)

```
GET    /monitoring/api/devices/                        장비 목록 (device_type 필터)
POST   /monitoring/api/gas-readings/                   가스 데이터 직접 수신 (FastAPI는 Celery 큐 사용)
POST   /monitoring/api/power-readings/                 전력 데이터 수신 (FastAPI → Django)
POST   /monitoring/api/node-readings/                  노드 데이터 수신 (FastAPI → Django)
GET    /monitoring/api/threshold-policies/             임계값 정책 목록
PATCH  /monitoring/api/threshold-policies/{id}/        임계값 수정
```

### 시설 (Facilities)

```
GET    /facilities/api/facilities/                     시설 목록
GET    /facilities/api/buildings/?facility_id={id}     건물 목록
GET    /facilities/api/floors/?building_id={id}        층 목록
GET    /facilities/api/geofences/?floor_id={id}        지오펜스 목록
POST   /facilities/api/geofences/                      지오펜스 생성
GET    /facilities/api/workers/                        작업자 목록
POST   /facilities/api/worker-locations/dummy/         위치 데이터 수신 (FastAPI → Django)
GET    /facilities/api/sensor-locations/?floor_id={id} 센서 위치 목록
```

### 알람 (Alerts)

```
GET    /alerts/api/events/                             알람 이벤트 목록 (status 필터)
GET    /alerts/api/events/{id}/                        이벤트 상세 + 이력
POST   /alerts/api/events/{id}/change-status/          상태 변경 (acknowledged / closed)
GET    /alerts/api/recent/                             최근 5분 열린 알람 (대시보드 폴링용)
```

### 계정 (Accounts)

```
POST   /accounts/login/                                로그인
POST   /accounts/logout/                               로그아웃
GET    /accounts/profile/                              현재 사용자 프로필
```

### FastAPI ↔ Django 데이터 계약

```json
// 가스 데이터 — HTTP가 아닌 Celery 태스크 페이로드로 전달
// celery.send_task('alerts.tasks.ingest_gas_task', args=[payload])
{
  "device_uid": "GAS-001",
  "measured_at": "2026-06-11T09:00:00+09:00",
  "co": 18.4,
  "h2s": 2.1,
  "o2": 20.5,
  "co2": 412.0,
  "no2": 0.1,
  "so2": 0.2,
  "o3": 0.05,
  "nh3": 1.2,
  "voc": 0.3
}

// 작업자 위치
POST /facilities/api/worker-locations/dummy/
{
  "worker_id": 1,
  "x": 23.5,
  "y": 14.2,
  "floor_id": 1
}

// WebSocket 서버 → 프론트엔드
{
  "type": "sensor.update",
  "data": { "device_uid": "GAS-001", "co": 18.4, "danger_level": "normal" }
}
```

---

## 설치 및 실행

### 사전 요구사항

- Docker + Docker Compose (권장)
- 또는 Python 3.10+ + Redis 7.x (로컬 실행 시)

### Docker Compose 실행 (권장)

```bash
# 저장소 클론
git clone <repo-url>
cd ICMP2

# 환경 변수 파일 작성
cp .env.example .env   # DB_USER, DB_PASSWORD, DB_NAME, REDIS_HOST 등 설정

# 전체 스택 실행
# (PostgreSQL, Redis, Django, FastAPI, Celery workers, Prometheus, Grafana, Alertmanager)
docker compose up --build
```

| 서비스 | 주소 |
|---|---|
| Django (관제 화면) | http://localhost:8000 |
| FastAPI (AI 엔진) | http://localhost:8001 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
| Alertmanager | http://localhost:9093 |

### 로컬 직접 실행

```bash
# 가상환경 생성 및 의존성 설치
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# DB 마이그레이션
python manage.py migrate

# (선택) 초기 시드 데이터 생성
python manage.py seed              # 전체 시드 (--flush: DB 초기화 후, --section: 부분 시드)
```

서버 5개를 **각각 별도 터미널**에서 실행합니다.

```bash
# 터미널 1 — Redis
redis-server

# 터미널 2 — Django (Daphne ASGI)
python manage.py runserver

# 터미널 3 — FastAPI (가짜 데이터 + AI 분석)
uvicorn fastapi_app.main:app --host 0.0.0.0 --port 8001 --reload

# 터미널 4 — Celery Worker (default + forecast + events 큐 통합 처리)
celery -A config worker -Q celery,forecast,events --loglevel=info
# Docker Compose에서는 큐별로 worker 3개 분리 실행 (celery / celery-forecast / celery-events)

# 터미널 5 — Celery Beat (스케줄러)
celery -A config beat --loglevel=info
```

---

## 테스트

핵심 알람 파이프라인 로직(임계값 판단, AlarmEvent 생성/중복방지/자동종료, 이벤트 상태 전이, Celery TaskLog 추적)에 대한 회귀 테스트가 `alerts`, `monitoring` 앱에 있습니다.

```bash
docker compose exec django python manage.py test alerts monitoring
```

---

## 환경 설정

### Redis 연결

[config/settings.py](config/settings.py)에서 Redis 호스트/포트를 수정합니다.

```python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [(os.environ.get('REDIS_HOST', 'redis'), 6379)],
        },
    },
}
```

### 데이터베이스

기본값은 PostgreSQL(Docker)입니다. 로컬 SQLite로 전환하려면 `settings.py`의 `DATABASES`를 수정합니다.

### 알림 웹훅

```bash
# .env — 애플리케이션 알람 이벤트 발송
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...      # 알람 이벤트 발송 (AlarmEvent → Slack)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...     # 알람 이벤트 발송 (AlarmEvent → Discord)
# 알림 확인 초대 링크 
"디스코드 서버 초대 링크": https://discord.gg/NnbCTaGbKvv
"Slack" : https://join.slack.com/t/icmp2/shared_invite/zt-3yebkguky-57BhmlTnb0udZoHMBG75eA
```

> **Alertmanager 시스템 장애 알림**(Django/FastAPI 다운 등)은 위 앱 알람과 별개입니다.
> - Docker Compose: [alertmanager/alertmanager.yml](alertmanager/alertmanager.yml)의 `discord_configs` webhook으로 설정
> - Kubernetes: `ALERTMANAGER_DISCORD_WEBHOOK_URL` 시크릿을 init container가 주입 ([k8s/08-monitoring.yaml](k8s/08-monitoring.yaml))

### FastAPI → Django 전송 주소

[fastapi_app/sender.py](fastapi_app/sender.py)는 환경 변수 2개를 사용합니다.

- `DJANGO_BASE` (기본: `http://localhost:8000`) — 전력·위치·노드 HTTP POST 대상
- `REDIS_URL` (기본: `redis://localhost:6379/0`) — 가스 데이터 Celery 큐잉용 브로커

---

## 앱별 설명

### `accounts` — 사용자 인증

- 커스텀 User 모델 (`user_type`: admin / manager / worker)
- Position, Department, Role, UserRole, LoginHistory
- JWT 기반 인증 (`PyJWT`)

### `facilities` — 시설 및 위치

- 시설 → 건물 → 층 계층 구조
- `Geofence`: 원형·다각형 위험 구역 정의
- `WorkerLocation`: 실시간 작업자 좌표
- `services/geofence_checker.py`: 레이 캐스팅 + 거리 공식 기반 판단 로직
- `services/`: 그리드 생성·검증·좌표↔인덱스 변환·포인트 스내핑 등 그리드 서비스 모듈
- `repositories/`: IndexGrid 읽기/쓰기 분리
- `consumers.py`: WebSocket Consumer 3개 (worker / sensor / geofence)
- `signals.py` + `tasks.py`: Floor/FloorGrid 변경 시 signal에서 직접 큐잉되는 Celery 태스크 (`events` 큐) — IndexGrid 재생성, 캐시 무효화

### `monitoring` — 센서 데이터

- `Device`: 가스 / 전력 장비 등록
- `DeviceChannel`: 장비별 채널 정의
- `DeviceStatusLog`: 장비 상태 변경 이력
- `GasReading`: 9종 가스 측정값 저장
- `PowerStatusReading`: 전력 장비 ON/OFF·통신 상태
- `PowerReading`: 채널별 전류·전압·전력 저장
- `NodeReading`: 위치 노드 수신값 저장
- `ThresholdPolicy`: 가스 종류별 경고·위험 임계값 관리
- `services.py`: `calc_danger_level()`, `check_gas_thresholds()`
- `ai/`: Isolation Forest(`gas_if.py`, `power_if.py`) + ARIMA 예측(`gas_forecast.py`, `power_forecast.py`) 모듈
- `anomaly/`: Z-Score / 슬라이딩 윈도우 / Change Point Detection

### `alerts` — 알람 이벤트

- `RiskCriteria`: 위험 기준 색상·등급 정의
- `AlarmRule`: 규칙 정의 (threshold / missing / power / ai / forecast)
- `AlarmEvent`: 트리거된 이벤트 (open → acknowledged → closed)
- `EventHistory`: 상태 변경 이력
- `ForecastSnapshot`: AI 예측 스냅샷 저장
- `NotificationTemplate`: 채널별 알림 템플릿
- `TaskLog`: Celery 태스크 실행 상태 추적 (PENDING → STARTED → SUCCESS/FAILURE/RETRY)
- `services.py`: 임계값·전력·AI 알람 생성, 5분 중복 방지 로직
- `tasks.py`: 가스 인제스트(`ingest_gas_task`), ARIMA 예측(`forecast_gas_task` / `forecast_power_task`), 알람 발송 (Slack / Discord / WebSocket), 누락 감지, 데이터 보존

### `dashboard` — 관제 화면

- `DashboardWidget`: 위젯 타입·위치·크기 정의
- `DashboardLayout`: 역할(role)별 레이아웃 구성
- 메인 대시보드 WebSocket 수신 + Chart.js 렌더링

### `safety` — 안전 관리

- 안전 체크리스트 작성 및 이력 관리 (`SafetyCheckItem`, `SafetyCheckSession`, `SafetyCheckItemResult`)
- 사고 등록 및 추적 (`Incident`)
- 작업 허가서 관리 (`WorkPermit`)
- 위험성 평가 (`RiskAssessment`)
- 시정 조치 (`CorrectiveAction`)
- VR 교육 완료 여부 연동

### `manager` — 관리자 기능

- 사용자 관리: 계정 생성·편집·잠금, 일괄 처리
- 직위 관리: 직위 등록·수정·삭제
- 조직 관리: 부서 트리, 구성원 추가·제외, 팀장 임명
- 공통코드 관리: 그룹코드 및 코드값 등록·편집
- 공지사항(`Notice`), 알람 발송 이력(`AlarmSendHistory`), 알람 정책(`AlarmPolicy`), 데이터 보존 정책(`DataRetentionPolicy`)
- `AlarmSendHistory` 발송 채널: 관제 실시간 알림 / Slack / Discord

### `fastapi_app/fake_data.py` — 가짜 데이터 생성기 (확률적 스파이크 적용한 데이터 생성)

- `main.py`: 60초 주기 데이터 루프 — 가스/전력/위치 더미 데이터를 생성해 Django로 전송
- `routers/`: gas / power 라우터 (Phase 5 placeholder, 현재 미구현)
- `ai_engine/`: 라이브 파이프라인과는 별도 — 모델 학습/검증, 시나리오 데이터 생성용
  - `gas/`, `power/`: Isolation Forest + ARIMA 학습 스크립트 (`train_*_models.py`)에서 사용하는 모듈
  - `common/`: Z-Score, 슬라이딩 윈도우, Change Point Detection, 공통 데이터 타입
  - `generator/`: 시나리오 기반 데이터 생성기 (정상/경고/위험 전이 확률 제어)
- `adapters/`: ORM ↔ AI 엔진 데이터 변환
- `sender.py`: 데이터 전송 클라이언트 — 가스는 Celery `send_task()` 직접 큐잉 (Redis), 전력·위치·노드는 httpx 비동기 POST

**데이터 생성 확률 분포:**
- 가스: 85% 정상 / 10% 경고 / 5% 위험
- 전력: 60% 정상 / 15% 경고 / 10% 위험 / 10% OFF / 5% 통신오류
- 위치: 이전 좌표 ±2m 범위 랜덤 워크

### `fastapi_app/fake_data2.py' — AI 통합 검증 스토리 데이터 생성기.

본 모듈은 "어느 공장의 어느 오전"(08:45~09:30) 시나리오를 재생하기 위한 데이터를 생성한다. 

스토리 전제 조건 
    1. 1 tick = STORY_STEP 논리분(밀도 5). STORY_START(08:00)~STORY_END(10:05).
    2. measured_at = 실제 now (가상시각 ❌ — is_stale·중복방지 정합 보존).
       "논리분 m"은 값 계산용 인덱스일 뿐 타임스탬프가 아니다.
    3. CO2 = 완만 상승(+9.47/분) → 09:12 warn(1000) 사전경고 → 09:20 정점 ~1076
       → 완만 회복 하강(~-10/분) → 10:05 ~620(정상). 기울기를 CP 게이트(50ppm)
       미발화로 제한 + 미세 노이즈로 ARIMA 적합 안정화 → 전 구간 정규 예측.
    4. 키프레임만 정의하고 사이는 선형 보간.

대상:
    - 가스 : GAS-001 (배치 10,5)
    - 전력 : PWR-001 / slave61 충전스테이션 A (rated 1000W, active, 배치 10,20)
    - 작업자: worker_id 1~5 (fake_data.py와 동일)

시간은 약 21분. 시간을 줄이려면 05-fastapi.yaml의 34줄의 value 값을  변경


## 기술문서
[기술문서](./기술문서.pdf)