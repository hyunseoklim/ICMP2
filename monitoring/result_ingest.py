"""result_ingest — AI 엔진 결과 stream(stream:*:result) → DB 적재 + 저장 후 전파 (가스/전력 공용).

stage로 모델 분기:
  THRESHOLD/ZSCORE/CHANGEPOINT/IF → DetectionResult
  ARIMA                            → ForecastSnapshot (채널당 1행 upsert)

저장 성공 후 post_store_dispatch()로 전파 — 저장책임/전파책임 분리 (STEP2 §10):
  · dispatch_forecast_ws : floor_*_forecast → ForecastConsumer (AI 예측·판정 실시간)
  · 알람                  : C1(AlarmRule/severity) 결정 후 연결 — 현재 미연결(추측 금지)
신규 Redis 버스 없이 기존 channel layer 재사용(방대화 방지).

계보 = trace_id. device_uid→Device, channel_code→DeviceChannel(전력) 해석.
"""
import logging
import uuid

logger = logging.getLogger(__name__)

_DETECTION_STAGES = {"THRESHOLD", "ZSCORE", "CHANGEPOINT", "IF"}


def _sensor_type(payload: dict):
    """가스=sensor_type / 전력 thr·z·cp={channel}/{metric} / 전력 IF=channel / 가스 IF=None.

    합성키 '/' 관례는 기존 power ARIMA(alerts/tasks.py)와 일치.
    """
    st = payload.get("sensor_type")
    ch = payload.get("channel_code")
    if ch and st:
        return f"{ch}/{st}"
    return ch or st


def store_result(payload: dict) -> bool:
    """결과 payload 1건 적재 + 저장 후 전파. 적재 True / 스킵 False."""
    from alerts.models import ForecastSnapshot
    from monitoring.models import Device, DeviceChannel, DetectionResult

    device = Device.objects.filter(device_uid=payload.get("device_uid")).first()
    if device is None:
        logger.warning("[result] device 미존재 — %s 스킵", payload.get("device_uid"))
        return False

    stage = payload.get("stage")
    try:
        trace_uuid = uuid.UUID(str(payload.get("trace_id")))
    except (ValueError, TypeError):
        trace_uuid = uuid.uuid4()  # 방어 — 계보 키 누락 시

    if stage in _DETECTION_STAGES:
        DetectionResult.objects.create(
            trace_id=trace_uuid, gas_reading=None, device=device,
            sensor_type=_sensor_type(payload), stage=stage,
            level=str(payload.get("level")), score=payload.get("score"),
            detail=payload.get("detail") or {},
        )
    elif stage == "ARIMA":
        channel = None
        ch_code = payload.get("channel_code")
        if ch_code:
            channel = DeviceChannel.objects.filter(device=device, channel_code=ch_code).first()
            if channel is None:
                logger.warning("[result] channel 미존재 — %s/%s 스킵", device.device_uid, ch_code)
                return False
        d = payload.get("detail") or {}
        ForecastSnapshot.objects.update_or_create(
            device=device, channel=channel, sensor_type=payload.get("sensor_type"),
            defaults={
                "headline_severity":   d.get("headline_severity"),
                "headline_confidence": d.get("headline_confidence") or "UNKNOWN",
                "caution_confidence":  d.get("caution_confidence") or "UNKNOWN",
                "danger_confidence":   d.get("danger_confidence") or "UNKNOWN",
                "caution_eta_step":    d.get("caution_eta_step"),
                "danger_eta_step":     d.get("danger_eta_step"),
                "path":                d.get("path") or "unknown",
                "forecast_steps":      d.get("forecast_steps", 0),
                "reason":              d.get("reason", ""),
                "forecast_mean":       d.get("forecast_mean"),   # 곡선(결과 객체가 담아 전달)
                "ci_lower":            d.get("ci_lower"),
                "ci_upper":            d.get("ci_upper"),
            },
        )
    else:
        logger.warning("[result] 알 수 없는 stage=%s 스킵", stage)
        return False

    # ── 저장 성공 후 전파 (저장책임과 분리) ──
    post_store_dispatch(device, payload)
    return True


def post_store_dispatch(device, payload: dict) -> None:
    """저장 성공 후 전파 (STEP2 §10). 신규 Redis 버스 없이 기존 channel layer/broker 재사용.

    각 dispatch는 guarded — 전파 실패가 이미 완료된 저장을 무효화하지 않는다.
    """
    dispatch_forecast_ws(device, payload)               # 화면 push — 항상
    # AI 알람: dispatch_alert 상시(F4 컷오버 — ingest trigger_* 제거, XOR 플래그 불요)
    try:
        dispatch_alert(device, payload)
    except Exception as e:                              # 알람 실패가 저장·화면을 무효화하지 않음
        logger.warning("[result] dispatch_alert 실패 trace_id=%s: %s", payload.get("trace_id"), e)


