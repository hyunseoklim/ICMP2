#!/usr/bin/env python
"""scripts/validate_power_pool — Phase B-4 정적 검증.

도메인 비의존 코어 함수 + power 어댑터 분리. gas 확장 시 코어 함수를
ai_engine/validation/ 같은 별도 모듈로 이동 가능 (시그니처 호환).

검증 항목 V1·V2·V3·V4·V6 (V5 폐기 — 시나리오 ① 확정으로 1000W (P)/(Q) 비교 불필요):
    V1: 그룹별 학습 풀 통계 (mean/std/min/max/median)
    V2: 양자화 *전* 옴의 법칙 위반 비율 (B-2-7 결정 (iii)) — _ohm_truncated 안전장치
    V3: 그룹 분리도 (마할라노비스 매트릭스 + within_std_ratio 직접 보고)
    V4: 정수 양자화 시뮬레이션 — 전 그룹 (Finding-3 Evidence-3 정량화)
    V6: 학습된 IF 모델 train_mean 검증 — Phase C-1 (a) 2 모델 회귀 안전망

의사결정 매트릭스 자동 분류:
    V1: 평균이 working_means(rated_w) 가정 ±30% 벗어남 → Phase B 재산정
    V2: 양자화 전 옴 위반 > 1% → _ohm_truncated 버그 의심
    V3: 일부 쌍 < 3σ → Phase C 정규화 통합 / 3~5σ → 인접 병합 / ≥5σ → 그룹별 N개
    V4: 저전력 양자화 zero_ratio_loss > 50% → Finding-3 통신 프로토콜 분석 필수

사용:
    python scripts/validate_power_pool.py
    python scripts/validate_power_pool.py --output reports/phase_b_validation.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from devkit.core.utils.logger import setup_logger
from power.premises import (
    POWER_SENSOR_TYPES, POWER_RESOLUTION,
    working_means,
)
from devkit.generator.power_generator import generate_power_normal_pool


# Phase B-4 검증 대상 그룹 — train_power_models.py와 일치
RATED_GROUPS: list = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]


# ============================================================================
# 도메인 비의존 코어 함수 — gas 확장 시 별도 모듈로 이동 가능
# 시그니처: numpy array + dict + float만. PowerReading/GasReading 등 도메인
# 모델 직접 import 금지. 추출 비용을 0에 가깝게 유지.
# ============================================================================

def compute_pool_stats(samples: np.ndarray) -> dict:
    """학습 풀 통계 — V1.

    Args:
        samples: shape (n, k). 결측은 NaN.

    Returns:
        차원별 mean/std/min/max/median + n/n_valid.
    """
    valid = ~np.isnan(samples).any(axis=1)
    arr = samples[valid]
    if len(arr) == 0:
        return {"n": int(len(samples)), "n_valid": 0}
    return {
        "n": int(len(samples)),
        "n_valid": int(len(arr)),
        "mean": arr.mean(axis=0).tolist(),
        "std": arr.std(axis=0).tolist(),
        "min": arr.min(axis=0).tolist(),
        "max": arr.max(axis=0).tolist(),
        "median": np.median(arr, axis=0).tolist(),
    }


def compute_mahalanobis_matrix(distributions: list[dict]) -> np.ndarray:
    """그룹 간 pairwise 마할라노비스 거리 매트릭스 — V3.

    분포 i,j 간 거리: sqrt((μ_i - μ_j)ᵀ · ((Σ_i+Σ_j)/2)⁻¹ · (μ_i - μ_j))

    Args:
        distributions: [{"name": str, "mean": np.array, "cov": np.array}, ...]

    Returns:
        (N, N) 거리 매트릭스. 대각은 0.
    """
    n = len(distributions)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            diff = distributions[i]["mean"] - distributions[j]["mean"]
            pooled_cov = (distributions[i]["cov"] + distributions[j]["cov"]) / 2
            try:
                cov_inv = np.linalg.inv(pooled_cov)
            except np.linalg.LinAlgError:
                cov_inv = np.linalg.pinv(pooled_cov)
            matrix[i, j] = float(np.sqrt(diff @ cov_inv @ diff))
    return matrix


def classify_separation(
    matrix: np.ndarray,
    threshold_5sigma: float = 5.0,
    threshold_3sigma: float = 3.0,
) -> dict:
    """분리도 매트릭스 → 의사결정 셀 자동 분류 — V3.

    Returns:
        {"cell": ..., "min_distance": float, "max_distance": float,
         "recommendation": str}
    """
    mask = ~np.eye(matrix.shape[0], dtype=bool)
    distances = matrix[mask]
    if len(distances) == 0:
        return {
            "cell": "single_group",
            "min_distance": 0.0, "max_distance": 0.0,
            "recommendation": "단일 그룹 — 분리도 의미 없음",
        }
    min_d = float(distances.min())
    max_d = float(distances.max())
    if min_d >= threshold_5sigma:
        cell, rec = "all_5sigma", "Phase C: 그룹별 IF 모델 N개 학습"
    elif min_d >= threshold_3sigma:
        cell, rec = "some_3to5sigma", "Phase C: 인접 그룹 병합 후 N' < N개 학습"
    else:
        cell, rec = "any_below_3sigma", "Phase C: 정규화 통합 모델 1개"
    return {
        "cell": cell,
        "min_distance": min_d,
        "max_distance": max_d,
        "recommendation": rec,
    }


def simulate_quantization(
    samples: np.ndarray,
    resolution: dict,
    sensor_types: list,
) -> dict:
    """정수 양자화 시뮬레이션 — V4 (Finding-3 Evidence-3 정량화).

    학습 풀(float)을 양자화한 후 분포 변화를 측정:
        - 평균 drift (마할라노비스 단위)
        - 차원별 zero_ratio 증가 (저전력 그룹 신호)

    Args:
        samples: shape (n, k). float 분포 (양자화 *전*).
        resolution: 차원별 양자화 분해능 dict.
        sensor_types: 차원 이름 순서.

    Returns:
        양자화 영향 정량 dict.
    """
    valid_mask = ~np.isnan(samples).any(axis=1)
    arr = samples[valid_mask]
    if len(arr) == 0:
        return {"n_samples": 0}
    arr_q = arr.copy()
    for i, st in enumerate(sensor_types):
        res = resolution.get(st, 1.0)
        arr_q[:, i] = np.round(arr_q[:, i] / res) * res
    mean_orig = arr.mean(axis=0)
    mean_q = arr_q.mean(axis=0)
    cov_orig = np.cov(arr.T)
    diff = mean_q - mean_orig
    try:
        cov_inv = np.linalg.inv(cov_orig)
        mahal_drift = float(np.sqrt(diff @ cov_inv @ diff))
    except np.linalg.LinAlgError:
        mahal_drift = float("nan")
    by_dim = {}
    for i, st in enumerate(sensor_types):
        n_zero_orig = float(np.mean(arr[:, i] == 0))
        n_zero_q = float(np.mean(arr_q[:, i] == 0))
        by_dim[st] = {
            "mean_drift": float(mean_q[i] - mean_orig[i]),
            "zero_ratio_orig": n_zero_orig,
            "zero_ratio_quantized": n_zero_q,
            "zero_ratio_loss": n_zero_q - n_zero_orig,
        }
    return {
        "n_samples": int(len(arr)),
        "mahalanobis_drift": mahal_drift,
        "by_dim": by_dim,
    }


def validate_trained_models(
    models_dir: Path,
    deviation_threshold: float = 0.01,
    n_samples: int = 5000,
    seed: int = 42,
) -> dict:
    """V6 — 학습된 IF 모델 train_mean 검증.

    [Phase D 결정 (2026-05-23): STEP F 비활성 — 본 함수 비활성 보존 (옵션 a)]

    삭제 검증 방법 (본 함수 + V6 호출부 안전 삭제 가능 확인):
        1. iforest_g0050.joblib + iforest_high.joblib 운영 활용 0건 확인
        2. monitoring/ai/power_if.py 삭제됨 (선결 조건)
        3. 위 통과 시:
           - 본 함수 (validate_trained_models) 삭제
           - run_power_validation() 의 V6 호출부 (V6_trained_models 섹션) 삭제
           - _write_report() 의 V6 markdown 출력 섹션 삭제

    Phase C-1 (a) 2 모델 회귀 안전망 (원래 설계):

    iforest_g0050.joblib + iforest_high.joblib의 메타데이터 train_mean이
    *양자화 후 학습 풀 실측 평균*과 일치하는지 검증. Phase C 재학습 시 회귀 감지.

    비교 기준 정정 (Phase C-4 회귀 분석):
        working_means(rated_w)는 양자화 *전* 분포 정의. 학습 풀은 양자화 *후*
        평균이 다름 (저전력 그룹은 V4 mahal_drift 5σ+). 양자화 *후* 학습 풀을
        실시간 재생성하여 train_mean과 비교 — 같은 시드 + 분포라 편차 < 0.01%
        예상. 큰 편차는 학습 코드 회귀 신호.

    Args:
        models_dir: 모델 디렉토리.
        deviation_threshold: 통과 임계 (기본 1% — 양자화 영향이 비교 기준에 포함되므로 좁게).
        n_samples: 검증용 학습 풀 샘플 수 (train_power_models.py와 일치 필요).
        seed: 검증용 학습 풀 시드 (train_power_models.py와 일치 필요).

    Returns:
        {'low': {...}, 'high': {...}}.
    """
    import joblib

    results: dict = {}

    # ── low 모델 검증 ──
    low_path = models_dir / 'iforest_g0050.joblib'
    if low_path.exists():
        # 양자화 후 학습 풀 재생성 (같은 시드 + 분포 — train_power_models.py와 일치)
        low_pool = generate_power_normal_pool(
            rated_w=50, n_samples=n_samples, seed=seed,
        )
        low_arr = _bundles_to_array(low_pool)
        low_valid = low_arr[~np.isnan(low_arr).any(axis=1)]
        expected_arr = low_valid.mean(axis=0).tolist()

        md = joblib.load(low_path)
        actual = md['train_mean'].tolist()
        deviations = [
            ((a - e) / e * 100) if e != 0 else 0.0
            for a, e in zip(actual, expected_arr)
        ]
        results['low'] = {
            'file_exists': True,
            'expected': expected_arr,
            'actual': actual,
            'deviations_pct': deviations,
            'pass': all(abs(d) < deviation_threshold * 100 for d in deviations),
        }
    else:
        results['low'] = {'file_exists': False}

    # ── high 모델 검증 — 10 그룹 통합 학습 풀 평균 ──
    high_path = models_dir / 'iforest_high.joblib'
    if high_path.exists():
        high_groups = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        high_valid_arrs = []
        for rw in high_groups:
            pool = generate_power_normal_pool(
                rated_w=rw, n_samples=n_samples, seed=seed,
            )
            arr = _bundles_to_array(pool)
            high_valid_arrs.append(arr[~np.isnan(arr).any(axis=1)])
        high_combined = np.concatenate(high_valid_arrs, axis=0)
        expected_arr = high_combined.mean(axis=0).tolist()

        md = joblib.load(high_path)
        actual = md['train_mean'].tolist()
        deviations = [
            ((a - e) / e * 100) if e != 0 else 0.0
            for a, e in zip(actual, expected_arr)
        ]
        results['high'] = {
            'file_exists': True,
            'expected': expected_arr,
            'actual': actual,
            'deviations_pct': deviations,
            'pass': all(abs(d) < deviation_threshold * 100 for d in deviations),
        }
    else:
        results['high'] = {'file_exists': False}

    return results


def compute_ohm_violation_rate(samples: np.ndarray) -> float:
    """V2 — 양자화 전 옴의 법칙 위반 비율.

    |P - V·I| > 5% × |V·I| 인 샘플 비율.

    Args:
        samples: shape (n, 3) — [V, I, P] 순서.

    Returns:
        위반 비율 (0~1).
    """
    valid = ~np.isnan(samples).any(axis=1)
    arr = samples[valid]
    if len(arr) == 0:
        return 0.0
    ohm_diff = np.abs(arr[:, 2] - arr[:, 0] * arr[:, 1])
    return float(np.mean(ohm_diff > 0.05 * np.abs(arr[:, 0] * arr[:, 1])))


# ============================================================================
# Power 도메인 어댑터 — gas 확장 시 분리 대상
# ============================================================================

def _bundles_to_array(bundles: list) -> np.ndarray:
    """SensorBundle 리스트 → (n, 3) numpy array."""
    return np.array([
        [
            b.values["voltage"] if b.values["voltage"] is not None else np.nan,
            b.values["current"] if b.values["current"] is not None else np.nan,
            b.values["power"]   if b.values["power"]   is not None else np.nan,
        ]
        for b in bundles
    ])


def build_power_distributions(group_pools: dict) -> list[dict]:
    """power 그룹별 학습 풀 → 코어 함수 입력 형식.

    Args:
        group_pools: {rated_w: samples_array}

    Returns:
        [{"name": "g0050", "rated_w": int, "mean": array, "cov": array}, ...]
    """
    distributions = []
    for rated_w in sorted(group_pools.keys()):
        samples = group_pools[rated_w]
        valid = ~np.isnan(samples).any(axis=1)
        arr = samples[valid]
        if len(arr) < 2:
            continue
        distributions.append({
            "name": f"g{rated_w:04d}",
            "rated_w": int(rated_w),
            "mean": arr.mean(axis=0),
            "cov": np.cov(arr.T),
        })
    return distributions


def run_power_validation(
    output_path: Optional[Path] = None,
    n_samples: int = 5000,
    seed: int = 42,
) -> dict:
    """Phase B-4 전체 검증 실행."""
    logger = logging.getLogger("validate_power_pool")
    results = {
        "timestamp": datetime.now().isoformat(),
        "n_samples": n_samples,
        "seed": seed,
        "groups": {},
        "V3_separation": None,
        "V3_within_std_ratio": [],
        "decisions": [],
    }

    # ── V1·V2·V4: 그룹별 학습 풀 생성 + 통계 + 옴 위반 + 양자화 ──
    logger.info("=" * 70)
    logger.info("V1·V2·V4 — 그룹별 학습 풀 (양자화 전, n=%d, seed=%d)", n_samples, seed)
    logger.info("=" * 70)

    group_pools_unq = {}  # 양자화 전
    for rated_w in RATED_GROUPS:
        pool = generate_power_normal_pool(
            rated_w=rated_w, n_samples=n_samples,
            apply_quantization=False, seed=seed,
        )
        arr = _bundles_to_array(pool)
        group_pools_unq[rated_w] = arr

        stats = compute_pool_stats(arr)
        ohm_violation = compute_ohm_violation_rate(arr)
        quant_sim = simulate_quantization(arr, POWER_RESOLUTION, POWER_SENSOR_TYPES)

        results["groups"][rated_w] = {
            "V1_stats": stats,
            "V2_ohm_violation": ohm_violation,
            "V4_quantization": quant_sim,
        }
        logger.info(
            "  rated_w=%4d  n=%d  P=%.1f±%.2f  V2 옴위반=%.4f%%  V4 mahal_drift=%.3f",
            rated_w, stats["n_valid"], stats["mean"][2], stats["std"][2],
            ohm_violation * 100, quant_sim["mahalanobis_drift"],
        )

    # ── V3: 마할라노비스 분리도 ──
    logger.info("")
    logger.info("=" * 70)
    logger.info("V3 — 그룹 간 분리도 (마할라노비스 매트릭스)")
    logger.info("=" * 70)
    distributions = build_power_distributions(group_pools_unq)
    matrix = compute_mahalanobis_matrix(distributions)
    separation = classify_separation(matrix)
    results["V3_separation"] = {
        "matrix": matrix.tolist(),
        "group_names": [d["name"] for d in distributions],
        "classification": separation,
    }

    # within_std_ratio 직접 보고 (함정 ① CoV 환산 폐기 후 대체)
    for d in distributions:
        std_arr = np.sqrt(np.diag(d["cov"]))
        ratio = float(std_arr[2] / d["mean"][2]) if d["mean"][2] > 0 else 0.0
        results["V3_within_std_ratio"].append({
            "rated_w": d["rated_w"], "within_std_ratio": ratio,
        })
        logger.info("  %s  P within_std_ratio=%.3f", d["name"], ratio)

    logger.info("  분리도 분류: %s", separation["cell"])
    logger.info("    min 거리: %.2fσ", separation["min_distance"])
    logger.info("    max 거리: %.2fσ", separation["max_distance"])
    logger.info("    권장: %s", separation["recommendation"])

    # ── 의사결정 매트릭스 자동 분류 ──
    results["decisions"].append(f"V3 → {separation['recommendation']}")

    for rated_w in RATED_GROUPS:
        stats = results["groups"][rated_w]["V1_stats"]
        expected = working_means(rated_w)
        actual_p = stats["mean"][2]
        deviation = abs(actual_p - expected["power"]) / expected["power"]
        if deviation > 0.30:
            results["decisions"].append(
                f"⚠ V1: rated_w={rated_w} 평균 편차 {deviation*100:.1f}% > 30%"
            )

        ohm = results["groups"][rated_w]["V2_ohm_violation"]
        if ohm > 0.01:
            results["decisions"].append(
                f"⚠ V2: rated_w={rated_w} 양자화 전 옴 위반 {ohm*100:.2f}% > 1%"
                f" — _ohm_truncated 버그 의심"
            )

    for rated_w in [50, 100, 200, 300, 400]:
        v4 = results["groups"][rated_w]["V4_quantization"]
        current_loss = v4["by_dim"]["current"]["zero_ratio_loss"]
        if current_loss > 0.5:
            results["decisions"].append(
                f"⚠ V4: rated_w={rated_w} current 양자화 zero_ratio_loss "
                f"+{current_loss*100:.0f}% — Finding-3 통신 프로토콜 분석 필수"
            )

    # ── V6: 학습된 IF 모델 train_mean 검증 (Phase C-1 회귀 안전망) ──
    logger.info("")
    logger.info("=" * 70)
    logger.info("V6 — 학습된 IF 모델 train_mean 검증")
    logger.info("=" * 70)
    models_dir = _PROJECT_ROOT / 'models' / 'power'
    v6_results = validate_trained_models(models_dir)
    results['V6_trained_models'] = v6_results

    for model_name in ('low', 'high'):
        m = v6_results[model_name]
        if not m.get('file_exists'):
            logger.warning("  %s 모델 파일 부재 — Phase C-1 IF 학습 미실행", model_name)
            results['decisions'].append(
                f"⚠ V6: {model_name} 모델 파일 부재 — train_power_models.py --with-if-train 필요"
            )
            continue
        status = "✅" if m['pass'] else "⚠ 경고"
        logger.info(
            "  %s 모델  train_mean=%s  기대=%s  편차=%s  %s",
            model_name,
            [f"{a:.3f}" for a in m['actual']],
            [f"{e:.3f}" for e in m['expected']],
            [f"{d:+.2f}%" for d in m['deviations_pct']],
            status,
        )
        if not m['pass']:
            results['decisions'].append(
                f"⚠ V6: {model_name} 모델 편차 > 5% — Phase C-1 재학습 또는 분포 가정 재검토"
            )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_report(results, output_path)
        logger.info("")
        logger.info("보고서 저장: %s", output_path)

    return results


def _write_report(results: dict, output_path: Path) -> None:
    """검증 결과 → markdown 보고서."""
    lines = [
        "# Phase B-4 — power 학습 풀 정적 검증",
        "",
        f"검증 시각: {results['timestamp']}",
        f"n_samples/그룹: {results['n_samples']}, seed: {results['seed']}",
        "",
        "## V1 — 그룹별 학습 풀 통계 (양자화 *전*)",
        "",
        "| rated_w | n | V mean | A mean | P mean | P std | P min | P max |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rw in sorted(results["groups"].keys()):
        s = results["groups"][rw]["V1_stats"]
        lines.append(
            f"| {rw} | {s['n_valid']} | {s['mean'][0]:.2f} | "
            f"{s['mean'][1]:.3f} | {s['mean'][2]:.1f} | {s['std'][2]:.2f} | "
            f"{s['min'][2]:.1f} | {s['max'][2]:.1f} |"
        )

    lines.extend([
        "",
        "## V2 — 양자화 전 옴의 법칙 위반 비율 (`_ohm_truncated` 안전장치)",
        "",
        "| rated_w | 옴 위반율 | 판정 |",
        "|---:|---:|:---:|",
    ])
    for rw in sorted(results["groups"].keys()):
        v = results["groups"][rw]["V2_ohm_violation"]
        status = "✅" if v <= 0.01 else "⚠ 경고"
        lines.append(f"| {rw} | {v*100:.4f}% | {status} |")

    lines.extend([
        "",
        "## V3 — 그룹 분리도 (마할라노비스 매트릭스 + within_std_ratio)",
        "",
        f"분류 셀: **{results['V3_separation']['classification']['cell']}**",
        "",
        f"- min 거리: {results['V3_separation']['classification']['min_distance']:.2f}σ",
        f"- max 거리: {results['V3_separation']['classification']['max_distance']:.2f}σ",
        f"- 권장: {results['V3_separation']['classification']['recommendation']}",
        "",
        "### within_std_ratio (함정 ① CoV 환산 폐기 후 대체 — 직접 보고)",
        "",
        "| rated_w | P within_std_ratio |",
        "|---:|---:|",
    ])
    for entry in results["V3_within_std_ratio"]:
        lines.append(f"| {entry['rated_w']} | {entry['within_std_ratio']:.3f} |")

    lines.extend([
        "",
        "## V4 — 정수 양자화 시뮬레이션 (Finding-3 Evidence-3)",
        "",
        "| rated_w | mahalanobis_drift | A zero_loss | P zero_loss |",
        "|---:|---:|---:|---:|",
    ])
    for rw in sorted(results["groups"].keys()):
        v = results["groups"][rw]["V4_quantization"]
        a_loss = v["by_dim"]["current"]["zero_ratio_loss"]
        p_loss = v["by_dim"]["power"]["zero_ratio_loss"]
        lines.append(
            f"| {rw} | {v['mahalanobis_drift']:.3f} | "
            f"{a_loss*100:.1f}% | {p_loss*100:.2f}% |"
        )

    # V6 학습된 모델 검증
    lines.extend([
        "",
        "## V6 — 학습된 IF 모델 train_mean 검증 (Phase C-1 회귀 안전망)",
        "",
        "| 모델 | 파일 존재 | train_mean (actual) | 기대 (expected) | 편차 | 판정 |",
        "|---|:---:|---|---|---|:---:|",
    ])
    for model_name in ('low', 'high'):
        m = results.get('V6_trained_models', {}).get(model_name, {})
        if not m.get('file_exists'):
            lines.append(f"| {model_name} | ❌ | — | — | — | 미학습 |")
            continue
        actual_s = "[" + ", ".join(f"{a:.3f}" for a in m['actual']) + "]"
        expected_s = "[" + ", ".join(f"{e:.3f}" for e in m['expected']) + "]"
        dev_s = "[" + ", ".join(f"{d:+.2f}%" for d in m['deviations_pct']) + "]"
        status = "✅" if m['pass'] else "⚠"
        lines.append(f"| {model_name} | ✅ | {actual_s} | {expected_s} | {dev_s} | {status} |")

    lines.extend([
        "",
        "## 의사결정 매트릭스 — 자동 분류 결과",
        "",
    ])
    if results["decisions"]:
        for d in results["decisions"]:
            lines.append(f"- {d}")
    else:
        lines.append("- 모든 검증 항목 통과. Phase C 진입 조건 충족.")
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Phase B-4 power 학습 풀 정적 검증")
    parser.add_argument(
        "--output", type=Path,
        default=Path("reports/phase_b_validation.md"),
    )
    parser.add_argument("--n-samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logger = setup_logger("validate_power_pool")
    logger.info("Phase B-4 — power 학습 풀 정적 검증 시작")
    results = run_power_validation(
        output_path=args.output, n_samples=args.n_samples, seed=args.seed,
    )
    logger.info("")
    logger.info("=" * 70)
    logger.info("의사결정 매트릭스 — 자동 분류 결과")
    logger.info("=" * 70)
    for d in results["decisions"]:
        logger.info("  %s", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
