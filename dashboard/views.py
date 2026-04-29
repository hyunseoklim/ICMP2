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

    return render(request, "dashboard.html", {"today_session": today_session})
