#!/usr/bin/env python
"""scripts/generate_story.py — 24시간 통합 스토리 생성 및 저장.

사용:
    python scripts/generate_story.py
    python scripts/generate_story.py --duration-hours 12 --seed 42
    python scripts/generate_story.py --output-dir data/synthetic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd

from devkit.core.utils.logger import setup_logger
from devkit.generator.integrated_story import generate_integrated_story_24h


def parse_args():
    parser = argparse.ArgumentParser(description="24시간 통합 스토리 생성")
    parser.add_argument("--duration-hours", type=float, default=12.0,
                        help="스토리 길이 (시간, 기본 12.0)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--format", choices=["parquet", "csv"], default="parquet",
                        help="저장 형식")
    return parser.parse_args()


def bundles_to_dataframe(bundles: list) -> pd.DataFrame:
    """SensorBundle 리스트 → 평탄 DataFrame.
    
    각 행: (timestamp, device_id, sensor_type, value, is_valid)
    """
    rows = []
    for b in bundles:
        for st, v in b.values.items():
            rows.append({
                "timestamp": b.timestamp,
                "device_id": b.device_id,
                "sensor_type": st,
                "value": v,
                "is_valid": b.is_valid_flags.get(st, False),
            })
    return pd.DataFrame(rows)


def main():
    args = parse_args()
    logger = setup_logger("generate_story")

    logger.info("=" * 60)
    logger.info("통합 스토리 생성 시작")
    logger.info("=" * 60)
    logger.info(f"길이: {args.duration_hours}시간")
    logger.info(f"시드: {args.seed}")
    logger.info(f"출력 형식: {args.format}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 스토리 생성
    logger.info("")
    logger.info("[1/3] 스토리 생성 중...")
    result = generate_integrated_story_24h(
        duration_hours=args.duration_hours,
        seed=args.seed,
    )
    logger.info(f"      가스 묶음: {len(result['gas_bundles'])}개")
    logger.info(f"      전력 묶음: {len(result['power_bundles'])}개")
    logger.info(f"      사건: {len(result['events'])}개")

    # 2. DataFrame 변환
    logger.info("")
    logger.info("[2/3] DataFrame 변환 중...")
    df_gas = bundles_to_dataframe(result["gas_bundles"])
    df_power = bundles_to_dataframe(result["power_bundles"])
    logger.info(f"      가스 DataFrame: {len(df_gas)} 행")
    logger.info(f"      전력 DataFrame: {len(df_power)} 행")

    # 3. 저장
    logger.info("")
    logger.info(f"[3/3] {args.format} 저장 중...")
    if args.format == "parquet":
        gas_path = args.output_dir / "story_gas.parquet"
        power_path = args.output_dir / "story_power.parquet"
        df_gas.to_parquet(gas_path, index=False)
        df_power.to_parquet(power_path, index=False)
    else:
        gas_path = args.output_dir / "story_gas.csv"
        power_path = args.output_dir / "story_power.csv"
        df_gas.to_csv(gas_path, index=False)
        df_power.to_csv(power_path, index=False)

    gas_size_mb = gas_path.stat().st_size / (1024 * 1024)
    power_size_mb = power_path.stat().st_size / (1024 * 1024)
    logger.info(f"      가스: {gas_path} ({gas_size_mb:.2f} MB)")
    logger.info(f"      전력: {power_path} ({power_size_mb:.2f} MB)")

    # 이벤트 메타데이터 JSON
    events_path = args.output_dir / "story_events.json"
    events_data = {
        "events": result["events"],
        "metadata": result["metadata"],
    }
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(events_data, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"      이벤트: {events_path}")

    logger.info("")
    logger.info("=" * 60)
    logger.info("통합 스토리 생성 완료")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
