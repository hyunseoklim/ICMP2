"""
generator/integrated_story/story_24h — 24시간 통합 스토리 생성기.

본 모듈은 보고서 5.3의 *24시간 통합 시나리오*를 합성 데이터로 구현한다.
가스·전력 데이터가 *시간축 위에서 연결된 사건*에 따라 변화하는
통합 시나리오를 생성.

이벤트 시퀀스 (U.1~U.10):
    U.1 (06:00): IDLE 시작 (야간 → 새벽)
    U.2 (07:00): 환기 WEAK 시작 (정비)
    U.3 (08:00): WORKING 진입, 환기 NORMAL 회복
    U.4 (10:30): 도장 작업 집중 — VOC 점진 상승 (사전 경고)
    U.5 (12:00): 점심 (IDLE), 환기 약화
    U.6 (13:00): WORKING 재개
    U.7 (15:00): 환기 STRONG 강제
    U.8 (16:00): H2S 누출 사고 (위험)
    U.9 (17:00): 환기·차단 대응
    U.10 (18:00): IDLE 전환 (퇴근)

활용처:
    - Phase 4 통합 검증
    - 학습된 모델의 *시간 연속성 판정* 평가
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from devkit.core.data_types import SensorBundle
from devkit.core.enums import WorkMode, RiskLevel
from power.core.enums import WorkMode as _PowerWorkMode  # 수직 분리: power 호출용 값변환
from gas.premises import (
    GAS_SENSOR_TYPES, GAS_RESOLUTION,
    VentilationLevel, get_distribution_params as gas_params,
    INTER_DEVICE_GAS_CORRELATION,
)
from power.premises import (
    POWER_SENSOR_TYPES, POWER_RESOLUTION,
    get_distribution_params as power_params,
)
from devkit.generator.core.time_index import build_time_axis


# ============================================================================
# Event dataclass — U.1~U.10 사건 정의
# ============================================================================

@dataclass
class Event:
    """24시간 스토리의 단일 사건.
    
    Attributes:
        event_id: 'U.1', 'U.2', ... 'U.10'.
        time_offset_seconds: 스토리 시작 시점부터의 오프셋 (초).
        name: 한글 사건 이름.
        ventilation: 본 사건 *이후*의 환기 단계.
        work_mode: 본 사건 *이후*의 작업 모드.
        anomaly_type: 이상 상태 코드 ('none', 'voc_rising', 'h2s_leak', ...).
        anomaly_intensity: 이상 강도 (0.0~1.0).
        expected_max_level: 본 구간의 예상 최대 위험 등급.
        notes: 한글 설명.
    """

    event_id: str
    time_offset_seconds: int
    name: str
    ventilation: VentilationLevel
    work_mode: WorkMode
    anomaly_type: str = "none"
    anomaly_intensity: float = 0.0
    expected_max_level: RiskLevel = RiskLevel.NORMAL
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "time_offset_seconds": self.time_offset_seconds,
            "name": self.name,
            "ventilation": self.ventilation.value,
            "work_mode": self.work_mode.value,
            "anomaly_type": self.anomaly_type,
            "anomaly_intensity": self.anomaly_intensity,
            "expected_max_level": self.expected_max_level.value,
            "notes": self.notes,
        }


# ============================================================================
# STORY_EVENTS — U.1~U.10 사전 정의
# ============================================================================

# 24시간 = 86400초, 3초 간격 = 28,800 시점
# 본 스토리는 06:00~18:00 (12시간 = 14,400 시점, 합리적 크기)
# 사건 시점은 스토리 시작(06:00)부터의 오프셋

# 시간 변환 도움: H시간 = H * 3600초
def _h(hours: float) -> int:
    return int(hours * 3600)


STORY_EVENTS: list = [
    Event(
        event_id="U.1",
        time_offset_seconds=_h(0),       # 06:00
        name="IDLE 시작",
        ventilation=VentilationLevel.NORMAL,
        work_mode=WorkMode.IDLE,
        notes="야간 → 새벽, IDLE 시작",
    ),
    Event(
        event_id="U.2",
        time_offset_seconds=_h(1),       # 07:00
        name="환기 WEAK (정비)",
        ventilation=VentilationLevel.WEAK,
        work_mode=WorkMode.IDLE,
        anomaly_type="ventilation_weak",
        anomaly_intensity=0.5,
        expected_max_level=RiskLevel.CAUTION,
        notes="정비 시간 동안 환기 약화 → 가스 농도 점진 상승",
    ),
    Event(
        event_id="U.3",
        time_offset_seconds=_h(2),       # 08:00
        name="WORKING 진입",
        ventilation=VentilationLevel.NORMAL,
        work_mode=WorkMode.WORKING,
        notes="WORKING 진입 + 환기 NORMAL 회복",
    ),
    Event(
        event_id="U.4",
        time_offset_seconds=int(2.5 * 3600),  # 08:30 (NORMAL 안정 후)
        name="도장 작업 집중",
        ventilation=VentilationLevel.NORMAL,
        work_mode=WorkMode.WORKING,
        anomaly_type="voc_rising",
        anomaly_intensity=0.6,
        expected_max_level=RiskLevel.CAUTION,
        notes="VOC 점진 상승 — ARIMA 사전 경고 트리거",
    ),
    Event(
        event_id="U.5",
        time_offset_seconds=_h(6),       # 12:00
        name="점심 IDLE",
        ventilation=VentilationLevel.WEAK,
        work_mode=WorkMode.IDLE,
        notes="점심 시간 — IDLE + 환기 약화",
    ),
    Event(
        event_id="U.6",
        time_offset_seconds=_h(7),       # 13:00
        name="WORKING 재개",
        ventilation=VentilationLevel.NORMAL,
        work_mode=WorkMode.WORKING,
        notes="작업 재개 — 정상 패턴 복귀",
    ),
    Event(
        event_id="U.7",
        time_offset_seconds=_h(9),       # 15:00
        name="환기 STRONG",
        ventilation=VentilationLevel.STRONG,
        work_mode=WorkMode.WORKING,
        notes="환기 강제 강화 — 가스 농도 ↓",
    ),
    Event(
        event_id="U.8",
        time_offset_seconds=_h(10),      # 16:00
        name="H2S 누출 사고",
        ventilation=VentilationLevel.STRONG,
        work_mode=WorkMode.WORKING,
        anomaly_type="h2s_leak",
        anomaly_intensity=1.0,
        expected_max_level=RiskLevel.DANGER,
        notes="H2S 위험 임계 초과 — DANGER 발생",
    ),
    Event(
        event_id="U.9",
        time_offset_seconds=int(10.5 * 3600),  # 16:30
        name="환기·차단 대응",
        ventilation=VentilationLevel.STRONG,
        work_mode=WorkMode.IDLE,
        anomaly_type="h2s_recovery",
        anomaly_intensity=0.3,
        expected_max_level=RiskLevel.CAUTION,
        notes="H2S 회복 중 (강제 환기·작업 중단)",
    ),
    Event(
        event_id="U.10",
        time_offset_seconds=_h(12),      # 18:00
        name="IDLE 전환 (퇴근)",
        ventilation=VentilationLevel.NORMAL,
        work_mode=WorkMode.IDLE,
        notes="작업 종료 — 일상 패턴 종료",
    ),
]


# ============================================================================
# 통합 스토리 생성 함수
# ============================================================================

def generate_integrated_story_24h(
    start_time: Optional[datetime] = None,
    duration_hours: float = 12.0,
    seed: int = 42,
    apply_quantization: bool = True,
) -> dict:
    """24시간(기본 12시간 6시~18시) 통합 스토리 생성.
    
    Args:
        start_time: 시작 시각. None이면 2026-05-19 06:00 UTC.
        duration_hours: 스토리 길이 (기본 12시간).
        seed: 난수 시드.
        apply_quantization: M.7 양자화 적용.
    
    Returns:
        dict:
            - gas_bundles: list[SensorBundle] (gas_A + gas_B)
            - power_bundles: list[SensorBundle] (power_1)
            - events: list[dict] (사건 정보)
            - metadata: dict (시작/종료, 시점 수 등)
    """
    if start_time is None:
        start_time = datetime(2026, 5, 19, 6, 0, tzinfo=timezone.utc)

    rng = np.random.default_rng(seed)
    n_steps = int(duration_hours * 3600 / 3.0)  # M.4 3초 간격
    timestamps = build_time_axis(start_time, n_steps)

    # 각 시점의 활성 사건 결정
    active_events = _resolve_active_events_per_step(n_steps)

    # 가스·전력 합성
    gas_samples_A, gas_samples_B = _generate_gas_timeseries(
        n_steps, active_events, rng
    )
    power_samples = _generate_power_timeseries(n_steps, active_events, rng)

    # 양자화
    if apply_quantization:
        for i, st in enumerate(GAS_SENSOR_TYPES):
            res = GAS_RESOLUTION[st]
            gas_samples_A[:, i] = np.round(gas_samples_A[:, i] / res) * res
            gas_samples_B[:, i] = np.round(gas_samples_B[:, i] / res) * res
        for i, st in enumerate(POWER_SENSOR_TYPES):
            res = POWER_RESOLUTION[st]
            power_samples[:, i] = np.round(power_samples[:, i] / res) * res

    # SensorBundle 변환
    gas_bundles = []
    for t_idx, ts in enumerate(timestamps):
        # gas_A
        values_A = {st: float(gas_samples_A[t_idx, i]) for i, st in enumerate(GAS_SENSOR_TYPES)}
        flags_A = {st: True for st in GAS_SENSOR_TYPES}
        gas_bundles.append(SensorBundle(
            timestamp=ts, device_id="gas_A",
            values=values_A, is_valid_flags=flags_A,
        ))
        # gas_B
        values_B = {st: float(gas_samples_B[t_idx, i]) for i, st in enumerate(GAS_SENSOR_TYPES)}
        flags_B = {st: True for st in GAS_SENSOR_TYPES}
        gas_bundles.append(SensorBundle(
            timestamp=ts, device_id="gas_B",
            values=values_B, is_valid_flags=flags_B,
        ))

    power_bundles = []
    for t_idx, ts in enumerate(timestamps):
        values = {st: float(power_samples[t_idx, i]) for i, st in enumerate(POWER_SENSOR_TYPES)}
        flags = {st: True for st in POWER_SENSOR_TYPES}
        power_bundles.append(SensorBundle(
            timestamp=ts, device_id="power_1",
            values=values, is_valid_flags=flags,
        ))

    return {
        "gas_bundles": gas_bundles,
        "power_bundles": power_bundles,
        "events": [e.to_dict() for e in STORY_EVENTS],
        "metadata": {
            "start_time": start_time.isoformat(),
            "end_time": timestamps[-1].isoformat(),
            "duration_hours": duration_hours,
            "n_steps": n_steps,
            "interval_seconds": 3.0,
            "n_gas_bundles": len(gas_bundles),
            "n_power_bundles": len(power_bundles),
            "seed": seed,
        },
    }


# ============================================================================
# 내부 헬퍼
# ============================================================================

def _resolve_active_events_per_step(n_steps: int) -> list:
    """각 시점에 활성화된 사건(가장 최근 사건) 리스트 반환."""
    active = [None] * n_steps
    current_event = STORY_EVENTS[0]
    event_idx = 0

    for step in range(n_steps):
        t_offset = step * 3  # 초
        # 다음 사건의 시점에 도달했는지 확인
        while (event_idx + 1 < len(STORY_EVENTS) and
               STORY_EVENTS[event_idx + 1].time_offset_seconds <= t_offset):
            event_idx += 1
            current_event = STORY_EVENTS[event_idx]
        active[step] = current_event

    return active


def _generate_gas_timeseries(
    n_steps: int,
    active_events: list,
    rng: np.random.Generator,
) -> tuple:
    """각 시점의 활성 사건에 따른 가스 9차원 시계열 생성 (gas_A, gas_B)."""
    samples = np.zeros((n_steps, len(GAS_SENSOR_TYPES)))
    rho = INTER_DEVICE_GAS_CORRELATION

    # 1. 각 시점의 환기 단계별 기본 평균·공분산으로 truth 추출
    for step in range(n_steps):
        event = active_events[step]
        params = gas_params(event.ventilation)
        truth = rng.multivariate_normal(params["mean"], params["cov"])

        # 이상 상태 적용
        truth = _apply_gas_anomaly(truth, event, step, n_steps, rng)

        samples[step] = truth

    # 2. 두 장비 간 상관 ρ = 0.78 적용 (잔차 결합)
    noise_scale = np.sqrt((1.0 - rho) / rho)
    gas_stds = np.array([np.sqrt(gas_params(VentilationLevel.NORMAL)["cov"][i, i])
                         for i in range(len(GAS_SENSOR_TYPES))])
    noise_std = gas_stds * noise_scale
    noise_A = rng.normal(0, noise_std, size=samples.shape)
    noise_B = rng.normal(0, noise_std, size=samples.shape)

    return samples + noise_A, samples + noise_B


def _apply_gas_anomaly(
    truth: np.ndarray,
    event: Event,
    step: int,
    n_steps: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """사건별 이상 상태를 가스 truth 벡터에 적용."""
    if event.anomaly_type == "voc_rising":
        # VOC 점진 상승 — 진행 비율에 따라
        voc_idx = GAS_SENSOR_TYPES.index("voc")
        # 사건 시작 시점부터의 진행도 계산 (대략)
        progress = min(1.0, (step * 3 - event.time_offset_seconds) / 7200.0)  # 2시간 동안 상승
        progress = max(0.0, progress)
        truth[voc_idx] = 50.0 + progress * 200.0 * event.anomaly_intensity

    elif event.anomaly_type == "h2s_leak":
        # H2S 급격 누출
        h2s_idx = GAS_SENSOR_TYPES.index("h2s")
        progress = min(1.0, (step * 3 - event.time_offset_seconds) / 600.0)  # 10분 동안 상승
        progress = max(0.0, progress)
        truth[h2s_idx] = 1.0 + progress * 25.0 * event.anomaly_intensity

    elif event.anomaly_type == "h2s_recovery":
        # H2S 회복 (강제 환기로 점진 하락)
        h2s_idx = GAS_SENSOR_TYPES.index("h2s")
        progress = min(1.0, (step * 3 - event.time_offset_seconds) / 1800.0)  # 30분 회복
        progress = max(0.0, progress)
        peak = 25.0
        recovery_target = 1.0
        truth[h2s_idx] = peak * (1.0 - progress) + recovery_target * progress

    return truth


def _generate_power_timeseries(
    n_steps: int,
    active_events: list,
    rng: np.random.Generator,
) -> np.ndarray:
    """각 시점의 활성 사건에 따른 전력 3차원 시계열 생성."""
    samples = np.zeros((n_steps, len(POWER_SENSOR_TYPES)))
    v_idx = POWER_SENSOR_TYPES.index("voltage")
    i_idx = POWER_SENSOR_TYPES.index("current")
    p_idx = POWER_SENSOR_TYPES.index("power")

    for step in range(n_steps):
        event = active_events[step]
        # 수직 분리: 스토리의 WorkMode(devkit.core)를 power.core 값으로 변환해 전달
        params = power_params(_PowerWorkMode(event.work_mode.value))

        # V·I만 분포에서 추출
        vi_mean = np.array([params["mean"][v_idx], params["mean"][i_idx]])
        vi_cov = np.array([
            [params["cov"][v_idx, v_idx], params["cov"][v_idx, i_idx]],
            [params["cov"][i_idx, v_idx], params["cov"][i_idx, i_idx]],
        ])
        vi = rng.multivariate_normal(vi_mean, vi_cov)

        # P = V × I + 1% 노이즈 (옴의 법칙 보장)
        v = vi[0]
        i = vi[1]
        p_expected = v * i
        p = p_expected + rng.normal(0, 0.01 * abs(p_expected))

        samples[step, v_idx] = v
        samples[step, i_idx] = i
        samples[step, p_idx] = p

    return samples
