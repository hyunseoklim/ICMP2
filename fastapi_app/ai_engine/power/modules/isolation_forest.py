"""
power/modules/isolation_forest — 전력 3차원 IsolationForest 학습·예측 모듈.

본 모듈은 gas/modules/isolation_forest.py와 *구조 대칭*. 차이점:
    - 차원: 9 → 3 (voltage, current, power)
    - 장비: 2개 → 1개 (power_1)
    - 마할라노비스 임계: 5.0 → 3.76 (D-20260519-002)
    - 환기 단계 의존 → 작업 모드 의존 (T.3: WORKING 100% 학습)

핵심 결정 (Phase 2 + D-20260519-002):
    - 결정 I: scikit-learn IsolationForest, n_estimators=100, random_state=42
    - 결정 H': 3차원 카이제곱(df=3) 99.7% 임계 = √14.156 ≈ 3.76 (D-002)
    - 결정 B: 단일 학습
    - B.2: 전력 IF 1개 모델
    - T.3: WORKING 모드 100% 학습 (IDLE은 모듈 비활성)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from power.core.data_types import SensorBundle
from power.core.enums import RiskLevel
from power.core.premises.measurement import MIN_VALID_RATIO
from power.premises.power_distribution import POWER_SENSOR_TYPES, POWER_DIMENSION


_DEFAULT_N_ESTIMATORS: int = 100
_DEFAULT_RANDOM_STATE: int = 42
_DEFAULT_CONTAMINATION: str = "auto"
_DEFAULT_MAHALANOBIS_THRESHOLD: float = 3.76  # 3차원 카이제곱 99.7% (D-20260519-002)
_MODEL_VERSION: str = "1.0"


@dataclass
class IsolationForestResult:
    """전력 IF 모듈의 판정 결과.
    
    Attributes:
        timestamp: 판정 대상 시각.
        device_id: 장비 식별자 (보통 'power_1').
        is_anomaly: IF 자체 ANOMALY 판정.
        anomaly_score: decision_function 출력.
        mahalanobis_distance: 학습 분포 중심까지 거리.
        is_out_of_distribution: 거리 ≥ 3.76 (D-002) 시 True.
        level: 종합 위험 등급.
        feature_vector: 입력된 3차원 벡터.
        valid_ratio: SensorBundle 유효 비율.
        reason: 한글 사유.
        sensor_types: 차원 순서.
    """

    timestamp: datetime
    device_id: str
    is_anomaly: bool
    anomaly_score: Optional[float]
    mahalanobis_distance: Optional[float]
    is_out_of_distribution: bool
    level: RiskLevel
    feature_vector: list
    valid_ratio: float
    reason: str
    sensor_types: list = field(default_factory=lambda: list(POWER_SENSOR_TYPES))

    def to_dict(self) -> dict:
        def _safe(x):
            if x is None:
                return None
            if isinstance(x, float) and np.isnan(x):
                return None
            return x

        return {
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "is_anomaly": self.is_anomaly,
            "anomaly_score": _safe(self.anomaly_score),
            "mahalanobis_distance": _safe(self.mahalanobis_distance),
            "is_out_of_distribution": self.is_out_of_distribution,
            "level": self.level.value,
            "feature_vector": [_safe(v) for v in self.feature_vector],
            "valid_ratio": self.valid_ratio,
            "reason": self.reason,
            "sensor_types": list(self.sensor_types),
        }


class PowerIsolationForestDetector:
    """전력 3차원 IsolationForest 학습·예측 클래스.
    
    가스 GasIsolationForestDetector와 구조 동일. 차원과 임계만 다름.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._n_estimators = int(config.get("n_estimators", _DEFAULT_N_ESTIMATORS))
        self._random_state = int(config.get("random_state", _DEFAULT_RANDOM_STATE))
        self._contamination = config.get("contamination", _DEFAULT_CONTAMINATION)
        self._mahalanobis_threshold = float(
            config.get("mahalanobis_threshold", _DEFAULT_MAHALANOBIS_THRESHOLD)
        )
        self._min_valid_ratio = float(config.get("min_valid_ratio", MIN_VALID_RATIO))

        self._model: Optional[IsolationForest] = None
        self._train_mean: Optional[np.ndarray] = None
        self._train_cov_inv: Optional[np.ndarray] = None
        self._is_fitted: bool = False
        self._trained_at: Optional[str] = None

    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def mahalanobis_threshold(self) -> float:
        """마할라노비스 거리 임계.
        
        기본값 3.76은 3차원 카이제곱 99.7% 임계 (D-20260519-002).
        """
        return self._mahalanobis_threshold

    @property
    def n_estimators(self) -> int:
        return self._n_estimators

    def fit(self, training_bundles: list) -> dict:
        """학습 풀로 모델 학습.
        
        Args:
            training_bundles: SensorBundle 리스트 (3차원).
        
        Returns:
            학습 메트릭 dict.
        """
        if not training_bundles:
            raise ValueError("training_bundles가 비어있음")

        start_time = time.time()

        X = np.array([
            b.to_vector(POWER_SENSOR_TYPES) for b in training_bundles
        ])

        if X.shape[1] != POWER_DIMENSION:
            raise ValueError(
                f"학습 데이터 차원 {X.shape[1]}, 기대 {POWER_DIMENSION}"
            )

        nan_mask = np.isnan(X).any(axis=1)
        X_clean = X[~nan_mask]
        n_input = len(X)
        n_clean = len(X_clean)

        if n_clean < POWER_DIMENSION + 1:
            raise ValueError(
                f"유효 학습 샘플 부족: {n_clean}개 (최소 {POWER_DIMENSION + 1})"
            )

        self._model = IsolationForest(
            n_estimators=self._n_estimators,
            random_state=self._random_state,
            contamination=self._contamination,
        )
        self._model.fit(X_clean)

        self._train_mean = X_clean.mean(axis=0)
        cov = np.cov(X_clean.T)
        try:
            self._train_cov_inv = np.linalg.inv(cov)
        except np.linalg.LinAlgError:
            self._train_cov_inv = np.linalg.pinv(cov)

        diffs = X_clean - self._train_mean
        mahal_distances = np.sqrt(
            np.einsum("ij,jk,ik->i", diffs, self._train_cov_inv, diffs)
        )
        mahal_mean = float(np.mean(mahal_distances))

        self._is_fitted = True
        self._trained_at = datetime.now(timezone.utc).isoformat()
        training_time = time.time() - start_time

        return {
            "n_samples_input": n_input,
            "n_samples_trained": n_clean,
            "n_features": POWER_DIMENSION,
            "mahalanobis_mean": mahal_mean,
            "training_time_seconds": training_time,
        }

    def save(self, path: Union[str, Path]) -> None:
        if not self._is_fitted:
            raise RuntimeError("학습되지 않은 모델은 저장할 수 없음")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        metadata = {
            "version": _MODEL_VERSION,
            "model": self._model,
            "train_mean": self._train_mean,
            "train_cov_inv": self._train_cov_inv,
            "sensor_types": list(POWER_SENSOR_TYPES),
            "n_estimators": self._n_estimators,
            "random_state": self._random_state,
            "contamination": self._contamination,
            "mahalanobis_threshold": self._mahalanobis_threshold,
            "min_valid_ratio": self._min_valid_ratio,
            "trained_at": self._trained_at,
        }
        joblib.dump(metadata, path)

    def load(self, path: Union[str, Path]) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"모델 파일 없음: {path}")

        metadata = joblib.load(path)
        saved_types = metadata.get("sensor_types")
        if saved_types != list(POWER_SENSOR_TYPES):
            raise ValueError(
                f"sensor_types 불일치. 저장: {saved_types}, 기대: {POWER_SENSOR_TYPES}"
            )

        self._model = metadata["model"]
        self._train_mean = metadata["train_mean"]
        self._train_cov_inv = metadata["train_cov_inv"]
        self._n_estimators = metadata.get("n_estimators", _DEFAULT_N_ESTIMATORS)
        self._random_state = metadata.get("random_state", _DEFAULT_RANDOM_STATE)
        self._contamination = metadata.get("contamination", _DEFAULT_CONTAMINATION)
        self._mahalanobis_threshold = metadata.get(
            "mahalanobis_threshold", _DEFAULT_MAHALANOBIS_THRESHOLD
        )
        self._min_valid_ratio = metadata.get("min_valid_ratio", MIN_VALID_RATIO)
        self._trained_at = metadata.get("trained_at")
        self._is_fitted = True

    def predict(self, bundle: SensorBundle) -> IsolationForestResult:
        if not self._is_fitted:
            raise RuntimeError("학습되지 않은 모델. fit() 또는 load() 먼저")

        x = bundle.to_vector(POWER_SENSOR_TYPES)
        valid_ratio = bundle.valid_ratio()
        feature_vector = x.tolist()

        if valid_ratio < self._min_valid_ratio:
            return self._build_unknown(
                bundle, feature_vector, valid_ratio,
                reason=f"유효 비율 부족 ({valid_ratio:.2f} < {self._min_valid_ratio})",
            )

        if np.isnan(x).any():
            return self._build_unknown(
                bundle, feature_vector, valid_ratio,
                reason="입력 벡터에 결측 포함",
            )

        x_reshaped = x.reshape(1, -1)
        pred = self._model.predict(x_reshaped)[0]
        is_anomaly = bool(pred == -1)
        score = float(self._model.decision_function(x_reshaped)[0])

        diff = x - self._train_mean
        mahal = float(np.sqrt(diff @ self._train_cov_inv @ diff))
        is_ood = mahal >= self._mahalanobis_threshold

        if is_anomaly or is_ood:
            level = RiskLevel.CAUTION
            reasons = []
            if is_anomaly:
                reasons.append(f"IF ANOMALY (score={score:.3f})")
            if is_ood:
                reasons.append(
                    f"분포 외 (마할라노비스 {mahal:.2f} ≥ {self._mahalanobis_threshold})"
                )
            reason = " + ".join(reasons)
        else:
            level = RiskLevel.NORMAL
            reason = f"정상 분포 내 (score={score:.3f}, 거리={mahal:.2f})"

        return IsolationForestResult(
            timestamp=bundle.timestamp,
            device_id=bundle.device_id,
            is_anomaly=is_anomaly,
            anomaly_score=score,
            mahalanobis_distance=mahal,
            is_out_of_distribution=is_ood,
            level=level,
            feature_vector=feature_vector,
            valid_ratio=valid_ratio,
            reason=reason,
        )

    def _build_unknown(self, bundle, feature_vector, valid_ratio, reason):
        return IsolationForestResult(
            timestamp=bundle.timestamp,
            device_id=bundle.device_id,
            is_anomaly=False,
            anomaly_score=None,
            mahalanobis_distance=None,
            is_out_of_distribution=False,
            level=RiskLevel.UNKNOWN,
            feature_vector=feature_vector,
            valid_ratio=valid_ratio,
            reason=reason,
        )
