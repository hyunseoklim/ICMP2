"""tests/common/test_modules.py — common/modules 4개 모듈 핵심 테스트."""

import numpy as np
import pytest
from datetime import timedelta

from common.data_types import DataPoint
from common.enums import RiskLevel, CPPurpose
from common.modules import (
    SlidingWindow, ThresholdClassifier,
    ZScoreDetector, ChangePointDetector,
)


# ============================================================================
# SlidingWindow
# ============================================================================

class TestSlidingWindow:
    def test_init(self):
        sw = SlidingWindow(window_size=30)
        assert sw.window_size == 30

    def test_push_and_full(self, ts, make_point):
        sw = SlidingWindow(window_size=5)
        for i in range(5):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'co', 5.0))
        assert sw.is_full('gas_A', 'co')

    def test_valid_ratio(self, ts, make_point):
        sw = SlidingWindow(window_size=10)
        for i in range(8):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'co', 5.0))
        for i in range(2):
            sw.push(make_point(ts + timedelta(seconds=(8+i)*3), 'gas_A', 'co', None, is_valid=False))
        assert sw.valid_ratio('gas_A', 'co') == 0.8

    def test_multi_channel_separation(self, ts, make_point):
        sw = SlidingWindow(window_size=30)
        for i in range(30):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'co', 5.0))
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'h2s', 1.0))
        assert sw.is_full('gas_A', 'co')
        assert sw.is_full('gas_A', 'h2s')


# ============================================================================
# ThresholdClassifier
# ============================================================================

class TestThresholdClassifier:
    @pytest.fixture
    def classifier(self):
        table = {
            'co': {'direction': 'high', 'caution': 25.0, 'danger': 200.0},
            'o2': {'direction': 'low', 'caution': 18.0, 'danger': 16.0},
        }
        return ThresholdClassifier(table)

    def test_high_normal(self, ts, classifier, make_point):
        r = classifier.classify(make_point(ts, 'gas_A', 'co', 10.0))
        assert r.level == RiskLevel.NORMAL

    def test_high_caution(self, ts, classifier, make_point):
        r = classifier.classify(make_point(ts, 'gas_A', 'co', 100.0))
        assert r.level == RiskLevel.CAUTION

    def test_high_danger(self, ts, classifier, make_point):
        r = classifier.classify(make_point(ts, 'gas_A', 'co', 300.0))
        assert r.level == RiskLevel.DANGER

    def test_low_direction(self, ts, classifier, make_point):
        # O2가 낮을수록 위험
        assert classifier.classify(make_point(ts, 'gas_A', 'o2', 20.0)).level == RiskLevel.NORMAL
        assert classifier.classify(make_point(ts, 'gas_A', 'o2', 17.0)).level == RiskLevel.CAUTION
        assert classifier.classify(make_point(ts, 'gas_A', 'o2', 14.0)).level == RiskLevel.DANGER

    def test_failsafe_null(self, ts, classifier, make_point):
        r = classifier.classify(make_point(ts, 'gas_A', 'co', None))
        assert r.level == RiskLevel.UNKNOWN


# ============================================================================
# ZScoreDetector
# ============================================================================

class TestZScoreDetector:
    def test_window_not_full(self, ts, make_point):
        sw = SlidingWindow(window_size=30)
        detector = ZScoreDetector(sw)
        # 5개만 push
        for i in range(5):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'co', 5.0))
        last = make_point(ts + timedelta(seconds=15), 'gas_A', 'co', 5.0)
        sw.push(last)
        r = detector.detect(last)
        assert r.level == RiskLevel.UNKNOWN

    def test_std_zero_normal(self, ts, make_point):
        sw = SlidingWindow(window_size=30)
        detector = ZScoreDetector(sw)
        for i in range(30):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'co', 5.0))
        last = make_point(ts + timedelta(seconds=90), 'gas_A', 'co', 5.0)
        sw.push(last)
        r = detector.detect(last)
        assert r.level == RiskLevel.NORMAL

    def test_spike(self, ts, make_point):
        sw = SlidingWindow(window_size=30)
        detector = ZScoreDetector(sw, z_threshold=3.0)
        # 정상 분포
        rng = np.random.default_rng(42)
        for i in range(29):
            v = float(rng.normal(5.0, 1.0))
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'co', v))
        # SPIKE
        spike = make_point(ts + timedelta(seconds=87), 'gas_A', 'co', 15.0)
        sw.push(spike)
        r = detector.detect(spike)
        assert r.level == RiskLevel.CAUTION
        assert r.is_spike
        assert abs(r.z_score) >= 3.0


# ============================================================================
# ChangePointDetector
# ============================================================================

class TestChangePointDetector:
    def test_init(self, ts, make_point):
        sw = SlidingWindow(window_size=40)
        cp = ChangePointDetector(sw, purpose=CPPurpose.FLOW_DETECTION)
        assert cp.min_size == 10  # 40 * 0.25

    def test_predict_validation_min_size(self):
        sw = SlidingWindow(window_size=60)
        cp = ChangePointDetector(sw, purpose=CPPurpose.PREDICT_VALIDATION)
        assert cp.min_size == 15  # 60 * 0.25

    def test_window_not_full(self, ts, make_point):
        sw = SlidingWindow(window_size=40)
        cp = ChangePointDetector(sw, purpose=CPPurpose.FLOW_DETECTION)
        for i in range(5):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'voc', 100.0))
        r = cp.detect('gas_A', 'voc')
        assert r.level == RiskLevel.UNKNOWN

    def test_no_change_point(self, ts, make_point):
        sw = SlidingWindow(window_size=40)
        cp = ChangePointDetector(sw, purpose=CPPurpose.FLOW_DETECTION)
        # 모두 같은 값 → 분산 0
        for i in range(40):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'voc', 100.0))
        r = cp.detect('gas_A', 'voc')
        assert r.level == RiskLevel.NORMAL
        assert r.breakpoints == []

    def test_step_change(self, ts, make_point):
        sw = SlidingWindow(window_size=40)
        cp = ChangePointDetector(sw, purpose=CPPurpose.FLOW_DETECTION)
        rng = np.random.default_rng(42)
        # 앞 20: 평균 100, 뒤 20: 평균 250
        for i in range(20):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'voc',
                              float(rng.normal(100.0, 3.0))))
        for i in range(20, 40):
            sw.push(make_point(ts + timedelta(seconds=i*3), 'gas_A', 'voc',
                              float(rng.normal(250.0, 3.0))))
        r = cp.detect('gas_A', 'voc')
        assert r.has_change_point
        assert r.level == RiskLevel.CAUTION
        # 변화점은 20 부근에서 탐지
        nearest = min(r.breakpoints, key=lambda x: abs(x - 20))
        assert abs(nearest - 20) <= 3
