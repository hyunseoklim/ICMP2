import calendar
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import SafetyCheckItem, SafetyCheckItemResult, SafetyCheckSession


def _get_worker(request):
    try:
        return request.user.worker
    except Exception:
        return None


def _build_calendar(sessions_qs, year, month):
    session_map = {}
    for s in sessions_qs.filter(check_date__year=year, check_date__month=month):
        session_map[s.check_date] = s

    cal = calendar.monthcalendar(year, month)
    weeks = []
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append({"day": None, "status": None, "checklist": None, "vr": None})
            else:
                d = date(year, month, day)
                s = session_map.get(d)
                cell = {"day": day, "date": d, "checklist": None, "vr": None, "status": None}
                if s:
                    cell["checklist"] = s.checklist_completed
                    cell["vr"] = s.vr_completed
                    if s.checklist_completed and s.vr_completed:
                        cell["status"] = "complete"
                    elif s.checklist_completed or s.vr_completed:
                        cell["status"] = "partial"
                    else:
                        cell["status"] = "incomplete"
                row.append(cell)
        weeks.append(row)
    return weeks


@login_required(login_url="login")
def mysafety_detail(request):
    worker = _get_worker(request)
    today = timezone.localdate()

    if worker is None:
        return render(request, "safety/mysafety_detail.html", {"no_worker": True})

    session = SafetyCheckSession.objects.filter(worker=worker, check_date=today).first()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "submit_checklist":
            if session and session.checklist_completed:
                return JsonResponse({"ok": False, "error": "이미 오늘 체크리스트를 완료하였습니다."})

            items = SafetyCheckItem.objects.filter(is_active=True)
            checked_ids = set(map(int, request.POST.getlist("checked_items")))

            if not session:
                from facilities.models import Facility
                facility = Facility.objects.first()
                session = SafetyCheckSession.objects.create(
                    worker=worker,
                    facility=facility,
                    check_date=today,
                )

            SafetyCheckItemResult.objects.filter(session=session).delete()
            SafetyCheckItemResult.objects.bulk_create([
                SafetyCheckItemResult(session=session, item=item, is_checked=(item.pk in checked_ids))
                for item in items
            ])

            all_checked = len(checked_ids) == items.count()
            session.checklist_completed = all_checked
            session.checklist_completed_at = timezone.now() if all_checked else None
            session.save()

            from django.urls import reverse
            return JsonResponse({"ok": True, "redirect": reverse("mysafety_vr")})

        return JsonResponse({"ok": False, "error": "잘못된 요청"}, status=400)

    items = SafetyCheckItem.objects.filter(is_active=True)
    categories = {}
    for item in items:
        categories.setdefault(item.category, {"order": item.category_order, "items": []})
        categories[item.category]["items"].append(item)
    categories_list = sorted(categories.items(), key=lambda x: x[1]["order"])

    checked_ids = set()
    if session:
        checked_ids = set(
            SafetyCheckItemResult.objects.filter(session=session, is_checked=True).values_list("item_id", flat=True)
        )

    return render(request, "safety/mysafety_detail.html", {
        "categories_list": categories_list,
        "items_count": items.count(),
        "session": session,
        "checked_ids": checked_ids,
        "today": today,
    })


@login_required(login_url="login")
def mysafety_vr(request):
    worker = _get_worker(request)
    if worker is None:
        return redirect("mysafety_detail")

    today = timezone.localdate()
    session = SafetyCheckSession.objects.filter(worker=worker, check_date=today).first()

    if session is None or not session.checklist_completed:
        return redirect("mysafety_detail")

    if request.method == "POST" and request.POST.get("action") == "vr_complete":
        session.vr_completed = True
        session.vr_completed_at = timezone.now()
        session.save()
        return JsonResponse({"ok": True})

    return render(request, "safety/mysafety_vr.html", {
        "session": session,
        "today": today,
    })


