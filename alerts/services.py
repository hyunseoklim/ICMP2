import math
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import AlarmEvent, AlarmRule, EventHistory, ForecastSnapshot

_SEVERITY_LABEL = {AlarmEvent.Severity.DANGER: '위험', AlarmEvent.Severity.WARNING: '주의'}


def check_gas_thresholds(device, reading) -> None:
    """GasReading 임계치 체크 → open 이벤트 갱신 또는 신규 생성. 정상 복귀 시 자동 closed."""
    from monitoring.services import check_threshold_exceeded

    if not device.facility_id:
        return

    if getattr(reading, 'quality_flag', 'ok') != 'ok':
        return

    rule = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.THRESHOLD,
        is_active=True,
    ).first()
    if not rule:
        return

    exceeded = check_threshold_exceeded(reading)
    now = timezone.now()

    open_event = AlarmEvent.objects.filter(
        rule=rule,
        device=device,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if not exceeded:
        # 정상 복귀 → open 이벤트 자동 closed
        if open_event:
            open_event.event_status = AlarmEvent.EventStatus.CLOSED
            open_event.closed_at = now
            open_event.save(update_fields=['event_status', 'closed_at', 'updated_at'])
            EventHistory.objects.create(
                alarm_event=open_event,
                action_type='close',
                action_note='센서값 정상 복귀로 자동 종료',
            )
        return

    severity = (
        AlarmEvent.Severity.DANGER
        if any(e['level'] == '위험' for e in exceeded)
        else AlarmEvent.Severity.WARNING
    )
    gases_str     = ', '.join(e['gas'].upper() for e in exceeded)
    message       = ', '.join(f"{e['gas'].upper()}: {e['value']} ({e['level']})" for e in exceeded)
    max_value     = max(e['value'] for e in exceeded)

    if open_event:
        # 기존 open 이벤트 갱신
        open_event.last_seen_at   = now
        open_event.current_value  = max_value
        open_event.severity       = severity
        open_event.message        = message
        open_event.save(update_fields=['last_seen_at', 'current_value', 'severity', 'message', 'updated_at'])
    else:
        # 신규 생성
        create_alarm_event(
            rule=rule,
            facility=device.facility,
            severity=severity,
            title=f"[가스] {gases_str} 농도 이상 감지",
            device=device,
            message=message,
            current_value=max_value,
        )


def check_power_thresholds(device, channel, power_w: float) -> None:
    """전력 부하율 임계치 체크 → AlarmEvent 생성 (5분 중복 방지)"""
    if not device.facility_id:
        return

    rated_w = float(channel.rated_power_w or 1000)
    if power_w <= 0 or rated_w <= 0:
        return

    load_rate = (power_w / rated_w) * 100

    if load_rate >= 75:
        severity = AlarmEvent.Severity.DANGER
    elif load_rate >= 50:
        severity = AlarmEvent.Severity.WARNING
    else:
        return

    rule = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.POWER,
        is_active=True,
    ).first()
    if not rule:
        return

    already = AlarmEvent.objects.filter(
        rule=rule,
        device=device,
        channel=channel,
        event_status=AlarmEvent.EventStatus.OPEN,
        occurred_at__gte=timezone.now() - timedelta(minutes=5),
    ).exists()
    if already:
        return

    create_alarm_event(
        rule=rule,
        facility=device.facility,
        severity=severity,
        title=f"[전력] {channel.channel_name or channel.channel_code} 부하율 {load_rate:.0f}% {_SEVERITY_LABEL[severity]}",
        device=device,
        channel=channel,
        message=f"현재 전력: {power_w}W, 부하율: {load_rate:.1f}%",
    )

