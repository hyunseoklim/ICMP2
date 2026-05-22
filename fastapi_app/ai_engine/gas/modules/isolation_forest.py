"""
gas/modules/isolation_forest — 가스 9차원 IsolationForest 학습·예측 모듈.

본 모듈은 본 과업의 *첫 번째 학습 모듈*. scikit-learn IsolationForest로
가스 9차원 정상 분포를 학습한 뒤, 새 측정값이 분포 내인지 판정.

설계 원칙:
    - 4개 인터페이스 분리: __init__ / fit / save·load / predict
    - IF 자체 판정 + 마할라노비스 거리(결정 H') 두 신호 결합
    - 학습 데이터의 *평균·역 공분산*을 함께 저장하여 OOD 판정 지원
    - 결측 처리: 학습 시 NaN 행 제거, 예측 시 UNKNOWN 반환

핵심 결정 (Phase 2 + 변경 D-20260519-001):
    - 결정 I: scikit-learn IsolationForest, n_estimators=100, random_state=42
    - 결정 H: 학습 풀 5,000 / 검증 풀 2,150
    - 결정 H' (갱신): 마할라노비스 거리 ≥ 5.0이면 학습 분포 외
      - Phase 2 원안 3.0은 1차원 3σ 룰에서 차용
      - 9차원 카이제곱(df=9) 99.7% 임계 = 5.00 (D-20260519-001)
      - 차원 보정으로 결정 H' 정신 유지
    - 결정 B: 단일 학습, 본 과업 동안 갱신 없음
    - B.2: 가스 IF 1개 모델 (장비 무관 통합)
    - T.3: NORMAL 환기 100% 학습

표준 사용 예 (학습):
    >>> detector = GasIsolationForestDetector()
    >>> metrics = detector.fit(training_bundles)
    >>> detector.save("models/gas/iforest.joblib")

표준 사용 예 (FastAPI startup):
    >>> detector = GasIsolationForestDetector()
    >>> detector.load("models/gas/iforest.joblib")
    >>> result = detector.predict(bundle)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from common.data_types import SensorBundle
from common.enums import RiskLevel
from common.premises.measurement import MIN_VALID_RATIO
from gas.premises.gas_distribution import GAS_SENSOR_TYPES, GAS_DIMENSION


# ============================================================================
# 기본 결정값 (Phase 2)
# ============================================================================

_DEFAULT_N_ESTIMATORS: int = 100
_DEFAULT_RANDOM_STATE: int = 42
_DEFAULT_CONTAMINATION: str = "auto"
_DEFAULT_MAHALANOBIS_THRESHOLD: float = 5.0  # 9차원 카이제곱 99.7% 임계 (D-20260519-001)
_MODEL_VERSION: str = "1.0"


# ============================================================================
# IsolationForestResult — 판정 결과
# ============================================================================

@dataclass
class IsolationForestResult:
    """가스 IF 모듈의 판정 결과.
    
    Attributes:
        timestamp: 판정 대상 시각 (입력 SensorBundle의 timestamp).
        device_id: 장비 식별자 (gas_A 또는 gas_B).
        is_anomaly: IF 자체 ANOMALY 판정 (-1 → True).
        anomaly_score: decision_function 출력 (음수: 이상, 양수: 정상).
        mahalanobis_distance: 학습 분포 중심까지의 거리 (결정 H').
        is_out_of_distribution: 마할라노비스 거리 ≥ threshold 시 True.
        level: 종합 위험 등급 (NORMAL/CAUTION/UNKNOWN).
        feature_vector: 입력된 9차원 벡터 (디버깅용).
        valid_ratio: SensorBundle 유효 비율.
        reason: 판정 사유 한글 문자열.
        sensor_types: 차원 순서 (확인용).
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
    sensor_types: list = field(default_factory=lambda: list(GAS_SENSOR_TYPES))

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict.
        
        NaN은 None으로 안전 변환.
        """
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


# ============================================================================
# GasIsolationForestDetector — 본체 클래스
# ============================================================================

class GasIsolationForestDetector:
    """가스 9차원 IsolationForest 학습·예측 클래스.
    
    인터페이스 분리 (Phase 5 결합 친화성):
        - __init__: 설정만 받음, 학습 없음
        - fit: 학습 풀로 모델 + 학습 분포 통계 학습
        - save/load: joblib 직렬화
        - predict: SensorBundle → IsolationForestResult
    
    Examples (학습):
        >>> detector = GasIsolationForestDetector()
        >>> detector.fit(training_bundles)
        >>> detector.save("models/gas/iforest.joblib")
    
    Examples (FastAPI startup):
        >>> detector = GasIsolationForestDetector()
        >>> detector.load("models/gas/iforest.joblib")
        >>> result = detector.predict(bundle)
    """

    def __init__(self, config: Optional[dict] = None):
        """설정 dict로 초기화. 학습은 fit() 호출 시.
        
        Args:
            config: 설정 dict. 모든 키 선택 사항.
                - n_estimators (int, 기본 100)
                - random_state (int, 기본 42)
                - contamination (str|float, 기본 "auto")
                - mahalanobis_threshold (float, 기본 3.0)
                - min_valid_ratio (float, 기본 0.8)
        """
        config = config or {}
        self._n_estimators = int(config.get("n_estimators", _DEFAULT_N_ESTIMATORS))
        self._random_state = int(config.get("random_state", _DEFAULT_RANDOM_STATE))
        self._contamination = config.get("contamination", _DEFAULT_CONTAMINATION)
        self._mahalanobis_threshold = float(
            config.get("mahalanobis_threshold", _DEFAULT_MAHALANOBIS_THRESHOLD)
        )
        self._min_valid_ratio = float(
            config.get("min_valid_ratio", MIN_VALID_RATIO)
        )

        # 학습 후 채워지는 상태
        self._model: Optional[IsolationForest] = None
        self._train_mean: Optional[np.ndarray] = None
        self._train_cov_inv: Optional[np.ndarray] = None
        self._is_fitted: bool = False
        self._trained_at: Optional[str] = None

    # ------------------------------------------------------------------------
    # 상태 조회
    # ------------------------------------------------------------------------

    def is_fitted(self) -> bool:
        """학습 완료 상태인지."""
        return self._is_fitted

    @property
    def mahalanobis_threshold(self) -> float:
        """마할라노비스 거리 임계.
        
        기본값 5.0은 9차원 카이제곱 99.7% 임계 (D-20260519-001).
        Phase 2 원안 3.0(1차원 3σ 룰)을 9차원 등가로 보정.
        """
        return self._mahalanobis_threshold

    @property
    def n_estimators(self) -> int:
        """트리 수 (결정 I 기본 100)."""
        return self._n_estimators

    # ------------------------------------------------------------------------
    # 학습
    # ------------------------------------------------------------------------

    def fit(self, training_bundles: list) -> dict:
        """학습 풀로 모델 학습.
        
        Args:
            training_bundles: SensorBundle 리스트. 각 묶음은 9차원 가스 값.
        
        Returns:
            학습 메트릭 dict:
                - n_samples_input: 입력 묶음 수
                - n_samples_trained: NaN 제거 후 실제 학습 묶음 수
                - n_features: 9
                - mahalanobis_mean: 학습 풀 자체의 평균 거리 (참고)
                - training_time_seconds: 학습 소요 시간
        
        Raises:
            ValueError: 학습 풀이 비어있거나 유효 샘플이 부족할 때.
        """
        if not training_bundles:
            raise ValueError("training_bundles가 비어있음")

        start_time = time.time()

        # SensorBundle 리스트 → numpy 9차원 행렬
        X = np.array([
            b.to_vector(GAS_SENSOR_TYPES) for b in training_bundles
        ])

        if X.shape[1] != GAS_DIMENSION:
            raise ValueError(
                f"학습 데이터 차원이 {X.shape[1]}, 기대 {GAS_DIMENSION}"
            )

        # NaN 행 제거 (결정 H 정책)
        nan_mask = np.isnan(X).any(axis=1)
        X_clean = X[~nan_mask]
        n_input = len(X)
        n_clean = len(X_clean)

        if n_clean < GAS_DIMENSION + 1:
            raise ValueError(
                f"유효 학습 샘플 부족: {n_clean}개 (최소 {GAS_DIMENSION + 1} 필요)"
            )

        # IsolationForest 학습
        self._model = IsolationForest(
            n_estimators=self._n_estimators,
            random_state=self._random_state,
            contamination=self._contamination,
        )
        self._model.fit(X_clean)

        # 학습 분포의 평균·역 공분산 저장 (마할라노비스 거리용)
        self._train_mean = X_clean.mean(axis=0)
        cov = np.cov(X_clean.T)
        try:
            self._train_cov_inv = np.linalg.inv(cov)
        except np.linalg.LinAlgError:
            # 특이 행렬일 때 의사역행렬 사용
            self._train_cov_inv = np.linalg.pinv(cov)

        # 학습 풀 자체의 평균 마할라노비스 거리 (참고용)
        diffs = X_clean - self._train_mean
        mahal_distances = np.sqrt(
            np.einsum("ij,jk,ik->i", diffs, self._train_cov_inv, diffs)
        )
        mahal_mean = float(np.mean(mahal_distances))

        self._is_fitted = True
        self._trained_at = datetime.now().isoformat()

        training_time = time.time() - start_time

        return {
            "n_samples_input": n_input,
            "n_samples_trained": n_clean,
            "n_features": GAS_DIMENSION,
            "mahalanobis_mean": mahal_mean,
            "training_time_seconds": training_time,
        }

    # ------------------------------------------------------------------------
    # 저장 / 로드
    # ------------------------------------------------------------------------

    def save(self, path: Union[str, Path]) -> None:
        """학습된 모델 + 메타데이터를 joblib로 저장.
        
        Args:
            path: 저장 경로. 부모 디렉토리는 자동 생성.
        
        Raises:
            RuntimeError: 학습 전 호출 시.
        """
        if not self._is_fitted:
            raise RuntimeError("학습되지 않은 모델은 저장할 수 없음. fit()을 먼저 호출")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        metadata = {
            "version": _MODEL_VERSION,
            "model": self._model,
            "train_mean": self._train_mean,
            "train_cov_inv": self._train_cov_inv,
            "sensor_types": list(GAS_SENSOR_TYPES),
            "n_estimators": self._n_estimators,
            "random_state": self._random_state,
            "contamination": self._contamination,
            "mahalanobis_threshold": self._mahalanobis_threshold,
            "min_valid_ratio": self._min_valid_ratio,
            "trained_at": self._trained_at,
        }
        joblib.dump(metadata, path)

    def load(self, path: Union[str, Path]) -> None:
        """저장된 모델 로드.
        
        sensor_types 일치 검증 — 재학습 후 차원 순서 변경 방지.
        
        Args:
            path: 로드할 joblib 파일 경로.
        
        Raises:
            FileNotFoundError: 파일 없음.
            ValueError: sensor_types 불일치 또는 차원 불일치.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"모델 파일 없음: {path}")

        metadata = joblib.load(path)

        # sensor_types 일치 검증
        saved_types = metadata.get("sensor_types")
        if saved_types != list(GAS_SENSOR_TYPES):
            raise ValueError(
                f"sensor_types 불일치. 저장됨: {saved_types}, "
                f"기대: {GAS_SENSOR_TYPES}"
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

    # ------------------------------------------------------------------------
    # 예측
    # ------------------------------------------------------------------------

    def predict(self, bundle: SensorBundle) -> IsolationForestResult:
        """단일 SensorBundle 판정.
        
        Args:
            bundle: 9차원 가스 묶음.
        
        Returns:
            IsolationForestResult.
        
        Raises:
            RuntimeError: 학습 전 호출 시.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "학습되지 않은 모델. fit() 또는 load()를 먼저 호출"
            )

        # 9차원 벡터 변환
        x = bundle.to_vector(GAS_SENSOR_TYPES)
        valid_ratio = bundle.valid_ratio()
        feature_vector = x.tolist()

        # M.6 유효 비율 부족 → UNKNOWN
        if valid_ratio < self._min_valid_ratio:
            return self._build_unknown(
                bundle, feature_vector, valid_ratio,
                reason=f"유효 비율 부족 ({valid_ratio:.2f} < {self._min_valid_ratio})",
            )

        # NaN 포함 → UNKNOWN
        if np.isnan(x).any():
            return self._build_unknown(
                bundle, feature_vector, valid_ratio,
                reason="입력 벡터에 결측 포함",
            )

        # IF 자체 판정
        x_reshaped = x.reshape(1, -1)
        pred = self._model.predict(x_reshaped)[0]
        is_anomaly = bool(pred == -1)
        score = float(self._model.decision_function(x_reshaped)[0])

        # 마할라노비스 거리 (결정 H')
        diff = x - self._train_mean
        mahal = float(np.sqrt(diff @ self._train_cov_inv @ diff))
        is_ood = mahal >= self._mahalanobis_threshold

        # 종합 등급 (둘 중 하나라도 신호이면 CAUTION — 보수적)
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

    # ------------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------------

    def _build_unknown(
        self,
        bundle: SensorBundle,
        feature_vector: list,
        valid_ratio: float,
        reason: str,
    ) -> IsolationForestResult:
        """UNKNOWN 결과 생성."""
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
