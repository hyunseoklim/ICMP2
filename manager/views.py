from datetime import timedelta

from django.contrib.auth.models import User
from manager.models import DataRetentionPolicy
from django.db.models import Count, Q
import csv
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, ListView, UpdateView, DeleteView

from django.core.paginator import Paginator
from datetime import datetime, date

from core.models import CommonCode
from monitoring.models import ThresholdPolicy, GasReading, PowerReading, Device, NodeReading
from alerts.models import AlarmRule, RiskCriteria
from facilities.models import WorkerLocation, Worker, LocationNode

from .mixins import AdminRequiredMixin, ManagerRequiredMixin, RoleRequiredMixin, DepartmentScopeMixin

# ── 임계치 카테고리 분류 ──────────────────────────────────────────
_GAS_METRICS   = {'co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc', 'ch4'}
_POWER_METRICS = {'current_value', 'power_value', 'voltage', 'kw', 'kwh', 'pf'}
_METRIC_UNIT = {
    'co': 'ppm', 'h2s': 'ppm', 'co2': 'ppm', 'no2': 'ppm',
    'so2': 'ppm', 'o3': 'ppm', 'nh3': 'ppm', 'voc': 'ppm',
    'ch4': '%LEL', 'o2': '%',
    'current_value': 'A', 'power_value': 'kW', 'voltage': 'V', 'kw': 'kW', 'kwh': 'kWh',
}
_RULE_TYPE_LABEL = {
    'threshold': '임계치 초과', 'missing': '데이터 누락',
    'offline': '장비 오프라인', 'power': '전력 이상',
}
_RULE_COLOR = {
    'threshold': ('green', '녹색'),
    'power':     ('orange', '주황'),
    'missing':   ('gray', '회색'),
    'offline':   ('gray', '회색'),
}


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

def _get_code_groups(prefix=''):
    """그룹 목록: code=='__meta__' 항목이 각 그룹의 대표."""
    qs = CommonCode.objects.filter(code='__meta__')
    if prefix:
        qs = qs.filter(group_code__startswith=prefix)
    return qs.order_by('sort_order', 'group_code')


def code_list(request):
    """공통 코드 관리 메인 페이지"""
    group_code = request.GET.get('group', '')
    search = request.GET.get('search', '')
    code_search = request.GET.get('code_search', '')

    groups = _get_code_groups()
    if search:
        groups = groups.filter(code_name__icontains=search)

    if not group_code and groups.exists():
        group_code = groups.first().group_code

    selected_group = None
    codes = CommonCode.objects.none()

    total_codes = 0
    if group_code:
        selected_group = CommonCode.objects.filter(group_code=group_code, code='__meta__').first()
        codes_qs = CommonCode.objects.filter(group_code=group_code).exclude(code='__meta__').order_by('sort_order', 'code')
        if code_search:
            codes_qs = codes_qs.filter(Q(code__icontains=code_search) | Q(code_name__icontains=code_search))
        if selected_group:
            selected_group.code_count = CommonCode.objects.filter(
                group_code=group_code, is_active=True
            ).exclude(code='__meta__').count()
        total_codes = codes_qs.count()
        paginator = Paginator(codes_qs, 20)
        page_num = request.GET.get('page', 1)
        codes = paginator.get_page(page_num)
    else:
        codes = Paginator(CommonCode.objects.none(), 20).get_page(1)

    user = request.user
    return render(request, 'admin/codes/code_list.html', {
        'active_menu': 'reference',
        'groups': groups,
        'selected_group': selected_group,
        'selected_group_code': group_code,
        'codes': codes,
        'total_codes': total_codes,
        'search': search,
        'code_search': code_search,
        'current_user_name': getattr(user, 'name', None) or user.get_full_name() or user.username,
    })


def code_group_create(request):
    """코드 그룹 등록"""
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    if request.method == 'POST':
        group_code  = request.POST.get('group_code', '').strip().upper()
        group_name  = request.POST.get('group_name', '').strip()
        scope       = request.POST.get('scope', '').strip()
        description = request.POST.get('description', '').strip()
        if group_code and group_name:
            obj, created = CommonCode.objects.get_or_create(
                group_code=group_code, code='__meta__',
                defaults={
                    'code_name': group_name, 'sort_order': 0, 'is_active': True,
                    'scope': scope, 'updated_by': current_user_name, 'description': description,
                },
            )
            if not created:
                obj.code_name   = group_name
                obj.scope       = scope
                obj.updated_by  = current_user_name
                obj.description = description
                obj.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect(f'/manager/codes/?group={group_code}')
    return render(request, 'admin/codes/code_group_create.html', {
        'active_menu': 'reference',
        'current_user_name': current_user_name,
    })


def code_group_edit(request, group_code):
    """코드 그룹 수정 (GET: JSON 반환, POST: 저장)"""
    meta = get_object_or_404(CommonCode, group_code=group_code, code='__meta__')
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    if request.method == 'POST':
        group_name  = request.POST.get('group_name', '').strip()
        scope       = request.POST.get('scope', '').strip()
        description = request.POST.get('description', '').strip()
        if group_name:
            meta.code_name   = group_name
            meta.scope       = scope
            meta.updated_by  = current_user_name
            meta.description = description
            meta.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect(f'/manager/codes/?group={group_code}')
    # GET → JSON (모달 pre-fill 용)
    code_count = CommonCode.objects.filter(group_code=group_code, is_active=True).exclude(code='__meta__').count()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'group_code':  meta.group_code,
            'group_name':  meta.code_name,
            'scope':       meta.scope,
            'description': meta.description,
            'updated_at':  meta.updated_at.strftime('%Y-%m-%d %H:%M') if meta.updated_at else '',
            'updated_by':  meta.updated_by or '-',
            'code_count':  code_count,
        })
    return render(request, 'admin/codes/code_group_edit.html', {
        'active_menu': 'reference',
        'meta': meta,
        'current_user_name': current_user_name,
        'code_count': code_count,
    })


