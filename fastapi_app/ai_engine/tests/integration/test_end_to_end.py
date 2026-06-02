"""tests/integration/test_end_to_end.py — 통합 흐름 (생성 → 학습 → 판정)."""

import numpy as np
import pytest

from common.enums import RiskLevel, WorkMode
from common.modules import ThresholdClassifier
from gas.modules import GasIsolationForestDetector
from gas.thresholds import load_gas_thresholds
from gas.premises import VentilationLevel, get_distribution_params as gas_params
from power.modules import PowerIsolationForestDetector
from power.thresholds import load_power_thresholds
from power.premises import get_distribution_params as power_params
from generator.gas_generator import (
    generate_gas_normal_pool, split_pool_by_device,
    generate_scenario as gen_gas_scenario,
)
from generator.power_generator import (
    generate_power_normal_pool,
    generate_scenario as gen_power_scenario,
)


@pytest.mark.slow
class TestEndToEndGas:
    """가스 통합 흐름: 생성 → 학습 → 시나리오 카드 판정."""

    def test_full_gas_workflow(self):
        # 1. 생성: 학습 풀
        bundles = generate_gas_normal_pool(n_samples=2000, seed=42)
        gas_a, _ = split_pool_by_device(bundles)

        # 2. 학습: IF
        detector = GasIsolationForestDetector()
        metrics = detector.fit(gas_a)
        assert detector.is_fitted()

        # 3. 판정: S-T1 시나리오 (CO 점진 상승)
        scenario = gen_gas_scenario('S-T1', n_samples=200)
        late_results = [detector.predict(b) for b in scenario[150:]]
        caution_count = sum(1 for r in late_results if r.level == RiskLevel.CAUTION)
        # 위험 구간 50개 중 대부분 CAUTION
        assert caution_count >= 40


@pytest.mark.slow
class TestEndToEndPower:
    """전력 통합 흐름."""

    def test_full_power_workflow(self):
        # 1. 생성: 학습 풀 (옴의 법칙 보장)
        bundles = generate_power_normal_pool(n_samples=2000, seed=42)

        # 2. 학습: IF
        detector = PowerIsolationForestDetector()
        metrics = detector.fit(bundles)
        assert detector.is_fitted()

        # 3. 판정: S-T-I 시나리오 (전류 급증)
        scenario = gen_power_scenario('S-T-I', n_samples=200)
        late_results = [detector.predict(b) for b in scenario[150:]]
        caution_count = sum(1 for r in late_results if r.level == RiskLevel.CAUTION)
        # 위험 구간 50개 중 대부분 CAUTION
        assert caution_count >= 40


@pytest.mark.slow
class TestEndToEndThreshold:
    """Threshold 기반 통합 흐름 (학습 불필요)."""

    def test_gas_threshold_workflow(self, ts, make_point):
        # 1. Threshold 로드
        classifier = ThresholdClassifier(load_gas_thresholds())
        # 2. 시나리오 데이터 판정
        scenario = gen_gas_scenario('S-T1', n_samples=200)
        # S-T1 끝부분은 CO 위험 (200+ ppm)
        last_bundle = scenario[-1]
        # 9개 가스 중 CO 판정
        from common.data_types import DataPoint
        p = DataPoint(
            timestamp=last_bundle.timestamp,
            device_id='gas_A',
            sensor_type='co',
            value=last_bundle.values['co'],
        )
        r = classifier.classify(p)
        assert r.level == RiskLevel.DANGER

    def test_power_threshold_workflow(self, ts, make_point):
        classifier = ThresholdClassifier(load_power_thresholds())
        # 전력 시나리오 S-T-V (전압 강하 → 위험)
        scenario = gen_power_scenario('S-T-V', n_samples=200)
        last = scenario[-1]
        from common.data_types import DataPoint
        p = DataPoint(
            timestamp=last.timestamp,
            device_id='power_1',
            sensor_type='voltage',
            value=last.values['voltage'],
        )
        r = classifier.classify(p)
        # 170V 부근 → 위험
        assert r.level == RiskLevel.DANGER


class TestB1Corroboration:
    """B1 — 교차모듈 확인. 예측 등급은 불변, 현재 탐지는 보강 증거로만."""

    @staticmethod
    def _arima_result(mean, ci_lower, ci_upper):
        """단일 채널 ARIMAResult를 합성 (normal 경로)."""
        from datetime import datetime, timezone
        from gas.modules.arima import ARIMAResult
        h = 60
        return ARIMAResult(
            timestamp=datetime.now(timezone.utc), device_id='g', sensor_type='voc',
            path='normal',
            forecast_mean=[mean] * h, ci_lower=[ci_lower] * h,
            ci_upper=[ci_upper] * h, forecast_steps=h,
            drift=0.5, drift_tstat=0.5, segment_length=60,
            anchor_index=0, order=(0, 1, 1), reason='test',
        )

    def test_grade_unchanged_by_present_level(self):
        # 예측 등급은 present_level과 무관하게 동일해야 함 (보수적 유지)
        from common.integration.forecast_policy import ForecastPolicy
        ar = self._arima_result(mean=100.0, ci_lower=30.0, ci_upper=175.0)
        r_normal = ForecastPolicy().grade(
            ar, caution=200.0, danger=500.0, present_level=RiskLevel.NORMAL)
        r_caution = ForecastPolicy().grade(
            ar, caution=200.0, danger=500.0, present_level=RiskLevel.CAUTION)
        assert r_normal.caution_confidence == r_caution.caution_confidence
        assert r_normal.headline_confidence == r_caution.headline_confidence

    def test_corroborated_when_present_and_forecast_both_risk(self):
        # 현재 CAUTION/DANGER + 예측 위험 → corroborated True
        from common.integration.forecast_policy import ForecastPolicy
        from common.enums import ForecastConfidence
        ar = self._arima_result(mean=100.0, ci_lower=30.0, ci_upper=175.0)
        r = ForecastPolicy().grade(
            ar, caution=200.0, danger=500.0, present_level=RiskLevel.CAUTION)
        assert r.headline_confidence == ForecastConfidence.TENTATIVE
        assert r.corroborated is True
        assert r.present_level == RiskLevel.CAUTION

    def test_uncorroborated_when_present_normal(self):
        # 현재 정상 → 미보강 (예측만으로는 corroborated 아님 — 강등도 없음)
        from common.integration.forecast_policy import ForecastPolicy
        ar = self._arima_result(mean=100.0, ci_lower=30.0, ci_upper=175.0)
        r = ForecastPolicy().grade(
            ar, caution=200.0, danger=500.0, present_level=RiskLevel.NORMAL)
        assert r.corroborated is False

    def test_no_corroboration_when_forecast_not_risk(self):
        # 예측이 위험을 가리키지 않으면 현재 CAUTION이어도 보강 대상 없음
        from common.integration.forecast_policy import ForecastPolicy
        ar = self._arima_result(mean=60.0, ci_lower=40.0, ci_upper=80.0)
        r = ForecastPolicy().grade(
            ar, caution=200.0, danger=500.0, present_level=RiskLevel.CAUTION)
        assert r.corroborated is False
