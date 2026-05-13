import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models as db_models
from django.db.models import Count, Q
from django.http import JsonResponse, FileResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, ListView, UpdateView, DeleteView

from .mixins import AdminRequiredMixin, ManagerRequiredMixin, RoleRequiredMixin, DepartmentScopeMixin
from .models import Notice, NoticeAttachment, AlarmPolicy, AlarmSendHistory, VREducation, ChecklistSnapshot


# class DashboardView(ManagerRequiredMixin, TemplateView):
#     """
#     관리자 공통 대시보드
#     - 슈퍼유저: 전체 통계
#     - 스태프: 본인 담당 데이터만
#     """
#     template_name = "/dashboard.html"

#     def get_context_data(self, **kwargs):
#         ctx = super().get_context_data(**kwargs)
#         user = self.request.user

#         # 슈퍼유저 vs 스태프 분기 — 뷰 레이어에서 한 번만 처리
#         if user.user_type:
#             ctx["stats"] = self._admin_stats()
#         else:
#             ctx["stats"] = self._manager_stats(user)

#         ctx["is_admin"] = user.is_superuser
#         return ctx

#     def _admin_stats(self):
#         """슈퍼유저용 전체 통계 — 실제 모델로 교체하세요"""
#         return {
#             "total_users": User.objects.count(),
#             "staff_count": User.objects.filter(is_staff=True).count(),
#             "active_users": User.objects.filter(is_active=True).count(),
#             "new_users_this_week": User.objects.filter(
#                 date_joined__gte=timezone.now() - timedelta(days=7)
#             ).count(),
#         }

#     def _manager_stats(self, user):
#         """스태프용 본인 담당 통계 — 실제 모델로 교체하세요"""
#         return {
#             "my_items": 0,      # 예: MyModel.objects.filter(assigned_to=user).count()
#             "pending": 0,       # 예: MyModel.objects.filter(assigned_to=user, status='pending').count()
#             "completed": 0,
#         }


# # =============================================
# # 유저 관리 (슈퍼유저 전용 예시)
# # =============================================

# class UserListView(SuperuserRequiredMixin, ListView):
#     """
#     전체 유저 목록 — 슈퍼유저 전용
#     """
#     model = User
#     template_name = "management/user_list.html"
#     context_object_name = "users"
#     paginate_by = 20

#     def get_queryset(self):
#         qs = User.objects.order_by("-date_joined")
#         q = self.request.GET.get("q", "").strip()
#         if q:
#             qs = qs.filter(
#                 Q(username__icontains=q) |
#                 Q(email__icontains=q) |
#                 Q(first_name__icontains=q) |
#                 Q(last_name__icontains=q)
#             )
#         return qs

#     def get_context_data(self, **kwargs):
#         ctx = super().get_context_data(**kwargs)
#         ctx["q"] = self.request.GET.get("q", "")
#         return ctx


# # =============================================
# # 권한별 데이터 뷰 예시 (실제 모델로 교체)
# # =============================================

# class ManagedItemListView(PermissionMixin, ListView):
#     """
#     권한 코드 기반 데이터 뷰 예시
#     - 슈퍼유저: 전체 조회
#     - 스태프: 본인 담당만 조회
    
#     실제 사용 시 model = YourModel 로 교체하세요.
#     """
#     model = User  # TODO: 실제 모델로 교체
#     template_name = "management/item_list.html"
#     context_object_name = "items"
#     paginate_by = 20
#     permission_required = None  # 예: 'myapp.can_view_items'

#     def get_queryset(self):
#         qs = super().get_queryset()
#         user = self.request.user

#         # 슈퍼유저는 전체, 스태프는 본인 담당만
#         if not user.is_superuser:
#             # TODO: 실제 필드명으로 교체
#             # qs = qs.filter(assigned_to=user)
#             pass

#         return qs
    

    
def user_list(request):
    """사용자 관리 메인 페이지"""
    return render(request, 'admin/users/user_list.html', {'active_menu': 'account'})

def user_create(request):
    """사용자 등록 모달"""
    return render(request, 'admin/users/user_create.html', {'active_menu': 'account'})

