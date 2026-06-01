"""tests/power/test_power.py — 전력 영역 핵심 테스트."""

import numpy as np
import pytest

from power.core.enums import RiskLevel, WorkMode
from power.core.modules import ThresholdClassifier
from power.premises import (
    POWER_SENSOR_TYPES, POWER_DIMENSION,
    correlation_matrix, covariance_matrix,
    mean_vector, get_distribution_params,
    POWER_MEANS_WORKING, POWER_MEANS_IDLE,
    working_means, working_stds,
    expected_power, verify_ohm_law,
)
from power.thresholds import load_power_thresholds


class TestPowerDistribution:
    def test_dimension(self):
        assert len(POWER_SENSOR_TYPES) == 3
        assert POWER_DIMENSION == 3
        assert POWER_SENSOR_TYPES == ['voltage', 'current', 'power']

    def test_legacy_working_means_dict_preserved(self):
        """Deprecated POWER_MEANS_WORKING dict — 외부 호환성 위해 유지.

        Phase B-2에서 working_means(rated_w) 함수로 대체됐으나 dict 자체는
        병행 export (reports/MIGRATION.md). 6개월 후 제거 예정.
        """
        assert POWER_MEANS_WORKING['voltage'] == 220.0
        assert POWER_MEANS_WORKING['current'] == 11.0
        assert POWER_MEANS_WORKING['power'] == 2420.0

    def test_working_means_low_power_group(self):
        """Phase B-2 (가) 통일 공식 — rated × 0.4 fallback (정상 데이터 부족 그룹)."""
        m_50 = working_means(50)
        assert m_50['voltage'] == 220.0
        assert m_50['power'] == pytest.approx(20.0, abs=0.01)   # 50 × 0.4
        assert m_50['current'] == pytest.approx(0.091, abs=0.001)  # 20 / 220

        m_400 = working_means(400)
        assert m_400['power'] == pytest.approx(160.0, abs=0.01)  # 400 × 0.4

    def test_working_means_high_power_group(self):
        """Phase B-2 (다) 하이브리드 — DB 실측 평균 (부하율<50% 필터 후)."""
        # 1000W: 시나리오 ① 채택 후 (P) 그룹 평균
        m_1000 = working_means(1000)
        assert m_1000['power'] == pytest.approx(365.9, abs=0.01)
        # mean/rated ≈ 0.366 — 결정 ① "rated × 0.4 정상 평균" 정합
        assert 0.35 < m_1000['power'] / 1000 < 0.40

        # 800W
        m_800 = working_means(800)
        assert m_800['power'] == pytest.approx(290.3, abs=0.01)

    def test_working_means_fallback(self):
        """미정의 rated_w → (가) 통일 공식 fallback."""
        m = working_means(150)   # _GROUP_MEANS_WORKING에 없음
        assert m['power'] == pytest.approx(60.0, abs=0.01)   # 150 × 0.4

    def test_working_stds_ratio(self):
        """working_stds — voltage 절대값, current/power는 평균 × 0.25."""
        s = working_stds(1000)
        assert s['voltage'] == 5.0
        m = working_means(1000)
        assert s['current'] == pytest.approx(m['current'] * 0.25, rel=1e-6)
        assert s['power'] == pytest.approx(m['power'] * 0.25, rel=1e-6)

    def test_idle_means(self):
        assert POWER_MEANS_IDLE['current'] == 1.0
        assert POWER_MEANS_IDLE['power'] == 220.0

    def test_correlation_positive_definite(self):
        R = correlation_matrix()
        assert np.all(np.linalg.eigvalsh(R) > 0)

    def test_correlation_values(self):
        R = correlation_matrix()
        idx = {st: i for i, st in enumerate(POWER_SENSOR_TYPES)}
        # current-power 0.95
        assert R[idx['current'], idx['power']] == 0.95
        # voltage-current 0.1 (D-20260519-002 보정값)
        assert R[idx['voltage'], idx['current']] == 0.1

    def test_covariance_positive_definite(self):
        C = covariance_matrix(WorkMode.WORKING)
        assert np.all(np.linalg.eigvalsh(C) > 0)
        C_idle = covariance_matrix(WorkMode.IDLE)
        assert np.all(np.linalg.eigvalsh(C_idle) > 0)


class TestOhmLaw:
    def test_expected_power(self):
        assert expected_power(220, 11) == 2420.0

    def test_consistent(self):
        r = verify_ohm_law(220.0, 11.0, 2420.0)
        assert r['is_consistent']
        assert r['residual'] == 0.0

    def test_inconsistent(self):
        r = verify_ohm_law(220.0, 11.0, 3000.0)
        assert not r['is_consistent']

    def test_tolerance(self):
        # 5% 오차는 기본 10% 허용 안에서 일관성 인정
        r = verify_ohm_law(220.0, 11.0, 2541.0)  # +5%
        assert r['is_consistent']


class TestPowerThresholds:
    def test_load(self):
        table = load_power_thresholds()
        assert len(table) == 3

    def test_voltage_both_direction(self):
        table = load_power_thresholds()
        assert table['voltage']['direction'] == 'both'
        assert table['voltage']['caution_low'] == 200.0
        assert table['voltage']['caution_high'] == 240.0

    def test_classifier_voltage(self, ts, make_point):
        classifier = ThresholdClassifier(load_power_thresholds())
        # 정상
        assert classifier.classify(make_point(ts, 'power_1', 'voltage', 220.0)).level == RiskLevel.NORMAL
        # 고측 주의
        assert classifier.classify(make_point(ts, 'power_1', 'voltage', 250.0)).level == RiskLevel.CAUTION
        # 저측 위험
        assert classifier.classify(make_point(ts, 'power_1', 'voltage', 170.0)).level == RiskLevel.DANGER


@pytest.mark.slow
class TestPowerIsolationForest:
    def test_default_threshold_d002(self):
        from power.modules import PowerIsolationForestDetector
        detector = PowerIsolationForestDetector()
        # D-20260519-002: 3차원 카이제곱 99.7% 임계
        assert detector.mahalanobis_threshold == 3.76

    def test_fit_and_predict(self, make_power_bundle, ts):
        from power.modules import PowerIsolationForestDetector
        from datetime import timedelta

        params = get_distribution_params(WorkMode.WORKING)
        rng = np.random.default_rng(42)
        samples = rng.multivariate_normal(params['mean'], params['cov'], size=1000)

        bundles = []
        for i in range(1000):
            values = {st: float(samples[i, j]) for j, st in enumerate(POWER_SENSOR_TYPES)}
            bundles.append(make_power_bundle(
                ts + timedelta(seconds=i*3), 'power_1', values
            ))

        detector = PowerIsolationForestDetector()
        metrics = detector.fit(bundles)
        assert detector.is_fitted()
        assert metrics['n_features'] == 3
