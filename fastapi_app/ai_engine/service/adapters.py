"""adapters — 경계 변환 (순수 함수, ORM 무관).

raw stream payload(dict) ↔ 엔진 자료형(SensorBundle·DataPoint), 그리고
분석 결과 → result stream payload(계약 §4). Django 의존이 없어 AI 이미지에 그대로 포함된다.

엔진 타입 import는 gas 패키지가 (pip install로) 설치돼야 하므로 함수 내부 지연 import
(monitoring/ai/gas_if.py 의 지연 import 관례와 동일).
"""
from datetime import datetime, timezone

# gas/premises/gas_distribution.GAS_SENSOR_TYPES 와 일치 (monitoring/ai/gas_if.py 미러)
GAS_CHANNELS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']


def _parse_ts(raw) -> datetime:
    """measured_at(ISO 문자열) → tz-aware datetime. 누락·파싱실패 시 now(UTC)."""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except ValueError:
        return datetime.now(timezone.utc)


def raw_to_gas_bundle(payload: dict):
    """가스 raw payload → SensorBundle (9채널 1시점). 결측 채널은 is_valid=False."""
    from gas.core.data_types import SensorBundle

    values = {ch: payload.get(ch) for ch in GAS_CHANNELS}
    is_valid = {ch: values[ch] is not None for ch in GAS_CHANNELS}
    return SensorBundle(
        timestamp=_parse_ts(payload.get('measured_at')),
        device_id=payload.get('device_uid'),
        values=values,
        is_valid_flags=is_valid,
    )


def raw_to_datapoint(payload: dict, sensor_type: str):
    """가스 raw payload의 한 센서 → DataPoint (ARIMA history push용)."""
    from gas.core.data_types import DataPoint

    value = payload.get(sensor_type)
    return DataPoint(
        timestamp=_parse_ts(payload.get('measured_at')),
        device_id=payload.get('device_uid'),
        sensor_type=sensor_type,
        value=value,
        is_valid=value is not None,
    )


# 전력 metric(sensor_type) → raw payload 키
POWER_METRIC_KEYS = {'voltage': 'voltage_v', 'current': 'current_a', 'power': 'power_w'}


def raw_to_power_bundle(payload: dict):
    """전력 raw payload → SensorBundle (voltage/current/power). IF 분포 분석용."""
    from power.core.data_types import SensorBundle
    from power.premises.power_distribution import POWER_SENSOR_TYPES

    values = {st: payload.get(POWER_METRIC_KEYS.get(st, st)) for st in POWER_SENSOR_TYPES}
    is_valid = {st: values[st] is not None for st in POWER_SENSOR_TYPES}
    return SensorBundle(
        timestamp=_parse_ts(payload.get('measured_at')),
        device_id=payload.get('device_uid'),
        values=values,
        is_valid_flags=is_valid,
    )


def result_to_payload(
    *, trace_id, device_uid, sensor_type, stage, level, score,
    computed_at, channel_code=None, detail=None,
) -> dict:
    """분석 결과 → result stream payload (계약 §4). channel_code는 전력만."""
    payload = {
        'trace_id': trace_id,
        'device_uid': device_uid,
        'sensor_type': sensor_type,
        'stage': stage,
        'level': level,
        'score': score,
        'computed_at': computed_at,
        'detail': detail or {},
    }
    if channel_code is not None:
        payload['channel_code'] = channel_code
    return payload
