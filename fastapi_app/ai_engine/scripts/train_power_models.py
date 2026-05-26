#!/usr/bin/env python
"""
[Phase D 결정 (2026-05-23): IF 학습 (--with-if-train) 비활성 — 보존 (옵션 a)]
─────────────────────────────────────────────────────────────────────────────
본 스크립트의 IF 학습 부분 (RATED_GROUPS_LOW/HIGH, MODEL_SELECT_THRESHOLD,
--with-if-train flag, 'Phase C-1 — IF 2 모델 학습' 블록)은 Phase C-1에서
작성됐으나 STEP F 비활성으로 현재 미사용.

*보존* 부분 (현재도 활용):
    - 학습 풀 생성 (RATED_GROUPS 11개 그룹 + 통계 보고)
        → validate_power_pool.py V1/V2/V4 검증에 학습 풀 필요
        → working_means/working_stds 분포 검증 산출물

╔════════════════════════════════════════════════════════════════════════╗
║ 삭제 검증 방법 — IF 학습 부분만 안전 삭제 가능 확인                    ║
╠════════════════════════════════════════════════════════════════════════╣
║ 1. iforest_g0050.joblib + iforest_high.joblib 로드 0건 확인:           ║
║    $ grep -rn "iforest_g0050\\|iforest_high" --include="*.py"          ║
║      --exclude-dir=__pycache__ --exclude-dir=.venv                     ║
║                                                                         ║
║ 2. monitoring/ai/power_if.py 삭제됨 (선결 조건 — 거기 docstring 참조) ║
║                                                                         ║
║ 3. 위 통과 시 본 스크립트에서 다음 안전 삭제:                          ║
║    - RATED_GROUPS_LOW / RATED_GROUPS_HIGH / MODEL_SELECT_THRESHOLD     ║
║    - --with-if-train CLI flag                                          ║
║    - main() 의 'Phase C-1 — IF 2 모델 학습' 블록 (low/high fit/save)  ║
║    - 'from power.modules import PowerIsolationForestDetector' import   ║
║                                                                         ║
║   *학습 풀 생성 부분은 그대로 유지* (V1/V2/V4 산출물 가치).           ║
╚════════════════════════════════════════════════════════════════════════╝

─────────────────────────────────────────────────────────────────────────────
scripts/train_power_models.py — 전력 IsolationForest 그룹별 학습 풀 생성 + IF 학습.

Phase B-2-4·5 — 정격 그룹별 학습 풀 생성 + (옵션) IF 모델 학습.
    - 학습 풀: RATED_GROUPS의 11개 그룹별로 generate_power_normal_pool 호출.
    - HIGH_VARIANCE_RATEDS: stop_rejection_ratio 완화 대상 그룹. 빈 set으로
      시작 (B-2-3 회귀 결과 모든 그룹 0.02%로 충분 안전).
    - IF 학습은 --with-if-train 플래그 명시 시에만 실행. B-2-5에선 학습 풀
      생성·통계만 검증, IF 11개 학습은 Phase C 진입 시점에 활성화.

사용:
    # B-2-5: 학습 풀 11개 생성 + 통계 (기본)
    python scripts/train_power_models.py --n-samples 5000

    # Phase C: 학습 풀 + IF 11개 모델 학습
    python scripts/train_power_models.py --n-samples 5000 --with-if-train
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from common.utils.logger import setup_logger
from power.modules import PowerIsolationForestDetector
from generator.power_generator import generate_power_normal_pool


# Phase B-2-4 — 정격 그룹 정의 + HIGH_VARIANCE 분기
RATED_GROUPS: list = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
"""학습 풀 생성 대상 정격 그룹 (단위: W).

B-2-1 _GROUP_MEANS_WORKING과 일치. 새 그룹 추가 시 _GROUP_MEANS_WORKING도
동반 갱신 필요 — 자동 일치 검증 없음 (별도 단위 테스트 권장)."""

HIGH_VARIANCE_RATEDS: set = set()
"""stop_rejection_ratio를 0.10으로 완화할 그룹.