def user_create_error(request):
    """사용자 등록 - 유효성 에러"""
    return render(request, 'admin/users/user_create_error.html', {'active_menu': 'account'})

def user_detail(request):
    """사용자 정보 조회"""
    return render(request, 'admin/users/user_detail.html', {'active_menu': 'account'})

def user_edit(request):
    """사용자 정보 수정"""
    return render(request, 'admin/users/user_edit.html', {'active_menu': 'account'})

def logout_complete(request):
    """로그아웃 완료"""
    return render(request, 'admin/users/logout_complete.html', {'active_menu': 'account'})

def user_list_filter(request):
    """필터 펼친 상태"""
    return render(request, 'admin/users/user_list_filter_open.html', {'active_menu': 'account'})

# ===== 직위 관리 =====
def position_list(request):
    """직위 관리 메인 페이지"""
    return render(request, 'admin/positions/position_list.html', {'active_menu': 'account'})

def position_create(request):
    """직위 등록 모달"""
    return render(request, 'admin/positions/position_create.html', {'active_menu': 'account'})

def position_edit(request, pk=0):
    """직위 수정 모달"""
    return render(request, 'admin/positions/position_edit.html', {'active_menu': 'account', 'pk': pk})


# ===== 조직 관리 =====
def org_list(request):
    """조직 관리 메인 페이지"""
    return render(request, 'admin/organizations/org_list.html', {'active_menu': 'account'})

def org_member_select(request):
    """구성원 선택 모달"""
    return render(request, 'admin/organizations/org_member_select.html', {'active_menu': 'account'})

def org_dept_move(request):
    """부서 이동 모달"""
    return render(request, 'admin/organizations/org_dept_move.html', {'active_menu': 'account'})

def org_confirm(request):
    """재확인 모달"""
    return render(request, 'admin/organizations/org_confirm.html', {'active_menu': 'account'})

# ===== 공통 코드 관리 =====
def code_list(request):
    """공통 코드 관리 메인 페이지"""
    return render(request, 'admin/codes/code_list.html', {'active_menu': 'reference'})

def code_group_create(request):
    """코드 그룹 등록 모달"""
    return render(request, 'admin/codes/code_group_create.html')

def code_group_edit(request):
    """코드 그룹 수정 모달"""
    return render(request, 'admin/codes/code_group_edit.html')

def code_value_create(request):
    """공통 코드 등록 모달"""
    return render(request, 'admin/codes/code_value_create.html')

def code_value_edit(request):
    """공통 코드 수정 모달"""
    return render(request, 'admin/codes/code_value_edit.html')

# ===== 위험 유형 관리 =====
def risk_list(request):
    """위험 유형 관리 메인 페이지"""
    return render(request, 'admin/risks/risk_list.html', {'active_menu': 'reference'})

def risk_create(request):
    """위험 유형 코드 등록 모달"""
    return render(request, 'admin/risks/risk_create.html')

def risk_edit(request):
    """위험 유형 코드 수정 모달"""
    return render(request, 'admin/risks/risk_edit.html')

def risk_group_create(request):
    """분류 그룹 등록 모달"""
    return render(request, 'admin/risks/risk_group_create.html')

def risk_group_edit(request):
    """분류 그룹 수정 모달"""
    return render(request, 'admin/risks/risk_group_edit.html')

# ===== 위험 기준 관리 =====
def risk_criteria_list(request):
    """위험 기준 관리 - 메인 + 등록/수정 모달 통합"""
    return render(request, 'admin/risk_criteria/risk_criteria_list.html', {'active_menu': 'reference'})

# ===== 임계치 기준 관리 =====
def threshold_list(request):
    """임계치 기준 관리 메인 페이지 (모든 모달 포함)"""
    return render(request, 'admin/thresholds/threshold_list.html', {'active_menu': 'reference'})

