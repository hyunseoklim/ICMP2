"""
generator/transition/parametric — 파라미터화 전이 시나리오 생성기.

미래 위험 예측 서브시스템의 B2·C3 보정용. 단일 채널의 *정상→이상 전이*
시계열을 형태·전개속도를 파라미터로 받아 합성한다.

설계 의도:
    - steps_to_threshold가 연속 knob — B2·C3가 전개속도를 sweep 가능.
    - speed 3프리셋(slow/medium/fast)은 카탈로그·리포트의 대표값.
    - 배경 잡음은 AR(1) 자기상관 (noise_phi 기본 0.95) — 구조 진단의
      i.i.d. 백색잡음 데이터 정책 결함을 반복하지 않음. noise_phi=0이면
      백색잡음 (비교 실험용 옵션).

⚠ 전개속도(slow/medium/fast)는 실측 도메인 사실이 아니라 *검증용 더미
   가정값*이다 (실측·연구 근거 없음). 3초 측정 간격 기준.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


# speed 프리셋 → 임계 도달 스텝 (3초 간격 — 더미 가정값)
SPEED_PRESETS: dict = {
    "slow": 900,    # ≈ 45분
    "medium": 200,  # ≈ 10분
    "fast": 40,     # ≈ 2분
}

_SHAPES: tuple = ("linear", "accelerating", "saturation", "step", "spike")
_DEFAULT_SPIKE_DURATION: int = 8


def generate_transition(
    shape: str,
    *,
    speed: str = "medium",
    steps_to_threshold: Optional[int] = None,
    baseline: float = 50.0,
    threshold: float = 200.0,
    n_steps: int = 400,
    onset_step: int = 120,
    noise_std: float = 12.0,
    noise_phi: float = 0.95,
    spike_duration: int = _DEFAULT_SPIKE_DURATION,
    seed: int = 42,
) -> np.ndarray:
    """단일 채널 정상→이상 전이 시계열을 합성.

    Args:
        shape: 전이 형태 — 'linear'/'accelerating'/'saturation'/'step'/'spike'.
        speed: 전개속도 프리셋 'slow'/'medium'/'fast' (SPEED_PRESETS).
               step/spike에는 적용 안 됨 (즉시 전이).
        steps_to_threshold: 임계 도달까지 스텝 수. 지정 시 speed 무시
                            (B2·C3 sweep용 연속 knob).
        baseline: 정상 레벨.
        threshold: 전이가 향하는 목표 임계.
        n_steps: 전체 시계열 길이.
        onset_step: 전이 시작 시점 (이전은 평탄 baseline).
        noise_std: 측정 잡음의 정상 표준편차.
        noise_phi: 잡음 AR(1) 자기상관 계수. 기본 0.95(자기상관),
                   0이면 백색잡음.
        spike_duration: shape='spike'의 급등 지속 스텝 수.
        seed: 난수 시드.

    Returns:
        np.ndarray (1D, 길이 n_steps) — 전이 시계열.

    Raises:
        ValueError: 파라미터 위반.
    """
    if shape not in _SHAPES:
        raise ValueError(f"shape는 {_SHAPES} 중 하나여야 함. 받은 값: {shape!r}")
    if speed not in SPEED_PRESETS:
        raise ValueError(
            f"speed는 {tuple(SPEED_PRESETS)} 중 하나여야 함. 받은 값: {speed!r}"
        )
    if n_steps < 1:
        raise ValueError(f"n_steps는 1 이상. 받은 값: {n_steps}")
    if not 0 <= onset_step < n_steps:
        raise ValueError(
            f"onset_step은 [0, n_steps) 범위여야 함. 받은 값: {onset_step}"
        )
    if not 0.0 <= noise_phi < 1.0:
        raise ValueError(f"noise_phi는 [0, 1) 범위여야 함. 받은 값: {noise_phi}")
    if noise_std < 0:
        raise ValueError(f"noise_std는 0 이상이어야 함. 받은 값: {noise_std}")

    S = int(steps_to_threshold) if steps_to_threshold is not None else SPEED_PRESETS[speed]
    if S < 1:
        raise ValueError(f"steps_to_threshold는 1 이상이어야 함. 받은 값: {S}")

    rng = np.random.default_rng(seed)
    baseline = float(baseline)
    threshold = float(threshold)
    delta = threshold - baseline

    # ── 1. 결정적 truth 궤적 ──
    truth = np.full(n_steps, baseline, dtype=float)
    # 전이 시작부터의 경과 스텝 t = 0, 1, 2, ...
    post = np.arange(n_steps - onset_step, dtype=float)

    if shape == "linear":
        truth[onset_step:] = baseline + delta * (post / S)
    elif shape == "accelerating":
        # 볼록 — 점점 빠르게 (t=S에서 임계 통과)
        truth[onset_step:] = baseline + delta * (post / S) ** 2
    elif shape == "saturation":
        # 오목 — 빠르게 상승 후 포화. 점근선이 임계보다 위라
        # t=S에서 정확히 임계를 통과한다.
        delta_sat = delta / (1.0 - np.exp(-1.0))
        truth[onset_step:] = baseline + delta_sat * (1.0 - np.exp(-post / S))
    elif shape == "step":
        # onset에서 즉시 임계로 계단 (speed 무관)
        truth[onset_step:] = threshold
    elif shape == "spike":
        # onset에서 임계로 급등, spike_duration 후 baseline 복귀
        end = min(onset_step + max(1, int(spike_duration)), n_steps)
        truth[onset_step:end] = threshold

    # ── 2. AR(1) 배경 잡음 (noise_phi=0이면 백색) ──
    if noise_phi > 0.0:
        innov_std = noise_std * np.sqrt(1.0 - noise_phi ** 2)
    else:
        innov_std = noise_std
    noise = np.empty(n_steps, dtype=float)
    noise[0] = rng.normal(0.0, noise_std)
    for t in range(1, n_steps):
        noise[t] = noise_phi * noise[t - 1] + rng.normal(0.0, innov_std)

    return truth + noise