def code_value_create(request):
    """공통 코드 등록"""
    group_code = request.GET.get('group', '') or request.POST.get('group_code', '')
    selected_group = CommonCode.objects.filter(group_code=group_code, code='__meta__').first()
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        code_name = request.POST.get('code_name', '').strip()
        sort_order = int(request.POST.get('sort_order', 0) or 0)
        is_active = request.POST.get('is_active', 'true') == 'true'
        description = request.POST.get('description', '').strip()
        if code and code_name and group_code:
            # 동일 그룹 내 코드명 중복 검사
            dup = CommonCode.objects.filter(group_code=group_code, code_name=code_name).exclude(code='__meta__').exclude(code=code).exists()
            if dup:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'ok': False, 'field': 'code_name', 'error': '같은 코드 그룹에 동일한 코드명이 이미 등록되어 있습니다.'})
            else:
                CommonCode.objects.update_or_create(
                    group_code=group_code, code=code,
                    defaults={
                        'code_name': code_name, 'sort_order': sort_order,
                        'is_active': is_active, 'description': description,
                        'updated_by': current_user_name,
                    },
                )
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect(f'/manager/codes/?group={group_code}')
    return render(request, 'admin/codes/code_value_create.html', {
        'active_menu': 'reference',
        'group_code': group_code,
        'selected_group': selected_group,
        'current_user_name': current_user_name,
    })


def code_value_edit(request, pk):
    """공통 코드 수정 (GET: JSON 반환, POST: 저장)"""
    code_obj = get_object_or_404(CommonCode, pk=pk)
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    if request.method == 'POST':
        new_name = request.POST.get('code_name', code_obj.code_name).strip()
        dup = CommonCode.objects.filter(
            group_code=code_obj.group_code, code_name=new_name
        ).exclude(code='__meta__').exclude(pk=pk).exists()
        if dup:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'ok': False, 'field': 'code_name', 'error': '같은 코드 그룹에 동일한 코드명이 이미 등록되어 있습니다.'})
        else:
            code_obj.code_name   = new_name
            code_obj.sort_order  = int(request.POST.get('sort_order', code_obj.sort_order) or 0)
            code_obj.is_active   = request.POST.get('is_active', 'true') == 'true'
            code_obj.description = request.POST.get('description', '').strip()
            code_obj.updated_by  = current_user_name
            code_obj.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect(f'/manager/codes/?group={code_obj.group_code}')
    # GET → JSON (모달 pre-fill 용)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'pk':          code_obj.pk,
            'code':        code_obj.code,
            'code_name':   code_obj.code_name,
            'description': code_obj.description,
            'sort_order':  code_obj.sort_order,
            'is_active':   code_obj.is_active,
            'group_code':  code_obj.group_code,
            'updated_by':  code_obj.updated_by or '-',
        })
    return render(request, 'admin/codes/code_value_edit.html', {
        'active_menu': 'reference',
        'code_obj': code_obj,
        'current_user_name': current_user_name,
    })


@require_POST
def code_value_delete(request):
    """공통 코드 삭제 (복수)"""
    pks = request.POST.getlist('pks')
    group_code = request.POST.get('group_code', '')
    if pks:
        CommonCode.objects.filter(pk__in=pks).exclude(code='__meta__').delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect(f'/manager/codes/?group={group_code}')


# ===== 위험 유형 관리 =====

def risk_list(request):
    """위험 유형 관리 메인 페이지"""
    group_code = request.GET.get('group', '')
    search = request.GET.get('search', '')
    code_search = request.GET.get('code_search', '')

    groups = _get_code_groups(prefix='RISK_')
    if search:
        groups = groups.filter(code_name__icontains=search)

    if not group_code and groups.exists():
        group_code = groups.first().group_code

    selected_group = None
    codes = CommonCode.objects.none()

    if group_code:
        selected_group = CommonCode.objects.filter(group_code=group_code, code='__meta__').first()
        codes = CommonCode.objects.filter(group_code=group_code).exclude(code='__meta__').order_by('sort_order', 'code')
        if code_search:
            codes = codes.filter(Q(code__icontains=code_search) | Q(code_name__icontains=code_search))
        if selected_group:
            selected_group.type_count = CommonCode.objects.filter(
                group_code=group_code, is_active=True
            ).exclude(code='__meta__').count()
            selected_group.scope_display = ' / '.join(
                s.strip() for s in (selected_group.scope or '').split(',') if s.strip()
            ) or '-'

    return render(request, 'admin/risks/risk_list.html', {
        'active_menu': 'reference',
        'groups': groups,
        'selected_group': selected_group,
        'selected_group_code': group_code,
        'codes': codes,
        'search': search,
        'code_search': code_search,
    })


def risk_create(request):
    """위험 유형 코드 등록 (AJAX POST 지원)"""
    group_code = request.GET.get('group', '') or request.POST.get('group_code', '')
    selected_group = CommonCode.objects.filter(group_code=group_code, code='__meta__').first()
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        code_name = request.POST.get('code_name', '').strip()
        sort_order = int(request.POST.get('sort_order', 0) or 0)
        is_active = request.POST.get('is_active', 'true') == 'true'
        map_reflect = request.POST.get('map_reflect', '') == 'true'
        description = request.POST.get('description', '').strip()
        if code and code_name and group_code:
            # 코드 중복 검사
            if CommonCode.objects.filter(group_code=group_code, code=code).exists():
                if is_ajax:
                    return JsonResponse({'ok': False, 'field': 'code', 'error': '이미 해당 코드 그룹에 등록된 코드입니다.'})
            # 코드명 중복 검사
            elif CommonCode.objects.filter(group_code=group_code, code_name=code_name).exclude(code='__meta__').exists():
                if is_ajax:
                    return JsonResponse({'ok': False, 'field': 'code_name', 'error': '같은 코드 그룹에 동일한 유형명이 이미 등록되어 있습니다.'})
            else:
                CommonCode.objects.update_or_create(
                    group_code=group_code, code=code,
                    defaults={
                        'code_name': code_name, 'sort_order': sort_order,
                        'is_active': is_active, 'map_reflect': map_reflect,
                        'description': description, 'updated_by': current_user_name,
                    },
                )
                if is_ajax:
                    return JsonResponse({'ok': True})
        if is_ajax:
            return JsonResponse({'ok': False, 'error': '필수 항목을 확인하세요.'})
        return redirect(f'/manager/risks/?group={group_code}')
    return render(request, 'admin/risks/risk_create.html', {
        'active_menu': 'reference',
        'group_code': group_code,
        'selected_group': selected_group,
        'current_user_name': current_user_name,
    })


