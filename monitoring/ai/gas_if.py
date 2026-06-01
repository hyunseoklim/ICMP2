"""
STEP F — Isolation Forest 가스 즉시판단 (AI 엔진 연결부).

fastapi_app/ai_engine 의 GasIsolationForestDetector 를 ICMP2 가스 인제스트
파이프라인에 연결한다. 엔진은 무상태(load 후 predict 가 순수 함수)이므로
Celery prefork worker(다중 프로세스)에서 안전하다.

- 모델 로드: load_models() 를 Celery worker_process_init 에서 1회 호출.
- worker 외 경로(HTTP fallback 등)에서는 get_detector() 가 지연 로드한다.
- 엔진 import(`from gas...`, `from gas.core...`)는 settings.py 가 sys.path 에
  fastapi_app/ai_engine 를 등록한 뒤에만 가능하므로 함수 내부에서 지연 import.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# 엔진 가스 9채널 — Django GasReading 컬럼명·순서와 동일
# (fastapi_app/ai_engine/gas/premises/gas_distribution.GAS_SENSOR_TYPES 와 일치)
GAS_CHANNELS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']

# 프로세스 로컬 모델 보관소 (worker 프로세스당 1개)
_detector = None


def _model_path() -> str:
    return str(
        settings.BASE_DIR / 'fastapi_app' / 'ai_engine' / 'models' / 'gas' / 'iforest.joblib'
    )


def load_models() -> None:
    """가스 IF 모델을 로드한다. Celery worker_process_init 에서 호출."""
    global _detector
    if _detector is not None:
        return
    from gas.modules.isolation_forest import GasIsolationForestDetector

    detector = GasIsolationForestDetector()
    detector.load(_model_path())

    # 운영 튜닝 훅 — settings.GAS_IF_MAHALANOBIS_THRESHOLD 가 지정되면
    # 모델에 학습된 기본 임계(5.0)를 덮어쓴다. 미지정이면 모델 학습값 유지.
    # Phase 1 관측 결과로 false-positive 비율을 조정할 때 재학습 없이 사용한다.
    override = getattr(settings, 'GAS_IF_MAHALANOBIS_THRESHOLD', None)
    if override is not None:
        detector._mahalanobis_threshold = float(override)
        logger.info("IF mahalanobis_threshold 재정의 — %s", override)

    _detector = detector
    logger.info("가스 IF 모델 로드 완료 — %s", _model_path())


def get_detector():
    """로드된 detector 를 반환. 미로드 시 지연 로드 (worker 외 경로 대비)."""
    if _detector is None:
        load_models()
    return _detector


def gasreading_to_bundle(reading):
    """Django GasReading → 엔진 SensorBundle (9채널 단순 매핑).

    한 GasReading row 가 이미 9채널·1시점이므로 채널 집계 없이 직접 변환한다.
    결측(None) 채널은 is_valid_flags=False — 엔진이 UNKNOWN 으로 처리한다.
    """
    from gas.core.data_types import SensorBundle

    values = {ch: getattr(reading, ch) for ch in GAS_CHANNELS}
    is_valid = {ch: values[ch] is not None for ch in GAS_CHANNELS}
    return SensorBundle(
        timestamp=reading.measured_at,
        device_id=reading.device.device_uid,
        values=values,
        is_valid_flags=is_valid,
    )


def predict_gas_anomaly(reading):
    """GasReading 1건에 IF 즉시판단을 수행한다.

    Returns:
        IsolationForestResult, 또는 모델 미가용·추론 실패 시 None.
        None 이면 STEP F 알람 단계(trigger_if_anomaly_alarms)가 자연히
        건너뛰어지므로 가스 인제스트 파이프라인 전체에는 영향이 없다.
    """
    try:
        detector = get_detector()
        bundle = gasreading_to_bundle(reading)
        return detector.predict(bundle)
    except Exception as exc:
        logger.error(
            "IF 추론 실패 — device=%s: %s",
            getattr(getattr(reading, 'device', None), 'device_uid', '?'),
            exc,
        )
        return None