@login_required(login_url="login")
def mysafety_history(request):
    worker = _get_worker(request)
    if worker is None:
        return render(request, "safety/mysafety_history.html", {"no_worker": True})

    today = date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

    sessions_qs = SafetyCheckSession.objects.filter(worker=worker)
    weeks = _build_calendar(sessions_qs, year, month)

    prev_month_date = date(year, month, 1) - timedelta(days=1)
    next_month_date = (date(year, month, 28) + timedelta(days=4)).replace(day=1)

    # 관리자용: 전체 근무자 + 오늘 출근 여부
    admin_workers = []
    departments = []
    if request.user.is_staff:
        from facilities.models import Worker
        dept_q = request.GET.get("dept", "")
        name_q = request.GET.get("q", "")
        qs = Worker.objects.filter(status="active").select_related("user")
        if dept_q:
            qs = qs.filter(department=dept_q)
        if name_q:
            qs = qs.filter(worker_name__icontains=name_q)
        today_sessions = {
            s.worker_id: s
            for s in SafetyCheckSession.objects.filter(check_date=today)
        }
        for w in qs:
            s = today_sessions.get(w.pk)
            admin_workers.append({
                "worker": w,
                "attendance": "출근" if s and s.checklist_completed else "미출근",
                "attendance_ok": bool(s and s.checklist_completed),
            })
        departments = list(
            Worker.objects.filter(status="active")
            .exclude(department="")
            .values_list("department", flat=True)
            .distinct()
            .order_by("department")
        )

    return render(request, "safety/mysafety_history.html", {
        "weeks": weeks,
        "year": year,
        "month": month,
        "month_label": f"{year}년 {month}월",
        "prev_year": prev_month_date.year,
        "prev_month": prev_month_date.month,
        "next_year": next_month_date.year,
        "next_month": next_month_date.month,
        "today": today,
        "worker": worker,
        "admin_workers": admin_workers,
        "departments": departments,
        "dept_q": request.GET.get("dept", ""),
        "name_q": request.GET.get("q", ""),
    })


@login_required(login_url="login")
def mysafety_worker_calendar(request, worker_id):
    if not request.user.is_staff:
        return JsonResponse({"error": "권한 없음"}, status=403)
    from facilities.models import Worker
    worker = get_object_or_404(Worker, pk=worker_id)
    year = int(request.GET.get("year", date.today().year))
    month = int(request.GET.get("month", date.today().month))
    sessions_qs = SafetyCheckSession.objects.filter(worker=worker)
    weeks = _build_calendar(sessions_qs, year, month)

    prev_month_date = date(year, month, 1) - timedelta(days=1)
    next_month_date = (date(year, month, 28) + timedelta(days=4)).replace(day=1)

    today = date.today()
    weeks_data = []
    for week in weeks:
        row = []
        for cell in week:
            d = cell.get("date")
            row.append({
                "day": cell["day"],
                "date": d.isoformat() if d else None,
                "checklist": cell["checklist"],
                "vr": cell["vr"],
                "status": cell["status"],
                "is_today": d == today if d else False,
            })
        weeks_data.append(row)

    return JsonResponse({
        "worker_name": worker.worker_name,
        "month_label": f"{year}년 {month}월",
        "year": year,
        "month": month,
        "prev_year": prev_month_date.year,
        "prev_month": prev_month_date.month,
        "next_year": next_month_date.year,
        "next_month": next_month_date.month,
        "weeks": weeks_data,
    })


@login_required(login_url="login")
def mysafety_history_download(request):
    import io
    import openpyxl
    from django.http import HttpResponse as DjangoHttpResponse

    try:
        start_date = date.fromisoformat(request.GET.get("start", ""))
        end_date = date.fromisoformat(request.GET.get("end", ""))
    except ValueError:
        return DjangoHttpResponse("날짜 형식 오류", status=400)

    # 관리자가 다수 작업자 선택한 경우
    worker_ids_str = request.GET.get("workers", "")
    if worker_ids_str and request.user.is_staff:
        from facilities.models import Worker as FacWorker
        try:
            worker_ids = [int(i) for i in worker_ids_str.split(",") if i.strip()]
        except ValueError:
            return DjangoHttpResponse("잘못된 worker id", status=400)
        target_workers = list(FacWorker.objects.filter(pk__in=worker_ids))
    else:
        w = _get_worker(request)
        if w is None:
            return DjangoHttpResponse("근무자 정보 없음", status=400)
        target_workers = [w]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "안전확인 이력"
    ws.append(["작업자명", "날짜", "안전 체크리스트", "체크리스트 완료 시각", "VR 교육", "VR 완료 시각"])

    for worker in target_workers:
        sessions = {
            s.check_date: s
            for s in SafetyCheckSession.objects.filter(
                worker=worker, check_date__range=(start_date, end_date)
            )
        }
        name = worker.worker_name
        cur = start_date
        while cur <= end_date:
            s = sessions.get(cur)
            ws.append([
                name,
                cur.strftime("%Y-%m-%d"),
                "완료" if s and s.checklist_completed else "미완료",
                s.checklist_completed_at.strftime("%H:%M") if s and s.checklist_completed_at else "-",
                "완료" if s and s.vr_completed else "미완료",
                s.vr_completed_at.strftime("%H:%M") if s and s.vr_completed_at else "-",
            ])
            cur += timedelta(days=1)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"안전확인이력_{start_date}_{end_date}.xlsx"
    resp = DjangoHttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename*=UTF-8\'\'{filename}'
    return resp