def risk_edit(request, pk):
    """위험 유형 코드 수정 (AJAX 지원)"""
    code_obj = get_object_or_404(CommonCode, pk=pk)
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        new_name    = request.POST.get('code_name', code_obj.code_name).strip()
        map_reflect = request.POST.get('map_reflect', '') == 'true'
        # 코드명 중복 검사 (자기 자신 제외)
        if CommonCode.objects.filter(
            group_code=code_obj.group_code, code_name=new_name
        ).exclude(code='__meta__').exclude(pk=pk).exists():
            if is_ajax:
                return JsonResponse({'ok': False, 'field': 'code_name', 'error': '같은 코드 그룹에 동일한 유형명이 이미 등록되어 있습니다.'})
        else:
            code_obj.code_name   = new_name
            code_obj.sort_order  = int(request.POST.get('sort_order', code_obj.sort_order) or 0)
            code_obj.is_active   = request.POST.get('is_active', 'true') == 'true'
            code_obj.map_reflect = map_reflect
            code_obj.description = request.POST.get('description', '').strip()
            code_obj.updated_by  = current_user_name
            code_obj.save()
        if is_ajax:
            return JsonResponse({'ok': True})
        return redirect(f'/manager/risks/?group={code_obj.group_code}')
    # GET → JSON
    if is_ajax:
        return JsonResponse({
            'pk':          code_obj.pk,
            'code':        code_obj.code,
            'code_name':   code_obj.code_name,
            'description': code_obj.description or '',
            'map_reflect': code_obj.map_reflect,
            'is_active':   code_obj.is_active,
            'group_code':  code_obj.group_code,
        })
    return render(request, 'admin/risks/risk_edit.html', {
        'active_menu': 'reference',
        'code_obj': code_obj,
        'current_user_name': current_user_name,
    })


def risk_group_create(request):
    """위험 분류 그룹 등록"""
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    if request.method == 'POST':
        group_code  = request.POST.get('group_code', '').strip().upper()
        group_name  = request.POST.get('group_name', '').strip()
        # 모달에서는 hidden input 하나로, 기존 페이지에서는 getlist로 전송
        scope_list  = request.POST.getlist('scope')
        scope       = scope_list[0] if len(scope_list) == 1 else ','.join(scope_list)
        is_active   = request.POST.get('is_active', 'true') == 'true'
        description = request.POST.get('description', '').strip()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if group_code and group_name:
            if not group_code.startswith('RISK_'):
                group_code = 'RISK_' + group_code
            obj, created = CommonCode.objects.get_or_create(
                group_code=group_code, code='__meta__',
                defaults={
                    'code_name': group_name, 'sort_order': 0,
                    'is_active': is_active, 'scope': scope,
                    'description': description, 'updated_by': current_user_name,
                },
            )
            if not created:
                obj.code_name   = group_name
                obj.is_active   = is_active
                obj.scope       = scope
                obj.description = description
                obj.updated_by  = current_user_name
                obj.save()
        if is_ajax:
            return JsonResponse({'ok': True, 'group_code': group_code})
        return redirect(f'/manager/risks/?group={group_code}')
    return render(request, 'admin/risks/risk_group_create.html', {
        'active_menu': 'reference',
        'current_user_name': current_user_name,
    })


def risk_group_edit(request, group_code):
    """위험 분류 그룹 수정 (AJAX 지원)"""
    meta = get_object_or_404(CommonCode, group_code=group_code, code='__meta__')
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        group_name  = request.POST.get('group_name', '').strip()
        scope_raw   = request.POST.get('scope', '')
        is_active   = request.POST.get('is_active', 'true') == 'true'
        description = request.POST.get('description', '').strip()
        if group_name:
            meta.code_name   = group_name
            meta.is_active   = is_active
            meta.scope       = scope_raw
            meta.description = description
            meta.updated_by  = current_user_name
            meta.save()
        if is_ajax:
            return JsonResponse({'ok': True})
        return redirect(f'/manager/risks/?group={group_code}')
    # GET → JSON
    type_count = CommonCode.objects.filter(group_code=group_code, is_active=True).exclude(code='__meta__').count()
    if is_ajax:
        return JsonResponse({
            'group_code':   meta.group_code,
            'group_name':   meta.code_name,
            'scope':        meta.scope or '',
            'is_active':    meta.is_active,
            'description':  meta.description or '',
            'updated_at':   meta.updated_at.strftime('%Y-%m-%d %H:%M') if meta.updated_at else '',
            'updated_by':   meta.updated_by or '-',
            'type_count':   type_count,
        })
    selected_scopes = meta.scope.split(',') if meta.scope else []
    return render(request, 'admin/risks/risk_group_edit.html', {
        'active_menu': 'reference',
        'meta': meta,
        'current_user_name': current_user_name,
        'type_count': type_count,
        'selected_scopes': selected_scopes,
    })


@require_POST
def risk_delete(request):
    """위험 유형 코드 삭제 (복수)"""
    pks = request.POST.getlist('pks')
    group_code = request.POST.get('group_code', '')
    if pks:
        CommonCode.objects.filter(pk__in=pks).exclude(code='__meta__').delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect(f'/manager/risks/?group={group_code}')


# ===== 위험 기준 관리 =====

def risk_criteria_list(request):
    search        = request.GET.get('search', '')
    is_active_f   = request.GET.get('is_active', '')
    color_f       = request.GET.get('color_type', '')

    qs = RiskCriteria.objects.all()
    if search:
        qs = qs.filter(Q(stage_code__icontains=search) | Q(stage_name__icontains=search))
    if is_active_f == 'true':
        qs = qs.filter(is_active=True)
    elif is_active_f == 'false':
        qs = qs.filter(is_active=False)
    if color_f:
        qs = qs.filter(color_type=color_f)

    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username

    return render(request, 'admin/risk_criteria/risk_criteria_list.html', {
        'active_menu': 'reference',
        'criteria':   qs,
        'total':      qs.count(),
        'search':     search,
        'is_active_filter': is_active_f,
        'color_filter':     color_f,
        'color_choices':    RiskCriteria.ColorType.choices,
        'current_user_name': current_user_name,
    })