def trigger_anomaly_alarms(device, zscore_results: list) -> None:
    """Z-score ANOMALY_WARNING 결과 → AlarmEvent 생성 (open 이벤트 있으면 갱신)."""
    if not device.facility_id:
        return

    anomalies = [r for r in zscore_results if r['final_status'] == 'ANOMALY_WARNING']
    if not anomalies:
        return

    rule = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.THRESHOLD,
        is_active=True,
    ).first()
    if not rule:
        return

    now = timezone.now()
    gases_str = ', '.join(r['metric'].upper() for r in anomalies)
    message   = ', '.join(
        f"{r['metric'].upper()}: {r['value']} (z={r['z_score']:.2f})"
        for r in anomalies
    )
    max_value = max(abs(r['z_score']) for r in anomalies)

    open_event = AlarmEvent.objects.filter(
        rule=rule,
        device=device,
        severity=AlarmEvent.Severity.ANOMALY,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if open_event:
        open_event.last_seen_at  = now
        open_event.current_value = max_value
        open_event.message       = message
        open_event.save(update_fields=['last_seen_at', 'current_value', 'message', 'updated_at'])
    else:
        create_alarm_event(
            rule=rule,
            facility=device.facility,
            severity=AlarmEvent.Severity.ANOMALY,
            title=f"[AI] {gases_str} 통계 이상 감지",
            device=device,
            message=message,
            current_value=max_value,
        )


def trigger_changepoint_alarms(device, cp_results: list) -> None:
    """
    Change Point 탐지 결과 → AlarmEvent 생성/종료.
    - CHANGE_POINT  : WARNING 이벤트 신규 생성
    - BACK_TO_STABLE: 해당 가스 open 이벤트 자동 종료
    - 이벤트 없는 경우 무시 (상태 유지 중인 SHIFT/STABLE은 처리 안 함)
    """
    if not device.facility_id:
        return

    rule = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.THRESHOLD,
        is_active=True,
    ).first()
    if not rule:
        return

    now = timezone.now()

    for r in cp_results:
        event = r.get('event')
        if event is None:
            continue

        gas = r['metric'].upper()

        open_event = AlarmEvent.objects.filter(
            rule=rule,
            device=device,
            severity=AlarmEvent.Severity.ANOMALY,
            event_status=AlarmEvent.EventStatus.OPEN,
            title__contains=f'[CP] {gas}',
        ).order_by('-occurred_at').first()

        if event == 'CHANGE_POINT':
            if open_event:
                open_event.last_seen_at  = now
                open_event.current_value = r['mean_shift_score']
                open_event.message = (
                    f"mean_shift={r['mean_shift_score']:.2f}, "
                    f"std_ratio={r['std_ratio']:.2f} | "
                    f"prev_mean={r['prev_mean']:.2f} → curr_mean={r['curr_mean']:.2f}"
                )
                open_event.save(update_fields=['last_seen_at', 'current_value', 'message', 'updated_at'])
            else:
                create_alarm_event(
                    rule=rule,
                    facility=device.facility,
                    severity=AlarmEvent.Severity.ANOMALY,
                    title=f"[CP] {gas} 상태 변화 감지",
                    device=device,
                    message=(
                        f"mean_shift={r['mean_shift_score']:.2f}, "
                        f"std_ratio={r['std_ratio']:.2f} | "
                        f"prev_mean={r['prev_mean']:.2f} → curr_mean={r['curr_mean']:.2f}"
                    ),
                    current_value=r['mean_shift_score'],
                )

        elif event == 'BACK_TO_STABLE':
            if open_event:
                open_event.event_status = AlarmEvent.EventStatus.CLOSED
                open_event.closed_at    = now
                open_event.save(update_fields=['event_status', 'closed_at', 'updated_at'])
                EventHistory.objects.create(
                    alarm_event=open_event,
                    action_type='close',
                    action_note=f'{gas} 상태 안정화로 자동 종료',
                )


