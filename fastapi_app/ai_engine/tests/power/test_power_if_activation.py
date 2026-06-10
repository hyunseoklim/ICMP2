"""tests/power/test_power_if_activation.py — 전력 IF 활성화(STEP F) 거동 잠금.

통합 검증 스토리(보고서 5.2.4) 단계 5의 핵심 명제:
    "① Threshold가 못 잡는 위험을 ③ Isolation Forest가 잡는다."

high 모델(rated 100~1000W 풀)에 스토리 전력 벡터를 넣어 다음을 보증한다:
    - 정상(366W/1.66A)        → NORMAL (분포 내)
    - 09:08(480W/3.0A, load48%) → CAUTION/OOD  ← Threshold 침묵(load<50%) 구간을 IF가 포착
    - 09:09(850W/4.0A, load85%) → CAUTION/OOD  ← Threshold(DANGER)와 동시

decision #4 (IF 고유 포착 값) 보정 결과를 회귀 테스트로 고정한다.
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from common.data_types import SensorBundle
from common.enums import RiskLevel
from power.modules.isolation_forest import PowerIsolationForestDetector

_MODEL = Path(__file__).resolve().parents[2] / "models" / "power" / "iforest_high.joblib"


@pytest.fixture(scope="module")
def high_detector():
    if not _MODEL.exists():
        pytest.skip(f"high 모델 없음: {_MODEL}")
    d = PowerIsolationForestDetector()
    d.load(str(_MODEL))
    return d


def _predict(detector, V, I, P):
    bundle = SensorBundle(
        timestamp=datetime.now(timezone.utc),
        device_id="PWR-001",
        values={"voltage": V, "current": I, "power": P},
        is_valid_flags={"voltage": True, "current": True, "power": True},
    )
    return detector.predict(bundle)


class TestPowerIFStoryVectors:
    def test_normal_passes(self, high_detector):
        """정상 운영(366W/1.66A)은 분포 내 → NORMAL."""
        r = _predict(high_detector, 220.0, 1.66, 366.0)
        assert r.level == RiskLevel.NORMAL
        assert not r.is_out_of_distribution

    def test_if_unique_catch_when_threshold_silent(self, high_detector):
        """09:08 (480W/3.0A) — load_rate 48% < 50%라 Threshold는 침묵하나
        전압 안정+전류/전력 조합 이탈을 IF가 포착(CAUTION/OOD).
        단계 5의 핵심 명제 — 이 어서션이 깨지면 시연이 무너진다."""
        r = _predict(high_detector, 220.0, 3.0, 480.0)
        assert r.level == RiskLevel.CAUTION
        assert r.is_out_of_distribution
        assert r.mahalanobis_distance >= high_detector.mahalanobis_threshold

    def test_strong_spike_flagged(self, high_detector):
        """09:09 (850W/4.0A) — Threshold DANGER 구간도 IF가 함께 포착."""
        r = _predict(high_detector, 220.0, 4.0, 850.0)
        assert r.level == RiskLevel.CAUTION
        assert r.is_out_of_distribution