def risk_criteria_create(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'method not allowed'}, status=405)
    user = request.user
    updated_by = getattr(user, 'name', None) or user.get_full_name() or user.username
    stage_code = request.POST.get('stage_code', '').strip().upper()
    stage_name = request.POST.get('stage_name', '').strip()
    if not stage_code:
        return JsonResponse({'ok': False, 'field': 'code', 'error': '단계 코드를 입력해 주세요.'})
    if not stage_name:
        return JsonResponse({'ok': False, 'field': 'name', 'error': '단계명을 입력해 주세요.'})
    if RiskCriteria.objects.filter(stage_code=stage_code).exists():
        return JsonResponse({'ok': False, 'field': 'code', 'error': '이미 등록된 단계 코드입니다.'})
    if RiskCriteria.objects.filter(stage_name=stage_name).exists():
        return JsonResponse({'ok': False, 'field': 'name', 'error': '이미 등록된 단계명입니다.'})
    color_type = request.POST.get('color_type', '').strip()
    if not color_type:
        return JsonResponse({'ok': False, 'field': 'color', 'error': '표시 색상을 선택해 주세요.'})
    priority_raw = request.POST.get('priority', '1').strip() or '1'
    try:
        priority = int(priority_raw)
        if priority < 1:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'field': 'priority', 'error': '이벤트 우선순위는 1 이상의 숫자여야 합니다.'})
    if RiskCriteria.objects.filter(priority=priority).exists():
        return JsonResponse({'ok': False, 'field': 'priority', 'error': '이미 사용 중인 이벤트 우선순위입니다.'})
    try:
        RiskCriteria.objects.create(
            stage_code     = stage_code,
            stage_name     = stage_name,
            color_type     = color_type,
            alert_emphasis = request.POST.get('alert_emphasis', '').strip(),
            priority       = priority,
            is_active      = request.POST.get('is_active', 'true') == 'true',
            description    = request.POST.get('description', '').strip(),
            updated_by     = updated_by,
        )
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})
    return JsonResponse({'ok': True})


def risk_criteria_edit(request, pk):
    obj = get_object_or_404(RiskCriteria, pk=pk)
    if request.method == 'POST':
        stage_code = request.POST.get('stage_code', obj.stage_code).strip().upper()
        stage_name = request.POST.get('stage_name', obj.stage_name).strip()
        if not stage_code:
            return JsonResponse({'ok': False, 'field': 'code', 'error': '단계 코드를 입력해 주세요.'})
        if not stage_name:
            return JsonResponse({'ok': False, 'field': 'name', 'error': '단계명을 입력해 주세요.'})
        if RiskCriteria.objects.filter(stage_code=stage_code).exclude(pk=pk).exists():
            return JsonResponse({'ok': False, 'field': 'code', 'error': '이미 등록된 단계 코드입니다.'})
        if RiskCriteria.objects.filter(stage_name=stage_name).exclude(pk=pk).exists():
            return JsonResponse({'ok': False, 'field': 'name', 'error': '이미 등록된 단계명입니다.'})
        priority_raw = request.POST.get('priority', str(obj.priority)).strip() or str(obj.priority)
        try:
            priority = int(priority_raw)
            if priority < 1:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({'ok': False, 'field': 'priority', 'error': '이벤트 우선순위는 1 이상의 숫자여야 합니다.'})
        if RiskCriteria.objects.filter(priority=priority).exclude(pk=pk).exists():
            return JsonResponse({'ok': False, 'field': 'priority', 'error': '이미 사용 중인 이벤트 우선순위입니다.'})
        try:
            obj.stage_code     = stage_code
            obj.stage_name     = stage_name
            obj.color_type     = request.POST.get('color_type', obj.color_type)
            obj.alert_emphasis = request.POST.get('alert_emphasis', obj.alert_emphasis).strip()
            obj.priority       = priority
            obj.is_active      = request.POST.get('is_active', 'true') == 'true'
            obj.description    = request.POST.get('description', obj.description).strip()
            obj.updated_by     = getattr(request.user, 'name', None) or request.user.get_full_name() or request.user.username
            obj.save()
        except Exception as e:
            return JsonResponse({'ok': False, 'error': str(e)})
        return JsonResponse({'ok': True})
    return JsonResponse({
        'id':             obj.pk,
        'stage_code':     obj.stage_code,
        'stage_name':     obj.stage_name,
        'color_type':     obj.color_type,
        'alert_emphasis': obj.alert_emphasis,
        'priority':       obj.priority,
        'is_active':      obj.is_active,
        'description':    obj.description,
        'updated_at':     obj.updated_at.strftime('%Y-%m-%d %H:%M') if obj.updated_at else '',
        'updated_by':     obj.updated_by or '-',
    })


@require_POST
def risk_criteria_delete(request):
    pks = request.POST.getlist('pks')
    if pks:
        RiskCriteria.objects.filter(pk__in=pks).delete()
    return redirect('/manager/risk-criteria/')


# ===== 임계치 기준 관리 =====

def _th_category(metric_code):
    mc = metric_code.lower()
    if mc in _GAS_METRICS:
        return 'TH_GAS'
    if mc in _POWER_METRICS:
        return 'TH_POWER'
    return 'TH_COMMON'


def _ensure_th_categories():
    """CommonCode에 TH_CATEGORY 기본값이 없으면 생성하고, 기존 ThresholdPolicy에 category 필드 채우기"""
    defaults = [
        {'code': 'TH_GAS',   'code_name': '유해가스', 'sort_order': 1,
         'scope': '실시간 관제,AI 예측,알림', 'updated_by': '시스템'},
        {'code': 'TH_POWER', 'code_name': '전력',     'sort_order': 2,
         'scope': '실시간 관제,알림',        'updated_by': '시스템'},
    ]
    for d in defaults:
        obj, created = CommonCode.objects.get_or_create(
            group_code='TH_CATEGORY', code=d['code'],
            defaults={
                'code_name':  d['code_name'],
                'sort_order': d['sort_order'],
                'is_active':  True,
                'scope':      d['scope'],
                'updated_by': d['updated_by'],
            },
        )
        if not created and not obj.scope:
            obj.scope = d['scope']
            obj.updated_by = d['updated_by']
            obj.save(update_fields=['scope', 'updated_by'])
    # system → 시스템 마이그레이션
    CommonCode.objects.filter(group_code='TH_CATEGORY', updated_by='system').update(updated_by='시스템')
    ThresholdPolicy.objects.filter(updated_by='system').update(updated_by='시스템')
    # 기존 데이터 unit이 비어있는 경우 모두 보정
    for p in ThresholdPolicy.objects.filter(unit=''):
        cat = _th_category(p.metric_code)
        unit = _METRIC_UNIT.get(p.metric_code.lower(), '')
        cond = '이하' if p.metric_code.lower() == 'o2' else '이상'
        scope = '실시간 관제,AI 예측,알림' if cat == 'TH_GAS' else '실시간 관제,알림'
        ThresholdPolicy.objects.filter(pk=p.pk).update(
            category=cat, unit=unit, condition=cond, scope=scope,
        )
    # category가 기본값('TH_GAS')이지만 실제론 전력인 경우 보정
    for p in ThresholdPolicy.objects.filter(category='TH_GAS', metric_code__in=_POWER_METRICS):
        ThresholdPolicy.objects.filter(pk=p.pk).update(
            category='TH_POWER',
            unit=_METRIC_UNIT.get(p.metric_code.lower(), ''),
            condition='이상',
            scope='실시간 관제,알림',
        )
    # 초과/미만 → 이상/이하 복구
    ThresholdPolicy.objects.filter(condition='초과').update(condition='이상')
    ThresholdPolicy.objects.filter(condition='미만').update(condition='이하')