def dispatch_forecast_ws(device, payload: dict) -> None:
    """AI 예측·판정을 floor_*_forecast로 실시간 push (ForecastConsumer).

    store-first 후 호출되므로 화면=DB 일관. WS 실패는 로그+무시(저장 이미 완료).
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from facilities.models import SensorLocation

        sensor = SensorLocation.objects.filter(device_id=device.id, is_active=True).first()
        if sensor is None:
            return
        async_to_sync(get_channel_layer().group_send)(
            f"floor_{sensor.floor_id}_forecast",
            {"type": "forecast.update", "msg_type": "delta", "data": [payload]},
        )
    except Exception as e:
        logger.warning("[result] forecast WS 실패 trace_id=%s: %s", payload.get("trace_id"), e)


# ── 알람 (C1 §11) — stage→rule/severity, level→class(이상/정상/불명), open_event 9경우 ──
_STAGE_ALARM = {
    "ZSCORE":      ("AI", "ANOMALY"),
    "CHANGEPOINT": ("AI", "ANOMALY"),
    "IF":          ("AI", "ANOMALY"),
    "ARIMA":       ("FORECAST", "PREDICTIVE_WARNING"),
    # THRESHOLD 제외 — 운영 알람은 Django ingest(동기)가 담당(결정2)
}


def _alarm_class(level: str) -> str:
    """모듈별 level 어휘 → 이상/정상/불명 정규화."""
    if level in ("판정불가", "UNKNOWN", "unknown"):
        return "unknown"
    if level in ("정상", "NORMAL", "normal"):
        return "normal"
    return "anomaly"   # 주의·위험·SHIFT·danger·caution


def _alarm_title(stage: str, payload: dict) -> str:
    st = (payload.get("sensor_type") or "").upper()
    ch = payload.get("channel_code")
    tag = f"{ch} " if ch else ""
    return {
        "ZSCORE":      f"[AI] {tag}{st} 통계 이상",
        "CHANGEPOINT": f"[CP] {tag}{st} 상태 변화",
        "IF":          f"[IF] {tag}분포 이상",
        "ARIMA":       f"[예측] {tag}{st} 사전 경고",
    }.get(stage, "[AI] 이상")


def _alarm_message(stage: str, payload: dict) -> str:
    """문구 모듈 분기 (결정3 — severity는 통일이나 사유는 구별)."""
    d = payload.get("detail") or {}
    sc = payload.get("score")
    st = payload.get("sensor_type", "")
    if stage == "ZSCORE":      return f"{st} 통계 이상 (z={sc})"
    if stage == "CHANGEPOINT": return f"{st} 상태 변화 — {d.get('reason', '')}"
    if stage == "IF":          return f"분포 이상 — {d.get('reason', '')}"
    if stage == "ARIMA":       return f"예측 사전경고 (sev={d.get('headline_severity')}, eta={d.get('danger_eta_step') or d.get('caution_eta_step')})"
    return str(d)


def dispatch_alert(device, payload: dict) -> None:
    """AI 결과 → AlarmEvent (open_event 9경우 분기, C1 §11).

    이상→생성/갱신 · 정상→종료(close) · 불명→기록만(비종료). THRESHOLD 제외(운영=Django).
    'result' 플래그일 때만 호출됨(ingest trigger_*와 XOR — 이중알람 방지).
    """
    from django.utils import timezone

    from alerts.models import AlarmEvent, AlarmRule, EventHistory
    from alerts.services import create_alarm_event
    from monitoring.models import DeviceChannel

    spec = _STAGE_ALARM.get(payload.get("stage"))
    if spec is None or not device.facility_id:
        return
    rule_type_name, severity_name = spec
    cls = _alarm_class(str(payload.get("level")))
    if cls == "unknown":
        return  # 기록만 (DetectionResult엔 이미 저장), open_event 유지(비종료)

    rule = AlarmRule.objects.filter(
        rule_type=getattr(AlarmRule.RuleType, rule_type_name), is_active=True,
    ).first()
    if rule is None:
        return

    stage = payload.get("stage")
    title = _alarm_title(stage, payload)
    open_event = AlarmEvent.objects.filter(
        rule=rule, device=device, title=title,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by("-occurred_at").first()

    if cls == "anomaly":
        if open_event:                                   # 갱신(중복 억제)
            open_event.last_seen_at = timezone.now()
            open_event.current_value = payload.get("score")
            open_event.save(update_fields=["last_seen_at", "current_value", "updated_at"])
        else:                                            # 신규 생성
            channel = None
            ch_code = payload.get("channel_code")
            if ch_code:
                channel = DeviceChannel.objects.filter(device=device, channel_code=ch_code).first()
            create_alarm_event(
                rule=rule, facility=device.facility,
                severity=getattr(AlarmEvent.Severity, severity_name),
                title=title, device=device, channel=channel,
                message=_alarm_message(stage, payload),
                current_value=payload.get("score"),
            )
    elif cls == "normal":                                # 정상 복귀 → 종료
        if open_event:
            open_event.event_status = AlarmEvent.EventStatus.CLOSED
            open_event.closed_at = timezone.now()
            open_event.save(update_fields=["event_status", "closed_at", "updated_at"])
            EventHistory.objects.create(
                alarm_event=open_event, action_type="close",
                action_note=f"{stage} 정상 복귀 자동 종료",
            )
