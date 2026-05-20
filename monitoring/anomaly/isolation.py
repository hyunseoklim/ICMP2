"""
STEP F — Isolation Forest (비지도 다변량 이상탐지)

9개 가스를 동시에 입력으로 받아 정상 구간에서 벗어난 조합을 탐지.
Z-score(단변량)로는 잡히지 않는 복합 이상 패턴을 검출.

학습 전략:
  - train_isolation_forest 커맨드로 시나리오 A 데이터 초기 학습 후 파일 저장
  - 서버 시작 시 저장된 모델 자동 로드
  - 슬라이딩 윈도우에 MIN_TRAIN_SAMPLES 이상 쌓이면 재학습 가능
"""

from __future__ import annotations

import logging
import os

from .window import get_vectors, GAS_FIELDS

logger = logging.getLogger(__name__)

MIN_TRAIN_SAMPLES = 20
CONTAMINATION     = 0.05

_MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'models')

# device_uid → {'model': IsolationForest | None, 'trained': bool}
_models: dict[str, dict] = {}

_latest: dict[str, dict] = {}


def _model_path(device_uid: str) -> str:
    os.makedirs(_MODEL_DIR, exist_ok=True)
    return os.path.join(_MODEL_DIR, f'isolation_{device_uid}.pkl')


def save_model(device_uid: str) -> bool:
    """학습된 모델을 파일로 저장. train_isolation_forest 커맨드에서 호출."""
    try:
        import joblib
    except ImportError:
        logger.warning("joblib 미설치 — 모델 저장 불가")
        return False
    entry = _models.get(device_uid)
    if not entry or not entry['trained']:
        return False
    joblib.dump(entry['model'], _model_path(device_uid))
    logger.info("IsolationForest 저장: %s", _model_path(device_uid))
    return True


def load_model(device_uid: str) -> bool:
    """저장된 모델 파일 로드. 서버 시작 시 또는 _get_entry() 최초 호출 시 실행."""
    try:
        import joblib
    except ImportError:
        return False
    path = _model_path(device_uid)
    if not os.path.exists(path):
        return False
    try:
        model = joblib.load(path)
        _models[device_uid] = {'model': model, 'trained': True}
        logger.info("IsolationForest 로드: %s", path)
        return True
    except Exception as e:
        logger.warning("모델 로드 실패 (%s): %s", device_uid, e)
        return False


def _get_entry(device_uid: str) -> dict:
    if device_uid not in _models:
        _models[device_uid] = {'model': None, 'trained': False}
        load_model(device_uid)  # 저장된 모델 있으면 자동 로드
    return _models[device_uid]


def _build_matrix(device_uid: str) -> list[list[float]] | None:
    vectors = get_vectors(device_uid)
    if len(vectors) < MIN_TRAIN_SAMPLES:
        # 버퍼 부족 시 DB에서 보충 후 재시도
        from .window import init_from_db
        init_from_db(device_uid)
        vectors = get_vectors(device_uid)
    if len(vectors) < MIN_TRAIN_SAMPLES:
        return None
    return vectors


def train(device_uid: str) -> bool:
    """
    슬라이딩 윈도우 데이터로 Isolation Forest 학습.
    학습 성공 시 True 반환.
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        logger.warning("scikit-learn 미설치 — Isolation Forest 비활성화")
        return False

    matrix = _build_matrix(device_uid)
    if matrix is None:
        return False

    entry = _get_entry(device_uid)
    model = IsolationForest(
        n_estimators=50,
        contamination=CONTAMINATION,
        random_state=42,
        n_jobs=1,
    )
    model.fit(matrix)
    entry['model']   = model
    entry['trained'] = True
    logger.debug("IsolationForest trained for %s (%d samples)", device_uid, len(matrix))
    return True


def make_feature_row(device_uid: str, reading) -> list[float]:
    """9개 가스 raw값 → 9차원 feature 벡터."""
    return [
        float(getattr(reading, gas, None) or 0.0)
        for gas in GAS_FIELDS
    ]


def analyze(device_uid: str, reading) -> dict:
    """
    GasReading 1건에 대해 Isolation Forest 이상 판정 수행.
    반환: {device_uid, score, is_anomaly, final_status, measured_at}
    """
    measured_at = reading.measured_at.isoformat() if reading.measured_at else None
    entry = _get_entry(device_uid)

    if not entry['trained']:
        train(device_uid)

    if not entry['trained']:
        result = _make_result(device_uid, None, False, 'INSUFFICIENT_DATA', measured_at)
        _latest[device_uid] = result
        return result

    row = make_feature_row(device_uid, reading)

    model      = entry['model']
    score      = float(model.score_samples([row])[0])
    predicted  = model.predict([row])[0]
    is_anomaly = predicted == -1

    status = 'ISOLATION_ANOMALY' if is_anomaly else 'NORMAL'
    result = _make_result(device_uid, round(score, 6), is_anomaly, status, measured_at)
    _latest[device_uid] = result
    return result


def get_latest(device_uid: str) -> dict:
    """가장 최근 Isolation Forest 판정 결과 반환."""
    return _latest.get(device_uid, {})


def is_trained(device_uid: str) -> bool:
    return _get_entry(device_uid)['trained']


def _make_result(device_uid, score, is_anomaly, status, measured_at) -> dict:
    return {
        'device_uid':   device_uid,
        'score':        score,
        'is_anomaly':   is_anomaly,
        'final_status': status,
        'measured_at':  measured_at,
    }