빈 set으로 시작 (B-2-3 회귀 결과 모든 그룹 분포 거부 0.02%로 충분 안전).
향후 분포 거부율이 stop 임계 근접하는 그룹 발견 시 추가."""

# Phase C-1 — IF 2 모델 구조 (B-4 V3 결정 (a))
RATED_GROUPS_LOW: list = [50]
"""저전력 IF 모델 학습 대상 — g0050 단독.

V3 매트릭스: g0050이 모든 다른 그룹과 ≥4σ로 분리. 통합 모델과 별도 학습 필요."""

RATED_GROUPS_HIGH: list = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
"""고전력 통합 IF 모델 학습 대상.

V3 매트릭스: 인접 그룹 모두 < 3σ. 단일 통합 모델로 학습."""

MODEL_SELECT_THRESHOLD: int = 75
"""어댑터(monitoring/ai/power_if.py)에서 모델 선택 임계 (W).

rated_w ≤ MODEL_SELECT_THRESHOLD → iforest_g0050.joblib (low)
rated_w >  MODEL_SELECT_THRESHOLD → iforest_high.joblib (high)

75 = g0050(20W±5) ↔ g0100(40W±10) 사이 자연 mid-point."""


def parse_args():
    parser = argparse.ArgumentParser(
        description="전력 IsolationForest 그룹별 학습 풀 생성 (+ 옵션 IF 학습)"
    )
    parser.add_argument("--n-samples", type=int, default=5000,
                        help="그룹당 학습 풀 샘플 수")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("models/power"),
                        help="IF 모델 저장 디렉토리 (--with-if-train 시)")
    parser.add_argument("--with-if-train", action="store_true",
                        help="IF 모델 11개 학습 활성화 (Phase C). 미지정 시 학습 풀만.")
    return parser.parse_args()


def main():
    args = parse_args()
    logger = setup_logger("train_power")

    logger.info("=" * 70)
    logger.info("전력 IsolationForest 그룹별 학습 풀 생성")
    logger.info(f"  그룹: {RATED_GROUPS}")
    logger.info(f"  HIGH_VARIANCE: {sorted(HIGH_VARIANCE_RATEDS) or '(빈 set)'}")
    logger.info(f"  샘플 수/그룹: {args.n_samples}")
    logger.info(f"  IF 학습: {'예 (Phase C)' if args.with_if_train else '아니오 (학습 풀만)'}")
    logger.info("=" * 70)

    if args.with_if_train:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    metrics_table: list = []
    all_pools: dict = {}   # Phase C-1 — 2 모델 통합 학습 시 그룹별 bundles 보관

    # ── 1단계: 11개 그룹 학습 풀 생성 + 통계 ──
    for rated_w in RATED_GROUPS:
        stop_ratio = 0.10 if rated_w in HIGH_VARIANCE_RATEDS else 0.05

        logger.info("")
        logger.info(f"[rated_w={rated_w}W] 학습 풀 생성 (stop={stop_ratio:.0%})")
        t0 = time.time()
        bundles = generate_power_normal_pool(
            rated_w=rated_w,
            n_samples=args.n_samples,
            seed=args.seed,
            stop_rejection_ratio=stop_ratio,
        )
        pool_time = time.time() - t0
        all_pools[rated_w] = bundles   # C-1 — 2 모델 학습 시 통합 위해 보관

        # 통계 — 결측 제외한 유효 샘플 기준
        arr = np.array([
            [b.values["voltage"] or 0, b.values["current"] or 0, b.values["power"] or 0]
            for b in bundles if all(b.is_valid_flags.values())
        ])
        n_valid = len(arr)
        v_mean = float(arr[:, 0].mean())
        i_mean = float(arr[:, 1].mean())
        p_mean = float(arr[:, 2].mean())
        v_std = float(arr[:, 0].std())
        i_std = float(arr[:, 1].std())
        p_std = float(arr[:, 2].std())
        # 옴의 법칙 검증은 B-4 validate_power_pool.py V2에서 apply_quantization=False로
        # 별도 측정 (B-2-7 결정 (iii)). 양자화 후 측정은 분해능 노이즈가 임계를
        # 압도해 신호 가치 없음 (저전력 그룹 80%+ — Finding-3 Evidence-3).

        metrics_table.append({
            "rated_w": rated_w,
            "n_total": len(bundles),
            "n_valid": n_valid,
            "p_mean": p_mean,
            "p_std": p_std,
            "v_mean": v_mean,
            "i_mean": i_mean,
            "stop_ratio": stop_ratio,
            "pool_time_s": pool_time,
        })

        logger.info(
            f"  → 총 {len(bundles)}, 유효 {n_valid} "
            f"(V={v_mean:.1f}±{v_std:.2f}, A={i_mean:.3f}±{i_std:.3f}, "
            f"W={p_mean:.1f}±{p_std:.2f}), 소요 {pool_time:.2f}s"
        )

    # ── 2단계: IF 2 모델 학습 (Phase C-1 옵션) ──
    # (a) low 모델: g0050 단독 (5000 샘플)
    # (b) high 모델: g0100~g1000 통합 (10그룹 × 5000 = 50000 샘플)
    if args.with_if_train:
        logger.info("")
        logger.info("=" * 70)
        logger.info("Phase C-1 — IF 2 모델 학습 (low / high)")
        logger.info("=" * 70)

        # (a) low 모델
        low_bundles: list = []
        for rated_w in RATED_GROUPS_LOW:
            low_bundles.extend(all_pools[rated_w])
        logger.info(
            f"[LOW: g{RATED_GROUPS_LOW[0]:04d}] 단독 학습 — 총 {len(low_bundles)} bundles"
        )
        t1 = time.time()
        if_low = PowerIsolationForestDetector()
        fit_low = if_low.fit(low_bundles)
        low_path = args.output_dir / "iforest_g0050.joblib"
        if_low.save(low_path)
        size_low = low_path.stat().st_size / (1024 * 1024)
        logger.info(
            f"  저장: {low_path.name} ({size_low:.2f} MB), "
            f"입력 {fit_low['n_samples_input']} / 학습 {fit_low['n_samples_trained']}, "
            f"평균 마할라노비스 {fit_low['mahalanobis_mean']:.3f}, 소요 {time.time() - t1:.2f}s"
        )

        # (b) high 모델 (통합) — 결정 1 (가): 각 그룹 5000 × 10 = 50000 통합
        high_bundles: list = []
        for rated_w in RATED_GROUPS_HIGH:
            high_bundles.extend(all_pools[rated_w])
        logger.info("")
        logger.info(
            f"[HIGH: g{RATED_GROUPS_HIGH[0]:04d}~g{RATED_GROUPS_HIGH[-1]:04d}] "
            f"통합 학습 — 총 {len(high_bundles)} bundles"
        )
        t2 = time.time()
        if_high = PowerIsolationForestDetector()
        fit_high = if_high.fit(high_bundles)
        high_path = args.output_dir / "iforest_high.joblib"
        if_high.save(high_path)
        size_high = high_path.stat().st_size / (1024 * 1024)
        logger.info(
            f"  저장: {high_path.name} ({size_high:.2f} MB), "
            f"입력 {fit_high['n_samples_input']} / 학습 {fit_high['n_samples_trained']}, "
            f"평균 마할라노비스 {fit_high['mahalanobis_mean']:.3f}, 소요 {time.time() - t2:.2f}s"
        )

        logger.info("")
        logger.info(
            f"어댑터 모델 선택 임계: rated_w ≤ {MODEL_SELECT_THRESHOLD} → low, "
            f"> {MODEL_SELECT_THRESHOLD} → high"
        )

    # ── 메트릭 요약표 ──
    logger.info("")
    logger.info("=" * 70)
    logger.info("그룹별 학습 풀 메트릭 요약")
    logger.info("=" * 70)
    logger.info(
        f"{'rated_w':>8} | {'유효':>5} | {'V평균':>6} | {'A평균':>6} | "
        f"{'P평균':>7} | {'P_std':>6} | {'stop':>5}"
    )
    logger.info("-" * 70)
    for m in metrics_table:
        logger.info(
            f"{m['rated_w']:>8} | {m['n_valid']:>5} | "
            f"{m['v_mean']:>6.1f} | {m['i_mean']:>6.3f} | "
            f"{m['p_mean']:>7.1f} | {m['p_std']:>6.2f} | {m['stop_ratio']:>4.0%}"
        )

    logger.info("")
    logger.info("=" * 70)
    logger.info("전력 학습 풀 생성 완료")
    logger.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
