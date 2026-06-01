#!/usr/bin/env python
"""scripts/train_gas_models.py — 가스 IsolationForest 학습.

가스 학습 풀을 생성하고 IsolationForest를 학습하여
models/gas/iforest.joblib에 저장한다.

미래 위험 예측 서브시스템 재설계로 ARIMA는 frozen(1회 학습·저장) 구조를
폐기하고 predict 시점 CP-anchored 재적합으로 전환됨 — 본 스크립트는
IF만 학습한다 (ARIMA 학습 단계 없음).

사용:
    python scripts/train_gas_models.py
    python scripts/train_gas_models.py --n-samples 5000 --seed 42
    python scripts/train_gas_models.py --output-dir models/gas
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from devkit.core.utils.logger import setup_logger
from gas.modules import GasIsolationForestDetector
from devkit.generator.gas_generator import generate_gas_normal_pool, split_pool_by_device


def parse_args():
    parser = argparse.ArgumentParser(description="가스 IsolationForest 학습")
    parser.add_argument(
        "--n-samples", type=int, default=5000,
        help="학습 풀 크기 (T.1 기본 5000)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="난수 시드 (기본 42)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("models/gas"),
        help="모델 저장 디렉토리 (기본 models/gas)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logger = setup_logger("train_gas")

    logger.info("=" * 60)
    logger.info("가스 IsolationForest 학습 시작")
    logger.info("=" * 60)
    logger.info(f"학습 풀 크기: {args.n_samples}")
    logger.info(f"시드: {args.seed}")
    logger.info(f"출력 디렉토리: {args.output_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 학습 풀 생성
    logger.info("")
    logger.info("[1/2] 학습 풀 생성 중...")
    t0 = time.time()
    bundles = generate_gas_normal_pool(n_samples=args.n_samples, seed=args.seed)
    gas_a, gas_b = split_pool_by_device(bundles)
    logger.info(f"      gas_A {len(gas_a)}개, gas_B {len(gas_b)}개, "
                f"소요 {time.time() - t0:.2f}초")

    # 2. IsolationForest 학습 (B.2: 가스 IF 1개 모델 — 장비 무관 통합)
    logger.info("")
    logger.info("[2/2] IsolationForest 학습 중...")
    if_detector = GasIsolationForestDetector()
    metrics = if_detector.fit(gas_a + gas_b)
    logger.info(f"      입력: {metrics['n_samples_input']}, "
                f"학습됨: {metrics['n_samples_trained']} (NaN 제외)")
    logger.info(f"      차원: {metrics['n_features']}, "
                f"평균 마할라노비스: {metrics['mahalanobis_mean']:.3f}")
    logger.info(f"      소요: {metrics['training_time_seconds']:.2f}초")

    if_path = args.output_dir / "iforest.joblib"
    if_detector.save(if_path)
    size_mb = if_path.stat().st_size / (1024 * 1024)
    logger.info(f"      저장: {if_path} ({size_mb:.2f} MB)")

    logger.info("")
    logger.info("=" * 60)
    logger.info("가스 IsolationForest 학습 완료")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