def threshold_list(request):
    """임계치 기준 관리 메인 페이지 (모든 모달 포함)"""
    _ensure_th_categories()
    category = request.GET.get('category', 'TH_GAS')
    search = request.GET.get('search', '')
    cat_search = request.GET.get('cat_search', '')
    sort = request.GET.get('sort', 'metric_asc')

    cats_qs = CommonCode.objects.filter(group_code='TH_CATEGORY').order_by('sort_order')
    if cat_search:
        cats_qs = cats_qs.filter(Q(code_name__icontains=cat_search) | Q(code__icontains=cat_search))
    categories = list(cats_qs)

    selected_cat_obj = CommonCode.objects.filter(group_code='TH_CATEGORY', code=category).first()
    category_name = selected_cat_obj.code_name if selected_cat_obj else category
    scope_raw = selected_cat_obj.scope if selected_cat_obj else ''
    scope_display = ' / '.join(s.strip() for s in scope_raw.split(',') if s.strip()) or '-'

    policies = ThresholdPolicy.objects.filter(category=category)

    if search:
        policies = policies.filter(metric_code__icontains=search)

    sort_map = {
        'metric_asc':  'metric_code',
        'metric_desc': '-metric_code',
        'active':      '-is_active',
        'updated_new': '-updated_at',
        'updated_old': 'updated_at',
    }
    policies = policies.order_by(sort_map.get(sort, 'metric_code'))

    policies = list(policies)
    for p in policies:
        p.warning_val   = p.warning_max if p.warning_max is not None else p.warning_min
        p.danger_val    = p.danger_max  if p.danger_max  is not None else p.danger_min
        p.scope_display = ' / '.join(s.strip() for s in (p.scope or '').split(',') if s.strip()) or '-'

    all_in_cat = ThresholdPolicy.objects.filter(category=category)
    total_count = all_in_cat.count()
    latest = all_in_cat.order_by('-updated_at').first()

    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username

    return render(request, 'admin/thresholds/threshold_list.html', {
        'active_menu': 'reference',
        'categories': categories,
        'selected_category': category,
        'category_name': category_name,
        'scope_display': scope_display,
        'selected_cat_obj': selected_cat_obj,
        'policies': policies,
        'search': search,
        'cat_search': cat_search,
        'sort': sort,
        'total': len(policies),
        'total_count': total_count,
        'latest': latest,
        'current_user_name': current_user_name,
    })


def threshold_group_create(request):
    """임계치 기준 분류 등록 (AJAX)"""
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        code = request.POST.get('code', '').strip().upper()
        code_name = request.POST.get('code_name', '').strip()
        scope = request.POST.get('scope', '').strip()
        is_active = request.POST.get('is_active', 'true') == 'true'
        description = request.POST.get('description', '').strip()
        user = request.user
        updated_by = getattr(user, 'name', None) or user.get_full_name() or user.username

        if not code or not code_name:
            return JsonResponse({'ok': False, 'error': '분류코드와 분류명은 필수입니다.'})
        if CommonCode.objects.filter(group_code='TH_CATEGORY', code=code).exists():
            return JsonResponse({'ok': False, 'field': 'code', 'error': '이미 사용 중인 분류코드입니다.'})

        CommonCode.objects.create(
            group_code='TH_CATEGORY', code=code, code_name=code_name,
            scope=scope, is_active=is_active, description=description,
            updated_by=updated_by,
            sort_order=CommonCode.objects.filter(group_code='TH_CATEGORY').count() + 1,
        )
        return JsonResponse({'ok': True, 'code': code})
    return JsonResponse({'ok': False}, status=400)


def threshold_group_edit(request, cat_code):
    """임계치 기준 분류 수정 (GET: JSON, POST: 저장)"""
    obj = get_object_or_404(CommonCode, group_code='TH_CATEGORY', code=cat_code)
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        new_code = request.POST.get('code', obj.code).strip().upper()
        obj.code_name = request.POST.get('code_name', obj.code_name).strip()
        obj.scope = request.POST.get('scope', '').strip()
        obj.is_active = request.POST.get('is_active', 'true') == 'true'
        obj.description = request.POST.get('description', '').strip()
        user = request.user
        obj.updated_by = getattr(user, 'name', None) or user.get_full_name() or user.username
        if new_code and new_code != obj.code:
            if CommonCode.objects.filter(group_code='TH_CATEGORY', code=new_code).exists():
                return JsonResponse({'ok': False, 'error': '이미 사용 중인 분류코드입니다.'})
            obj.code = new_code
        obj.save()
        return JsonResponse({'ok': True})
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        type_count = ThresholdPolicy.objects.all()
        if cat_code == 'TH_GAS':
            type_count = type_count.filter(metric_code__in=_GAS_METRICS)
        elif cat_code == 'TH_POWER':
            type_count = type_count.filter(metric_code__in=_POWER_METRICS)
        return JsonResponse({
            'code':       obj.code,
            'code_name':  obj.code_name,
            'scope':      obj.scope,
            'is_active':  obj.is_active,
            'description': obj.description,
            'updated_at': obj.updated_at.strftime('%Y-%m-%d %H:%M') if obj.updated_at else '-',
            'updated_by': obj.updated_by or '-',
            'type_count': type_count.count(),
        })
    return JsonResponse({'ok': False}, status=400)