# ===== 안전 확인 관리 =====
def safety_checklist_list(request):
    from safety.models import SafetyCheckItem
    from itertools import groupby

    items = SafetyCheckItem.objects.filter(is_active=True).order_by('category_order', 'item_order')

    sections = []
    for category, group in groupby(items, key=lambda x: x.category):
        grp = list(group)
        sections.append({
            'name':        category,
            'desc':        grp[0].category_description,
            'answer_type': grp[0].answer_type,
            'order':       grp[0].category_order,
            'questions': [
                {'id': q.pk, 'text': q.item_text, 'order': q.item_order}
                for q in grp
            ],
        })

    latest = ChecklistSnapshot.objects.first()
    snapshots = list(
        ChecklistSnapshot.objects
        .select_related('saved_by')
        .values('id', 'saved_at', 'saved_by__name', 'data')[:20]
    )
    snap_data = [
        {
            'id':       s['id'],
            'saved_at': s['saved_at'].strftime('%Y-%m-%d %H:%M'),
            'date':     s['saved_at'].strftime('%Y-%m-%d'),
            'time':     s['saved_at'].strftime('%H:%M'),
            'saved_by': s['saved_by__name'] or '-',
            'data':     s['data'],
        }
        for s in snapshots
    ]

    return render(request, 'admin/safety_checklist/safety_checklist_list.html', {
        'active_menu':  'safety',
        'sections':     sections,
        'snapshots':    snap_data,
        'latest_saved': latest.saved_at.strftime('%Y-%m-%d') if latest else '-',
    })


@require_POST
def safety_checklist_save(request):
    from safety.models import SafetyCheckItem

    try:
        body = json.loads(request.body)
        sections = body.get('sections', [])
    except Exception:
        return JsonResponse({'success': False, 'message': '잘못된 요청'}, status=400)

    old_pks = set(SafetyCheckItem.objects.filter(is_active=True).values_list('pk', flat=True))
    new_pks = set()

    for s_order, section in enumerate(sections):
        name = section.get('name', '').strip()
        desc        = section.get('desc', '')
        answer_type = section.get('answer_type', '체크 박스')
        if not name:
            continue
        for q_order, q in enumerate(section.get('questions', [])):
            text = q.get('text', '').strip()
            if not text:
                continue
            item_id = q.get('id')
            if item_id and SafetyCheckItem.objects.filter(pk=item_id).exists():
                SafetyCheckItem.objects.filter(pk=item_id).update(
                    category=name,
                    category_description=desc,
                    answer_type=answer_type,
                    category_order=s_order + 1,
                    item_text=text,
                    item_order=q_order + 1,
                    is_active=True,
                )
                new_pks.add(int(item_id))
            else:
                item = SafetyCheckItem.objects.create(
                    category=name,
                    category_description=desc,
                    answer_type=answer_type,
                    category_order=s_order + 1,
                    item_text=text,
                    item_order=q_order + 1,
                    is_active=True,
                )
                new_pks.add(item.pk)

    # 제거된 항목 비활성화 (삭제 아님 — SafetyCheckItemResult 보존)
    removed = old_pks - new_pks
    if removed:
        SafetyCheckItem.objects.filter(pk__in=removed).update(is_active=False)

    snapshot = ChecklistSnapshot.objects.create(
        saved_by=request.user if request.user.is_authenticated else None,
        data={'sections': sections},
    )

    return JsonResponse({
        'success':    True,
        'saved_at':   snapshot.saved_at.strftime('%Y-%m-%d %H:%M'),
        'saved_date': snapshot.saved_at.strftime('%Y-%m-%d'),
    })

# ===== VR 교육 관리 =====
def vr_education_list(request):
    edu, _ = VREducation.objects.get_or_create(
        pk=1,
        defaults={
            'title':       '밀폐공간 작업 전 안전 확인',
            'target':      '가스 센서',
            'is_active':   True,
            'duration':    0,
            'description': '밀폐공간 진입 전 작업자가 반드시 확인해야 할 안전 절차와 비상 대응을 설명합니다.',
            'memo':        '콘텐츠는 1건만 운영합니다. 수정 시 기존 콘텐츠를 교체합니다.',
        },
    )
    return render(request, 'admin/vr_education/vr_education_list.html', {
        'active_menu': 'safety',
        'edu':         edu,
    })


