"""
[Phase D 결정 (2026-05-23): STEP F 비활성 — 보존 (옵션 a)]
─────────────────────────────────────────────────────────────────
본 어댑터는 Phase C-3에서 STEP F (Isolation Forest 즉시 판단) 통합을 위해
작성됐으나, 사용자 명시 의도 (STEP G — ARIMA 예측만)에 따라 *현재 비활성*.

비활성 보존 정책:
    - 어디서도 import 안 됨 (process_power_ingest 등 호출 없음)
    - 학습 모델 2개 (models/power/iforest_g0050.joblib + iforest_high.joblib) 보존
    - Phase B-C 학습 인프라 (working_means/working_stds, train_power_models.py
      IF 학습 부분, validate_power_pool.py V6) 보존

╔════════════════════════════════════════════════════════════════════════╗
║ 삭제 검증 방법 — 본 파일·관련 산출물 모두 안전 삭제 가능 확인           ║
╠════════════════════════════════════════════════════════════════════════╣
║ 1. 코드베이스 전수 import 검증 (0건이어야 안전):                       ║
║    $ grep -rn "from monitoring.ai.power_if\\|monitoring\\.ai\\.power_if" \\
║          --include="*.py" --exclude-dir=__pycache__ --exclude-dir=.venv ║
║                                                                         ║
║ 2. Celery worker_process_init 확인:                                    ║
║    config/celery.py:_load_ai_models 에 본 모듈 호출 0건                ║
║                                                                         ║
║ 3. 운영 메트릭 확인 (6개월 이상 누적):                                 ║
║    - power AlarmEvent 중 title "[전력·AI]" 발생 0건                   ║
║    - STEP F 활성화 도메인 요구 0건                                    ║
║                                                                         ║
║ 4. 위 3개 모두 통과 시 동시 안전 삭제 가능:                            ║
║    - monitoring/ai/power_if.py                                         ║
║    - models/power/iforest_g0050.joblib + iforest_high.joblib           ║
║    - train_power_models.py 의 IF 학습 부분 (RATED_GROUPS_LOW/HIGH,    ║
║      MODEL_SELECT_THRESHOLD, --with-if-train, 2모델 fit/save 블록)    ║
║    - scripts/validate_power_pool.py 의 V6 (validate_trained_models)   ║
╚════════════════════════════════════════════════════════════════════════╝

활성화 검증 방법 (본 모듈 활성화 시):
    1. process_power_ingest 또는 ingest_power_task 에 다음 추가:
        from monitoring.ai.power_if import predict_power_anomaly
        from alerts.services import trigger_if_anomaly_alarms_power
        if_result = predict_power_anomaly(reading)
        trigger_if_anomaly_alarms_power(device, channel, if_result)
    2. config/celery.py _load_ai_models 에 load_models() 호출 추가
    3. alerts/services.py 에 trigger_if_anomaly_alarms_power 신설
    4. tests/power 에 IF 추론 통합 테스트 추가

─────────────────────────────────────────────────────────────────
STEP F — Isolation Forest 전력 즉시판단 (AI 엔진 연결부, Phase C-3).

fastapi_app/ai_engine 의 PowerIsolationForestDetector 를 ICMP2 전력 인제스트
파이프라인에 연결한다. gas_if.py 패턴 미러. 단 *2개 모델*을 보유 + 채널의
rated_power_w에 따라 적합한 모델 선택 (Phase C-1 (a) 2 모델 결정).

모델 선택 (어댑터 임계 — train_power_models.py의 MODEL_SELECT_THRESHOLD=75):
    - rated_power_w ≤ 75  → iforest_g0050.joblib (low)
    - rated_power_w >  75  → iforest_high.joblib (high)

(75 = g0050[20W±5] ↔ g0100[40W±10] 사이 자연 mid-point.
 V3 분리도: g0050이 모든 다른 그룹과 ≥4σ 분리, g0100~g1000은 인접 < 3σ로 통합)

상태:
    엔진은 무상태(load 후 predict 가 순수 함수)이므로 Celery prefork worker
    (다중 프로세스)에서 안전. 두 모델 모두 프로세스 로컬로 보관.

지연 import:
    엔진 import(`from power...`)는 settings.py 가 sys.path 에
    fastapi_app/ai_engine 를 등록한 뒤에만 가능하므로 함수 내부에서 지연 import.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# 전력 3채널 — 엔진 POWER_SENSOR_TYPES 와 일치
POWER_CHANNELS = ['voltage', 'current', 'power']

# 어댑터 모델 선택 임계 (W) — train_power_models.py MODEL_SELECT_THRESHOLD와 일치
MODEL_SELECT_THRESHOLD: int = 75

# 프로세스 로컬 모델 보관소 (worker 프로세스당 2개)
_detector_low = None
_detector_high = None


def _models_dir():
    return settings.BASE_DIR / 'fastapi_app' / 'ai_engine' / 'models' / 'power'


def load_models() -> None:
    """전력 IF 모델 2개를 로드한다. Celery worker_process_init 에서 호출.

    rated_w ≤ 75 → low (iforest_g0050.joblib)
    rated_w >  75 → high (iforest_high.joblib)
    """
    global _detector_low, _detector_high
    if _detector_low is not None and _detector_high is not None:
        return
    from power.modules.isolation_forest import PowerIsolationForestDetector

    if _detector_low is None:
        d = PowerIsolationForestDetector()
        d.load(str(_models_dir() / 'iforest_g0050.joblib'))
        # 운영 튜닝 훅 — 필요 시 settings로 임계 재정의
        override = getattr(settings, 'POWER_IF_LOW_MAHALANOBIS_THRESHOLD', None)
        if override is not None:
            d._mahalanobis_threshold = float(override)
            logger.info("Power IF (low) mahalanobis_threshold 재정의 — %s", override)
        _detector_low = d
        logger.info("Power IF (low) 모델 로드 완료 — iforest_g0050.joblib")

    if _detector_high is None:
        d = PowerIsolationForestDetector()
        d.load(str(_models_dir() / 'iforest_high.joblib'))
        override = getattr(settings, 'POWER_IF_HIGH_MAHALANOBIS_THRESHOLD', None)
        if override is not None:
            d._mahalanobis_threshold = float(override)
            logger.info("Power IF (high) mahalanobis_threshold 재정의 — %s", override)
        _detector_high = d
        logger.info("Power IF (high) 모델 로드 완료 — iforest_high.joblib")


def get_detector_for_rated(rated_w: int):
    """rated_power_w에 따라 적합한 detector 반환 (지연 로드 fallback)."""
    if _detector_low is None or _detector_high is None:
        load_models()
    return _detector_low if rated_w <= MODEL_SELECT_THRESHOLD else _detector_high


def powerreading_to_bundle(reading):
    """Django PowerReading → 엔진 SensorBundle (3채널 변환).

    PowerReading의 -1.0 결측 규약 → is_valid_flags=False (엔진이 UNKNOWN 처리).
    Phase C-5: FloatField 마이그레이션 후 -1.0 비교 정확성.
    """
    from common.data_types import SensorBundle

    raw = {
        'voltage': reading.voltage_v,
        'current': reading.current_a,
        'power':   reading.power_w,
    }
    values = {ch: (float(raw[ch]) if raw[ch] != -1.0 else None) for ch in POWER_CHANNELS}
    is_valid = {ch: (raw[ch] != -1.0) for ch in POWER_CHANNELS}
    return SensorBundle(
        timestamp=reading.measured_at,
        device_id=reading.device.device_uid,
        values=values,
        is_valid_flags=is_valid,
    )


def predict_power_anomaly(reading):
    """PowerReading 1건에 IF 즉시판단을 수행한다.

    채널의 rated_power_w에 따라 low/high 모델 자동 선택.

    Returns:
        IsolationForestResult, 또는 모델 미가용·추론 실패 시 None.
        None 이면 STEP F 알람 단계(trigger_if_anomaly_alarms)가 자연히
        건너뛰어지므로 전력 인제스트 파이프라인 전체에는 영향이 없다.
    """
    try:
        rated_w = int(reading.channel.rated_power_w or 1000)
        detector = get_detector_for_rated(rated_w)
        bundle = powerreading_to_bundle(reading)
        return detector.predict(bundle)
    except Exception as exc:
        logger.error(
            "Power IF 추론 실패 — device=%s ch=%s: %s",
            getattr(getattr(reading, 'device', None), 'device_uid', '?'),
            getattr(getattr(reading, 'channel', None), 'channel_code', '?'),
            exc,
        )
        return None