def threshold_create(request):
    """임계치 기준 등록"""
    if request.method == 'POST':
        is_ajax     = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        metric_code = request.POST.get('metric_code', '').strip().lower()
        unit        = request.POST.get('unit', '').strip()
        condition   = request.POST.get('condition', '이상').strip()
        warning_val = request.POST.get('warning_val') or None
        danger_val  = request.POST.get('danger_val')  or None
        scope       = request.POST.get('scope', '').strip()
        description = request.POST.get('description', '').strip()
        category    = request.POST.get('category', 'TH_GAS')

        # 중복 검사
        if ThresholdPolicy.objects.filter(metric_code=metric_code, category=category).exists():
            return JsonResponse({'ok': False, 'field': 'metric_code',
                                 'error': '동일한 기준 분류에 같은 측정 항목이 이미 등록되어 있습니다.'})

        if not metric_code:
            return JsonResponse({'ok': False, 'field': 'metric_code', 'error': '측정 항목을 입력해 주세요.'})

        is_lte = condition == '이하'
        user = request.user
        updated_by = getattr(user, 'name', None) or user.get_full_name() or user.username
        try:
            ThresholdPolicy.objects.create(
                metric_code=metric_code,
                category=category,
                unit=unit,
                condition=condition,
                warning_min=float(warning_val) if is_lte and warning_val else None,
                warning_max=float(warning_val) if not is_lte and warning_val else None,
                danger_min =float(danger_val)  if is_lte and danger_val  else None,
                danger_max =float(danger_val)  if not is_lte and danger_val  else None,
                scope=scope,
                description=description,
                is_active=request.POST.get('is_active', 'true') == 'true',
                updated_by=updated_by,
            )
        except Exception as e:
            return JsonResponse({'ok': False, 'error': f'저장 중 오류가 발생했습니다: {e}'})
        return JsonResponse({'ok': True})
    return redirect(f"/manager/thresholds/?category={request.POST.get('category', 'TH_GAS')}")


def threshold_edit(request, pk):
    """임계치 기준 수정 (GET: JSON 반환, POST: 저장)"""
    policy = get_object_or_404(ThresholdPolicy, pk=pk)
    if request.method == 'POST':
        condition   = request.POST.get('condition', policy.condition).strip()
        warning_val = request.POST.get('warning_val') or None
        danger_val  = request.POST.get('danger_val')  or None
        is_lte = condition == '이하'
        policy.unit        = request.POST.get('unit', policy.unit).strip()
        policy.condition   = condition
        policy.warning_min = float(warning_val) if is_lte and warning_val else None
        policy.warning_max = float(warning_val) if not is_lte and warning_val else None
        policy.danger_min  = float(danger_val)  if is_lte and danger_val  else None
        policy.danger_max  = float(danger_val)  if not is_lte and danger_val  else None
        policy.scope       = request.POST.get('scope', '').strip()
        policy.description = request.POST.get('description', '').strip()
        policy.is_active   = request.POST.get('is_active', 'true') == 'true'
        user = request.user
        policy.updated_by  = getattr(user, 'name', None) or user.get_full_name() or user.username
        try:
            policy.save()
        except Exception as e:
            return JsonResponse({'ok': False, 'error': f'저장 중 오류가 발생했습니다: {e}'})
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect(f'/manager/thresholds/?category={policy.category}')
    warning_val = policy.warning_max if policy.warning_max is not None else policy.warning_min
    danger_val  = policy.danger_max  if policy.danger_max  is not None else policy.danger_min
    return JsonResponse({
        'id':          policy.pk,
        'metric_code': policy.metric_code,
        'unit':        policy.unit or _METRIC_UNIT.get(policy.metric_code.lower(), ''),
        'condition':   policy.condition or ('이하' if policy.metric_code.lower() == 'o2' else '이상'),
        'warning_val': warning_val,
        'danger_val':  danger_val,
        'scope':       policy.scope or '',
        'description': policy.description or '',
        'is_active':   policy.is_active,
        'updated_at':  policy.updated_at.strftime('%Y-%m-%d %H:%M') if policy.updated_at else '',
        'updated_by':  policy.updated_by or '-',
    })


@require_POST
def threshold_delete(request):
    """임계치 기준 삭제 (복수)"""
    pks = request.POST.getlist('pks')
    category = request.POST.get('category', 'TH_GAS')
    if pks:
        ThresholdPolicy.objects.filter(pk__in=pks).delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect(f'/manager/thresholds/?category={category}')

# ===== 안전 확인 관리 =====
def safety_checklist_list(request):
    """작업 전 안전 점검 체크리스트 관리"""
    return render(request, 'admin/safety_checklist/safety_checklist_list.html', {'active_menu': 'safety'})

# ===== VR 교육 관리 =====
def vr_education_list(request):
    """VR 교육 관리 - 메인 + 수정 모달 통합"""
    return render(request, 'admin/vr_education/vr_education_list.html', {'active_menu': 'safety'})

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
def _parse_date_range(request):
    """GET 파라미터에서 date_from / date_to를 파싱, 기본값 = 최근 7일"""
    today = date.today()
    default_from = today - timedelta(days=6)
    try:
        date_from = datetime.strptime(request.GET.get('date_from', ''), '%Y-%m-%d').date()
    except ValueError:
        date_from = default_from
    try:
        date_to = datetime.strptime(request.GET.get('date_to', ''), '%Y-%m-%d').date()
    except ValueError:
        date_to = today
    return date_from, date_to


def gas_data_list(request):
    """유해가스 센서 데이터 관리"""
    date_from, date_to = _parse_date_range(request)
    device_uid = request.GET.get('device_uid', '')
    sort       = request.GET.get('sort', 'new')
    page_num   = request.GET.get('page', 1)

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = GasReading.objects.select_related('device').filter(
        measured_at__date__gte=date_from,
        measured_at__date__lte=date_to,
    ).order_by(ordering)
    if device_uid:
        qs = qs.filter(device__device_uid=device_uid)

    devices   = Device.objects.filter(device_type='gas').order_by('device_uid')
    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(page_num)

    return render(request, 'admin/data/gas_data_list.html', {
        'active_menu': 'data',
        'page_obj':    page_obj,
        'total':       paginator.count,
        'devices':     devices,
        'device_uid':  device_uid,
        'date_from':   date_from.strftime('%Y-%m-%d'),
        'date_to':     date_to.strftime('%Y-%m-%d'),
        'sort':        sort,
    })