def _extract_video_duration(file_field) -> int:
    """저장된 영상 파일에서 재생 시간(초)을 추출합니다."""
    import subprocess, json as _json
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                file_field.path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = _json.loads(result.stdout)
        for stream in data.get('streams', []):
            dur = stream.get('duration')
            if dur:
                return int(float(dur))
    except Exception:
        pass
    return 0


@require_POST
def vr_education_save(request):
    edu = VREducation.objects.get_or_create(pk=1)[0]
    edu.title       = request.POST.get('title', edu.title).strip()
    edu.description = request.POST.get('description', edu.description).strip()
    if 'video' in request.FILES:
        edu.video = request.FILES['video']
        edu.save()
        edu.duration = _extract_video_duration(edu.video)
    if 'thumbnail' in request.FILES:
        edu.thumbnail = request.FILES['thumbnail']
    edu.save()
    return JsonResponse({
        'success':          True,
        'title':            edu.title,
        'description':      edu.description,
        'updated_at':       edu.updated_at.strftime('%Y-%m-%d'),
        'duration_badge':   edu.duration_badge,
        'duration_display': edu.duration_display,
    })

# ===== 설비 관리 =====
def facility_list(request):
    """설비 관리 메인 페이지"""
    return render(request, 'admin/facilities/facility_list.html', {'active_menu': 'facility'})

def gas_list(request):
    """유해가스 센서 관리 메인 페이지"""
    return render(request, 'admin/gas/gas_list.html', {'active_menu': 'facility'})

def power_list(request):
    """스마트 전력 시스템 관리 메인 페이지"""
    return render(request, 'admin/power/power_list.html', {'active_menu': 'facility'})

def node_list(request):
    """위치 노드 관리 메인 페이지"""
    return render(request, 'admin/node/node_list.html', {'active_menu': 'facility'})

# ===== 데이터 관리 =====
def gas_data_list(request):
    """유해가스 센서 데이터 관리"""
    return render(request, 'admin/data/gas_data_list.html', {'active_menu': 'data'})

def power_data_list(request):
    """스마트 전력 시스템 데이터 관리"""
    return render(request, 'admin/data/power_data_list.html', {'active_menu': 'data'})

def node_data_list(request):
    """위치 노드 데이터 관리"""
    return render(request, 'admin/data/node_data_list.html', {'active_menu': 'data'})

def worker_data_list(request):
    """작업자 위치 데이터 관리"""
    return render(request, 'admin/data/worker_data_list.html', {'active_menu': 'data'})

def retention_list(request):
    """데이터 보관 주기 관리"""
    return render(request, 'admin/data/retention_list.html', {'active_menu': 'data'})

# ===== 공지사항 관리 =====

def notice_list(request):
    notices = (
        Notice.objects
        .select_related('author')
        .annotate(attachment_count=Count('attachments'))
        .order_by('-created_at')
    )
    notices_data = [
        {
            'id':            n.pk,
            'title':         n.title,
            'hasAttachment': n.attachment_count > 0,
            'category':      n.category,
            'exposed':       n.is_exposed,
            'author':        n.author.name if n.author else '',
            'modDate':       n.updated_at.strftime('%Y-%m-%d'),
        }
        for n in notices
    ]
    return render(request, 'admin/notice/notice_list.html', {
        'active_menu':  'notice',
        'notices_data': notices_data,
    })


def notice_detail(request, pk):
    notice = get_object_or_404(
        Notice.objects.select_related('author').prefetch_related('attachments'),
        pk=pk,
    )
    Notice.objects.filter(pk=pk).update(view_count=db_models.F('view_count') + 1)
    notice.view_count += 1

    prev_notice = Notice.objects.filter(pk__lt=pk).order_by('-pk').first()
    next_notice = Notice.objects.filter(pk__gt=pk).order_by('pk').first()

    return render(request, 'admin/notice/notice_detail.html', {
        'active_menu': 'notice',
        'notice':      notice,
        'prev_notice': prev_notice,
        'next_notice': next_notice,
    })


