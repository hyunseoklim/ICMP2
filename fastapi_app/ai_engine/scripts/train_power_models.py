#!/usr/bin/env python
"""scripts/train_power_models.py — 전력 IsolationForest 학습.

전력 학습 풀(옴의 법칙 보장)을 생성하고 IsolationForest를 학습하여
models/power/iforest.joblib에 저장한다.

미래 위험 예측 서브시스템 재설계로 ARIMA는 frozen 구조를 폐기하고
predict 시점 재적합으로 전환됨 — 본 스크립트는 IF만 학습한다.

사용:
    python scripts/train_power_models.py
    python scripts/train_power_models.py --n-samples 5000 --seed 42
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from common.utils.logger import setup_logger
from power.modules import PowerIsolationForestDetector
from generator.power_generator import generate_power_normal_pool


def parse_args():
    parser = argparse.ArgumentParser(description="전력 IsolationForest 학습")
    parser.add_argument("--n-samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("models/power"))
    return parser.parse_args()


def main():
    args = parse_args()
    logger = setup_logger("train_power")

    logger.info("=" * 60)
    logger.info("전력 IsolationForest 학습 시작")
    logger.info("=" * 60)
    logger.info(f"학습 풀 크기: {args.n_samples}")
    logger.info(f"시드: {args.seed}")
    logger.info(f"출력 디렉토리: {args.output_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 학습 풀 생성 (옴의 법칙 보장)
    logger.info("")
    logger.info("[1/2] 학습 풀 생성 중 (옴의 법칙 P=V*I 보장)...")
    t0 = time.time()
    bundles = generate_power_normal_pool(
        n_samples=args.n_samples,
        seed=args.seed,
        enforce_ohm_law=True,
    )
    logger.info(f"      생성됨: {len(bundles)}개, 소요 {time.time() - t0:.2f}초")

    # 2. IsolationForest 학습
    logger.info("")
    logger.info("[2/2] IsolationForest 학습 중 (3차원, D-20260519-002 임계 3.76)...")
    if_detector = PowerIsolationForestDetector()
    metrics = if_detector.fit(bundles)
    logger.info(f"      입력: {metrics['n_samples_input']}, "
                f"학습됨: {metrics['n_samples_trained']}")
    logger.info(f"      차원: {metrics['n_features']}, "
                f"평균 마할라노비스: {metrics['mahalanobis_mean']:.3f}")
    logger.info(f"      소요: {metrics['training_time_seconds']:.2f}초")

    if_path = args.output_dir / "iforest.joblib"
    if_detector.save(if_path)
    size_mb = if_path.stat().st_size / (1024 * 1024)
    logger.info(f"      저장: {if_path} ({size_mb:.2f} MB)")

    logger.info("")
    logger.info("=" * 60)
    logger.info("전력 IsolationForest 학습 완료")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
