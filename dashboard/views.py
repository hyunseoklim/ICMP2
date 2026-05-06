from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Q


@login_required(login_url="login")
def dashboard_view(request):
    today_session = None
    try:
        from safety.models import SafetyCheckSession
        worker = request.user.worker
        today_session = SafetyCheckSession.objects.filter(
            worker=worker, check_date=timezone.localdate()
        ).first()
    except Exception:
        pass

    from alerts.services import get_recent_events

    current_worker_id   = None
    current_worker_name = None
    safety_done         = False
    vr_done             = False # vr 교육 때문에 추가 safety_done에서 안전 체크리스트를 확인한다고 가정

    try:
        worker = request.user.worker
        current_worker_id   = worker.id
        current_worker_name = worker.worker_name

        # 작업자 현재 위치 기반 facility 조회
        # mine=true 필터와 동일하게 본인 이벤트 + 위치한 층의 facility 이벤트 포함
        latest_location = worker.locations.select_related('floor__building__facility').first()

        if latest_location and latest_location.floor:
            facility = latest_location.floor.building.facility
            qs = get_recent_events(hours=24).filter(
                Q(worker=worker) | Q(facility=facility)
            )
        else:
            # 위치 정보 없으면 본인 이벤트만 카운트
            qs = get_recent_events(hours=24).filter(worker=worker)

        event_summary = {
            'danger':  qs.filter(severity='danger').count(),
            'warning': qs.filter(severity='warning').count(),
        }
        recent_events = qs[:20]
        if today_session:
            safety_done = today_session.checklist_completed
            vr_done     = today_session.vr_completed
    except Exception:
        recent_events = []
        event_summary = {'danger': 0, 'warning': 0}

    return render(request, "dashboard.html", {
        "today_session":       today_session,
        "recent_events":       recent_events,
        "event_summary":       event_summary,
        "current_worker_id":   current_worker_id,
        "current_worker_name": current_worker_name,
        "safety_done":         safety_done,
        "vr_done":             vr_done,
    })