"""
scripts/calibrate_prediction — 미래 위험 예측 서브시스템 B2·C3 운영점 보정.

예측 서브시스템(CP → ARIMA → 출력 정책)을 전이 카탈로그 11종 + 정상
baseline에 대해 *시점별* 구동하고, 시나리오별 5개 지표를 측정한다.
7개 잠정 파라미터를 좌표(축별) sweep 하여 운영점 후보를 비교한다.

⚠ 완전 격자 sweep(예: 3^7 = 2187 구성)는 시나리오당 ARIMA 시점별 재적합
   비용 때문에 비현실적이다. 따라서 *좌표 sweep* 을 채택한다 — provisional
   중심점에서 한 축씩만 변화시켜 ~19개 구성을 비교한다. 축간 상호작용은
   포착하지 못하므로, 권고 조합은 적용 전 확인 재구동이 필요하다.

지표 5종 (Step 4 확정안):
    lead_time       전개형 — 임계통과 − 첫 CONFIRMED_WARNING 시점 (클수록 우수)
    tentative_lead  전개형 — 임계통과 − 첫 TENTATIVE 시점
    false_alarm     전체 — 정온(quiet) 구간의 CONFIRMED_* 발생 수 (0이 목표)
    tentative_rate  전체 — 정온 구간의 TENTATIVE headline 비율 (화면 소음)
    unknown_rate    전체 — UNKNOWN 판정 비율

정온(quiet) 구간 = 실제 전이가 없어 경보가 떠선 안 되는 구간:
    전개형/step  : [0, onset)       — 전이 시작 전 평탄 baseline
    spike        : [0, onset) ∪ [복귀+settle, 끝]
    normal       : 전체 (전이 없음)

사용:
    python scripts/calibrate_prediction.py --mode full --output reports
    python scripts/calibrate_prediction.py --mode baseline   # 중심점만
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from devkit.core.data_types import DataPoint
from devkit.core.enums import CPPurpose, ForecastConfidence
from devkit.core.modules import SlidingWindow, ChangePointDetector
from devkit.core.integration import ForecastPolicy
from gas.modules import GasARIMAPredictor
from devkit.generator.transition import build_catalog_scenario, generate_transition, TRANSITION_CATALOG

warnings.filterwarnings("ignore")  # statsmodels 수렴 경고 억제
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("calibrate")


# ============================================================================
# 보정 대상 파라미터 — provisional 중심점 + 좌표 sweep 격자
# ============================================================================

PROVISIONAL: dict = {
    "margin_ratio": 0.125,  # 출력정책 — 모델형태 보정 마진 비율 (m=ratio×임계)
    "drift_tau": 2.0,       # 출력정책 — drift 유의성 임계 τ
    "k": 18,                # 출력정책 — K-연속 확인
    "horizon": 60,          # ARIMA — 예측 수평 H
    "min_segment": 45,      # ARIMA — 재적합 최소 구간
    "max_segment": 120,     # ARIMA — 재적합 최대 구간
    "magnitude_gate": 30.0,  # CP — 변화점 점프 크기 게이트
}

# 축별 sweep 후보 (중심점 포함). 좌표 sweep — 한 축만 바꾸고 나머지는 중심점.
SWEEP_GRID: dict = {
    "margin_ratio": [0.05, 0.125, 0.2, 0.3],
    "drift_tau": [1.0, 1.5, 2.0, 3.0],
    "k": [6, 12, 18, 30],
    "horizon": [30, 60, 90, 120],
    "min_segment": [30, 45, 60],
    "max_segment": [90, 120, 160],
    "magnitude_gate": [15.0, 30.0, 50.0],
}

# 운영점 권고 — 좌표 sweep 정정 해석 기반 (확인 재구동 대상).
# 정정 목적함수: CONFIRMED는 구조적 사후확정 → 실질 사전경고는 TENTATIVE.
# tentative_lead·unknown_rate·정온소음 기준으로 선정.
RECOMMENDED: dict = {
    "margin_ratio": 0.2,    # 0.125→0.2 — TENTATIVE 보강 (catalog 임계 200 기준 40)
    "drift_tau": 2.0,       # 유지 — CONFIRMED 보조, C2 step-오탐 가드
    "k": 18,                # 유지 — CONFIRMED 보조, 전이 필터
    "horizon": 60,          # 유지 — ↑시 UNKNOWN 악화 (Step 5 후 재검토)
    "min_segment": 45,      # 유지 — 본 시나리오 집합에서 무영향
    "max_segment": 90,      # 120→90 — 정온소음 ↓
    "magnitude_gate": 50.0,  # 30→50 — UNKNOWN 대폭 ↓ (단일 최대 개선)
}

# 채널 기준 — 카탈로그 baseline 50 / threshold 200 은 voc 채널과 일치
_CAUTION: float = 200.0
_DANGER: float = 500.0
_DEVICE: str = "cal"
_SENSOR: str = "voc"
_CP_WINDOW: int = 60
_SPIKE_SETTLE: int = 30   # spike 복귀 후 정온 재개까지 여유

_CONF_RANK = {
    ForecastConfidence.NORMAL: 0,
    ForecastConfidence.UNKNOWN: 0,
    ForecastConfidence.TENTATIVE: 1,
    ForecastConfidence.CONFIRMED_WARNING: 2,
    ForecastConfidence.CONFIRMED_STRONG: 3,
}


# ============================================================================
# 시나리오 정의 — 카탈로그 11종 + 정상 baseline
# ============================================================================

@dataclass
class Scenario:
    """보정 시나리오 1건."""

    name: str
    kind: str   # 'ramp' / 'abrupt' / 'normal'
    series: np.ndarray
    onset: int
    quiet_end: Optional[int]   # spike 복귀 후 정온 재개 인덱스 (그 외 None)


def build_scenarios(seed: int = 42) -> list:
    """카탈로그 11종 + 정상 baseline 시나리오를 생성."""
    scs: list = []
    for name, cfg in TRANSITION_CATALOG.items():
        series = build_catalog_scenario(name, seed=seed)
        onset = int(cfg["onset_step"])
        if name in ("step", "spike"):
            kind = "abrupt"
        else:
            kind = "ramp"
        quiet_end = None
        if name == "spike":
            # spike_duration 기본 8 (catalog 미지정) — 복귀 후 settle 여유
            quiet_end = onset + 8 + _SPIKE_SETTLE
        scs.append(Scenario(name, kind, series, onset, quiet_end))

    # 정상 baseline — 전이 없는 평탄 시계열 (기울기 ≈ 0)
    normal = generate_transition(
        "linear", steps_to_threshold=10_000_000, baseline=50.0, threshold=200.0,
        n_steps=520, onset_step=120, noise_std=12.0, noise_phi=0.95, seed=seed,
    )
    scs.append(Scenario("normal", "normal", normal, onset=0, quiet_end=None))
    return scs


# ============================================================================
# 파이프라인 — CP → ARIMA → 출력 정책 (PredictionSubsystem 미러, 전 파라미터 노출)
# ============================================================================

class _Pipeline:
    """보정용 예측 파이프라인.

    PredictionSubsystem 과 동일한 3단 배선이나, CP magnitude_gate 등
    7개 파라미터 전부를 생성자에서 받아 sweep을 가능케 한다.
    """

    def __init__(self, params: dict):
        history_size = max(150, int(params["max_segment"]) + 40)
        self._cpw = SlidingWindow(_CP_WINDOW)
        self._hist = SlidingWindow(history_size)
        self._cp = ChangePointDetector(
            self._cpw, purpose=CPPurpose.PREDICT_VALIDATION,
            magnitude_gate=float(params["magnitude_gate"]),
        )
        self._arima = GasARIMAPredictor(
            forecast_steps=int(params["horizon"]),
            min_segment=int(params["min_segment"]),
            max_segment=int(params["max_segment"]),
        )
        self._policy = ForecastPolicy(
            margin_ratio=float(params["margin_ratio"]),
            drift_tau=float(params["drift_tau"]),
            k_confirm=int(params["k"]),
        )

    def step(self, point: DataPoint):
        """1시점 투입 → ForecastPolicyResult."""
        self._cpw.push(point)
        self._hist.push(point)
        anchor = self._cp.anchor_status(point.device_id, point.sensor_type)
        history = self._hist.get_values(point.device_id, point.sensor_type)
        arima_result = self._arima.predict(history, anchor)
        return self._policy.grade(
            arima_result, caution=_CAUTION, danger=_DANGER, direction="high",
        )


# ============================================================================
# 시나리오 평가 — 5지표 산출
# ============================================================================

@dataclass
class ScenarioMetrics:
    """단일 시나리오 × 단일 구성의 5지표."""

    name: str
    kind: str
    lead_time: Optional[int]        # ramp 전용 (MISS=None)
    tentative_lead: Optional[int]   # ramp 전용 (MISS=None)
    false_alarm: int
    tentative_rate: float
    unknown_rate: float
    max_conf: str                   # 도달 최고 headline 확신도


def evaluate(scenario: Scenario, params: dict) -> ScenarioMetrics:
    """시나리오를 파이프라인에 시점별 스트리밍 → 5지표."""
    pipe = _Pipeline(params)
    series = scenario.series
    n = len(series)
    ts0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    ranks: list = []
    headlines: list = []
    for i, v in enumerate(series):
        point = DataPoint(
            timestamp=ts0 + timedelta(seconds=3 * i),
            device_id=_DEVICE, sensor_type=_SENSOR, value=float(v),
        )
        res = pipe.step(point)
        headlines.append(res.headline_confidence)
        ranks.append(_CONF_RANK[res.headline_confidence])

    # 정온(quiet) 마스크
    quiet = np.zeros(n, dtype=bool)
    if scenario.kind == "normal":
        quiet[:] = True
    else:
        quiet[: scenario.onset] = True
        if scenario.quiet_end is not None and scenario.quiet_end < n:
            quiet[scenario.quiet_end:] = True

    # false_alarm — 정온 구간의 CONFIRMED_* (rank ≥ 2)
    false_alarm = int(sum(1 for i in range(n) if quiet[i] and ranks[i] >= 2))

    # tentative_rate — 정온 구간의 TENTATIVE headline 비율
    quiet_count = int(quiet.sum())
    tent_quiet = sum(
        1 for i in range(n)
        if quiet[i] and headlines[i] == ForecastConfidence.TENTATIVE
    )
    tentative_rate = (tent_quiet / quiet_count) if quiet_count else 0.0

    # unknown_rate — 전체 대비 UNKNOWN 비율
    unknown_rate = sum(
        1 for h in headlines if h == ForecastConfidence.UNKNOWN
    ) / n

    # lead — ramp 전용. 실제 임계 통과 시점 기준
    lead_time = tentative_lead = None
    if scenario.kind == "ramp":
        cross = next((i for i, v in enumerate(series) if v >= _CAUTION), None)
        if cross is not None:
            fc = next((i for i in range(n) if ranks[i] >= 2), None)
            ft = next((i for i in range(n) if ranks[i] >= 1), None)
            if fc is not None and fc < cross:
                lead_time = cross - fc
            if ft is not None and ft < cross:
                tentative_lead = cross - ft

    max_rank = max(ranks) if ranks else 0
    max_conf = next(
        (c.value for c, r in _CONF_RANK.items() if r == max_rank
         and c != ForecastConfidence.UNKNOWN),
        ForecastConfidence.NORMAL.value,
    )

    return ScenarioMetrics(
        name=scenario.name, kind=scenario.kind,
        lead_time=lead_time, tentative_lead=tentative_lead,
        false_alarm=false_alarm, tentative_rate=tentative_rate,
        unknown_rate=unknown_rate, max_conf=max_conf,
    )


# ============================================================================
# 구성 단위 집계
# ============================================================================

@dataclass
class ConfigSummary:
    """단일 파라미터 구성의 전 시나리오 집계."""

    label: str
    metrics: list           # list[ScenarioMetrics]
    fa_total: int
    fa_scenarios: int
    warn_miss: int          # CONFIRMED 사전경고 누락 ramp 수 (총 9)
    mean_warn_lead: Optional[float]
    tent_miss: int          # TENTATIVE 사전경고 누락 ramp 수
    mean_tent_lead: Optional[float]
    noise_rate: float       # normal/step/spike 평균 tentative_rate
    unknown_mean: float


def run_config(label: str, params: dict, scenarios: list) -> ConfigSummary:
    """한 파라미터 구성으로 전 시나리오 평가 → 집계."""
    metrics = [evaluate(sc, params) for sc in scenarios]
    ramps = [m for m in metrics if m.kind == "ramp"]
    quiet_kinds = [m for m in metrics if m.kind in ("normal", "abrupt")]

    warn_leads = [m.lead_time for m in ramps if m.lead_time is not None]
    tent_leads = [m.tentative_lead for m in ramps if m.tentative_lead is not None]

    return ConfigSummary(
        label=label, metrics=metrics,
        fa_total=sum(m.false_alarm for m in metrics),
        fa_scenarios=sum(1 for m in metrics if m.false_alarm > 0),
        warn_miss=sum(1 for m in ramps if m.lead_time is None),
        mean_warn_lead=(float(np.mean(warn_leads)) if warn_leads else None),
        tent_miss=sum(1 for m in ramps if m.tentative_lead is None),
        mean_tent_lead=(float(np.mean(tent_leads)) if tent_leads else None),
        noise_rate=(float(np.mean([m.tentative_rate for m in quiet_kinds]))
                    if quiet_kinds else 0.0),
        unknown_mean=float(np.mean([m.unknown_rate for m in metrics])),
    )


def coordinate_sweep(scenarios: list) -> dict:
    """좌표 sweep — 축별로 한 파라미터만 변화. {axis: [ConfigSummary, ...]}."""
    out: dict = {}
    for axis, values in SWEEP_GRID.items():
        rows: list = []
        for val in values:
            params = dict(PROVISIONAL)
            params[axis] = val
            label = f"{axis}={val}"
            logger.info("  sweep %s ...", label)
            rows.append(run_config(label, params, scenarios))
        out[axis] = rows
    return out


# ============================================================================
# 리포트 렌더링
# ============================================================================

def _fmt_lead(m: ScenarioMetrics, attr: str) -> str:
    """lead 지표 표시 — ramp는 값/MISS, 그 외 N/A."""
    if m.kind != "ramp":
        return "—"
    v = getattr(m, attr)
    return "MISS" if v is None else str(v)


def _fmt_opt(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.0f}"


def render_report(baseline: ConfigSummary, sweep: Optional[dict],
                  generated_at: str) -> str:
    """보정 결과를 markdown 문자열로 변환."""
    L: list = []
    L.append("# 미래 위험 예측 서브시스템 — B2·C3 운영점 보정 리포트")
    L.append("")
    L.append(f"- 생성: {generated_at}")
    L.append("- 대상: 예측 서브시스템 (CP → ARIMA → 출력 정책)")
    L.append("- 시나리오: 전이 카탈로그 11종 + 정상 baseline 1종")
    L.append("- sweep: 좌표(축별) — provisional 중심점에서 한 축씩 변화")
    L.append("")

    # 1. 보정 대상 파라미터
    L.append("## 1. 보정 대상 파라미터 (provisional 중심점)")
    L.append("")
    L.append("| 파라미터 | 컴포넌트 | 중심값 | sweep 후보 |")
    L.append("|---|---|---|---|")
    _comp = {
        "margin_ratio": "출력정책", "drift_tau": "출력정책", "k": "출력정책",
        "horizon": "ARIMA", "min_segment": "ARIMA", "max_segment": "ARIMA",
        "magnitude_gate": "CP",
    }
    for p, v in PROVISIONAL.items():
        cand = ", ".join(str(x) for x in SWEEP_GRID[p])
        L.append(f"| {p} | {_comp[p]} | {v} | {cand} |")
    L.append("")

    # 2. 중심점 시나리오별 5지표
    L.append("## 2. provisional 중심점 — 시나리오별 5지표")
    L.append("")
    L.append("lead = 임계통과 − 첫 경보 시점 (클수록 조기, MISS=사전경보 없음).")
    L.append("")
    L.append("| 시나리오 | 종류 | lead_time | tentative_lead | "
             "false_alarm | tentative_rate | unknown_rate | 최고등급 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for m in baseline.metrics:
        L.append(
            f"| {m.name} | {m.kind} | {_fmt_lead(m, 'lead_time')} | "
            f"{_fmt_lead(m, 'tentative_lead')} | {m.false_alarm} | "
            f"{m.tentative_rate:.1%} | {m.unknown_rate:.1%} | {m.max_conf} |"
        )
    L.append("")
    L.append(f"- false_alarm 합계: **{baseline.fa_total}** "
             f"({baseline.fa_scenarios}개 시나리오)")
    L.append(f"- CONFIRMED 사전경고 누락: **{baseline.warn_miss}/9** ramp "
             f"(평균 lead {_fmt_opt(baseline.mean_warn_lead)} 스텝)")
    L.append(f"- TENTATIVE 사전경고 누락: **{baseline.tent_miss}/9** ramp "
             f"(평균 lead {_fmt_opt(baseline.mean_tent_lead)} 스텝)")
    L.append(f"- 정온구간 소음(tentative_rate, normal/step/spike 평균): "
             f"**{baseline.noise_rate:.1%}**")
    L.append(f"- 평균 unknown_rate: **{baseline.unknown_mean:.1%}**")
    L.append("")

    if sweep is None:
        L.append("> baseline 모드 — 좌표 sweep 생략.")
        L.append("")
        return "\n".join(L)

    # 3. 좌표 sweep — 축별 트레이드오프
    L.append("## 3. 좌표 sweep — 축별 트레이드오프")
    L.append("")
    L.append("각 축은 나머지 6개를 중심점에 고정하고 한 값만 변화시킨 결과.")
    L.append("")
    for axis, rows in sweep.items():
        L.append(f"### {axis}")
        L.append("")
        L.append("| 값 | false_alarm 합 | FA 시나리오 | warn 누락 | "
                 "평균 warn_lead | tent 누락 | 평균 tent_lead | "
                 "정온소음 | unknown |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            val = r.label.split("=", 1)[1]
            mark = " ←중심" if str(PROVISIONAL[axis]) == val else ""
            L.append(
                f"| {val}{mark} | {r.fa_total} | {r.fa_scenarios} | "
                f"{r.warn_miss}/9 | {_fmt_opt(r.mean_warn_lead)} | "
                f"{r.tent_miss}/9 | {_fmt_opt(r.mean_tent_lead)} | "
                f"{r.noise_rate:.1%} | {r.unknown_mean:.1%} |"
            )
        L.append("")

    # 4. 운영점 권고
    L.append("## 4. 운영점 권고 (좌표 sweep 기반 — 적용 전 확인 재구동 필요)")
    L.append("")
    L.append("선정 규칙: false_alarm 합 = 0 을 hard 제약으로, 그 안에서 "
             "warn 누락 최소 → 평균 warn_lead 최대 순.")
    L.append("")
    L.append("| 파라미터 | 중심값 | 권고값 | 근거 |")
    L.append("|---|---|---|---|")
    recommended: dict = {}
    for axis, rows in sweep.items():
        best = _pick_best(rows)
        rec_val = best.label.split("=", 1)[1]
        recommended[axis] = rec_val
        same = "(중심 유지)" if str(PROVISIONAL[axis]) == rec_val else ""
        L.append(
            f"| {axis} | {PROVISIONAL[axis]} | **{rec_val}** {same} | "
            f"FA {best.fa_total} · warn누락 {best.warn_miss}/9 · "
            f"lead {_fmt_opt(best.mean_warn_lead)} |"
        )
    L.append("")
    L.append("> ⚠ 좌표 sweep은 축간 상호작용을 포착하지 못한다. 위 권고 "
             "조합을 단일 구성으로 확인 재구동한 뒤 운영점으로 확정할 것 "
             "(forecast_policy.py / arima.py / change_point.py 기본값 적용은 "
             "별도 승인 대상).")
    L.append("")
    return "\n".join(L)


def _pick_best(rows: list) -> ConfigSummary:
    """축 sweep 행에서 운영점 후보 선정.

    false_alarm 합 최소 → warn 누락 최소 → 평균 warn_lead 최대.
    """
    def key(r: ConfigSummary):
        lead = r.mean_warn_lead if r.mean_warn_lead is not None else -1.0
        return (r.fa_total, r.warn_miss, -lead)

    return min(rows, key=key)


def render_confirm_report(prov: ConfigSummary, rec: ConfigSummary,
                          generated_at: str) -> str:
    """운영점 확인 재구동 — provisional vs recommended 비교 markdown."""
    L: list = []
    L.append("# 미래 위험 예측 서브시스템 — 운영점 확인 재구동 리포트")
    L.append("")
    L.append(f"- 생성: {generated_at}")
    L.append("- 목적: 좌표 sweep 권고 조합을 단일 구성으로 확인 (축간 상호작용 검증)")
    L.append("")

    # 1. 운영점 비교
    L.append("## 1. 운영점 비교")
    L.append("")
    L.append("| 파라미터 | provisional | recommended | 변경 |")
    L.append("|---|---|---|---|")
    for p in PROVISIONAL:
        a, b = PROVISIONAL[p], RECOMMENDED[p]
        mark = "" if a == b else "**변경**"
        L.append(f"| {p} | {a} | {b} | {mark} |")
    L.append("")

    # 2. 시나리오별 비교
    L.append("## 2. 시나리오별 비교 (provisional → recommended)")
    L.append("")
    L.append("| 시나리오 | 종류 | tentative_lead | false_alarm | "
             "tentative_rate | unknown_rate | 최고등급 |")
    L.append("|---|---|---|---|---|---|---|")
    for mp, mr in zip(prov.metrics, rec.metrics):
        L.append(
            f"| {mp.name} | {mp.kind} | "
            f"{_fmt_lead(mp, 'tentative_lead')} → {_fmt_lead(mr, 'tentative_lead')} | "
            f"{mp.false_alarm} → {mr.false_alarm} | "
            f"{mp.tentative_rate:.1%} → {mr.tentative_rate:.1%} | "
            f"{mp.unknown_rate:.1%} → {mr.unknown_rate:.1%} | "
            f"{mp.max_conf} → {mr.max_conf} |"
        )
    L.append("")

    # 3. 집계 비교
    L.append("## 3. 집계 비교")
    L.append("")
    L.append("| 지표 | provisional | recommended |")
    L.append("|---|---|---|")
    L.append(f"| false_alarm 합 | {prov.fa_total} | {rec.fa_total} |")
    L.append(f"| TENTATIVE 누락 | {prov.tent_miss}/9 | {rec.tent_miss}/9 |")
    L.append(f"| 평균 tentative_lead | {_fmt_opt(prov.mean_tent_lead)} | "
             f"{_fmt_opt(rec.mean_tent_lead)} |")
    L.append(f"| CONFIRMED 누락 | {prov.warn_miss}/9 | {rec.warn_miss}/9 |")
    L.append(f"| 평균 warn_lead | {_fmt_opt(prov.mean_warn_lead)} | "
             f"{_fmt_opt(rec.mean_warn_lead)} |")
    L.append(f"| 정온소음 (normal/step/spike) | {prov.noise_rate:.1%} | "
             f"{rec.noise_rate:.1%} |")
    L.append(f"| 평균 unknown_rate | {prov.unknown_mean:.1%} | "
             f"{rec.unknown_mean:.1%} |")
    L.append("")

    # 4. 판정
    L.append("## 4. 판정")
    L.append("")
    safe = rec.fa_total == 0
    L.append(f"- false_alarm 0 유지: {'✅' if safe else '❌ ' + str(rec.fa_total)}")
    L.append(f"- TENTATIVE 누락: {prov.tent_miss} → {rec.tent_miss} "
             f"({'개선' if rec.tent_miss < prov.tent_miss else '유지' if rec.tent_miss == prov.tent_miss else '악화'})")
    L.append(f"- 평균 unknown_rate: {prov.unknown_mean:.1%} → {rec.unknown_mean:.1%} "
             f"({'개선' if rec.unknown_mean < prov.unknown_mean else '유지/악화'})")
    L.append(f"- 정온소음: {prov.noise_rate:.1%} → {rec.noise_rate:.1%} "
             f"({'개선' if rec.noise_rate < prov.noise_rate else '유지/악화'})")
    L.append("")
    return "\n".join(L)


# ============================================================================
# 진입점
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="미래 위험 예측 서브시스템 B2·C3 운영점 보정"
    )
    parser.add_argument(
        "--mode", choices=("baseline", "full", "confirm"), default="full",
        help="baseline=중심점만, full=좌표 sweep, confirm=운영점 확인 재구동",
    )
    parser.add_argument("--output", type=Path, default=Path("reports"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logger.info("시나리오 생성 ...")
    scenarios = build_scenarios(seed=args.seed)
    logger.info("  %d종 (ramp %d / abrupt %d / normal %d)",
                len(scenarios),
                sum(1 for s in scenarios if s.kind == "ramp"),
                sum(1 for s in scenarios if s.kind == "abrupt"),
                sum(1 for s in scenarios if s.kind == "normal"))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")

    if args.mode == "confirm":
        logger.info("provisional 평가 ...")
        prov = run_config("provisional", PROVISIONAL, scenarios)
        logger.info("recommended 평가 ...")
        rec = run_config("recommended", RECOMMENDED, scenarios)
        report = render_confirm_report(prov, rec, generated_at)
        out_name = "calibration_confirm.md"
    else:
        logger.info("provisional 중심점 평가 ...")
        baseline = run_config("provisional", PROVISIONAL, scenarios)
        sweep = None
        if args.mode == "full":
            logger.info("좌표 sweep ...")
            sweep = coordinate_sweep(scenarios)
        report = render_report(baseline, sweep, generated_at)
        out_name = "calibration_report.md"

    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / out_name
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("리포트 저장: %s", report_path)


if __name__ == "__main__":
    main()
