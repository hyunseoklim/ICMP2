#!/usr/bin/env python
"""scripts/run_phase4_validation.py — Phase 4 시나리오 카드 통합 검증.

학습된 모델로 모든 시나리오 카드를 판정하고 reports/에 결과 markdown 저장.

사용:
    python scripts/run_phase4_validation.py
    python scripts/run_phase4_validation.py --models-dir models --output reports

종료 코드:
    0: 모든 시나리오 통과 (예상 등급에 부합)
    1: 일부 시나리오 실패
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from common.data_types import DataPoint
from common.enums import RiskLevel
from common.modules import ThresholdClassifier
from common.utils.logger import setup_logger

from gas.thresholds import load_gas_thresholds
from gas.modules import GasIsolationForestDetector
from gas.premises import GAS_SENSOR_TYPES
from power.thresholds import load_power_thresholds
from power.modules import PowerIsolationForestDetector
from power.premises import POWER_SENSOR_TYPES

from generator.gas_generator import generate_scenario as gen_gas_scenario
from generator.power_generator import generate_scenario as gen_power_scenario

# 예측 서브시스템 (Step 2 — 미래 위험 예측 연결)
from common.enums import ForecastConfidence
from common.integration import PredictionSubsystem
from gas.modules import GasARIMAPredictor
from power.modules import PowerARIMAPredictor


# ============================================================================
# 시나리오 카탈로그
# ============================================================================

# (scenario_id, domain, description, focus_channel, expected_max_level)
SCENARIOS = [
    ("S-T1", "gas",   "CO 점진 상승 (정상→주의→위험)",  "co",       RiskLevel.DANGER),
    ("S-T2", "gas",   "O2 점진 하락 (역방향)",            "o2",       RiskLevel.DANGER),
    ("S-T3", "gas",   "H2S 급격 상승",                     "h2s",      RiskLevel.DANGER),
    ("S-C1", "gas",   "CO 흐름 변화 (Change Point)",      "co",       RiskLevel.CAUTION),
    ("S-P1", "gas",   "VOC 점진 (사전 경고)",              "voc",      RiskLevel.CAUTION),
    ("S-T-V",     "power", "전압 강하 (220→170V)",         "voltage",  RiskLevel.DANGER),
    ("S-T-I",     "power", "전류 급증 (11→35A)",           "current",  RiskLevel.DANGER),
    ("S-C-Power", "power", "WORKING→IDLE 모드 변화",        "current",  RiskLevel.CAUTION),
    ("S-P-I",     "power", "전류 점진 (사전 경고)",         "current",  RiskLevel.CAUTION),
    ("S-Ohm",     "power", "옴의 법칙 위반",                 "power",    RiskLevel.CAUTION),
]

_SEVERITY = {
    RiskLevel.NORMAL: 0,
    RiskLevel.UNKNOWN: 0,
    RiskLevel.CAUTION: 1,
    RiskLevel.DANGER: 2,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Phase 4 시나리오 통합 검증")
    parser.add_argument("--models-dir", type=Path, default=Path("models"))
    parser.add_argument("--output", type=Path, default=Path("reports"))
    parser.add_argument("--n-samples", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def run_scenario(
    scenario_id: str,
    domain: str,
    focus_channel: str,
    expected_max: RiskLevel,
    threshold_classifier: ThresholdClassifier,
    if_detector,
    n_samples: int,
    seed: int,
) -> dict:
    """단일 시나리오 실행 및 결과 dict 반환."""
    # 시나리오 데이터 생성
    if domain == "gas":
        bundles = gen_gas_scenario(scenario_id, n_samples=n_samples, seed=seed)
    else:
        bundles = gen_power_scenario(scenario_id, n_samples=n_samples, seed=seed)

    # 각 시점에서 두 모듈 판정
    threshold_levels = []
    if_levels = []

    for b in bundles:
        # Threshold (focus_channel 기준)
        v = b.values.get(focus_channel)
        if v is not None:
            p = DataPoint(
                timestamp=b.timestamp,
                device_id=b.device_id,
                sensor_type=focus_channel,
                value=v,
            )
            tr = threshold_classifier.classify(p)
            threshold_levels.append(tr.level)

        # IF
        if if_detector.is_fitted():
            ir = if_detector.predict(b)
            if_levels.append(ir.level)

    # 시나리오의 *최대 위험 등급* (Threshold + IF 둘 중 더 높은 것)
    th_max = max(threshold_levels, key=lambda lv: _SEVERITY[lv]) if threshold_levels else RiskLevel.NORMAL
    if_max = max(if_levels, key=lambda lv: _SEVERITY[lv]) if if_levels else RiskLevel.NORMAL
    overall_max = max([th_max, if_max], key=lambda lv: _SEVERITY[lv])

    # 등급별 빈도
    th_counter = Counter(lv.value for lv in threshold_levels)
    if_counter = Counter(lv.value for lv in if_levels)

    # 통과 여부 — 실제 최대 등급이 기대 등급에 *부합* (도달함)
    passed = _SEVERITY[overall_max] >= _SEVERITY[expected_max]

    return {
        "scenario_id": scenario_id,
        "domain": domain,
        "focus_channel": focus_channel,
        "expected_max": expected_max,
        "threshold_max": th_max,
        "if_max": if_max,
        "overall_max": overall_max,
        "threshold_counts": dict(th_counter),
        "if_counts": dict(if_counter),
        "n_samples": n_samples,
        "passed": passed,
    }


# ============================================================================
# 예측 서브시스템 검증 (Step 2 — 미래 위험 예측 연결)
# ============================================================================

_CONF_RANK = {
    ForecastConfidence.NORMAL: 0,
    ForecastConfidence.UNKNOWN: 0,
    ForecastConfidence.TENTATIVE: 1,
    ForecastConfidence.CONFIRMED_WARNING: 2,
    ForecastConfidence.CONFIRMED_STRONG: 3,
}


def run_prediction_subsystem(
    scenario_id: str,
    domain: str,
    focus_channel: str,
    threshold_table: dict,
    arima_factory,
    n_samples: int,
    seed: int,
) -> dict:
    """시나리오를 예측 서브시스템에 스트리밍하여 2축 등급·Lead를 요약.

    direction='high' 채널만 등급화 (low/both는 본 골격 미지원 — 후속).
    """
    info = threshold_table.get(focus_channel, {})
    direction = info.get("direction", "high")
    caution = info.get("caution")
    base = {
        "scenario_id": scenario_id,
        "focus_channel": focus_channel,
        "direction": direction,
    }

    if direction != "high":
        return {
            **base, "supported": False,
            "headline": f"미지원 (direction '{direction}')",
            "max_caution": ForecastConfidence.UNKNOWN,
            "max_danger": ForecastConfidence.UNKNOWN,
            "tentative_lead": None, "warning_lead": None,
            "actual_cross": None, "caution_dist": {},
        }

    if domain == "gas":
        bundles = gen_gas_scenario(scenario_id, n_samples=n_samples, seed=seed)
    else:
        bundles = gen_power_scenario(scenario_id, n_samples=n_samples, seed=seed)

    sub = PredictionSubsystem(threshold_table, arima=arima_factory())
    results = []
    actuals = []
    for b in bundles:
        v = b.values.get(focus_channel)
        sub.push(DataPoint(
            timestamp=b.timestamp, device_id=b.device_id,
            sensor_type=focus_channel, value=v,
        ))
        results.append(sub.predict_channel(b.device_id, focus_channel))
        actuals.append(v)

    # 실제값이 주의 임계에 도달하는 시점
    actual_cross = None
    if caution is not None:
        actual_cross = next(
            (i for i, x in enumerate(actuals) if x is not None and x >= caution),
            None,
        )

    # Lead — 실제 임계 도달 前, 첫 TENTATIVE / CONFIRMED_WARNING
    tent_lead = warn_lead = None
    if actual_cross is not None and caution is not None:
        for i in range(actual_cross):
            x = actuals[i]
            if x is None or x >= caution:
                continue
            rank = _CONF_RANK[results[i].caution_confidence]
            if tent_lead is None and rank >= 1:
                tent_lead = actual_cross - i
            if warn_lead is None and rank >= 2:
                warn_lead = actual_cross - i

    # 도달 최고 등급
    def _max_conf(getter):
        confs = [getter(r) for r in results]
        graded = [c for c in confs if c != ForecastConfidence.UNKNOWN]
        if graded:
            return max(graded, key=lambda c: _CONF_RANK[c])
        return ForecastConfidence.UNKNOWN if confs else ForecastConfidence.NORMAL

    max_caution = _max_conf(lambda r: r.caution_confidence)
    max_danger = _max_conf(lambda r: r.danger_confidence)
    caution_dist = dict(Counter(r.caution_confidence.value for r in results))

    if _CONF_RANK[max_danger] > 0:
        headline = f"위험·{max_danger.value}"
    elif _CONF_RANK[max_caution] > 0:
        headline = f"주의·{max_caution.value}"
    elif ForecastConfidence.UNKNOWN in (max_caution, max_danger):
        headline = "판정불가"
    else:
        headline = "정상"

    return {
        **base, "supported": True, "headline": headline,
        "max_caution": max_caution, "max_danger": max_danger,
        "tentative_lead": tent_lead, "warning_lead": warn_lead,
        "actual_cross": actual_cross, "caution_dist": caution_dist,
    }


def render_report(results: list, prediction_results: list, generated_at: str) -> str:
    """검증 결과를 markdown 문자열로 변환."""
    lines = []
    lines.append("# Phase 4 시나리오 검증 결과")
    lines.append("")
    lines.append(f"생성 시각: {generated_at}")
    lines.append("")

    n_pass = sum(1 for r in results if r["passed"])
    n_total = len(results)
    lines.append(f"## 요약")
    lines.append(f"- 통과: **{n_pass}/{n_total}**")
    lines.append(f"- 통과율: **{n_pass / n_total * 100:.1f}%**")
    lines.append("")

    lines.append("## 시나리오별 결과")
    lines.append("")
    lines.append("| 시나리오 | 도메인 | 채널 | 기대 | 실제 | 통과 |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        mark = "✅" if r["passed"] else "❌"
        lines.append(
            f"| `{r['scenario_id']}` | {r['domain']} | `{r['focus_channel']}` | "
            f"{r['expected_max'].value} | {r['overall_max'].value} | {mark} |"
        )
    lines.append("")

    lines.append("## 세부 (모듈별 최대 등급)")
    lines.append("")
    lines.append("| 시나리오 | Threshold 최대 | IF 최대 |")
    lines.append("|---|---|---|")
    for r in results:
        lines.append(
            f"| `{r['scenario_id']}` | "
            f"{r['threshold_max'].value} | "
            f"{r['if_max'].value} |"
        )
    lines.append("")

    lines.append("## 등급별 빈도")
    lines.append("")
    for r in results:
        lines.append(f"### {r['scenario_id']} ({r['domain']}, 채널={r['focus_channel']}, n={r['n_samples']})")
        lines.append(f"- Threshold: {r['threshold_counts']}")
        lines.append(f"- IF: {r['if_counts']}")
        lines.append("")

    # 예측 서브시스템 섹션 (Step 2)
    lines.append("## 예측 서브시스템 (미래 위험 예측)")
    lines.append("")
    lines.append("ARIMA 예측 서브시스템(CP-anchored 재적합 + 2축 등급화)을 "
                 "시나리오에 스트리밍한 결과. 운영점 미보정(B2·C3 대기)이므로 "
                 "*정보 제공용* — pass/fail 미부과.")
    lines.append("")
    lines.append("| 시나리오 | 채널 | direction | 예측 등급(최고) | 사전경고 Lead(T/W) | actual 임계도달 |")
    lines.append("|---|---|---|---|---|---|")
    for p in prediction_results:
        if not p["supported"]:
            lines.append(
                f"| `{p['scenario_id']}` | `{p['focus_channel']}` | "
                f"{p['direction']} | {p['headline']} | — | — |"
            )
            continue
        tl = f"T+{p['tentative_lead']}" if p['tentative_lead'] is not None else "—"
        wl = f"W+{p['warning_lead']}" if p['warning_lead'] is not None else "—"
        cross = p['actual_cross'] if p['actual_cross'] is not None else "—"
        lines.append(
            f"| `{p['scenario_id']}` | `{p['focus_channel']}` | "
            f"{p['direction']} | {p['headline']} | {tl} / {wl} | {cross} |"
        )
    lines.append("")
    lines.append("### 예측 등급 분포 (caution 축)")
    lines.append("")
    for p in prediction_results:
        if p["supported"]:
            lines.append(f"- `{p['scenario_id']}`: {p['caution_dist']}")
    lines.append("")

    return "\n".join(lines)


def main():
    args = parse_args()
    logger = setup_logger("phase4_validation")

    logger.info("=" * 60)
    logger.info("Phase 4 시나리오 검증 시작")
    logger.info("=" * 60)
    logger.info(f"모델 디렉토리: {args.models_dir}")
    logger.info(f"시나리오당 시점: {args.n_samples}")
    logger.info(f"시드: {args.seed}")

    # 분류기·검출기 로드
    gas_classifier = ThresholdClassifier(load_gas_thresholds())
    power_classifier = ThresholdClassifier(load_power_thresholds())

    gas_if = GasIsolationForestDetector()
    gas_if_path = args.models_dir / "gas" / "iforest.joblib"
    if gas_if_path.exists():
        gas_if.load(gas_if_path)
        logger.info(f"가스 IF 로드: {gas_if_path}")
    else:
        logger.warning(f"가스 IF 모델 없음 — IF 검증 건너뜀: {gas_if_path}")

    power_if = PowerIsolationForestDetector()
    power_if_path = args.models_dir / "power" / "iforest.joblib"
    if power_if_path.exists():
        power_if.load(power_if_path)
        logger.info(f"전력 IF 로드: {power_if_path}")
    else:
        logger.warning(f"전력 IF 모델 없음 — IF 검증 건너뜀: {power_if_path}")

    # 시나리오 실행
    logger.info("")
    logger.info("시나리오 실행 중...")
    results = []
    for scenario_id, domain, desc, focus, expected in SCENARIOS:
        classifier = gas_classifier if domain == "gas" else power_classifier
        if_detector = gas_if if domain == "gas" else power_if

        r = run_scenario(
            scenario_id=scenario_id,
            domain=domain,
            focus_channel=focus,
            expected_max=expected,
            threshold_classifier=classifier,
            if_detector=if_detector,
            n_samples=args.n_samples,
            seed=args.seed,
        )
        results.append(r)

        mark = "✅" if r["passed"] else "❌"
        logger.info(
            f"  {mark} {scenario_id:12s} ({domain:5s}) "
            f"기대={expected.value:8s} 실제={r['overall_max'].value:8s}"
        )

    # 예측 서브시스템 검증 (Step 2 — 미래 위험 예측 연결)
    logger.info("")
    logger.info("예측 서브시스템 실행 중...")
    gas_table = load_gas_thresholds()
    power_table = load_power_thresholds()
    prediction_results = []
    for scenario_id, domain, desc, focus, expected in SCENARIOS:
        if domain == "gas":
            table, arima_factory = gas_table, GasARIMAPredictor
        else:
            table, arima_factory = power_table, PowerARIMAPredictor
        pr = run_prediction_subsystem(
            scenario_id=scenario_id, domain=domain, focus_channel=focus,
            threshold_table=table, arima_factory=arima_factory,
            n_samples=args.n_samples, seed=args.seed,
        )
        prediction_results.append(pr)
        logger.info(f"  {scenario_id:12s} ({domain:5s}) 예측등급={pr['headline']}")

    # 리포트 저장
    generated_at = datetime.now().isoformat(timespec="seconds")
    report_md = render_report(results, prediction_results, generated_at)

    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "phase4_validation_results.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    logger.info("")
    logger.info(f"리포트 저장: {report_path}")

    # 종료 코드
    n_pass = sum(1 for r in results if r["passed"])
    n_total = len(results)
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"통과: {n_pass}/{n_total} ({n_pass / n_total * 100:.1f}%)")
    logger.info("=" * 60)

    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
