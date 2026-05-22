"""tests/generator/test_generator.py — 생성기 영역 핵심 테스트."""

import numpy as np
import pytest

from generator.core import quantize_value, quantize_array, build_time_axis, inject_nan
from generator.gas_generator import generate_gas_normal_pool, generate_scenario as gen_gas_scenario
from generator.power_generator import generate_power_normal_pool, generate_scenario as gen_power_scenario
from generator.integrated_story import generate_integrated_story_24h, STORY_EVENTS
from generator.transition import (
    generate_transition, SPEED_PRESETS,
    TRANSITION_CATALOG, build_catalog_scenario,
    STORY_TRANSITION_MAP, get_story_transition,
)


class TestCore:
    def test_quantize_value(self):
        assert quantize_value(5.73, 1.0) == 6.0
        assert quantize_value(0.0157, 0.001) == 0.016

    def test_quantize_array_nan_preserved(self):
        arr = np.array([5.73, np.nan, 6.21])
        result = quantize_array(arr, 1.0)
        assert result[0] == 6.0
        assert np.isnan(result[1])

    def test_time_axis(self, ts):
        axis = build_time_axis(ts, n_steps=5)
        assert len(axis) == 5
        assert (axis[1] - axis[0]).total_seconds() == 3.0

    def test_inject_nan_ratio(self):
        rng = np.random.default_rng(0)
        X = rng.normal(0, 1, size=(1000, 9))
        _, mask = inject_nan(X, missing_ratio=0.05, seed=42)
        ratio = mask.sum() / mask.size
        assert abs(ratio - 0.05) < 0.01

    def test_inject_nan_seed_reproducibility(self):
        rng = np.random.default_rng(0)
        X = rng.normal(0, 1, size=(100, 9))
        _, mask1 = inject_nan(X, missing_ratio=0.05, seed=42)
        _, mask2 = inject_nan(X, missing_ratio=0.05, seed=42)
        assert np.array_equal(mask1, mask2)


@pytest.mark.slow
class TestGasGenerator:
    def test_normal_pool_size(self):
        bundles = generate_gas_normal_pool(n_samples=500, seed=42)
        # 2장비 × 500 = 1000
        assert len(bundles) == 1000

    def test_normal_pool_device_split(self):
        bundles = generate_gas_normal_pool(n_samples=500, seed=42)
        gas_a = [b for b in bundles if b.device_id == 'gas_A']
        gas_b = [b for b in bundles if b.device_id == 'gas_B']
        assert len(gas_a) == 500
        assert len(gas_b) == 500

    def test_scenario_st1_co_rising(self):
        bundles = gen_gas_scenario('S-T1', n_samples=200)
        co_start = bundles[0].values['co']
        co_end = bundles[-1].values['co']
        assert co_start < 50  # 정상 시작
        assert co_end > 200  # 위험 끝

    def test_scenario_st2_o2_falling(self):
        bundles = gen_gas_scenario('S-T2', n_samples=200)
        o2_start = bundles[0].values['o2']
        o2_end = bundles[-1].values['o2']
        assert o2_start > 19
        assert o2_end < 16  # 위험

    def test_scenario_invalid_id(self):
        with pytest.raises(ValueError):
            gen_gas_scenario('INVALID', n_samples=10)


@pytest.mark.slow
class TestPowerGenerator:
    def test_normal_pool_ohm_law(self):
        from power.premises import verify_ohm_law

        bundles = generate_power_normal_pool(n_samples=500, seed=42)
        consistent = 0
        total = 0
        for b in bundles:
            v = b.values.get('voltage')
            i = b.values.get('current')
            p = b.values.get('power')
            if v is not None and i is not None and p is not None:
                total += 1
                if verify_ohm_law(v, i, p, tolerance=0.05)['is_consistent']:
                    consistent += 1
        # 5% 허용 + 양자화 영향 고려, 85% 이상
        assert consistent / total >= 0.85

    def test_scenario_voltage_drop(self):
        bundles = gen_power_scenario('S-T-V', n_samples=200)
        v_end = bundles[-1].values['voltage']
        assert v_end < 200  # 강하

    def test_scenario_current_spike(self):
        bundles = gen_power_scenario('S-T-I', n_samples=200)
        i_end = bundles[-1].values['current']
        assert i_end > 30  # 위험