def trigger_if_anomaly_alarms(device, if_result) -> None:
    """STEP F — Isolation Forest 9채널 분포 이상 결과 → AlarmEvent.

    전용 AlarmRule(RuleType.AI)로 생성하므로 STEP B/D/E(THRESHOLD rule)와
    이벤트가 완전히 분리된다.
    - CAUTION : open '[IF]' 이벤트 갱신 또는 신규 생성
    - NORMAL  : open '[IF]' 이벤트 자동 종료
    - UNKNOWN : 결측 — 판정 보류
    """
    if if_result is None or not device.facility_id:
        return

    level = if_result.level.name  # 'NORMAL' / 'CAUTION' / 'UNKNOWN'
    if level == 'UNKNOWN':
        return

    rule = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.AI,
        is_active=True,
    ).first()
    if not rule:
        return

    now = timezone.now()
    open_event = AlarmEvent.objects.filter(
        rule=rule,
        device=device,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if level == 'NORMAL':
        # 분포 정상 복귀 → open 이벤트 자동 종료
        if open_event:
            open_event.event_status = AlarmEvent.EventStatus.CLOSED
            open_event.closed_at = now
            open_event.save(update_fields=['event_status', 'closed_at', 'updated_at'])
            EventHistory.objects.create(
                alarm_event=open_event,
                action_type='close',
                action_note='IF 분포 정상 복귀로 자동 종료',
            )
        return

    # level == 'CAUTION'
    score   = if_result.mahalanobis_distance
    message = f"[IF] 가스 9채널 분포 이상 — {if_result.reason}"

    if open_event:
        open_event.last_seen_at  = now
        open_event.current_value = score
        open_event.message       = message
        open_event.save(update_fields=['last_seen_at', 'current_value', 'message', 'updated_at'])
    else:
        create_alarm_event(
            rule=rule,
            facility=device.facility,
            severity=AlarmEvent.Severity.ANOMALY,
            title="[IF] 가스 9채널 분포 이상 감지",
            device=device,
            message=message,
            current_value=score,
        )


def trigger_forecast_alarms(device, results, channel=None) -> None:
    """STEP G — ARIMA 예측 결과 → predictive_warning AlarmEvent (채널별).

    전용 AlarmRule(RuleType.FORECAST)로 생성 — STEP B/D/E/F와 이벤트 격리.
    채널별로 '[예측] {GAS}' 타이틀의 open 이벤트를 재사용한다.
    - CONFIRMED_WARNING / CONFIRMED_STRONG : open 이벤트 갱신 또는 신규 생성
    - NORMAL                               : open 이벤트 자동 종료
    - TENTATIVE / UNKNOWN                  : 보류 (잠정·워밍업 — 생성도 종료도 안 함)

    Phase D M1-2 (2026-05-23) — power 채널 지원:
        channel=None 시 gas 동작 그대로. power는 channel 명시.
        title 형식: [예측] {sensor}  (gas) → [예측·{channel_code}] {sensor} (power)
    """
    if not results or not device.facility_id:
        return

    rule = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.FORECAST,
        is_active=True,
    ).first()
    if not rule:
        return

    # gas/power 라벨 접두사 — channel 명시 시 power, 아니면 gas
    title_prefix = f"[예측·{channel.channel_code}]" if channel is not None else "[예측]"

    now = timezone.now()
    for r in results:
        ch = r.sensor_type.upper()
        conf = r.headline_confidence.name  # NORMAL/TENTATIVE/CONFIRMED_WARNING/CONFIRMED_STRONG/UNKNOWN

        open_event_filter = dict(
            rule=rule,
            device=device,
            event_status=AlarmEvent.EventStatus.OPEN,
            title__contains=f'{title_prefix} {ch}',
        )
        if channel is not None:
            open_event_filter['channel'] = channel
        open_event = AlarmEvent.objects.filter(**open_event_filter).order_by('-occurred_at').first()

        if conf in ('CONFIRMED_WARNING', 'CONFIRMED_STRONG'):
            eta = r.danger_eta_step if r.headline_severity == 'danger' else r.caution_eta_step
            message = (
                f"{title_prefix} {ch} {r.headline_severity or '주의'} 임계 도달 예상 "
                f"(ETA {eta}스텝) — {r.reason}"
            )
            if open_event:
                open_event.last_seen_at  = now
                open_event.current_value = eta
                open_event.message       = message
                open_event.save(update_fields=['last_seen_at', 'current_value', 'message', 'updated_at'])
            else:
                create_kwargs = dict(
                    rule=rule,
                    facility=device.facility,
                    severity=AlarmEvent.Severity.PREDICTIVE_WARNING,
                    title=f"{title_prefix} {ch} 사전 경고",
                    device=device,
                    message=message,
                    current_value=eta,
                )
                if channel is not None:
                    create_kwargs['channel'] = channel
                create_alarm_event(**create_kwargs)
        elif conf == 'NORMAL' and open_event:
            open_event.event_status = AlarmEvent.EventStatus.CLOSED
            open_event.closed_at = now
            open_event.save(update_fields=['event_status', 'closed_at', 'updated_at'])
            EventHistory.objects.create(
                alarm_event=open_event,
                action_type='close',
                action_note=f'{ch} 예측 정상 복귀로 자동 종료',
            )
        # TENTATIVE / UNKNOWN → 보류


