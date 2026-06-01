"""gas/tests/conftest.py — 가스 도메인 테스트 공통 fixture.

수직 분리(ai-vertical-split): 가스 테스트는 gas.core를 쓴다.
교차 도메인 fixture(make_power_bundle)는 제거 — power 의존 차단.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np
import pytest

from gas.core.data_types import DataPoint, SensorBundle


@pytest.fixture
def ts():
    """표준 테스트 시각 (2026-05-19 09:00 UTC)."""
    return datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def time_axis_30(ts):
    """30시점 시간축 (3초 간격)."""
    return [ts + timedelta(seconds=i * 3) for i in range(30)]


@pytest.fixture
def rng():
    """재현 가능한 난수 생성기 (seed=42)."""
    return np.random.default_rng(42)


@pytest.fixture
def make_point():
    """DataPoint 생성 헬퍼."""
    def _make(timestamp, device_id, sensor_type, value, is_valid=True):
        return DataPoint(
            timestamp=timestamp,
            device_id=device_id,
            sensor_type=sensor_type,
            value=value,
            is_valid=is_valid,
        )
    return _make


@pytest.fixture
def make_gas_bundle():
    """9가스 SensorBundle 생성 헬퍼."""
    from gas.premises import GAS_SENSOR_TYPES

    def _make(timestamp, device_id, values_dict=None):
        if values_dict is None:
            values_dict = {st: 5.0 for st in GAS_SENSOR_TYPES}
        values = {st: values_dict.get(st) for st in GAS_SENSOR_TYPES}
        flags = {st: values[st] is not None for st in GAS_SENSOR_TYPES}
        return SensorBundle(
            timestamp=timestamp,
            device_id=device_id,
            values=values,
            is_valid_flags=flags,
        )
    return _make