def notice_create(request):
    if request.method == 'POST':
        title      = request.POST.get('title', '').strip()
        category   = request.POST.get('category', '').strip()
        content    = request.POST.get('content', '').strip()
        is_exposed = request.POST.get('is_exposed') == 'true'

        if not title or not category:
            return JsonResponse({'success': False, 'message': '필수 항목을 입력해주세요.'}, status=400)

        notice = Notice.objects.create(
            title=title,
            category=category,
            content=content,
            is_exposed=is_exposed,
            author=request.user if request.user.is_authenticated else None,
        )
        for f in request.FILES.getlist('attachments'):
            NoticeAttachment.objects.create(
                notice=notice,
                file=f,
                original_name=f.name,
                file_size=f.size,
            )
        return JsonResponse({'success': True, 'redirect': reverse('notice_detail', args=[notice.pk])})

    return render(request, 'admin/notice/notice_create.html', {'active_menu': 'notice'})


def notice_edit(request, pk):
    notice = get_object_or_404(Notice, pk=pk)

    if request.method == 'POST':
        title      = request.POST.get('title', '').strip()
        category   = request.POST.get('category', '').strip()
        content    = request.POST.get('content', '').strip()
        is_exposed = request.POST.get('is_exposed') == 'true'

        if not title or not category:
            return JsonResponse({'success': False, 'message': '필수 항목을 입력해주세요.'}, status=400)

        notice.title      = title
        notice.category   = category
        notice.content    = content
        notice.is_exposed = is_exposed
        notice.save()

        delete_ids = [i for i in request.POST.getlist('delete_attachments') if i.isdigit()]
        if delete_ids:
            NoticeAttachment.objects.filter(pk__in=delete_ids, notice=notice).delete()

        for f in request.FILES.getlist('attachments'):
            NoticeAttachment.objects.create(
                notice=notice,
                file=f,
                original_name=f.name,
                file_size=f.size,
            )
        return JsonResponse({'success': True, 'redirect': reverse('notice_detail', args=[notice.pk])})

    return render(request, 'admin/notice/notice_edit.html', {
        'active_menu': 'notice',
        'notice':      notice,
    })


@require_POST
def notice_delete(request, pk):
    notice = get_object_or_404(Notice, pk=pk)
    notice.delete()
    return JsonResponse({'success': True})


@require_POST
def notice_bulk_delete(request):
    try:
        body = json.loads(request.body)
        ids  = body.get('ids', [])
    except Exception:
        ids = request.POST.getlist('ids')
    ids = [int(i) for i in ids if str(i).isdigit()]
    Notice.objects.filter(pk__in=ids).delete()
    return JsonResponse({'success': True})


def notice_attachment_download(request, pk):
    att = get_object_or_404(NoticeAttachment, pk=pk)
    return FileResponse(att.file.open('rb'), as_attachment=True, filename=att.original_name)

# ===== 메뉴 관리 =====
def menu_manage(request):
    """메뉴 관리 (슈퍼관리자 전용)"""
    return render(request, 'admin/menu_manage/menu_manage.html', {'active_menu': 'menu_manage'})

# ===== 알림/이벤트 관리 =====

def alarm_policy_list(request):
    policies = AlarmPolicy.objects.order_by('-updated_at')
    policies_data = [
        {
            'id':        p.pk,
            'name':      p.name,
            'event':     p.event_type,
            'channels':  p.channels,
            'targets':   p.targets,
            'active':    p.is_active,
            'condition': p.condition_summary,
            'modDate':   p.updated_at.strftime('%Y-%m-%d'),
        }
        for p in policies
    ]
    return render(request, 'admin/alarm/alarm_policy_list.html', {
        'active_menu':   'alarm',
        'policies_data': policies_data,
    })


@require_POST
def alarm_policy_create(request):
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'}, status=400)

    name  = body.get('name', '').strip()
    event = body.get('event_type', '').strip()
    if not name or not event:
        return JsonResponse({'success': False, 'message': '정책명과 이벤트 상세는 필수입니다.'}, status=400)

    policy = AlarmPolicy.objects.create(
        name              = name,
        event_type        = event,
        channels          = body.get('channels', ''),
        targets           = body.get('targets', ''),
        is_active         = body.get('is_active', True),
        condition_summary = body.get('condition_summary', ''),
        alarm_title       = body.get('alarm_title', ''),
        alarm_content     = body.get('alarm_content', ''),
    )
    return JsonResponse({
        'success': True,
        'policy': {
            'id':        policy.pk,
            'name':      policy.name,
            'event':     policy.event_type,
            'channels':  policy.channels,
            'targets':   policy.targets,
            'active':    policy.is_active,
            'condition': policy.condition_summary,
            'modDate':   policy.updated_at.strftime('%Y-%m-%d'),
        },
    })