def _json_safe(seq) -> list:
    """JSONField 저장용 — NaN/Inf를 None으로 변환한 float 리스트."""
    out = []
    for x in seq:
        try:
            fx = float(x)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(fx if math.isfinite(fx) else None)
    return out


def save_forecast_snapshots(device, results, channel=None) -> None:
    """STEP G — 채널별 최신 예측을 ForecastSnapshot에 upsert (등급 + 곡선).

    채널당 1행(unique device+channel+sensor_type)을 갱신 — 행 수 고정(디스크 무증가).
    'AI 예측' 탭은 이 최신 행을 조회해 점선 차트를 그린다. 워밍업 구간의
    UNKNOWN 결과도 그대로 저장돼 UI가 '예측 준비 중'을 표시할 수 있다.

    Phase D M1-2 (2026-05-23) — power 채널 지원:
        channel=None 시 gas 동작 그대로 (channel=NULL row).
        power는 channel 명시 — 채널별 row 생성.

    Args:
        results: [(ForecastPolicyResult, ARIMAResult|None), ...] — 등급 결과와
                 원시 예측 곡선. 곡선이 None이거나 path='unknown'이면 곡선
                 필드(forecast_mean·ci_*)는 None으로 저장된다.
        channel: DeviceChannel 인스턴스 (power) 또는 None (gas).
    """
    for policy, arima in results:
        has_curve = arima is not None and getattr(arima, 'path', 'unknown') != 'unknown'
        ForecastSnapshot.objects.update_or_create(
            device=device,
            channel=channel,
            sensor_type=policy.sensor_type,
            defaults={
                'headline_severity':   policy.headline_severity,
                'headline_confidence': policy.headline_confidence.name,
                'caution_confidence':  policy.caution_confidence.name,
                'danger_confidence':   policy.danger_confidence.name,
                'caution_eta_step':    policy.caution_eta_step,
                'danger_eta_step':     policy.danger_eta_step,
                'path':                policy.path,
                'forecast_steps':      policy.forecast_steps,
                'reason':              policy.reason,
                'forecast_mean': _json_safe(arima.forecast_mean) if has_curve else None,
                'ci_lower':      _json_safe(arima.ci_lower) if has_curve else None,
                'ci_upper':      _json_safe(arima.ci_upper) if has_curve else None,
            },
        )


_RULE_TYPE_TO_EVENT_TYPE = {
    AlarmRule.RuleType.THRESHOLD: AlarmEvent.EventType.GAS,
    AlarmRule.RuleType.POWER:     AlarmEvent.EventType.POWER,
    AlarmRule.RuleType.MISSING:   AlarmEvent.EventType.DEVICE,
    AlarmRule.RuleType.OFFLINE:   AlarmEvent.EventType.DEVICE,
    AlarmRule.RuleType.AI:        AlarmEvent.EventType.GAS,
    AlarmRule.RuleType.FORECAST:  AlarmEvent.EventType.GAS,
}