def gas_data_export(request):
    """유해가스 센서 데이터 CSV 내보내기"""
    date_from, date_to = _parse_date_range(request)
    device_uid = request.GET.get('device_uid', '')
    sort       = request.GET.get('sort', 'new')

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = GasReading.objects.select_related('device').filter(
        measured_at__date__gte=date_from,
        measured_at__date__lte=date_to,
    ).order_by(ordering)
    if device_uid:
        qs = qs.filter(device__device_uid=device_uid)

    filename = f"gas_data_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['수집 시각', '장비명', 'CH4', 'O2', 'CO', 'CO2', 'H2S', 'NH3', 'VOC', 'SO2'])
    for r in qs.iterator(chunk_size=500):
        def fmt(val, unit='ppm'):
            return f'{val:.1f} {unit}' if val is not None else '-'
        writer.writerow([
            r.measured_at.strftime('%Y-%m-%d %H:%M:%S'),
            r.device.device_uid,
            fmt(r.co2),
            fmt(r.o2, '%'),
            fmt(r.co),
            fmt(r.h2s),
            fmt(r.nh3),
            fmt(r.voc),
            fmt(r.no2),
            fmt(r.so2),
        ])
    return response


def power_data_list(request):
    """스마트 전력 시스템 데이터 관리"""
    date_from, date_to = _parse_date_range(request)
    sort     = request.GET.get('sort', 'new')
    page_num = request.GET.get('page', 1)

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = PowerReading.objects.select_related('device').filter(
        measured_at__date__gte=date_from,
        measured_at__date__lte=date_to,
    ).order_by(ordering)

    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(page_num)

    return render(request, 'admin/data/power_data_list.html', {
        'active_menu': 'data',
        'page_obj':    page_obj,
        'total':       paginator.count,
        'date_from':   date_from.strftime('%Y-%m-%d'),
        'date_to':     date_to.strftime('%Y-%m-%d'),
        'sort':        sort,
    })


def power_data_export(request):
    """스마트 전력 시스템 데이터 CSV 내보내기"""
    date_from, date_to = _parse_date_range(request)
    sort = request.GET.get('sort', 'new')

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = PowerReading.objects.select_related('device').filter(
        measured_at__date__gte=date_from,
        measured_at__date__lte=date_to,
    ).order_by(ordering)

    filename = f"power_data_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['수집 시각', '장비명', '전력값(W)', '온도(℃)'])
    for r in qs.iterator(chunk_size=500):
        writer.writerow([
            r.measured_at.strftime('%Y-%m-%d %H:%M:%S'),
            r.device.device_uid,
            r.power_w if r.power_w >= 0 else '-',
            f'{r.temperature_c:.1f}' if r.temperature_c is not None else '-',
        ])
    return response


def node_data_list(request):
    """위치 노드 데이터 관리"""
    date_from, date_to = _parse_date_range(request)
    node_name = request.GET.get('node_name', '')
    sort      = request.GET.get('sort', 'new')
    page_num  = request.GET.get('page', 1)

    ordering = 'received_at' if sort == 'old' else '-received_at'
    qs = NodeReading.objects.select_related('node').filter(
        received_at__date__gte=date_from,
        received_at__date__lte=date_to,
    ).order_by(ordering)
    if node_name:
        qs = qs.filter(node__node_name__icontains=node_name)

    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(page_num)

    return render(request, 'admin/data/node_data_list.html', {
        'active_menu': 'data',
        'page_obj':    page_obj,
        'total':       paginator.count,
        'node_name':   node_name,
        'date_from':   date_from.strftime('%Y-%m-%d'),
        'date_to':     date_to.strftime('%Y-%m-%d'),
        'sort':        sort,
    })


def node_data_export(request):
    """위치 노드 데이터 CSV 내보내기"""
    date_from, date_to = _parse_date_range(request)
    node_name = request.GET.get('node_name', '')
    sort      = request.GET.get('sort', 'new')

    ordering = 'received_at' if sort == 'old' else '-received_at'
    qs = NodeReading.objects.select_related('node').filter(
        received_at__date__gte=date_from,
        received_at__date__lte=date_to,
    ).order_by(ordering)
    if node_name:
        qs = qs.filter(node__node_name__icontains=node_name)

    filename = f"node_data_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['수신 시각', '장비명', '위치 좌표'])
    for r in qs.iterator(chunk_size=500):
        x_str = f'{r.x:.3f}' if r.x is not None else '-'
        y_str = f'{r.y:.3f}' if r.y is not None else '-'
        coord = f'{x_str} / {y_str}'
        writer.writerow([
            r.received_at.strftime('%Y-%m-%d %H:%M:%S'),
            r.node.node_name,
            coord,
        ])
    return response


def worker_data_list(request):
    """작업자 위치 데이터 관리"""
    date_from, date_to = _parse_date_range(request)
    worker_name = request.GET.get('worker_name', '')
    sort        = request.GET.get('sort', 'new')
    page_num    = request.GET.get('page', 1)

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = WorkerLocation.objects.select_related('worker').filter(
        measured_at__date__gte=date_from,
        measured_at__date__lte=date_to,
    ).order_by(ordering)
    if worker_name:
        qs = qs.filter(worker__worker_name__icontains=worker_name)

    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(page_num)

    return render(request, 'admin/data/worker_data_list.html', {
        'active_menu': 'data',
        'page_obj':    page_obj,
        'total':       paginator.count,
        'worker_name': worker_name,
        'date_from':   date_from.strftime('%Y-%m-%d'),
        'date_to':     date_to.strftime('%Y-%m-%d'),
        'sort':        sort,
    })


def worker_data_export(request):
    """작업자 위치 데이터 CSV 내보내기"""
    date_from, date_to = _parse_date_range(request)
    worker_name = request.GET.get('worker_name', '')
    sort        = request.GET.get('sort', 'new')

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = WorkerLocation.objects.select_related('worker').filter(
        measured_at__date__gte=date_from,
        measured_at__date__lte=date_to,
    ).order_by(ordering)
    if worker_name:
        qs = qs.filter(worker__worker_name__icontains=worker_name)

    filename = f"worker_data_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['수신 시각', '작업자명', '위치 좌표'])
    for r in qs.iterator(chunk_size=500):
        writer.writerow([
            r.measured_at.strftime('%Y-%m-%d %H:%M:%S'),
            r.worker.worker_name,
            f'{r.x:.3f} / {r.y:.3f}',
        ])
    return response


