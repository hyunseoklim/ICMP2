"""tests/gas/test_gas.py — 가스 영역 핵심 테스트."""

import numpy as np
import pytest

from common.enums import RiskLevel
from common.modules import ThresholdClassifier
from gas.premises import (
    GAS_SENSOR_TYPES, GAS_DIMENSION,
    VentilationLevel, correlation_matrix, covariance_matrix,
    mean_vector, get_distribution_params,
    INTER_DEVICE_GAS_CORRELATION,
)
from gas.thresholds import load_gas_thresholds, validate_gas_thresholds


# ============================================================================
# 분포
# ============================================================================

class TestGasDistribution:
    def test_dimension(self):
        assert len(GAS_SENSOR_TYPES) == 9
        assert GAS_DIMENSION == 9

    def test_correlation_matrix(self):
        R = correlation_matrix()
        assert R.shape == (9, 9)
        assert np.allclose(np.diag(R), 1.0)
        assert np.allclose(R, R.T)
        # 양의 정부호
        assert np.all(np.linalg.eigvalsh(R) > 0)

    def test_e2_correlations(self):
        R = correlation_matrix()
        idx = {st: i for i, st in enumerate(GAS_SENSOR_TYPES)}
        assert R[idx['o2'], idx['co2']] == -0.3
        assert R[idx['co'], idx['voc']] == 0.4
        assert R[idx['co'], idx['no2']] == 0.3

    def test_covariance_positive_definite(self):
        C = covariance_matrix(VentilationLevel.NORMAL)
        assert np.all(np.linalg.eigvalsh(C) > 0)

    def test_mean_ventilation_levels(self):
        v_normal = mean_vector(VentilationLevel.NORMAL)
        v_weak = mean_vector(VentilationLevel.WEAK)
        idx = {st: i for i, st in enumerate(GAS_SENSOR_TYPES)}
        # CO: NORMAL=5, WEAK=10 (2배)
        assert v_normal[idx['co']] == 5.0
        assert v_weak[idx['co']] == 10.0
        # O2 별도: WEAK 시 약간 감소
        assert v_weak[idx['o2']] < v_normal[idx['o2']]

    def test_distribution_sampling(self):
        params = get_distribution_params(VentilationLevel.NORMAL)
        rng = np.random.default_rng(42)
        samples = rng.multivariate_normal(params['mean'], params['cov'], size=5000)
        idx = {st: i for i, st in enumerate(GAS_SENSOR_TYPES)}
        # CO 평균 5.0 근사
        assert abs(samples[:, idx['co']].mean() - 5.0) < 0.1
        # O2-CO2 상관 근사
        corr = np.corrcoef(samples[:, idx['o2']], samples[:, idx['co2']])[0, 1]
        assert abs(corr - (-0.3)) < 0.05


# ============================================================================
# 임계치
# ============================================================================

class TestGasThresholds:
    def test_load(self):
        table = load_gas_thresholds()
        assert len(table) == 9
        for st in GAS_SENSOR_TYPES:
            assert st in table

    def test_o2_low_direction(self):
        table = load_gas_thresholds()
        assert table['o2']['direction'] == 'low'
        assert table['o2']['caution'] > table['o2']['danger']

    def test_validate_missing_gas(self):
        bad = {st: {'direction': 'high', 'caution': 10, 'danger': 20}
               for st in GAS_SENSOR_TYPES if st != 'co'}
        with pytest.raises(ValueError, match='co'):
            validate_gas_thresholds(bad)

    def test_classifier_integration(self, ts, make_point):
        classifier = ThresholdClassifier(load_gas_thresholds())
        assert classifier.classify(make_point(ts, 'gas_A', 'co', 100.0)).level == RiskLevel.CAUTION
        assert classifier.classify(make_point(ts, 'gas_A', 'co', 300.0)).level == RiskLevel.DANGER
        assert classifier.classify(make_point(ts, 'gas_A', 'o2', 15.0)).level == RiskLevel.DANGER


# ============================================================================
# IsolationForest (느림 — 학습 포함)
# ============================================================================

@pytest.mark.slow
class TestGasIsolationForest:
    def test_default_threshold_d001(self):
        from gas.modules import GasIsolationForestDetector
        detector = GasIsolationForestDetector()
        # D-20260519-001: 9차원 카이제곱 99.7% 임계
        assert detector.mahalanobis_threshold == 5.0

    def test_fit_and_predict(self, make_gas_bundle, ts):
        from gas.modules import GasIsolationForestDetector
        from datetime import timedelta

        # 1000샘플 학습 (테스트 빠르게)
        params = get_distribution_params(VentilationLevel.NORMAL)
        rng = np.random.default_rng(42)
        samples = rng.multivariate_normal(params['mean'], params['cov'], size=1000)

        bundles = []
        for i in range(1000):
            values = {st: float(samples[i, j]) for j, st in enumerate(GAS_SENSOR_TYPES)}
            bundles.append(make_gas_bundle(
                ts + timedelta(seconds=i*3), 'gas_A', values
            ))

        detector = GasIsolationForestDetector()
        metrics = detector.fit(bundles)
        assert metrics['n_samples_trained'] >= 1000
        assert detector.is_fitted()

        # NORMAL 분포 예측 → 대부분 NORMAL
        rng2 = np.random.default_rng(100)
        normal_count = 0
        for _ in range(30):
            s = rng2.multivariate_normal(params['mean'], params['cov'])
            values = {st: float(s[j]) for j, st in enumerate(GAS_SENSOR_TYPES)}
            r = detector.predict(make_gas_bundle(ts, 'gas_A', values))
            if r.level == RiskLevel.NORMAL:
                normal_count += 1
        assert normal_count >= 24  # ~80%+

    def test_predict_before_fit_raises(self, make_gas_bundle, ts):
        from gas.modules import GasIsolationForestDetector
        detector = GasIsolationForestDetector()
        with pytest.raises(RuntimeError):
            detector.predict(make_gas_bundle(ts, 'gas_A'))