@pytest.mark.slow
class TestIntegratedStory:
    def test_default_generation(self):
        result = generate_integrated_story_24h(duration_hours=1.0, seed=42)
        assert 'gas_bundles' in result
        assert 'power_bundles' in result
        assert 'events' in result
        assert 'metadata' in result
        # 1시간 = 1200시점 × 2장비 = 2400 가스 묶음
        assert len(result['gas_bundles']) == 2400
        assert len(result['power_bundles']) == 1200

    def test_events_count(self):
        # U.1 ~ U.10 (10개)
        assert len(STORY_EVENTS) == 10
        event_ids = [e.event_id for e in STORY_EVENTS]
        assert event_ids == [f'U.{i}' for i in range(1, 11)]

    def test_h2s_leak_visible(self):
        # 12시간 스토리에서 H2S 누출(U.8) 영향 확인
        result = generate_integrated_story_24h(duration_hours=12.0, seed=42)
        gas_a = [b for b in result['gas_bundles'] if b.device_id == 'gas_A']
        h2s_values = [b.values['h2s'] for b in gas_a]
        max_h2s = max(h2s_values)
        # U.8 H2S 누출로 인해 max는 위험 임계(15) 초과 가능
        assert max_h2s > 10


class TestTransitionGenerator:
    """파라미터화 전이 생성기 (B2·C3 보정용)."""

    def test_length_all_shapes(self):
        for shape in ("linear", "accelerating", "saturation", "step", "spike"):
            s = generate_transition(shape, n_steps=300, seed=1)
            assert len(s) == 300

    def test_speed_presets(self):
        assert SPEED_PRESETS == {"slow": 900, "medium": 200, "fast": 40}

    def test_linear_reaches_threshold(self):
        # onset 120, 임계도달 100스텝 → index 220에서 임계 통과 (잡음 0)
        s = generate_transition(
            "linear", steps_to_threshold=100, baseline=50.0, threshold=200.0,
            n_steps=300, onset_step=120, noise_std=0.0, seed=1,
        )
        assert abs(s[220] - 200.0) < 1.0
        assert s[120] < 60.0  # onset 시점은 baseline 근처

    def test_step_jumps(self):
        s = generate_transition(
            "step", baseline=50.0, threshold=200.0, n_steps=300,
            onset_step=150, noise_std=0.0, seed=1,
        )
        assert abs(s[149] - 50.0) < 1.0
        assert abs(s[150] - 200.0) < 1.0

    def test_noise_phi_autocorrelation(self):
        def lag1(x):
            d = x - x.mean()
            return float(np.sum(d[1:] * d[:-1]) / np.sum(d * d))

        white = generate_transition(
            "linear", noise_phi=0.0, onset_step=300, n_steps=320,
            noise_std=10.0, seed=2,
        )[:300]
        ac = generate_transition(
            "linear", noise_phi=0.95, onset_step=300, n_steps=320,
            noise_std=10.0, seed=2,
        )[:300]
        assert abs(lag1(white)) < 0.25  # 백색잡음 — 자기상관 ≈ 0
        assert lag1(ac) > 0.6           # AR(1) — 자기상관 높음

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError):
            generate_transition("INVALID", n_steps=100)

    def test_catalog_entries(self):
        # {slow,medium,fast} × {linear,accelerating,saturation} = 9 + step + spike
        assert len(TRANSITION_CATALOG) == 11
        assert "medium-linear" in TRANSITION_CATALOG
        assert "step" in TRANSITION_CATALOG
        assert "spike" in TRANSITION_CATALOG

    def test_build_catalog_scenario(self):
        s = build_catalog_scenario("medium-linear", seed=1)
        # n_steps = onset(120) + S(200) + buffer(200)
        assert len(s) == 520
        with pytest.raises(ValueError):
            build_catalog_scenario("nonexistent")

    def test_story_transition_map_consistency(self):
        # 매핑 키는 실제 STORY_EVENTS 사건이며 anomaly_type이 일치해야 함
        events = {e.event_id: e for e in STORY_EVENTS}
        for event_id, m in STORY_TRANSITION_MAP.items():
            assert event_id in events
            assert m["anomaly_type"] == events[event_id].anomaly_type
            # catalog 값은 카탈로그 키이거나 None
            assert m["catalog"] is None or m["catalog"] in TRANSITION_CATALOG
        # anomaly_type != 'none'인 사건은 모두 매핑에 존재
        anomalous = {e.event_id for e in STORY_EVENTS if e.anomaly_type != "none"}
        assert anomalous == set(STORY_TRANSITION_MAP)

    def test_get_story_transition(self):
        assert get_story_transition("U.4")["catalog"] == "medium-linear"
        assert get_story_transition("U.9")["catalog"] is None
        with pytest.raises(KeyError):
            get_story_transition("U.1")  # anomaly_type='none' — 매핑 없음
