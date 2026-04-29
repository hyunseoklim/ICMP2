from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import AlarmEvent, AlarmRule, EventHistory

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
) -> AlarmEvent:
    event_type = _RULE_TYPE_TO_EVENT_TYPE.get(rule.rule_type, AlarmEvent.EventType.DEVICE)
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
