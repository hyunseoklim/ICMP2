"""analyzer — 도메인별 분석 디스패처 (수직 분리: 자기 도메인 core만 import).

F1-3a 범위: 즉시 스테이지(THRESHOLD + IF). ZSCORE/CP(F1-3b)·ARIMA(F1-3c)는 추후 확장.
결과는 result payload 리스트로 반환하며, 발행(result stream XADD)은 F1-4가 담당한다.

전력 IF 정격 라우팅: 채널 rated_w로 g0050/high 모델 선택. rated_w 정본은 DB
DeviceChannel.rated_power_w 이며, 여기 정적 맵은 부트스트랩(임시) — DB 공유는 DF-1.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import adapters, domain

logger = logging.getLogger(__name__)

_MODELS_DIR = Path(__file__).resolve().parents[1] / "models" / domain.DOMAIN

# 전력 IF 정격 라우팅 부트스트랩 (정본=DB DeviceChannel.rated_power_w, 공유는 DF-1)
POWER_RATED_W = {
    "slave01": 800, "slave02": 800, "slave11": 50, "slave12": 50,
    "slave21": 500, "slave22": 500, "slave31": 300, "slave32": 300,
    "slave41": 600, "slave42": 600, "slave51": 400, "slave52": 400,
    "slave61": 1000, "slave62": 1000,
}


def _power_if_group(channel_code) -> str:
    """채널 정격 → IF 모델 그룹. rated<=50: g0050, else: high (STATUS.md 2모델)."""
    rated = POWER_RATED_W.get(channel_code)
    return "g0050" if rated is not None and rated <= 50 else "high"


# 윈도우 크기 (z=30, cp=40[FLOW_DETECTION])
_ZSCORE_WINDOW = 30
_CP_WINDOW = 40
_ARIMA_THROTTLE_SEC = 30   # 채널별 ARIMA 예측 최소 간격(초) — fit 부하 절감(forecast는 매 reading 불요)
_last_arima: dict = {}     # (series_dev, sensor) -> monotonic 시각

# WorkMode 판정용 로컬 타임존 — settings.TIME_ZONE('Asia/Seoul')과 동일.
# 코드베이스 정책: UTC 저장 / KST는 "표시 또는 KST 업무규칙(작업시간) 해석"에만.
# AI 엔진은 Django 독립이라 core.timeutils(timezone.localtime) 대신 stdlib zoneinfo 사용.
try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo("Asia/Seoul")
except Exception:                       # tzdata 부재 폴백 (KST=UTC+9, DST 없음)
    _KST = timezone(timedelta(hours=9))

# 부트스트랩 상태 (1회 로드)
_classifier = None       # ThresholdClassifier
_gas_if = None           # GasIsolationForestDetector
_power_if: dict = {}     # group -> PowerIsolationForestDetector
_zscore = None           # ZScoreDetector
_zscore_window = None     # SlidingWindow (z용, 다중시리즈)
_cp = None               # ChangePointDetector (FLOW)
_cp_window = None         # SlidingWindow (cp용, 다중시리즈)
_subsystem = None        # PredictionSubsystem (ARIMA 예측, 다중시리즈)
_NORMAL = None           # RiskLevel.NORMAL
_ALERT_LEVELS = set()    # {CAUTION, DANGER} — emit 대상(NORMAL·UNKNOWN 제외)


def bootstrap() -> None:
    """도메인 모듈·모델·윈도우 1회 로드. 자기 도메인만 import (런타임 누수 0)."""
    global _classifier, _gas_if, _power_if, _NORMAL, _ALERT_LEVELS
    global _zscore, _zscore_window, _cp, _cp_window, _subsystem
    if domain.DOMAIN == "gas":
        from gas.core.enums import CPPurpose, RiskLevel
        from gas.core.integration import PredictionSubsystem
        from gas.core.modules import ThresholdClassifier
        from gas.core.modules.change_point import ChangePointDetector
        from gas.core.modules.sliding_window import SlidingWindow
        from gas.core.modules.z_score import ZScoreDetector
        from gas.modules import GasARIMAPredictor, GasIsolationForestDetector
        from gas.thresholds import load_gas_thresholds

        _classifier = ThresholdClassifier(load_gas_thresholds())
        _NORMAL = RiskLevel.NORMAL
        _ALERT_LEVELS = {RiskLevel.CAUTION, RiskLevel.DANGER}
        _gas_if = GasIsolationForestDetector()
        _gas_if.load(str(_MODELS_DIR / "iforest.joblib"))
        _subsystem = PredictionSubsystem(load_gas_thresholds(), arima=GasARIMAPredictor())
    else:
        from power.core.enums import CPPurpose, RiskLevel
        from power.core.integration import PredictionSubsystem
        from power.core.modules import ThresholdClassifier
        from power.core.modules.change_point import ChangePointDetector
        from power.core.modules.sliding_window import SlidingWindow
        from power.core.modules.z_score import ZScoreDetector
        from power.modules import PowerARIMAPredictor, PowerIsolationForestDetector
        from power.thresholds import load_power_thresholds

        _classifier = ThresholdClassifier(load_power_thresholds())
        _NORMAL = RiskLevel.NORMAL
        _ALERT_LEVELS = {RiskLevel.CAUTION, RiskLevel.DANGER}
        for grp, fname in (("g0050", "iforest_g0050.joblib"), ("high", "iforest_high.joblib")):
            det = PowerIsolationForestDetector()
            det.load(str(_MODELS_DIR / fname))
            _power_if[grp] = det
        _subsystem = PredictionSubsystem(load_power_thresholds(), arima=PowerARIMAPredictor())

    # ZSCORE/CHANGEPOINT 윈도우·detector (도메인 공통 — SlidingWindow가 (device,sensor) 다중시리즈)
    _zscore_window = SlidingWindow(_ZSCORE_WINDOW)
    _zscore = ZScoreDetector(_zscore_window)
    _cp_window = SlidingWindow(_CP_WINDOW)
    _cp = ChangePointDetector(_cp_window, purpose=CPPurpose.FLOW_DETECTION)
    logger.info("[ai-engine:%s] analyzer bootstrap 완료", domain.DOMAIN)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── THRESHOLD (즉시) ──────────────────────────────────────
def _gas_threshold(payload: dict) -> list:
    out = []
    for ch in adapters.GAS_CHANNELS:
        val = payload.get(ch)
        if val is None:
            continue
        level = _classifier.classify_value(ch, float(val))
        out.append(adapters.result_to_payload(
            trace_id=payload.get("trace_id"), device_uid=payload.get("device_uid"),
            sensor_type=ch, stage="THRESHOLD", level=level.value, score=float(val),
            computed_at=_now_iso(), detail={"config": {"module": "threshold"}},
        ))
    return out


def _power_threshold(payload: dict) -> list:
    out = []
    ch_code = payload.get("channel_code")
    for metric, key in adapters.POWER_METRIC_KEYS.items():
        val = payload.get(key)
        if val is None:
            continue
        level = _classifier.classify_value(metric, float(val))
        out.append(adapters.result_to_payload(
            trace_id=payload.get("trace_id"), device_uid=payload.get("device_uid"),
            channel_code=ch_code, sensor_type=metric, stage="THRESHOLD",
            level=level.value, score=float(val), computed_at=_now_iso(),
            detail={"config": {"module": "threshold"}},
        ))
    return out


# ── IF (분포) ─────────────────────────────────────────────
def _gas_if_analyze(payload: dict):
    res = _gas_if.predict(adapters.raw_to_gas_bundle(payload))
    if res is None:
        return None
    return adapters.result_to_payload(
        trace_id=payload.get("trace_id"), device_uid=payload.get("device_uid"),
        sensor_type=None, stage="IF", level=res.level.value,
        score=res.mahalanobis_distance, computed_at=_now_iso(),
        detail={"is_anomaly": bool(res.is_anomaly), "reason": str(res.reason),
                "anomaly_score": res.anomaly_score, "config": {"module": "isolation_forest"}},
    )


def _power_if_analyze(payload: dict):
    ch_code = payload.get("channel_code")
    det = _power_if.get(_power_if_group(ch_code))
    if det is None:
        return None
    res = det.predict(adapters.raw_to_power_bundle(payload))
    if res is None:
        return None
    group = _power_if_group(ch_code)
    return adapters.result_to_payload(
        trace_id=payload.get("trace_id"), device_uid=payload.get("device_uid"),
        channel_code=ch_code, sensor_type=None, stage="IF", level=res.level.value,
        score=res.mahalanobis_distance, computed_at=_now_iso(),
        detail={"is_anomaly": bool(res.is_anomaly), "reason": str(res.reason),
                "anomaly_score": res.anomaly_score,
                "config": {"module": "isolation_forest", "group": group}},
    )


# ── ZSCORE + CHANGEPOINT (윈도우·상태) ───────────────────
def _analyze_window(payload: dict) -> list:
    """가스 9채널 / 전력 current·power(채널별). SlidingWindow가 (device,sensor) 다중시리즈."""
    dev = payload.get("device_uid")
    ts = adapters._parse_ts(payload.get("measured_at"))
    if domain.DOMAIN == "gas":
        from gas.core.data_types import DataPoint
        series_dev, ch_code = dev, None
        targets = [(ch, payload.get(ch)) for ch in adapters.GAS_CHANNELS]
    else:
        from power.core.data_types import DataPoint
        ch_code = payload.get("channel_code")
        series_dev = f"{dev}:{ch_code}"  # 채널별 시리즈 분리
        targets = [(m, payload.get(adapters.POWER_METRIC_KEYS[m])) for m in ("current", "power")]

    out = []
    for sensor_type, value in targets:
        if value is None:
            continue
        dp = DataPoint(timestamp=ts, device_id=series_dev, sensor_type=sensor_type,
                       value=float(value), is_valid=True)
        _zscore_window.push(dp)
        _cp_window.push(dp)

        zr = _zscore.detect(dp)                               # 전수 emit (audit — NORMAL/UNKNOWN 포함)
        out.append(adapters.result_to_payload(
            trace_id=payload.get("trace_id"), device_uid=dev, channel_code=ch_code,
            sensor_type=sensor_type, stage="ZSCORE", level=zr.level.value, score=zr.z_score,
            computed_at=_now_iso(),
            detail={"is_spike": bool(zr.is_spike), "config": {"module": "z_score"}}))

        cr = _cp.detect(series_dev, sensor_type)              # 전수 emit (SHIFT/NORMAL)
        cp_level = "SHIFT" if cr.has_change_point else "NORMAL"
        out.append(adapters.result_to_payload(
            trace_id=payload.get("trace_id"), device_uid=dev, channel_code=ch_code,
            sensor_type=sensor_type, stage="CHANGEPOINT", level=cp_level, score=cr.penalty,
            computed_at=_now_iso(),
            detail={"reason": str(cr.reason), "config": {"module": "change_point_flow"}}))
    return out


# ── WorkMode 게이팅 (전력 전용 — boundary.py 의도를 서비스가 적용) ──
def _work_mode(payload: dict):
    """전력 측정 시각 → WorkMode(WORKING/IDLE). 작업시간 08:00~18:00은 **KST 기준**.

    determine_work_mode는 timestamp.time()만 보고 tz는 호출자 책임 →
    UTC measured_at을 KST(_KST=Asia/Seoul)로 변환 후 전달(미변환 시 정오가 03시로 오판→IDLE).
    """
    from power.core.premises import determine_work_mode
    ts = adapters._parse_ts(payload.get("measured_at"))
    return determine_work_mode(ts.astimezone(_KST))


def _active(module_name: str, mode) -> bool:
    from power.core.premises import is_module_active
    return is_module_active(module_name, mode)


def _run_safe(fn, payload: dict, label: str) -> list:
    """단건 분석 fn을 안전 실행 — 실패는 로그+스킵(다른 스테이지 보존)."""
    try:
        r = fn(payload)
        return [r] if r is not None else []
    except Exception as e:
        logger.warning("[ai-engine:%s] %s 실패 trace_id=%s: %s",
                       domain.DOMAIN, label, payload.get("trace_id"), e)
        return []


# ── ARIMA (예측) ─────────────────────────────────────────
def _analyze_arima(payload: dict) -> list:
    """ARIMA 예측 → ForecastSnapshot 매핑. 매번 emit(스냅샷 갱신). 가스 9채널 / 전력 power."""
    dev = payload.get("device_uid")
    ts = adapters._parse_ts(payload.get("measured_at"))
    if domain.DOMAIN == "gas":
        from gas.core.data_types import DataPoint
        series_dev, ch_code = dev, None
        targets = [(ch, payload.get(ch)) for ch in adapters.GAS_CHANNELS]
    else:
        from power.core.data_types import DataPoint
        ch_code = payload.get("channel_code")
        series_dev = f"{dev}:{ch_code}"
        targets = [("power", payload.get("power_w"))]

    out = []
    for sensor_type, value in targets:
        if value is None:
            continue
        dp = DataPoint(timestamp=ts, device_id=series_dev, sensor_type=sensor_type,
                       value=float(value), is_valid=True)
        _subsystem.push(dp)                               # history 유지(매번)
        key = (series_dev, sensor_type)
        now_m = time.monotonic()
        if now_m - _last_arima.get(key, 0.0) < _ARIMA_THROTTLE_SEC:
            continue                                      # 예측 스로틀 — fit 부하 절감(backlog 폭주 방지)
        _last_arima[key] = now_m
        fr = _subsystem.predict_channel(series_dev, sensor_type)
        out.append(adapters.result_to_payload(
            trace_id=payload.get("trace_id"), device_uid=dev, channel_code=ch_code,
            sensor_type=sensor_type, stage="ARIMA",
            level=(fr.headline_severity or "normal"), score=None, computed_at=_now_iso(),
            detail={
                "headline_severity": fr.headline_severity,
                "headline_confidence": fr.headline_confidence.name,
                "caution_confidence": fr.caution_confidence.name,
                "danger_confidence": fr.danger_confidence.name,
                "caution_eta_step": fr.caution_eta_step,
                "danger_eta_step": fr.danger_eta_step,
                "path": fr.path,
                "forecast_steps": getattr(fr, "forecast_steps", 0),
                "reason": getattr(fr, "reason", ""),
                "config": {"module": "arima"},
            }))
    return out


async def handle(stream: str, payload: dict) -> list:
    """raw 1건 → 스테이지 결과 리스트 (F1-4가 발행).

    가스: threshold(9채널)·IF·ZSCORE·CP·ARIMA.
    전력: threshold·IF(WORKING)·ZSCORE·CP·ARIMA(WORKING). WorkMode 게이팅 적용.
    """
    if _classifier is None:
        bootstrap()
    if domain.DOMAIN == "gas":
        out = _gas_threshold(payload)
        out += _run_safe(_gas_if_analyze, payload, "IF")
        arima_active = True
    else:
        out = _power_threshold(payload)            # threshold: WORKING+IDLE
        mode = _work_mode(payload)
        if _active("isolation_forest_power", mode):
            out += _run_safe(_power_if_analyze, payload, "IF")
        arima_active = _active("arima", mode)      # ARIMA: WORKING만
    # ZSCORE + CHANGEPOINT (둘 다 WorkMode 활성 → 항상)
    try:
        out += _analyze_window(payload)
    except Exception as e:
        logger.warning("[ai-engine:%s] ZSCORE/CP 실패 trace_id=%s: %s",
                       domain.DOMAIN, payload.get("trace_id"), e)
    # ARIMA (전력은 WORKING만)
    if arima_active:
        try:
            out += _analyze_arima(payload)
        except Exception as e:
            logger.warning("[ai-engine:%s] ARIMA 실패 trace_id=%s: %s",
                           domain.DOMAIN, payload.get("trace_id"), e)
    logger.info("[ai-engine:%s] 분석 %d건 trace_id=%s",
                domain.DOMAIN, len(out), payload.get("trace_id"))
    return out