def create_alarm_event(
    rule: AlarmRule,
    facility,
    severity: AlarmEvent.Severity,
    title: str,
    device=None,
    worker=None,
    channel=None,
    message: str = "",
    current_value: float = None,
) -> AlarmEvent:
    event_type = _RULE_TYPE_TO_EVENT_TYPE.get(rule.rule_type, AlarmEvent.EventType.DEVICE)
    now = timezone.now()
    event = AlarmEvent.objects.create(
        rule=rule,
        facility=facility,
        device=device,
        worker=worker,
        channel=channel,
        event_type=event_type,
        event_status=AlarmEvent.EventStatus.OPEN,
        severity=severity,
        title=title,
        message=message,
        current_value=current_value,
        last_seen_at=now,
    )
    from .tasks import send_all_notifications
    send_all_notifications.delay(event.id)
    return event


def get_base_qs():
    return (
        AlarmEvent.objects
        .select_related('facility', 'device', 'worker', 'acknowledged_by', 'rule')
        .order_by('-occurred_at')
    )


def get_status_counts() -> dict:
    qs = AlarmEvent.objects.values('event_status').annotate(cnt=Count('id'))
    counts = {'open': 0, 'acknowledged': 0, 'closed': 0}
    for row in qs:
        if row['event_status'] in counts:
            counts[row['event_status']] = row['cnt']
    return counts


def get_event_list(status_filter: str = ''):
    qs = get_base_qs()
    if status_filter:
        qs = qs.filter(event_status=status_filter)
    return qs

# main 화면 - 10. 이벤트 현황 구현시 사용함수
def get_recent_events(hours: int = 24):
    since = timezone.now() - timedelta(hours=hours)
    return (
        get_base_qs()
        .filter(occurred_at__gte=since)
        .order_by('-occurred_at', 'severity')
    )

# main 화면 - 10. 이벤트 현황 구현시 사용함수
def get_event_summary_24h() -> dict:
    since = timezone.now() - timedelta(hours=24)
    qs = (
        AlarmEvent.objects
        .filter(occurred_at__gte=since)
        .values('severity')
        .annotate(cnt=Count('id'))
    )
    summary = {'danger': 0, 'warning': 0}
    for row in qs:
        if row['severity'] in summary:
            summary[row['severity']] = row['cnt']
    return summary


def get_event_detail(pk: int):
    return get_base_qs().get(pk=pk)


def get_event_histories(event, limit: int = 20):
    return event.histories.select_related('action_by').order_by('-action_at')[:limit]


ALLOWED_TRANSITIONS = {
    'open':         ['acknowledged', 'closed'],
    'acknowledged': ['closed', 'open'],
    'closed':       ['open', 'acknowledged'],
}


def change_event_status(event: AlarmEvent, new_status: str, user=None, action_note: str = '') -> str:
    """
    상태 변경 후 EventHistory 생성.
    허용되지 않는 전환이면 ValueError 발생.
    """
    allowed = ALLOWED_TRANSITIONS.get(event.event_status, [])
    if new_status not in allowed:
        raise ValueError(f"'{event.event_status}' → '{new_status}' 전환은 허용되지 않습니다.")

    event.event_status = new_status
    now = timezone.now()

    if new_status == 'acknowledged':
        event.acknowledged_by = user
        event.acknowledged_at = now
    elif new_status == 'closed':
        event.closed_at = now
    elif new_status == 'open':
        event.closed_at = None

    event.save(update_fields=[
        'event_status', 'acknowledged_by', 'acknowledged_at', 'closed_at', 'updated_at',
    ])

    action_map = {'acknowledged': 'acknowledge', 'closed': 'close', 'open': 'reopen'}
    EventHistory.objects.create(
        alarm_event=event,
        action_type=action_map[new_status],
        action_by=user,
        action_note=action_note,
    )

    return new_status
