from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone


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
    vr_done             = False #vr 교육 때문에 추가 safety_done에서 안전 체크리스트를 확인한다고 가정 


    try:
        worker = request.user.worker
        current_worker_id   = worker.id
        current_worker_name = worker.worker_name
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
        "today_session":      today_session,
        "recent_events":      recent_events,
        "event_summary":      event_summary,
        "current_worker_id":  current_worker_id,
        "current_worker_name": current_worker_name,
        "safety_done":        safety_done,
        "vr_done":             vr_done,
    })
