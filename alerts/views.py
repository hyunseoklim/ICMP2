from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import AlarmEvent, EventHistory
from .serializers import AlarmEventSerializer
from .services import (
    get_event_list,
    get_event_detail,
    get_event_histories,
    get_status_counts,
    change_event_status,
    ALLOWED_TRANSITIONS,
    get_base_qs,
)


# ─── 이벤트 목록 ─────────────────────────────────────────────────────────────

def event_list(request):
    status_filter = request.GET.get('status', '')
    events = get_event_list(status_filter)[:20]
    counts = get_status_counts()

    return render(request, 'events/event_list.html', {
        'events':        events,
        'open_count':    counts['open'],
        'ack_count':     counts['acknowledged'],
        'closed_count':  counts['closed'],
        'total_count':   sum(counts.values()),
        'status_filter': status_filter,
    })


# ─── 이벤트 상세 ─────────────────────────────────────────────────────────────

def event_detail(request, pk):
    event = get_object_or_404(get_base_qs(), pk=pk)
    histories = get_event_histories(event)

    next_statuses = ALLOWED_TRANSITIONS.get(event.event_status, [])
    default_target = next_statuses[0] if next_statuses else ''

    return render(request, 'events/event_detail.html', {
        'event':          event,
        'histories':      histories,
        'next_statuses':  next_statuses,
        'default_target': default_target,
    })


# ─── 조치 상태 변경 POST ─────────────────────────────────────────────────────

@require_POST
def change_event_status_view(request, pk):
    event = get_object_or_404(AlarmEvent, pk=pk)
    new_status  = request.POST.get('status', '')
    action_note = request.POST.get('action_note', '').strip()
    user = request.user if request.user.is_authenticated else None

    try:
        change_event_status(event, new_status, user, action_note)
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({
        'status':     'ok',
        'new_status': new_status,
    })


# ─── 이벤트 API (DRF) ────────────────────────────────────────────────────────

class AlarmEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AlarmEventSerializer

    def get_queryset(self):
        return get_event_list(self.request.GET.get('status', ''))

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data['counts'] = get_status_counts()
        return response


# ─── 최근 알람 API (대시보드 폴링용) ─────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def recent_alarms(request):
    """
    GET /alerts/api/recent/
    대시보드에서 5초마다 폴링 — 최근 5분 내 open 알람 반환
    """
    minutes = int(request.GET.get('minutes', 5))
    limit   = int(request.GET.get('limit', 20))

    qs = AlarmEvent.objects.filter(
        occurred_at__gte=timezone.now() - timedelta(minutes=minutes),
        event_status='open'
    ).select_related('device', 'facility', 'worker')

    # ?mine=true 이면 로그인 유저의 worker 에 연결된 이벤트만
    if request.GET.get('mine') == 'true' and request.user.is_authenticated:
        try:
            qs = qs.filter(worker=request.user.worker)
        except Exception:
            qs = qs.none()

    recent = qs.order_by('-occurred_at')[:limit]

    return Response([{
        'id':          e.id,
        'title':       e.title,
        'severity':    e.severity,
        'event_type':  e.event_type,
        'device':      e.device.device_uid if e.device else None,
        'facility':    e.facility.facility_name if e.facility else None,
        'message':     e.message,
        'occurred_at': e.occurred_at.isoformat(),
    } for e in recent])


# ─── 조치 이력 ───────────────────────────────────────────────────────────────

def action_history(request):
    histories = (
        EventHistory.objects
        .select_related('alarm_event', 'action_by')
        .order_by('-action_at')
    )
    date_from          = request.GET.get('date_from', '')
    date_to            = request.GET.get('date_to', '')
    action_type_filter = request.GET.get('action_type', '')

    if date_from:
        histories = histories.filter(action_at__date__gte=date_from)
    if date_to:
        histories = histories.filter(action_at__date__lte=date_to)
    if action_type_filter:
        histories = histories.filter(action_type=action_type_filter)

    return render(request, 'alerts/action_history.html', {
        'histories':           histories,
        'action_type_choices': EventHistory.ActionType.choices,
        'date_from':           date_from,
        'date_to':             date_to,
        'action_type_filter':  action_type_filter,
    })