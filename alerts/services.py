from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import AlarmEvent, AlarmRule, EventHistory

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


def check_power_zscore_alarms(device, channel, zs_result: dict) -> None:
    """전력 Z-score ANOMALY_WARNING → AlarmEvent 생성/갱신. 정상 복귀 시 자동 closed."""
    if not device.facility_id:
        return
    if not zs_result:
        return

    final_status = zs_result.get('final_status', 'NORMAL')

    rule = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.POWER,
        is_active=True,
    ).first()
    if not rule:
        return

    now = timezone.now()
    open_event = AlarmEvent.objects.filter(
        rule=rule,
        device=device,
        channel=channel,
        severity=AlarmEvent.Severity.ANOMALY,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if final_status not in ('ANOMALY_WARNING',):
        if open_event:
            open_event.event_status = AlarmEvent.EventStatus.CLOSED
            open_event.closed_at = now
            open_event.save(update_fields=['event_status', 'closed_at', 'updated_at'])
            EventHistory.objects.create(
                alarm_event=open_event,
                action_type='close',
                action_note='전력 부하율 통계 정상 복귀로 자동 종료',
            )
        return

    z     = zs_result.get('z_score')
    mean  = zs_result.get('mean')
    value = zs_result.get('value')
    ch_label = channel.channel_name or channel.channel_code
    message  = f"부하율: {value}% (평균: {mean}%, z={z:.2f})" if z is not None else f"부하율: {value}%"

    if open_event:
        open_event.last_seen_at  = now
        open_event.current_value = value
        open_event.message       = message
        open_event.save(update_fields=['last_seen_at', 'current_value', 'message', 'updated_at'])
    else:
        create_alarm_event(
            rule=rule,
            facility=device.facility,
            severity=AlarmEvent.Severity.ANOMALY,
            title=f"[전력 AI] {ch_label} 부하율 통계 이상",
            device=device,
            channel=channel,
            message=message,
            current_value=value,
        )


def check_power_thresholds(device, channel, power_w: float) -> None:
    """전력 부하율 임계치 체크 → open 이벤트 갱신 또는 신규 생성. 정상 복귀 시 자동 closed."""
    if not device.facility_id:
        return

    rated_w = float(channel.rated_power_w or 1000)
    if rated_w <= 0:
        return

    rule = AlarmRule.objects.filter(
        rule_type=AlarmRule.RuleType.POWER,
        is_active=True,
    ).first()
    if not rule:
        return

    load_rate = (power_w / rated_w) * 100 if power_w > 0 else 0
    now = timezone.now()

    open_event = AlarmEvent.objects.filter(
        rule=rule,
        device=device,
        channel=channel,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if load_rate < 50:
        # 정상 복귀 → open 이벤트 자동 closed
        if open_event:
            open_event.event_status = AlarmEvent.EventStatus.CLOSED
            open_event.closed_at = now
            open_event.save(update_fields=['event_status', 'closed_at', 'updated_at'])
            EventHistory.objects.create(
                alarm_event=open_event,
                action_type='close',
                action_note='부하율 정상 복귀로 자동 종료',
            )
        return

    severity = AlarmEvent.Severity.DANGER if load_rate >= 75 else AlarmEvent.Severity.WARNING
    channel_label = channel.channel_name or channel.channel_code
    message = f"현재 전력: {power_w}W, 부하율: {load_rate:.1f}%"

    if open_event:
        # 기존 open 이벤트 갱신
        open_event.last_seen_at  = now
        open_event.current_value = load_rate
        open_event.severity      = severity
        open_event.message       = message
        open_event.save(update_fields=['last_seen_at', 'current_value', 'severity', 'message', 'updated_at'])
    else:
        create_alarm_event(
            rule=rule,
            facility=device.facility,
            severity=severity,
            title=f"[전력] {channel_label} 부하율 {load_rate:.0f}% {_SEVERITY_LABEL[severity]}",
            device=device,
            channel=channel,
            message=message,
            current_value=load_rate,
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
    """Change Point 결과 → AlarmEvent 생성/갱신."""
    if not device.facility_id:
        return
    anomalies = [r for r in cp_results if r.get('final_status', '').startswith('CHANGE_POINT')]
    if not anomalies:
        return

    rule = AlarmRule.objects.filter(rule_type=AlarmRule.RuleType.THRESHOLD, is_active=True).first()
    if not rule:
        return

    now = timezone.now()
    gases_str = ', '.join(r['metric'].upper() for r in anomalies)
    message   = ', '.join(
        f"{r['metric'].upper()}: shift={r['mean_shift_score']:.2f}"
        for r in anomalies
    )
    max_score = max(r['mean_shift_score'] for r in anomalies)

    open_event = AlarmEvent.objects.filter(
        rule=rule, device=device,
        severity=AlarmEvent.Severity.ANOMALY,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if open_event:
        open_event.last_seen_at  = now
        open_event.current_value = max_score
        open_event.message       = message
        open_event.save(update_fields=['last_seen_at', 'current_value', 'message', 'updated_at'])
    else:
        create_alarm_event(
            rule=rule, facility=device.facility,
            severity=AlarmEvent.Severity.ANOMALY,
            title=f"[AI] {gases_str} 변화점 감지",
            device=device, message=message, current_value=max_score,
        )


def trigger_power_changepoint_alarms(device, channel, cp_result: dict) -> None:
    """전력 Change Point 결과 → AlarmEvent 생성/갱신."""
    if not device.facility_id:
        return
    status = cp_result.get('final_status', 'NORMAL')
    if not status.startswith('CHANGE_POINT'):
        return

    rule = AlarmRule.objects.filter(rule_type=AlarmRule.RuleType.THRESHOLD, is_active=True).first()
    if not rule:
        return

    now = timezone.now()
    ch_name = channel.channel_name or channel.channel_code
    score   = cp_result.get('mean_shift_score') or cp_result.get('std_ratio') or 0
    message = (
        f"{ch_name}: shift={cp_result.get('mean_shift_score', 0):.2f}, "
        f"std_ratio={cp_result.get('std_ratio', 0):.2f}, "
        f"direction={cp_result.get('direction', '-')}"
    )

    open_event = AlarmEvent.objects.filter(
        rule=rule, device=device,
        severity=AlarmEvent.Severity.ANOMALY,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if open_event:
        open_event.last_seen_at  = now
        open_event.current_value = score
        open_event.message       = message
        open_event.save(update_fields=['last_seen_at', 'current_value', 'message', 'updated_at'])
    else:
        create_alarm_event(
            rule=rule, facility=device.facility,
            severity=AlarmEvent.Severity.ANOMALY,
            title=f"[AI] 전력 변화점 감지 — {ch_name}",
            device=device, message=message, current_value=score,
        )


def trigger_isolation_alarm(device, iso_result: dict) -> None:
    """Isolation Forest 이상 결과 → AlarmEvent 생성/갱신."""
    if not device.facility_id or not iso_result.get('is_anomaly'):
        return

    rule = AlarmRule.objects.filter(rule_type=AlarmRule.RuleType.THRESHOLD, is_active=True).first()
    if not rule:
        return

    now   = timezone.now()
    score = iso_result.get('score', 0)
    message = f"다변량 이상 감지 (score={score:.4f})"

    open_event = AlarmEvent.objects.filter(
        rule=rule, device=device,
        severity=AlarmEvent.Severity.ANOMALY,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if open_event:
        open_event.last_seen_at  = now
        open_event.current_value = abs(score)
        open_event.message       = message
        open_event.save(update_fields=['last_seen_at', 'current_value', 'message', 'updated_at'])
    else:
        create_alarm_event(
            rule=rule, facility=device.facility,
            severity=AlarmEvent.Severity.ANOMALY,
            title="[AI] 복합 가스 이상 패턴 감지",
            device=device, message=message, current_value=abs(score),
        )


def trigger_arima_alarms(device, arima_results: list) -> None:
    """ARIMA 예측 결과 → PREDICTIVE_WARNING AlarmEvent 생성/갱신."""
    if not device.facility_id or not arima_results:
        return

    rule = AlarmRule.objects.filter(rule_type=AlarmRule.RuleType.THRESHOLD, is_active=True).first()
    if not rule:
        return

    now = timezone.now()
    gases_str = ', '.join(r['metric'].upper() for r in arima_results)
    message   = ', '.join(
        f"{r['metric'].upper()} {r['first_exceed_step']}분 후 초과 예측"
        for r in arima_results
    )

    open_event = AlarmEvent.objects.filter(
        rule=rule, device=device,
        severity=AlarmEvent.Severity.PREDICTIVE_WARNING,
        event_status=AlarmEvent.EventStatus.OPEN,
    ).order_by('-occurred_at').first()

    if open_event:
        open_event.last_seen_at = now
        open_event.message      = message
        open_event.save(update_fields=['last_seen_at', 'message', 'updated_at'])
    else:
        create_alarm_event(
            rule=rule, facility=device.facility,
            severity=AlarmEvent.Severity.PREDICTIVE_WARNING,
            title=f"[AI] {gases_str} 위험 임박 예측",
            device=device, message=message,
        )


_RULE_TYPE_TO_EVENT_TYPE = {
    AlarmRule.RuleType.THRESHOLD: AlarmEvent.EventType.GAS,
    AlarmRule.RuleType.POWER:     AlarmEvent.EventType.POWER,
    AlarmRule.RuleType.MISSING:   AlarmEvent.EventType.DEVICE,
    AlarmRule.RuleType.OFFLINE:   AlarmEvent.EventType.DEVICE,
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
    return AlarmEvent.objects.create(
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