def retention_list(request):
    """데이터 보관 주기 관리"""
    device_type     = request.GET.get('device_type', '')
    data_category   = request.GET.get('data_category', '')
    delete_schedule = request.GET.get('delete_schedule', '')
    is_active_f     = request.GET.get('is_active', '')
    sort            = request.GET.get('sort', 'dtype-asc')
    page_num        = request.GET.get('page', 1)

    qs = DataRetentionPolicy.objects.select_related('manager')
    if device_type:
        qs = qs.filter(device_type=device_type)
    if data_category:
        qs = qs.filter(data_category=data_category)
    if delete_schedule:
        qs = qs.filter(delete_schedule=delete_schedule)
    if is_active_f == '1':
        qs = qs.filter(is_active=True)
    elif is_active_f == '0':
        qs = qs.filter(is_active=False)

    ordering_map = {
        'dtype-asc':  ('device_type', 'data_category'),
        'dtype-desc': ('-device_type', '-data_category'),
        'date-desc':  ('-updated_at',),
        'date-asc':   ('updated_at',),
    }
    qs = qs.order_by(*ordering_map.get(sort, ('device_type',)))

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(page_num)

    return render(request, 'admin/data/retention_list.html', {
        'active_menu':    'data',
        'page_obj':       page_obj,
        'total':          paginator.count,
        'device_type':    device_type,
        'data_category':  data_category,
        'delete_schedule': delete_schedule,
        'is_active_f':    is_active_f,
        'sort':           sort,
        'DEVICE_TYPE_CHOICES':     DataRetentionPolicy.DEVICE_TYPE,
        'DATA_CATEGORY_CHOICES':   DataRetentionPolicy.DATA_CATEGORY,
        'DELETE_SCHEDULE_CHOICES': DataRetentionPolicy.DELETE_SCHEDULE,
        'sort_options': [
            ('dtype-asc',  '장비 유형 오름차순'),
            ('dtype-desc', '장비 유형 내림차순'),
            ('date-desc',  '최근 수정일 최신순'),
            ('date-asc',   '최근 수정일 오래된순'),
        ],
    })


@require_POST
def retention_create(request):
    """보관 주기 등록 AJAX"""
    import json
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': '잘못된 요청입니다.'}, status=400)

    required = ['device_type', 'data_category', 'origin_days', 'history_days', 'delete_schedule', 'is_active']
    for f in required:
        if not str(data.get(f, '')).strip():
            return JsonResponse({'ok': False, 'error': f'{f} 값이 필요합니다.'}, status=400)

    try:
        origin  = int(data['origin_days'])
        history = int(data['history_days'])
        assert origin >= 1 and history >= 1
    except Exception:
        return JsonResponse({'ok': False, 'error': '보관 기간은 1 이상의 정수여야 합니다.'}, status=400)

    policy = DataRetentionPolicy.objects.create(
        device_type     = data['device_type'],
        data_category   = data['data_category'],
        origin_days     = origin,
        history_days    = history,
        delete_schedule = data['delete_schedule'],
        is_active       = data['is_active'] == '1',
        memo            = data.get('memo', ''),
        manager         = request.user if request.user.is_authenticated else None,
    )
    return JsonResponse({'ok': True, 'id': policy.pk})


@require_POST
def retention_update(request, pk):
    """보관 주기 수정 AJAX"""
    import json
    policy = get_object_or_404(DataRetentionPolicy, pk=pk)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': '잘못된 요청입니다.'}, status=400)

    try:
        origin  = int(data.get('origin_days', 0))
        history = int(data.get('history_days', 0))
        assert origin >= 1 and history >= 1
    except Exception:
        return JsonResponse({'ok': False, 'error': '보관 기간은 1 이상의 정수여야 합니다.'}, status=400)

    policy.device_type     = data.get('device_type', policy.device_type)
    policy.data_category   = data.get('data_category', policy.data_category)
    policy.origin_days     = origin
    policy.history_days    = history
    policy.delete_schedule = data.get('delete_schedule', policy.delete_schedule)
    policy.is_active       = data.get('is_active') == '1'
    policy.memo            = data.get('memo', '')
    policy.manager         = request.user if request.user.is_authenticated else None
    policy.save()
    return JsonResponse({'ok': True})


@require_POST
def retention_delete(request):
    """보관 주기 삭제 AJAX (복수)"""
    import json
    try:
        data = json.loads(request.body)
        ids  = [int(i) for i in data.get('ids', [])]
    except Exception:
        return JsonResponse({'ok': False, 'error': '잘못된 요청입니다.'}, status=400)

    deleted, _ = DataRetentionPolicy.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True, 'deleted': deleted})


# ===== 공지사항 관리 =====
def notice_list(request):
    """공지사항 관리"""
    return render(request, 'admin/notice/notice_list.html', {'active_menu': 'notice'})

def notice_detail(request):
    """공지사항 상세"""
    return render(request, 'admin/notice/notice_detail.html', {'active_menu': 'notice'})

def notice_create(request):
    """공지사항 등록"""
    return render(request, 'admin/notice/notice_create.html', {'active_menu': 'notice'})

def notice_edit(request):
    """공지사항 수정"""
    return render(request, 'admin/notice/notice_edit.html', {'active_menu': 'notice'})

# ===== 메뉴 관리 =====
def menu_manage(request):
    """메뉴 관리 (슈퍼관리자 전용)"""
    return render(request, 'admin/menu_manage/menu_manage.html', {'active_menu': 'menu_manage'})

# ===== 알림/이벤트 관리 =====
def alarm_policy_list(request):
    """알림 정책 관리"""
    return render(request, 'admin/alarm/alarm_policy_list.html', {'active_menu': 'alarm'})

def event_history_list(request):
    """이벤트 이력 조회"""
    return render(request, 'admin/alarm/event_history_list.html', {'active_menu': 'alarm'})

def alarm_send_history_list(request):
    """알림 발송 이력"""
    return render(request, 'admin/alarm/alarm_send_history_list.html', {'active_menu': 'alarm'})

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