@require_POST
def alarm_policy_bulk_delete(request):
    try:
        body = json.loads(request.body)
        ids  = body.get('ids', [])
    except Exception:
        ids = request.POST.getlist('ids')
    ids = [int(i) for i in ids if str(i).isdigit()]
    AlarmPolicy.objects.filter(pk__in=ids).delete()
    return JsonResponse({'success': True})

def event_history_list(request):
    from alerts.models import AlarmEvent
    from django.utils import timezone as tz

    EVENT_TYPE_LABEL = {
        'gas':      '가스 경보',
        'power':    '전력 이상',
        'location': '위치 이탈',
        'device':   '장비 이벤트',
    }
    STATUS_LABEL = {
        'open':         '발생',
        'acknowledged': '확인중',
        'closed':       '해제',
    }

    events = (
        AlarmEvent.objects
        .select_related('rule', 'device', 'worker', 'facility')
        .order_by('-occurred_at')[:500]
    )

    events_data = []
    for e in events:
        if e.device:
            target = e.device.device_name
        elif e.worker:
            target = e.worker.worker_name
        elif e.facility:
            target = e.facility.facility_name
        else:
            target = '-'

        events_data.append({
            'id':         e.pk,
            'time':       e.occurred_at.strftime('%Y-%m-%d %H:%M:%S'),
            'date':       e.occurred_at.strftime('%Y-%m-%d'),
            'type':       EVENT_TYPE_LABEL.get(e.event_type, e.event_type),
            'target':     target,
            'policy':     e.rule.rule_name if e.rule else '-',
            'status':     STATUS_LABEL.get(e.event_status, e.event_status),
            'releasedAt': e.closed_at.strftime('%Y-%m-%d %H:%M:%S') if e.closed_at else '-',
            'content':    e.message or e.title,
            'memo':       e.title,
        })

    today = tz.localdate().strftime('%Y-%m-%d')

    return render(request, 'admin/alarm/event_history_list.html', {
        'active_menu':  'alarm',
        'events_data':  events_data,
        'today':        today,
    })

def alarm_send_history_list(request):
    from django.utils import timezone as tz

    histories = AlarmSendHistory.objects.order_by('-sent_at')[:500]

    sends_data = [
        {
            'id':        h.pk,
            'time':      h.sent_at.strftime('%Y-%m-%d %H:%M:%S'),
            'date':      h.sent_at.strftime('%Y-%m-%d'),
            'channel':   h.channel,
            'targets':   h.targets,
            'result':    h.result,
            'policy':    h.alarm_policy.name if h.alarm_policy else h.policy_name,
            'policy_id': h.alarm_policy_id,
            'scope':     h.scope,
            'content':   h.content,
            'reason':    h.reason,
        }
        for h in histories
    ]

    today = tz.localdate().strftime('%Y-%m-%d')

    return render(request, 'admin/alarm/alarm_send_history_list.html', {
        'active_menu': 'alarm',
        'sends_data':  sends_data,
        'today':       today,
    })

# ===== 로그 및 연동 관리 =====
def system_log_list(request):
    """시스템 로그"""
    return render(request, 'admin/log/system_log_list.html', {'active_menu': 'log'})

def user_activity_log_list(request):
    """사용자 활동 로그"""
    return render(request, 'admin/log/user_activity_log_list.html', {'active_menu': 'log'})

def integration_log_list(request):
    """연동 로그"""
    return render(request, 'admin/log/integration_log_list.html', {'active_menu': 'log'})

def map_edit_log_list(request):
    """지도 편집 로그"""
    return render(request, 'admin/log/map_edit_log_list.html', {'active_menu': 'log'})

# ===== 지도 관리 =====
def map_editor(request):
    """지도 편집 관리"""
    return render(request, 'admin/map/map.html')
