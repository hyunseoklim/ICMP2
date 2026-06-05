import json
import re
import csv
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from functools import wraps

def admin_required(view_func):
    """슈퍼관리자(admin) 전용. 미로그인 → 로그인 페이지(302), 권한 없음 → 403."""
    @wraps(view_func)
    @login_required(login_url='/accounts/login/')
    def wrapped(request, *args, **kwargs):
        if request.user.user_type != 'admin':
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped


def manager_required(view_func):
    """슈퍼관리자+관리자 전용. 미로그인 → 로그인 페이지(302), 권한 없음 → 403."""
    @wraps(view_func)
    @login_required(login_url='/accounts/login/')
    def wrapped(request, *args, **kwargs):
        if request.user.user_type not in ('admin', 'manager'):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped



from django.db import models as db_models
from django.db.models import Count, Q, Max, Case, When, IntegerField, Value, Subquery, OuterRef, DateField, Exists, F
from django.http import JsonResponse, FileResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.views.generic import TemplateView, ListView, UpdateView, DeleteView

from manager.models import DataRetentionPolicy
from core.models import CommonCode, SystemLog
from monitoring.models import ThresholdPolicy, GasReading, PowerReading, Device, NodeReading, InspectionLog, ActionLog
from alerts.models import AlarmRule, RiskCriteria
from core.timeutils import to_korea_time_str
from facilities.models import WorkerLocation, Worker, LocationNode, Equipment, Facility, Floor, Geofence, SensorLocation
from accounts.models import User, Department, Position
from .mixins import AdminRequiredMixin, ManagerRequiredMixin, RoleRequiredMixin, DepartmentScopeMixin
from .models import Notice, NoticeAttachment, AlarmPolicy, AlarmSendHistory, VREducation, ChecklistSnapshot
from .constants import GAS_METRICS as _GAS_METRICS, POWER_METRICS as _POWER_METRICS, METRIC_UNIT as _METRIC_UNIT, RULE_TYPE_LABEL as _RULE_TYPE_LABEL, RULE_COLOR as _RULE_COLOR



@admin_required
def user_list(request):
    """사용자 관리 메인 페이지"""
    sort_map = {
        'name': 'name',
        'last_login': '-last_login_at',
        'date_joined': '-date_joined',
        'user_type': 'user_type',
        'is_active': '-is_active',
    }
    sort_key = request.GET.get('sort', 'date_joined')
    order_by = sort_map.get(sort_key, '-date_joined')
    qs = User.objects.select_related('department').order_by(order_by)

    if q := request.GET.get('username'):
        qs = qs.filter(Q(name__icontains=q) | Q(username__icontains=q))
    if dept := request.GET.get('dept'):
        qs = qs.filter(department_id=dept)
    if user_type := request.GET.get('user_type'):
        if user_type == 'superuser':
            qs = qs.filter(is_superuser=True)
        else:
            qs = qs.filter(user_type=user_type, is_superuser=False)
    account_status = request.GET.get('is_active')
    if account_status == 'true':
        qs = qs.filter(is_active=True, is_locked=False)
    elif account_status == 'false':
        qs = qs.filter(is_active=False)
    elif account_status == 'locked':
        qs = qs.filter(is_locked=True)
    if position := request.GET.get('position'):
        qs = qs.filter(position__icontains=position)

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    params = request.GET.copy()
    params.pop('page', None)
    base_params = params.urlencode()

    return render(request, 'admin/users/user_list.html', {
        'active_menu': 'account',
        'users': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'departments': Department.objects.all(),
        'positions': (
            User.objects.exclude(position='')
            .values_list('position', flat=True)
            .distinct()
            .order_by('position')
        ),
        'base_params': base_params,
    })

@admin_required
def user_bulk_delete(request):
    if request.method != 'POST':
        return redirect('user_list')
    ids = request.POST.getlist('selected_ids')
    if ids:
        count = User.objects.filter(pk__in=ids).count()
        User.objects.filter(pk__in=ids).delete()
        messages.success(request, f'{count}명의 사용자가 삭제되었습니다.')
    return redirect('user_list')


@admin_required
def user_bulk_lock(request):
    if request.method != 'POST':
        return redirect('user_list')
    ids = request.POST.getlist('selected_ids')
    if ids:
        count = User.objects.filter(pk__in=ids).update(is_locked=True)
        messages.success(request, f'{count}명의 계정이 잠금 처리되었습니다.')
    return redirect('user_list')


@admin_required
def user_bulk_unlock(request):
    if request.method != 'POST':
        return redirect('user_list')
    ids = request.POST.getlist('selected_ids')
    if ids:
        count = User.objects.filter(pk__in=ids).update(is_locked=False)
        messages.success(request, f'{count}명의 계정 잠금이 해제되었습니다.')
    return redirect('user_list')


@admin_required
def check_username(request):
    username = request.GET.get('username', '').strip()
    exists = User.objects.filter(username=username).exists() if username else False
    return JsonResponse({'exists': exists})


@admin_required
def user_create(request):
    """사용자 등록"""
    if request.method == 'POST':
        name           = request.POST.get('name', '').strip()
        username       = request.POST.get('username', '').strip()
        password1      = request.POST.get('password1', '')
        password2      = request.POST.get('password2', '')
        department     = request.POST.get('department', '').strip()
        user_type      = request.POST.get('user_type', '').strip()
        position       = request.POST.get('position', '').strip()
        account_status = request.POST.get('is_active', '').strip()
        email          = request.POST.get('email', '').strip()
        phone          = request.POST.get('phone', '').strip()

        errors = []

        # ── 사용자명 ──────────────────────────────────────────
        if not name:
            errors.append('사용자명을 입력해 주세요.')
        elif len(name) < 2:
            errors.append('사용자명을 2자 이상 입력해 주세요.')
        elif len(name) > 20:
            errors.append('사용자명은 20자 이하로 입력해 주세요.')
        elif not re.fullmatch(r'[가-힣a-zA-Z0-9]+', name):
            errors.append('사용자명은 한글, 영문, 숫자만 입력할 수 있습니다.')

        # ── 아이디 ───────────────────────────────────────────
        if not username:
            errors.append('아이디를 입력해 주세요.')
        elif ' ' in username:
            errors.append('아이디에는 공백을 입력할 수 없습니다.')
        elif not re.fullmatch(r'[a-zA-Z0-9]+', username):
            errors.append('아이디는 영문 또는 숫자만 입력할 수 있습니다.')
        elif len(username) < 4:
            errors.append('아이디를 4자 이상 입력해 주세요.')
        elif len(username) > 20:
            errors.append('아이디는 20자 이하로 입력해 주세요.')
        elif User.objects.filter(username=username).exists():
            errors.append('이미 사용 중인 아이디입니다.')

        # ── 비밀번호 ─────────────────────────────────────────
        pw_ok = True
        if not password1:
            errors.append('비밀번호를 입력해 주세요.')
            pw_ok = False
        elif ' ' in password1:
            errors.append('비밀번호에는 공백을 입력할 수 없습니다.')
            pw_ok = False
        elif len(password1) < 8:
            errors.append('비밀번호는 8자 이상 입력해 주세요.')
            pw_ok = False
        elif len(password1) > 20:
            errors.append('비밀번호는 20자 이하로 입력해 주세요.')
            pw_ok = False
        else:
            has_letter  = bool(re.search(r'[a-zA-Z]', password1))
            has_number  = bool(re.search(r'[0-9]', password1))
            has_special = bool(re.search(r'[^a-zA-Z0-9]', password1))
            if sum([has_letter, has_number, has_special]) < 2:
                errors.append('비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해 주세요.')
                pw_ok = False

        # ── 비밀번호 확인 ─────────────────────────────────────
        if not password2:
            errors.append('비밀번호 확인을 입력해 주세요.')
        elif pw_ok and password1 != password2:
            errors.append('비밀번호가 일치하지 않습니다.')

        # ── 소속 ─────────────────────────────────────────────
        if not department:
            errors.append('소속을 선택해 주세요.')

        # ── 권한 ─────────────────────────────────────────────
        if not user_type:
            errors.append('권한을 선택해 주세요.')

        # ── 계정 상태 ─────────────────────────────────────────
        if not account_status:
            errors.append('계정 상태를 선택해 주세요.')

        # ── 이메일 ───────────────────────────────────────────
        if not email:
            errors.append('이메일을 입력해 주세요.')
        elif len(email) > 100:
            errors.append('이메일은 100자 이하로 입력해 주세요.')
        elif not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
            errors.append('이메일 형식이 올바르지 않습니다.')

        # ── 연락처 ───────────────────────────────────────────
        if not phone:
            errors.append('연락처를 입력해 주세요.')
        elif re.search(r'[^0-9\-]', phone):
            errors.append('연락처는 숫자만 입력할 수 있습니다.')
        elif len(re.sub(r'\D', '', phone)) not in (10, 11):
            errors.append('연락처를 정확히 입력해 주세요.')
        elif not re.fullmatch(r'0\d{1,2}-\d{3,4}-\d{4}', phone):
            errors.append('연락처 형식이 올바르지 않습니다. (예: 010-1234-5678)')

        if errors:
            for e in errors:
                messages.error(request, e)
            return redirect('user_list')

        is_locked = account_status == 'locked'
        is_active = account_status != 'false'

        user = User(
            username=username,
            name=name,
            user_type=user_type,
            position=position,
            is_active=is_active,
            is_locked=is_locked,
            email=email,
            phone=phone,
        )
        user.department_id = int(department)
        if user_type == 'admin':
            user.is_staff = True
        user.set_password(password1)
        try:
            user.save()
        except Exception as e:
            messages.error(request, f'사용자 등록 중 오류가 발생했습니다: {e}')
            return redirect('user_list')

        messages.success(request, f'사용자 "{name}"({username})이 등록되었습니다.')
        return redirect('user_list')

    return render(request, 'admin/users/user_create.html', {
        'active_menu': 'account',
        'departments': Department.objects.all(),
        'positions': User.objects.exclude(position='').values_list('position', flat=True).distinct().order_by('position'),
    })

@admin_required
def user_create_error(request):
    """사용자 등록 - 유효성 에러"""
    return render(request, 'admin/users/user_create_error.html', {
        'active_menu': 'account',
        'departments': Department.objects.all(),
    })

@admin_required
def user_detail(request):
    """사용자 정보 조회"""
    return render(request, 'admin/users/user_detail.html', {
        'active_menu': 'account',
        'departments': Department.objects.all(),
    })

@admin_required
def user_edit(request, pk):
    """사용자 정보 수정"""
    from django.shortcuts import get_object_or_404
    target_user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        target_user.name       = request.POST.get('name', target_user.name).strip()
        target_user.email      = request.POST.get('email', target_user.email).strip()
        target_user.phone      = request.POST.get('phone', target_user.phone).strip()
        target_user.position   = request.POST.get('position', target_user.position).strip()
        target_user.user_type  = request.POST.get('user_type', target_user.user_type)
        account_status = request.POST.get('is_active', 'true')
        if account_status == 'locked':
            target_user.is_locked = True
            target_user.is_active = True
        elif account_status == 'false':
            target_user.is_locked = False
            target_user.is_active = False
        else:
            target_user.is_locked = False
            target_user.is_active = True

        dept_id = request.POST.get('department')
        target_user.department_id = int(dept_id) if dept_id else None

        pw1 = request.POST.get('password1', '')
        pw2 = request.POST.get('password2', '')
        if pw1:
            if pw1 != pw2:
                messages.error(request, '비밀번호가 일치하지 않습니다.')
                return redirect('user_list')
            target_user.set_password(pw1)

        if target_user.user_type == 'admin':
            target_user.is_staff = True

        target_user.save()
        messages.success(request, f'"{target_user.name}" 정보가 수정되었습니다.')
        return redirect('user_list')

    return render(request, 'admin/users/user_edit.html', {
        'active_menu': 'account',
        'target_user': target_user,
        'departments': Department.objects.all(),
        'positions': User.objects.exclude(position='').values_list('position', flat=True).distinct().order_by('position'),
    })

@login_required
def logout_complete(request):
    """로그아웃 완료"""
    return render(request, 'admin/users/logout_complete.html', {'active_menu': 'account'})

@admin_required
def user_list_filter(request):
    """필터 펼친 상태"""
    return render(request, 'admin/users/user_list_filter_open.html', {'active_menu': 'account'})

# ===== 직위 관리 =====
@admin_required
def position_list(request):
    """직위 관리 메인 페이지"""
    qs = Position.objects.all()
    if q := request.GET.get('q'):
        qs = qs.filter(name__icontains=q)
    return render(request, 'admin/positions/position_list.html', {
        'active_menu': 'account',
        'positions': qs,
        'total_count': qs.count(),
    })

@admin_required
def position_create(request):
    """직위 등록 POST 처리"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        is_active = request.POST.get('is_active') == 'true'
        if name:
            order = (Position.objects.aggregate(Max('order'))['order__max'] or 0) + 1
            Position.objects.create(name=name, is_active=is_active, order=order)
            messages.success(request, f'직위 "{name}"이(가) 등록되었습니다.')
        else:
            messages.error(request, '직위명을 입력하세요.')
    return redirect('position_list')


@admin_required
def position_edit(request, pk):
    """직위 수정 POST 처리"""
    from django.shortcuts import get_object_or_404
    position = get_object_or_404(Position, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        is_active = request.POST.get('is_active') == 'true'
        if name:
            position.name = name
            position.is_active = is_active
            position.save()
            messages.success(request, f'직위 "{name}"이(가) 수정되었습니다.')
        else:
            messages.error(request, '직위명을 입력하세요.')
    return redirect('position_list')


@admin_required
def position_bulk_delete(request):
    """직위 일괄 삭제"""
    if request.method != 'POST':
        return redirect('position_list')
    ids = request.POST.getlist('position_ids')
    if ids:
        count, _ = Position.objects.filter(pk__in=ids).delete()
        messages.success(request, f'{count}개의 직위가 삭제되었습니다.')
    return redirect('position_list')


# ===== 조직 관리 =====
@admin_required
def org_list(request):
    """조직 관리 메인 페이지"""
    departments = Department.objects.annotate(member_count=Count('users')).order_by('name')
    return render(request, 'admin/organizations/org_list.html', {
        'active_menu': 'account',
        'departments': departments,
    })


@admin_required
def org_dept_api(request, pk):
    """부서 클릭 시 부서 정보 + 구성원 목록 반환 (JSON AJAX)"""
    from django.http import JsonResponse
    from django.shortcuts import get_object_or_404

    if pk == 0:
        dept_data = {'id': 0, 'name': '조직 없음', 'code': '-', 'leader_id': None}
        qs = User.objects.filter(department__isnull=True).order_by('name')
        dept_data['member_count'] = qs.count()
    else:
        dept = get_object_or_404(Department, pk=pk)
        qs = User.objects.filter(department=dept).order_by('name')
        dept_data = {
            'id': dept.id, 'name': dept.name, 'code': dept.code or '-',
            'member_count': qs.count(),
            'leader_id': dept.leader_id,
            'leader_name': dept.leader.name if dept.leader else None,
            'created_at': to_korea_time_str(dept.created_at) if dept.created_at else '-',
            'updated_at': to_korea_time_str(dept.updated_at) if dept.updated_at else '-',
            'updated_by': dept.updated_by.name if dept.updated_by else '-',
        }

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(username__icontains=q))

    per_page = min(int(request.GET.get('per_page', 10)), 200)
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(int(request.GET.get('page', 1)))

    leader_id = dept_data.get('leader_id')
    members = [
        {
            'id': u.pk,
            'name': u.name,
            'username': u.username,
            'position': u.position or '-',
            'is_active': u.is_active,
            'user_type': u.user_type,
            'is_superuser': u.is_superuser,
            'is_leader': leader_id is not None and u.pk == leader_id,
        }
        for u in page_obj
    ]

    return JsonResponse({
        'dept': dept_data,
        'members': members,
        'total': paginator.count,
        'page': page_obj.number,
        'num_pages': paginator.num_pages,
        'has_previous': page_obj.has_previous(),
        'has_next': page_obj.has_next(),
        'start_index': page_obj.start_index() if paginator.count else 0,
        'end_index': page_obj.end_index() if paginator.count else 0,
    })


@admin_required
def org_all_api(request):
    """전체 사용자 목록 반환 (구성원 선택 팝업 회사 행용)"""
    from django.http import JsonResponse
    qs = User.objects.order_by('name')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(username__icontains=q))
    members = [
        {'id': u.pk, 'name': u.name, 'username': u.username,
         'position': u.position or '-', 'is_active': u.is_active}
        for u in qs[:200]
    ]
    return JsonResponse({'members': members, 'total': qs.count()})


@admin_required
def org_add_members(request):
    """구성원 부서 추가 저장"""
    from django.shortcuts import get_object_or_404
    if request.method != 'POST':
        return redirect('org_list')
    dept_id  = request.POST.get('dept_id')
    user_ids = request.POST.getlist('user_ids')
    if not dept_id or not user_ids:
        messages.error(request, '대상 부서 또는 구성원을 선택하세요.')
        return redirect('org_list')
    dept = get_object_or_404(Department, pk=dept_id)
    User.objects.filter(pk__in=user_ids).update(department=dept)
    messages.success(request, f'{len(user_ids)}명이 {dept.name}에 추가되었습니다.')
    return redirect('org_list')

@admin_required
def org_exclude_members(request):
    """소속 제외: 선택된 사용자들의 department를 NULL로 설정"""
    if request.method != 'POST':
        return redirect('org_list')
    user_ids = request.POST.getlist('user_ids')
    if not user_ids:
        messages.error(request, '제외할 구성원을 선택하세요.')
        return redirect('org_list')
    User.objects.filter(pk__in=user_ids).update(department=None)
    messages.success(request, f'{len(user_ids)}명이 소속에서 제외되었습니다.')
    return redirect('org_list')


@admin_required
def org_appoint_leader(request):
    """조직장 임명: 선택된 사용자를 해당 부서의 leader로 설정"""
    from django.shortcuts import get_object_or_404
    if request.method != 'POST':
        return redirect('org_list')
    user_id = request.POST.get('user_id')
    dept_id = request.POST.get('dept_id')
    if not user_id or not dept_id:
        messages.error(request, '구성원 또는 부서 정보가 없습니다.')
        return redirect('org_list')
    dept = get_object_or_404(Department, pk=dept_id)
    user = get_object_or_404(User, pk=user_id)
    dept.leader = user
    dept.updated_by = request.user
    dept.save(update_fields=['leader', 'updated_by', 'updated_at'])
    messages.success(request, f'{user.name}을(를) {dept.name}의 조직장으로 임명했습니다.')
    return redirect('org_list')


@admin_required
def org_revoke_leader(request):
    """조직장 해제: 해당 부서의 leader를 NULL로 설정"""
    from django.shortcuts import get_object_or_404
    if request.method != 'POST':
        return redirect('org_list')
    dept_id = request.POST.get('dept_id')
    if not dept_id:
        messages.error(request, '부서 정보가 없습니다.')
        return redirect('org_list')
    dept = get_object_or_404(Department, pk=dept_id)
    prev_name = dept.leader.name if dept.leader else ''
    dept.leader = None
    dept.updated_by = request.user
    dept.save(update_fields=['leader', 'updated_by', 'updated_at'])
    messages.success(request, f'{prev_name}의 조직장 직위가 해제되었습니다.')
    return redirect('org_list')


@admin_required
def org_member_select(request):
    """구성원 선택 (모달이 org_list에 통합됨, URL 하위호환 유지)"""
    return redirect('org_list')

@admin_required
def org_dept_move(request):
    """부서 이동 모달"""
    return render(request, 'admin/organizations/org_dept_move.html', {'active_menu': 'account'})

@admin_required
def org_confirm(request):
    """재확인 모달"""
    return render(request, 'admin/organizations/org_confirm.html', {'active_menu': 'account'})

# ===== 공통 코드 관리 =====

def _get_code_groups(prefix='', exclude_prefix=''):
    """그룹 목록: code=='__meta__' 항목이 각 그룹의 대표."""
    qs = CommonCode.objects.filter(code='__meta__', is_active=True)
    if prefix:
        qs = qs.filter(group_code__startswith=prefix)
    if exclude_prefix:
        qs = qs.exclude(group_code__startswith=exclude_prefix)
    return qs.order_by('sort_order', 'group_code')


@manager_required
def code_list(request):
    """공통 코드 관리 메인 페이지"""
    group_code = request.GET.get('group', '')
    search = request.GET.get('search', '')
    code_search = request.GET.get('code_search', '')

    groups = _get_code_groups(exclude_prefix='RISK_')
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

@manager_required
def code_group_create(request):
    """코드 그룹 등록"""
    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        group_code  = request.POST.get('group_code', '').strip().upper()
        group_name  = request.POST.get('group_name', '').strip()
        scope       = request.POST.get('scope', '').strip()
        description = request.POST.get('description', '').strip()
        if group_code and group_name:
            if CommonCode.objects.filter(group_code=group_code, code='__meta__').exists():
                if is_ajax:
                    return JsonResponse({'ok': False, 'field': 'group_code', 'error': '이미 등록된 그룹 코드입니다. 다른 그룹 코드를 입력해 주세요.'})
            elif CommonCode.objects.filter(code='__meta__', code_name=group_name).exists():
                if is_ajax:
                    return JsonResponse({'ok': False, 'field': 'group_name', 'error': '이미 등록된 그룹명입니다. 다른 그룹명을 입력해 주세요.'})
            else:
                CommonCode.objects.create(
                    group_code=group_code, code='__meta__',
                    code_name=group_name, sort_order=0, is_active=True,
                    scope=scope, updated_by=current_user_name, description=description,
                )
        if is_ajax:
            return JsonResponse({'ok': True})
        return redirect(f'/manager/codes/?group={group_code}')
    return render(request, 'admin/codes/code_group_create.html', {
        'active_menu': 'reference',
        'current_user_name': current_user_name,
    })


@manager_required
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
            'updated_at':  to_korea_time_str(meta.updated_at) if meta.updated_at else '',
            'updated_by':  meta.updated_by or '-',
            'code_count':  code_count,
        })
    return render(request, 'admin/codes/code_group_edit.html', {
        'active_menu': 'reference',
        'meta': meta,
        'current_user_name': current_user_name,
        'code_count': code_count,
    })


@manager_required
def code_value_create(request):
    """공통 코드 등록"""
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
        description = request.POST.get('description', '').strip()
        if code and code_name and group_code:
            if CommonCode.objects.filter(group_code=group_code, code=code).exists():
                if is_ajax:
                    return JsonResponse({'ok': False, 'field': 'code', 'error': '이미 해당 코드 그룹에 등록된 코드입니다.'})
            elif CommonCode.objects.filter(group_code=group_code, code_name=code_name).exclude(code='__meta__').exists():
                if is_ajax:
                    return JsonResponse({'ok': False, 'field': 'code_name', 'error': '같은 코드 그룹에 동일한 코드명이 이미 등록되어 있습니다.'})
            else:
                CommonCode.objects.create(
                    group_code=group_code, code=code,
                    code_name=code_name, sort_order=sort_order,
                    is_active=is_active, description=description,
                    updated_by=current_user_name,
                )
        if is_ajax:
            return JsonResponse({'ok': True})
        return redirect(f'/manager/codes/?group={group_code}')
    return render(request, 'admin/codes/code_value_create.html', {
        'active_menu': 'reference',
        'group_code': group_code,
        'selected_group': selected_group,
        'current_user_name': current_user_name,
    })


@manager_required
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


@manager_required
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

@manager_required
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


@manager_required
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


@manager_required
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


@manager_required
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
            if CommonCode.objects.filter(group_code=group_code, code='__meta__').exists():
                if is_ajax:
                    return JsonResponse({'ok': False, 'field': 'group_code', 'error': '이미 등록된 분류 코드입니다. 다른 분류 코드를 입력해 주세요.'})
            elif CommonCode.objects.filter(code='__meta__', code_name=group_name).exists():
                if is_ajax:
                    return JsonResponse({'ok': False, 'field': 'group_name', 'error': '이미 등록된 분류명입니다. 다른 분류명을 입력해 주세요.'})
            else:
                CommonCode.objects.create(
                    group_code=group_code, code='__meta__',
                    code_name=group_name, sort_order=0,
                    is_active=is_active, scope=scope,
                    description=description, updated_by=current_user_name,
                )
        if is_ajax:
            return JsonResponse({'ok': True, 'group_code': group_code})
        return redirect(f'/manager/risks/?group={group_code}')
    return render(request, 'admin/risks/risk_group_create.html', {
        'active_menu': 'reference',
        'current_user_name': current_user_name,
    })


@manager_required
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
            'updated_at':   to_korea_time_str(meta.updated_at) if meta.updated_at else '',
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


@manager_required
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

@manager_required
def risk_criteria_list(request):
    search      = request.GET.get('search', '')
    is_active_f = request.GET.get('is_active', '')
    color_f     = request.GET.get('color_type', '')
    sort        = request.GET.get('sort', 'priority_asc')

    qs = RiskCriteria.objects.all()
    if search:
        qs = qs.filter(Q(stage_code__icontains=search) | Q(stage_name__icontains=search))
    if is_active_f == 'true':
        qs = qs.filter(is_active=True)
    elif is_active_f == 'false':
        qs = qs.filter(is_active=False)
    if color_f:
        qs = qs.filter(color_type=color_f)

    _sort_map = {
        'priority_asc':  'priority',
        'priority_desc': '-priority',
        'priority_low':  '-priority',
        'name_asc':      'stage_name',
        'name_desc':     '-stage_name',
        'code_asc':      'stage_code',
        'code_desc':     '-stage_code',
        'updated_new':   '-updated_at',
        'updated_old':   'updated_at',
        'active_first':  '-is_active',
        'inactive_first': 'is_active',
    }
    qs = qs.order_by(_sort_map.get(sort, 'priority'))

    user = request.user
    current_user_name = getattr(user, 'name', None) or user.get_full_name() or user.username

    sort_options = [
        ('priority_asc',  '우선순위 오름차순'),
        ('priority_desc', '우선순위 내림차순'),
        ('name_asc',      '단계명 가나다순'),
        ('name_desc',     '단계명 가나다 역순'),
        ('code_asc',      '단계 코드 오름차순'),
        ('code_desc',     '단계 코드 내림차순'),
        ('updated_new',   '최근 수정일 최신순'),
        ('updated_old',   '최근 수정일 오래된순'),
        ('active_first',  '사용 여부 사용 우선'),
        ('inactive_first','사용 여부 미사용 우선'),
    ]

    total = qs.count()
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'admin/risk_criteria/risk_criteria_list.html', {
        'active_menu': 'reference',
        'criteria':   page_obj,
        'total':      total,
        'page_obj':   page_obj,
        'search':     search,
        'is_active_filter': is_active_f,
        'color_filter':     color_f,
        'color_choices':    RiskCriteria.ColorType.choices,
        'current_user_name': current_user_name,
        'sort':             sort,
        'sort_options':     sort_options,
    })


@manager_required
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


@manager_required
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
        'updated_at':     to_korea_time_str(obj.updated_at) if obj.updated_at else '',
        'updated_by':     obj.updated_by or '-',
    })


@manager_required
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


@manager_required
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


@manager_required
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

        import re
        if not code:
            return JsonResponse({'ok': False, 'field': 'code', 'error': '분류 코드를 입력해주세요.'})
        if len(code) > 50:
            return JsonResponse({'ok': False, 'field': 'code', 'error': '그룹명은 최대 50자까지 입력할 수 있습니다.'})
        if not re.match(r'^[A-Z0-9_]+$', code):
            return JsonResponse({'ok': False, 'field': 'code', 'error': '그룹 코드는 영문 대문자, 숫자, 밑줄(_)만 사용할 수 있습니다.'})
        if CommonCode.objects.filter(group_code='TH_CATEGORY', code=code).exists():
            return JsonResponse({'ok': False, 'field': 'code', 'error': '이미 등록된 분류 코드입니다. 다른 분류 코드를 입력해 주세요.'})
        if not code_name:
            return JsonResponse({'ok': False, 'field': 'name', 'error': '분류명 입력해 주세요.'})
        if len(code_name) > 50:
            return JsonResponse({'ok': False, 'field': 'name', 'error': '분류명은 최대 50자까지 입력할 수 있습니다.'})
        if not re.match(r'^[가-힣\s]+$', code_name):
            return JsonResponse({'ok': False, 'field': 'name', 'error': '분류명은 한글만 입력할 수 있습니다.'})
        if CommonCode.objects.filter(group_code='TH_CATEGORY', code_name=code_name).exists():
            return JsonResponse({'ok': False, 'field': 'name', 'error': '이미 등록된 분류명입니다. 다른 분류명을 입력해 주세요.'})

        CommonCode.objects.create(
            group_code='TH_CATEGORY', code=code, code_name=code_name,
            scope=scope, is_active=is_active, description=description,
            updated_by=updated_by,
            sort_order=CommonCode.objects.filter(group_code='TH_CATEGORY').count() + 1,
        )
        return JsonResponse({'ok': True, 'code': code})
    return JsonResponse({'ok': False}, status=400)


@manager_required
def threshold_group_edit(request, cat_code):
    """임계치 기준 분류 수정 (GET: JSON, POST: 저장)"""
    obj = get_object_or_404(CommonCode, group_code='TH_CATEGORY', code=cat_code)
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        import re
        new_code = request.POST.get('code', obj.code).strip().upper()
        new_name = request.POST.get('code_name', obj.code_name).strip()
        if not new_code:
            return JsonResponse({'ok': False, 'field': 'code', 'error': '분류 코드를 입력해주세요.'})
        if len(new_code) > 50:
            return JsonResponse({'ok': False, 'field': 'code', 'error': '그룹명은 최대 50자까지 입력할 수 있습니다.'})
        if not re.match(r'^[A-Z0-9_]+$', new_code):
            return JsonResponse({'ok': False, 'field': 'code', 'error': '그룹 코드는 영문 대문자, 숫자, 밑줄(_)만 사용할 수 있습니다.'})
        if new_code != obj.code and CommonCode.objects.filter(group_code='TH_CATEGORY', code=new_code).exists():
            return JsonResponse({'ok': False, 'field': 'code', 'error': '이미 등록된 분류 코드입니다. 다른 분류 코드를 입력해 주세요.'})
        if not new_name:
            return JsonResponse({'ok': False, 'field': 'name', 'error': '분류명 입력해 주세요.'})
        if len(new_name) > 50:
            return JsonResponse({'ok': False, 'field': 'name', 'error': '분류명은 최대 50자까지 입력할 수 있습니다.'})
        if not re.match(r'^[가-힣\s]+$', new_name):
            return JsonResponse({'ok': False, 'field': 'name', 'error': '분류명은 한글만 입력할 수 있습니다.'})
        if new_name != obj.code_name and CommonCode.objects.filter(group_code='TH_CATEGORY', code_name=new_name).exists():
            return JsonResponse({'ok': False, 'field': 'name', 'error': '이미 등록된 분류명입니다. 다른 분류명을 입력해 주세요.'})
        obj.code = new_code
        obj.code_name = new_name
        obj.scope = request.POST.get('scope', '').strip()
        obj.is_active = request.POST.get('is_active', 'true') == 'true'
        obj.description = request.POST.get('description', '').strip()
        user = request.user
        obj.updated_by = getattr(user, 'name', None) or user.get_full_name() or user.username
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
            'updated_at': to_korea_time_str(obj.updated_at) if obj.updated_at else '-',
            'updated_by': obj.updated_by or '-',
            'type_count': type_count.count(),
        })
    return JsonResponse({'ok': False}, status=400)


@manager_required
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


@manager_required
def threshold_edit(request, pk):
    """임계치 기준 수정 (GET: JSON 반환, POST: 저장)"""
    policy = get_object_or_404(ThresholdPolicy, pk=pk)
    if request.method == 'POST':
        new_metric  = request.POST.get('metric_code', policy.metric_code).strip().lower()
        if new_metric != policy.metric_code and \
                ThresholdPolicy.objects.filter(metric_code=new_metric, category=policy.category).exists():
            return JsonResponse({'ok': False, 'field': 'metric_code',
                                 'error': '동일한 기준 분류에 같은 측정 항목이 이미 등록되어 있습니다.'})
        condition   = request.POST.get('condition', policy.condition).strip()
        warning_val = request.POST.get('warning_val') or None
        danger_val  = request.POST.get('danger_val')  or None
        is_lte = condition == '이하'
        policy.metric_code = new_metric
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
        'updated_at':  to_korea_time_str(policy.updated_at) if policy.updated_at else '',
        'updated_by':  policy.updated_by or '-',
    })


@manager_required
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
@manager_required
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
            'saved_at': to_korea_time_str(s['saved_at']),
            'date':     to_korea_time_str(s['saved_at'], '%Y-%m-%d'),
            'time':     to_korea_time_str(s['saved_at'], '%H:%M'),
            'saved_by': s['saved_by__name'] or '-',
            'data':     s['data'],
        }
        for s in snapshots
    ]

    return render(request, 'admin/safety_checklist/safety_checklist_list.html', {
        'active_menu':  'safety',
        'sections':     sections,
        'snapshots':    snap_data,
        'latest_saved': to_korea_time_str(latest.saved_at, '%Y-%m-%d') if latest else '-',
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
        'saved_at':   to_korea_time_str(snapshot.saved_at),
        'saved_date': to_korea_time_str(snapshot.saved_at, '%Y-%m-%d'),
    })

# ===== VR 교육 관리 =====
@manager_required
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
        'updated_at':       to_korea_time_str(edu.updated_at, '%Y-%m-%d'),
        'duration_badge':   edu.duration_badge,
        'duration_display': edu.duration_display,
    })

# ===== 설비 관리 =====
@manager_required
def facility_list(request):
    """설비 관리 메인 페이지 (Equipment)"""
    qs = Equipment.objects.select_related('updated_by').annotate(
        status_order=Case(
            When(status='active', then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )

    if q := request.GET.get('q'):
        qs = qs.filter(Q(equipment_name__icontains=q) | Q(equipment_code__icontains=q))
    if status := request.GET.get('status'):
        qs = qs.filter(status=status)
    if ps := request.GET.get('power_system'):
        qs = qs.filter(power_system=ps)

    sort_map = {
        '-updated_at': ('status_order', '-updated_at'),
        'updated_at': ('status_order', 'updated_at'),
        'equipment_code': ('equipment_code',),
        'equipment_name': ('equipment_name',),
    }
    sort_key = request.GET.get('sort', '-updated_at')
    qs = qs.order_by(*sort_map.get(sort_key, ('status_order', '-updated_at')))

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # 파라미터 보존 (페이지네이션 링크용)
    params = request.GET.copy()
    params.pop('page', None)
    base_params = params.urlencode()

    # 전력 장비 목록을 DB에서 실제로 가져옴
    all_possible_ps = list(
        Device.objects.filter(device_type='power')
        .order_by('device_uid')
        .values_list('device_uid', flat=True)
    )

    # 이미 다른 설비에 연결된 전력 시스템 (equipment.id 포함)
    assigned_ps_qs = Equipment.objects.exclude(power_system='').values_list('power_system', 'id')
    assigned_ps_map = {ps: eq_id for ps, eq_id in assigned_ps_qs}  # {power_system: equipment_id}
    assigned_ps_set = set(assigned_ps_map.keys())

    # 필터 드롭다운: 실제 연결된 전력 시스템만 (없으면 전체 목록)
    power_systems = sorted(assigned_ps_set) if assigned_ps_set else all_possible_ps

    # 등록 폼: 아직 어떤 설비에도 연결되지 않은 전력 시스템만
    free_ps = [ps for ps in all_possible_ps if ps not in assigned_ps_set]

    return render(request, 'admin/facilities/facility_list.html', {
        'active_menu': 'facility',
        'equipments': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'base_params': base_params,
        'power_systems': power_systems,
        'free_power_systems': free_ps,
        'all_possible_power_systems': all_possible_ps,
        'assigned_ps': sorted(assigned_ps_set),
        'assigned_ps_map': {ps: eq_id for ps, eq_id in assigned_ps_qs},
        'current_sort': sort_key,
    })


@manager_required
def facility_create(request):
    """설비 등록 POST 처리"""
    if request.method == 'POST':
        name = request.POST.get('equipment_name', '').strip()
        power_system = request.POST.get('power_system', '').strip()
        status = request.POST.get('status', 'active')
        note = request.POST.get('note', '').strip()
        if name:
            last = Equipment.objects.order_by('-id').first()
            new_num = (last.id + 1) if last else 1
            code = f'FAC-{new_num:03d}'
            while Equipment.objects.filter(equipment_code=code).exists():
                new_num += 1
                code = f'FAC-{new_num:03d}'
            Equipment.objects.create(
                equipment_name=name,
                equipment_code=code,
                power_system=power_system,
                status=status,
                note=note,
                updated_by=request.user if request.user.is_authenticated else None,
            )
            messages.success(request, f'설비 "{name}"이(가) 등록되었습니다.', extra_tags='facility_register')
        else:
            messages.error(request, '설비명을 입력하세요.')
    return redirect('facility_list')


@manager_required
def facility_edit(request, pk):
    """설비 수정 POST 처리"""
    from django.shortcuts import get_object_or_404
    equipment = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('equipment_name', '').strip()
        power_system = request.POST.get('power_system', '').strip()
        status = request.POST.get('status', 'inactive')
        note = request.POST.get('note', '').strip()
        if name:
            equipment.equipment_name = name
            equipment.power_system = power_system
            equipment.status = status
            equipment.note = note
            equipment.updated_by = request.user if request.user.is_authenticated else None
            equipment.save()
            messages.success(request, f'설비 "{name}" 정보가 수정되었습니다.')
        else:
            messages.error(request, '설비명을 입력하세요.')
    return redirect('facility_list')


@manager_required
def facility_bulk_delete(request):
    """설비 일괄 삭제"""
    if request.method != 'POST':
        return redirect('facility_list')
    ids = request.POST.getlist('equipment_ids')
    if ids:
        count, _ = Equipment.objects.filter(pk__in=ids).delete()
        messages.success(request, str(count), extra_tags='facility_delete')
    return redirect('facility_list')

def _next_device_code(prefix, device_type):
    uids = Device.objects.filter(device_type=device_type).values_list('device_uid', flat=True)
    nums = [int(m.group(1)) for uid in uids if (m := re.search(rf'{prefix}-(\d+)', uid))]
    return f'{prefix}-{(max(nums) + 1 if nums else 1):03d}'


@manager_required
def gas_list(request):
    """유해가스 센서 관리 메인 페이지"""
    sort_map = {
        'sensor_id':          'device_uid',
        '-sensor_id':         '-device_uid',
        '-last_received_at':  '-last_seen_at',
        'last_received_at':   'last_seen_at',
        '-last_inspected_at': '-last_inspected_at',
        'last_inspected_at':  'last_inspected_at',
    }
    sort_key = request.GET.get('sort', 'sensor_id')
    order_by = sort_map.get(sort_key, 'device_uid')

    latest_insp_date_sq = InspectionLog.objects.filter(
        device=OuterRef('pk')
    ).order_by('-inspection_date').values('inspection_date')[:1]

    qs = (
        Device.objects
        .filter(device_type='gas')
        .select_related('department', 'manager')
        .annotate(last_inspected_at=Subquery(latest_insp_date_sq, output_field=DateField()))
        .order_by(order_by)
    )

    if sensor_id := request.GET.get('sensor_id'):
        qs = qs.filter(device_uid=sensor_id)
    if status := request.GET.get('status'):
        is_active_filter = (status == 'active')
        qs = qs.filter(is_active=is_active_filter)
    if connection := request.GET.get('connection'):
        conn_status = 'active' if connection == 'normal' else 'fault'
        qs = qs.filter(status=conn_status)

    paginator = Paginator(qs, 10)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    # 점검 상태 계산 (N+1 없이)
    page_sensors = list(page_obj.object_list)
    device_ids   = [s.id for s in page_sensors]
    all_inspections = (
        InspectionLog.objects
        .filter(device_id__in=device_ids)
        .order_by('-inspection_date')
    )
    action_insp_ids = set(
        ActionLog.objects
        .filter(inspection__device_id__in=device_ids)
        .values_list('inspection_id', flat=True)
    )
    latest_insp_map = {}
    for insp in all_inspections:
        if insp.device_id not in latest_insp_map:
            latest_insp_map[insp.device_id] = insp

    _mac_re = re.compile(r'MAC:\s*([^\n]+)')
    for s in page_sensors:
        latest = latest_insp_map.get(s.id)
        if not latest:
            s.computed_inspection_status = None
        elif latest.status == 'normal':
            s.computed_inspection_status = 'completed'
        elif latest.status == 'action_required':
            if latest.id in action_insp_ids:
                s.computed_inspection_status = 'completed'
            elif latest.expected_action_date:
                s.computed_inspection_status = 'scheduled'
            else:
                s.computed_inspection_status = 'required'
        else:
            s.computed_inspection_status = None
        m = _mac_re.search(s.note or '')
        s.mac_addr  = m.group(1).strip() if m else ''
        s.note_body = _mac_re.sub('', s.note or '').strip() if m else (s.note or '').strip()

    all_sensors = Device.objects.filter(device_type='gas').order_by('device_uid')

    return render(request, 'admin/gas/gas_list.html', {
        'active_menu':  'facility',
        'sensors':      page_sensors,
        'page_obj':     page_obj,
        'total_count':  paginator.count,
        'departments':  Department.objects.all(),
        'managers':     User.objects.filter(user_type__in=['admin', 'manager']),
        'all_sensors':  all_sensors,
        'next_gas_code': _next_device_code('GAS', 'gas'),
        'next_pwr_code': _next_device_code('PWR', 'power'),
        'next_loc_code': _next_device_code('LOC', 'loc'),
        'current_sort': sort_key,
    })


@manager_required
def gas_comm_check(request):
    """장비 통신 확인 API — TCP 소켓으로 IP:PORT 연결 가능 여부 확인"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    import socket

    ip   = request.POST.get('ip', '').strip()
    port_str = request.POST.get('port', '').strip()
    mac  = request.POST.get('mac', '').strip()

    if not ip:
        return JsonResponse({'ok': False, 'error': 'IP 주소를 입력해 주세요.'})
    if not port_str or not port_str.isdigit():
        return JsonResponse({'ok': False, 'error': '포트 번호를 입력해 주세요.'})
    port = int(port_str)
    if port < 1 or port > 65535:
        return JsonResponse({'ok': False, 'error': '포트 번호는 1~65535 범위로 입력해 주세요.'})

    from django.conf import settings
    if not settings.DEBUG:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((ip, port))
            sock.close()
        except socket.gaierror:
            return JsonResponse({'ok': False, 'conn_fail': True, 'error': '장비와 연결할 수 없습니다. 통신 정보를 확인해 주세요.'})
        except Exception:
            return JsonResponse({'ok': False, 'conn_fail': True, 'error': '장비와 연결할 수 없습니다. 통신 정보를 확인해 주세요.'})

        if result != 0:
            return JsonResponse({'ok': False, 'conn_fail': True, 'error': '장비와 연결할 수 없습니다. 통신 정보를 확인해 주세요.'})

    # MAC이 주어진 경우 이미 등록된 장비의 IP와 대조
    if mac:
        matched = Device.objects.filter(ip_address=ip, port=port).first()
        if matched:
            existing_mac = ''
            if matched.note and matched.note.startswith('MAC: '):
                existing_mac = matched.note.split('\n')[0].replace('MAC: ', '').strip()
            if existing_mac and existing_mac != mac:
                return JsonResponse({'ok': False, 'mac_mismatch': True,
                                     'error': '입력한 장비 ID와 실제 응답 장비 정보가 일치하지 않습니다.'})

    now = timezone.localtime(timezone.now())
    pad = lambda n: str(n).zfill(2)
    ts = (f"{now.year}-{pad(now.month)}-{pad(now.day)} "
          f"{pad(now.hour)}:{pad(now.minute)}:{pad(now.second)}")
    return JsonResponse({'ok': True, 'checked_at': ts})


@manager_required
def gas_create(request):
    """장비 등록 API (GAS / PWR / LOC 공통)"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    TYPE_MAP   = {'GAS': 'gas', 'PWR': 'power', 'LOC': 'loc'}
    PREFIX_MAP = {'GAS': 'GAS', 'PWR': 'PWR',   'LOC': 'LOC'}
    NAME_MAP   = {'GAS': '유해가스 센서', 'PWR': '스마트 전력 시스템', 'LOC': '위치 노드'}

    ui_type = (request.POST.get('device_type') or 'GAS').upper()
    if ui_type not in TYPE_MAP:
        return JsonResponse({'ok': False, 'error': '올바르지 않은 장비 유형입니다.'}, status=400)

    db_type = TYPE_MAP[ui_type]
    prefix  = PREFIX_MAP[ui_type]

    from django.db import transaction
    with transaction.atomic():
        existing_uids = list(
            Device.objects.filter(device_type=db_type)
            .values_list('device_uid', flat=True)
            .select_for_update()
        )
        nums = [int(m.group(1)) for uid in existing_uids if (m := re.search(rf'{prefix}-(\d+)', uid))]
        next_num   = max(nums) + 1 if nums else 1
        device_uid = f'{prefix}-{next_num:03d}'

        facility = Facility.objects.first()
        if not facility:
            return JsonResponse({'ok': False, 'error': '사업장 정보가 없습니다.'}, status=400)

        device_name  = request.POST.get('device_name', '').strip() or f'{NAME_MAP[ui_type]} {device_uid}'
        mac          = request.POST.get('device_mac', '').strip()
        dept_id      = request.POST.get('department') or None
        manager_id   = request.POST.get('manager') or None
        equipment_id = request.POST.get('equipment') or None
        ip           = request.POST.get('ip', '').strip() or None
        port_str     = request.POST.get('port', '').strip()
        port         = int(port_str) if port_str.isdigit() else 502
        is_active    = request.POST.get('is_active', 'true') == 'true'
        note         = request.POST.get('note', '').strip()

        if mac and Device.objects.filter(note__startswith=f'MAC: {mac}').exists():
            return JsonResponse({'ok': False, 'duplicate_mac': True, 'error': '이미 등록된 장비 ID입니다.'}, status=400)

        note_full = (f'MAC: {mac}\n' + note if mac else note)

        device = Device.objects.create(
            facility=facility,
            device_type=db_type,
            device_uid=device_uid,
            device_code=device_uid,
            device_name=device_name,
            ip_address=ip,
            port=port,
            is_active=is_active,
            status='active',
            note=note_full,
            department_id=dept_id,
            manager_id=manager_id,
            equipment_id=equipment_id,
        )

    return JsonResponse({'ok': True, 'device_uid': device_uid, 'id': device.id})


@manager_required
def gas_edit(request, pk):
    """유해가스 센서 수정 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    device = get_object_or_404(Device, pk=pk, device_type='gas')

    device_name      = request.POST.get('device_name', '').strip()
    mac              = request.POST.get('device_mac', '').strip()
    dept_id          = request.POST.get('department') or None
    manager_id       = request.POST.get('manager') or None
    ip               = request.POST.get('ip', '').strip() or None
    port_str         = request.POST.get('port', '').strip()
    port             = int(port_str) if port_str.isdigit() else device.port
    is_active        = request.POST.get('is_active', 'true') == 'true'
    install_date_str = request.POST.get('install_date', '').strip()
    note             = request.POST.get('note', '').strip()

    if device_name:
        device.device_name = device_name
    device.ip_address    = ip
    device.port          = port
    device.is_active     = is_active
    device.department_id = dept_id
    device.manager_id    = manager_id
    if mac and Device.objects.filter(note__startswith=f'MAC: {mac}').exclude(pk=pk).exists():
        return JsonResponse({'ok': False, 'duplicate_mac': True, 'error': '이미 등록된 장비 ID입니다.'}, status=400)

    note_full = (f'MAC: {mac}\n' + note if mac else note)
    device.note = note_full

    if install_date_str:
        try:
            device.installed_at = timezone.make_aware(datetime.strptime(install_date_str, '%Y.%m.%d'))
        except ValueError:
            pass

    device.save()
    return JsonResponse({'ok': True})


@manager_required
def gas_bulk_delete(request):
    """유해가스 센서 일괄 삭제 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    ids = request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'ok': False, 'error': '삭제할 항목을 선택해주세요.'}, status=400)

    count, _ = Device.objects.filter(pk__in=ids, device_type='gas').delete()
    return JsonResponse({'ok': True, 'count': count})


@manager_required
def gas_inspections_api(request, pk):
    """장비별 점검 이력 JSON API"""
    device = get_object_or_404(Device, pk=pk, device_type='gas')

    inspections = (
        InspectionLog.objects
        .filter(device=device)
        .select_related('inspector')
        .order_by('-inspection_date')
    )
    action_ids = set(
        ActionLog.objects
        .filter(inspection__in=inspections)
        .values_list('inspection_id', flat=True)
    )
    action_map = {
        a.inspection_id: a
        for a in ActionLog.objects.filter(inspection__in=inspections).select_related('actor')
    }

    data = []
    for log in inspections:
        action = action_map.get(log.id)
        data.append({
            'id':                   log.id,
            'type_code':            log.inspection_type,
            'type_label':           log.get_inspection_type_display(),
            'date':                 log.inspection_date.strftime('%Y-%m-%d'),
            'inspector':            log.inspector.name if log.inspector else '-',
            'status':               log.status,
            'status_label':         log.get_status_display(),
            'expected_action_date': log.expected_action_date.strftime('%Y-%m-%d') if log.expected_action_date else None,
            'note':                 log.note,
            'has_action':           log.id in action_ids,
            'action': {
                'actor':       action.actor.name if action and action.actor else '-',
                'action_date': action.action_date.strftime('%Y-%m-%d') if action else None,
                'note':        action.action_note if action else '',
            } if action else None,
        })

    # 점검 요약
    latest = inspections.first()
    summary = None
    if latest:
        has_action = latest.id in action_ids
        if latest.status == 'normal' or has_action:
            check_status = '점검 완료'
            current_state = '정상'
        elif latest.expected_action_date:
            check_status = '점검 예정'
            current_state = '조치 필요'
        else:
            check_status = '점검 필요'
            current_state = '조치 필요'
        summary = {
            'check_status':        check_status,
            'last_inspected':      latest.inspection_date.strftime('%Y-%m-%d'),
            'expected_action_date': latest.expected_action_date.strftime('%Y-%m-%d') if latest.expected_action_date else '-',
            'current_state':       current_state,
        }

    return JsonResponse({'ok': True, 'inspections': data, 'summary': summary})


@manager_required
def gas_inspect_create(request):
    """점검 이력 등록 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    device_id    = request.POST.get('device_id')
    inspect_type = request.POST.get('inspect_type', '').strip()
    date_str     = request.POST.get('inspect_date', '').strip()
    inspector_name = request.POST.get('inspector', '').strip()
    status_val   = request.POST.get('status', '').strip()
    action_date_str = request.POST.get('expected_action_date', '').strip()
    note         = request.POST.get('note', '').strip()

    device = get_object_or_404(Device, pk=device_id, device_type='gas')

    try:
        inspect_date = datetime.strptime(date_str, '%Y.%m.%d').date()
    except (ValueError, TypeError):
        inspect_date = timezone.localdate()

    action_date = None
    if action_date_str:
        try:
            action_date = datetime.strptime(action_date_str, '%Y.%m.%d').date()
        except ValueError:
            pass

    inspector = User.objects.filter(name=inspector_name).first() if inspector_name else None

    log = InspectionLog.objects.create(
        device=device,
        inspection_type=inspect_type,
        inspection_date=inspect_date,
        status=status_val,
        note=note,
        expected_action_date=action_date,
        inspector=inspector,
    )
    return JsonResponse({'ok': True, 'id': log.id})


@manager_required
def gas_action_create(request, inspection_id):
    """조치 이력 등록 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    inspection = get_object_or_404(InspectionLog, pk=inspection_id)

    if ActionLog.objects.filter(inspection=inspection).exists():
        return JsonResponse({'ok': False, 'error': '이미 조치가 등록되었습니다.'}, status=400)

    action_date_str = request.POST.get('action_date', '').strip()
    action_note     = request.POST.get('action_note', '').strip()
    actor_name      = request.POST.get('actor', '').strip()

    try:
        action_date = datetime.strptime(action_date_str, '%Y.%m.%d').date()
    except (ValueError, TypeError):
        action_date = timezone.localdate()

    actor = User.objects.filter(name=actor_name).first() if actor_name else None

    ActionLog.objects.create(
        inspection=inspection,
        actor=actor,
        action_date=action_date,
        action_note=action_note,
    )
    return JsonResponse({'ok': True})

@manager_required
def power_list(request):
    """스마트 전력 시스템 관리 메인 페이지"""
    sort_map = {
        'device_uid':         'device_uid',
        '-device_uid':        '-device_uid',
        '-last_seen_at':      '-last_seen_at',
        'last_seen_at':       'last_seen_at',
        '-last_inspected_at': '-last_inspected_at',
        'last_inspected_at':  'last_inspected_at',
        'manager_asc':        'manager__name',
        'manager_desc':       '-manager__name',
    }
    sort_key = request.GET.get('sort', 'device_uid')
    order_by = sort_map.get(sort_key, 'device_uid')

    latest_insp_date_sq = InspectionLog.objects.filter(
        device=OuterRef('pk')
    ).order_by('-inspection_date').values('inspection_date')[:1]

    qs = (
        Device.objects
        .filter(device_type='power')
        .select_related('manager', 'equipment', 'department')
        .annotate(last_inspected_at=Subquery(latest_insp_date_sq, output_field=DateField()))
        .order_by(order_by)
    )

    if device_uid := request.GET.get('device_name'):
        qs = qs.filter(device_uid=device_uid)
    if equipment_id := request.GET.get('equipment'):
        qs = qs.filter(equipment_id=equipment_id)
    if status_val := request.GET.get('status'):
        qs = qs.filter(is_active=(status_val == 'active'))

    inspect_filter = request.GET.get('inspect', '')

    if inspect_filter:
        # 점검 상태 필터: 전체 records에서 계산 후 파이썬 필터
        all_devices = list(qs)
        device_ids  = [d.id for d in all_devices]
        all_inspections = (
            InspectionLog.objects.filter(device_id__in=device_ids).order_by('-inspection_date')
        )
        action_insp_ids = set(
            ActionLog.objects.filter(inspection__device_id__in=device_ids).values_list('inspection_id', flat=True)
        )
        latest_insp_map = {}
        for insp in all_inspections:
            if insp.device_id not in latest_insp_map:
                latest_insp_map[insp.device_id] = insp

        insp_status_map = {'required': 'required', 'done': 'completed', 'scheduled': 'scheduled', 'none': None}
        target_status   = insp_status_map.get(inspect_filter)

        for d in all_devices:
            latest = latest_insp_map.get(d.id)
            if not latest:
                d.computed_inspection_status = None
            elif latest.status == 'normal':
                d.computed_inspection_status = 'completed'
            elif latest.status == 'action_required':
                if latest.id in action_insp_ids:
                    d.computed_inspection_status = 'completed'
                elif latest.expected_action_date:
                    d.computed_inspection_status = 'scheduled'
                else:
                    d.computed_inspection_status = 'required'
            else:
                d.computed_inspection_status = None

        filtered = [d for d in all_devices if d.computed_inspection_status == target_status]
        paginator   = Paginator(filtered, 10)
        page_obj    = paginator.get_page(request.GET.get('page', 1))
        page_devices = list(page_obj.object_list)
    else:
        paginator    = Paginator(qs, 10)
        page_obj     = paginator.get_page(request.GET.get('page', 1))
        page_devices = list(page_obj.object_list)
        device_ids   = [d.id for d in page_devices]

        all_inspections = (
            InspectionLog.objects.filter(device_id__in=device_ids).order_by('-inspection_date')
        )
        action_insp_ids = set(
            ActionLog.objects.filter(inspection__device_id__in=device_ids).values_list('inspection_id', flat=True)
        )
        latest_insp_map = {}
        for insp in all_inspections:
            if insp.device_id not in latest_insp_map:
                latest_insp_map[insp.device_id] = insp

        for d in page_devices:
            latest = latest_insp_map.get(d.id)
            if not latest:
                d.computed_inspection_status = None
            elif latest.status == 'normal':
                d.computed_inspection_status = 'completed'
            elif latest.status == 'action_required':
                if latest.id in action_insp_ids:
                    d.computed_inspection_status = 'completed'
                elif latest.expected_action_date:
                    d.computed_inspection_status = 'scheduled'
                else:
                    d.computed_inspection_status = 'required'
            else:
                d.computed_inspection_status = None

    _mac_re = re.compile(r'MAC:\s*([^\n]+)')
    for d in page_devices:
        m = _mac_re.search(d.note or '')
        d.mac_addr  = m.group(1).strip() if m else ''
        d.note_body = _mac_re.sub('', d.note or '').strip() if m else (d.note or '').strip()

    all_pwr_uids   = Device.objects.filter(device_type='power').order_by('device_uid').values_list('device_uid', flat=True)
    all_equipments = Equipment.objects.order_by('equipment_name')

    params = request.GET.copy()
    params.pop('page', None)
    base_params = params.urlencode()

    return render(request, 'admin/power/power_list.html', {
        'active_menu':    'facility',
        'devices':        page_devices,
        'page_obj':       page_obj,
        'total_count':    paginator.count,
        'all_pwr_uids':   all_pwr_uids,
        'all_equipments': all_equipments,
        'current_sort':   sort_key,
        'base_params':    base_params,
        'departments':    Department.objects.all(),
        'managers':       User.objects.filter(user_type__in=['admin', 'manager']),
        'next_gas_code':  _next_device_code('GAS', 'gas'),
        'next_pwr_code':  _next_device_code('PWR', 'power'),
        'next_loc_code':  _next_device_code('LOC', 'loc'),
    })

@manager_required
def power_bulk_delete(request):
    """스마트 전력 시스템 일괄 삭제 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    ids = request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'ok': False, 'error': '삭제할 항목을 선택해주세요.'}, status=400)
    count, _ = Device.objects.filter(pk__in=ids, device_type='power').delete()
    return JsonResponse({'ok': True, 'count': count})


@manager_required
def power_edit(request, pk):
    """스마트 전력 시스템 수정 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    device = get_object_or_404(Device, pk=pk, device_type='power')

    device_name  = request.POST.get('device_name', '').strip()
    mac          = request.POST.get('device_mac', '').strip()
    dept_id      = request.POST.get('department') or None
    manager_id   = request.POST.get('manager') or None
    equipment_id = request.POST.get('equipment') or None
    ip           = request.POST.get('ip', '').strip() or None
    port_str     = request.POST.get('port', '').strip()
    port         = int(port_str) if port_str.isdigit() else device.port
    is_active    = request.POST.get('is_active', 'true') == 'true'
    note         = request.POST.get('note', '').strip()

    device.device_name   = device_name
    device.ip_address    = ip
    device.port          = port
    device.is_active     = is_active
    device.department_id = dept_id
    device.manager_id    = manager_id
    device.equipment_id  = equipment_id
    device.note          = (f'MAC: {mac}\n' + note) if mac else note
    device.save()
    return JsonResponse({'ok': True})


@manager_required
def power_inspections_api(request, pk):
    """전력 장비별 점검 이력 JSON API"""
    device = get_object_or_404(Device, pk=pk, device_type='power')

    inspections = (
        InspectionLog.objects
        .filter(device=device)
        .select_related('inspector')
        .order_by('-inspection_date')
    )
    action_ids = set(
        ActionLog.objects
        .filter(inspection__in=inspections)
        .values_list('inspection_id', flat=True)
    )
    action_map = {
        a.inspection_id: a
        for a in ActionLog.objects.filter(inspection__in=inspections).select_related('actor')
    }

    data = []
    for log in inspections:
        action = action_map.get(log.id)
        data.append({
            'id':                   log.id,
            'type_code':            log.inspection_type,
            'type_label':           log.get_inspection_type_display(),
            'date':                 log.inspection_date.strftime('%Y-%m-%d'),
            'inspector':            log.inspector.name if log.inspector else '-',
            'status':               log.status,
            'status_label':         log.get_status_display(),
            'expected_action_date': log.expected_action_date.strftime('%Y-%m-%d') if log.expected_action_date else None,
            'note':                 log.note,
            'has_action':           log.id in action_ids,
            'action': {
                'actor':       action.actor.name if action and action.actor else '-',
                'action_date': action.action_date.strftime('%Y-%m-%d') if action else None,
                'note':        action.action_note if action else '',
            } if action else None,
        })

    latest = inspections.first()
    summary = None
    if latest:
        has_action = latest.id in action_ids
        if latest.status == 'normal':
            check_status  = '점검 완료'
            current_state = '정상'
        elif has_action:
            check_status  = '점검 완료'
            current_state = '조치 완료'
        else:
            check_status  = '점검 필요'
            current_state = '조치 필요'
        summary = {
            'check_status':         check_status,
            'last_inspected':       latest.inspection_date.strftime('%Y-%m-%d'),
            'expected_action_date': latest.expected_action_date.strftime('%Y-%m-%d') if latest.expected_action_date else '-',
            'current_state':        current_state,
        }

    return JsonResponse({'ok': True, 'inspections': data, 'summary': summary})


@require_POST
def power_action_create(request, inspection_id):
    """스마트 전력 시스템 조치 이력 등록 API"""
    inspection = get_object_or_404(InspectionLog, pk=inspection_id, device__device_type='power')

    if ActionLog.objects.filter(inspection=inspection).exists():
        return JsonResponse({'ok': False, 'error': '이미 조치가 등록되었습니다.'}, status=400)

    action_date_str = request.POST.get('action_date', '').strip()
    action_note     = request.POST.get('action_note', '').strip()
    actor_name      = request.POST.get('actor', '').strip()

    try:
        action_date = datetime.strptime(action_date_str, '%Y.%m.%d').date()
    except (ValueError, TypeError):
        action_date = timezone.localdate()

    actor = User.objects.filter(name=actor_name).first() if actor_name else None

    ActionLog.objects.create(
        inspection=inspection,
        actor=actor,
        action_date=action_date,
        action_note=action_note,
    )
    return JsonResponse({'ok': True})


@manager_required
def power_inspect_create(request):
    """전력 장비 점검 이력 등록 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    device_id      = request.POST.get('device_id')
    inspect_type   = request.POST.get('inspect_type', '').strip()
    date_str       = request.POST.get('inspect_date', '').strip()
    inspector_name = request.POST.get('inspector', '').strip()
    status_val     = request.POST.get('status', '').strip()
    action_date_str = request.POST.get('expected_action_date', '').strip()
    note           = request.POST.get('note', '').strip()

    device = get_object_or_404(Device, pk=device_id, device_type='power')

    try:
        inspect_date = datetime.strptime(date_str, '%Y.%m.%d').date()
    except (ValueError, TypeError):
        inspect_date = timezone.localdate()

    action_date = None
    if action_date_str:
        try:
            action_date = datetime.strptime(action_date_str, '%Y.%m.%d').date()
        except ValueError:
            pass

    inspector = User.objects.filter(name=inspector_name).first() if inspector_name else None

    log = InspectionLog.objects.create(
        device=device,
        inspection_type=inspect_type,
        inspection_date=inspect_date,
        status=status_val,
        note=note,
        expected_action_date=action_date,
        inspector=inspector,
    )
    return JsonResponse({'ok': True, 'id': log.id})


@manager_required
def node_list(request):
    """위치 노드 관리 메인 페이지"""
    sort_map = {
        'node_id_asc':  F('device_code').asc(),
        'node_id_desc': F('device_code').desc(),
        'recv_new':     F('last_seen_at').desc(nulls_last=True),
        'recv_old':     F('last_seen_at').asc(nulls_last=True),
        'inspect_new':  F('last_inspected_at').desc(nulls_last=True),
        'inspect_old':  F('last_inspected_at').asc(nulls_last=True),
        'manager_asc':  F('manager__name').asc(nulls_last=True),
        'manager_desc': F('manager__name').desc(nulls_last=True),
    }
    sort_key = request.GET.get('sort', 'node_id_asc')
    order_by = sort_map.get(sort_key, F('device_code').asc())

    latest_insp_sq = InspectionLog.objects.filter(
        device=OuterRef('pk')
    ).order_by('-inspection_date').values('inspection_date')[:1]

    qs = (
        Device.objects
        .filter(device_type='loc')
        .select_related('manager', 'department')
        .annotate(last_inspected_at=Subquery(latest_insp_sq, output_field=DateField()))
        .order_by(order_by)
    )

    if node_id := request.GET.get('node_id'):
        qs = qs.filter(device_code=node_id)
    if dev_status := request.GET.get('device_status'):
        qs = qs.filter(is_active=(dev_status == 'active'))
    if connection := request.GET.get('connection'):
        qs = qs.filter(status='active' if connection == 'normal' else 'fault')

    paginator = Paginator(qs, 10)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    page_nodes = list(page_obj.object_list)
    device_ids = [n.id for n in page_nodes]

    all_insp = (
        InspectionLog.objects
        .filter(device_id__in=device_ids)
        .order_by('-inspection_date')
    )
    action_ids = set(
        ActionLog.objects
        .filter(inspection__device_id__in=device_ids)
        .values_list('inspection_id', flat=True)
    )
    latest_map = {}
    for insp in all_insp:
        if insp.device_id not in latest_map:
            latest_map[insp.device_id] = insp

    _mac_re = re.compile(r'MAC:\s*([^\n]+)')
    for n in page_nodes:
        m = _mac_re.search(n.note or '')
        n.mac_addr  = m.group(1).strip() if m else ''
        n.note_body = _mac_re.sub('', n.note or '').strip() if m else (n.note or '').strip()

        latest = latest_map.get(n.id)
        if not n.is_active:
            n.computed_inspection_status = None
        elif not latest:
            n.computed_inspection_status = 'scheduled'
        elif latest.status == 'normal':
            n.computed_inspection_status = 'completed'
        elif latest.status == 'action_required':
            if latest.id in action_ids:
                n.computed_inspection_status = 'completed'
            elif latest.expected_action_date:
                n.computed_inspection_status = 'scheduled'
            else:
                n.computed_inspection_status = 'required'
        else:
            n.computed_inspection_status = None

    all_nodes = Device.objects.filter(device_type='loc').order_by('device_code')

    params = request.GET.copy()
    params.pop('page', None)
    base_params = params.urlencode()

    return render(request, 'admin/node/node_list.html', {
        'active_menu':     'facility',
        'nodes':           page_nodes,
        'page_obj':        page_obj,
        'total_count':     paginator.count,
        'all_nodes':       all_nodes,
        'departments':     Department.objects.all(),
        'managers':        User.objects.filter(user_type__in=['admin', 'manager']),
        'current_sort':    sort_key,
        'q_node_id':       request.GET.get('node_id', ''),
        'q_device_status': request.GET.get('device_status', ''),
        'q_connection':    request.GET.get('connection', ''),
        'base_params':     base_params,
        'next_gas_code':   _next_device_code('GAS', 'gas'),
        'next_pwr_code':   _next_device_code('PWR', 'power'),
        'next_loc_code':   _next_device_code('LOC', 'loc'),
    })


@require_POST
def node_bulk_delete(request):
    """위치 노드 일괄 삭제.

    Device(loc) 삭제 → facilities.signals 가 연결된 LocationNode 도 자동 삭제.
    점검 이력이 있는 노드는 PROTECT 로 막혀 개별 실패로 분류된다.
    """
    from django.db.models import ProtectedError

    ids_raw = request.POST.get('ids', '')
    ids = [i for i in ids_raw.split(',') if i.strip().isdigit()]

    deleted = 0
    protected = []
    for dev in Device.objects.filter(pk__in=ids, device_type='loc'):
        try:
            label = dev.device_code
            dev.delete()
            deleted += 1
        except ProtectedError:
            protected.append(label)

    if protected:
        return JsonResponse({
            'ok': deleted > 0,
            'deleted': deleted,
            'protected': protected,
            'message': f'점검 이력이 있어 삭제할 수 없는 노드: {", ".join(protected)}',
        })
    return JsonResponse({'ok': True, 'deleted': deleted})


@manager_required
def node_edit(request, pk):
    """위치 노드 수정 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    device = get_object_or_404(Device, pk=pk, device_type='loc')

    device_name  = request.POST.get('device_name', '').strip()
    mac          = request.POST.get('device_mac', '').strip()
    dept_id      = request.POST.get('department') or None
    manager_id   = request.POST.get('manager') or None
    ip           = request.POST.get('ip', '').strip() or None
    port_str     = request.POST.get('port', '').strip()
    port         = int(port_str) if port_str.isdigit() else device.port
    is_active    = request.POST.get('is_active', 'true') == 'true'
    note         = request.POST.get('note', '').strip()

    if device_name:
        device.device_name = device_name
    device.ip_address    = ip
    device.port          = port
    device.is_active     = is_active
    device.department_id = dept_id
    device.manager_id    = manager_id
    device.note          = (f'MAC: {mac}\n' + note) if mac else note
    device.save()
    return JsonResponse({'ok': True})


@manager_required
def node_inspections_api(request, pk):
    """위치 노드별 점검 이력 JSON API"""
    device = get_object_or_404(Device, pk=pk, device_type='loc')
    inspections = (
        InspectionLog.objects
        .filter(device=device)
        .select_related('inspector')
        .order_by('-inspection_date')
    )
    action_ids = set(
        ActionLog.objects
        .filter(inspection__device=device)
        .values_list('inspection_id', flat=True)
    )
    action_map = {
        a.inspection_id: a
        for a in ActionLog.objects.filter(inspection__device=device).select_related('actor')
    }

    data = []
    for log in inspections:
        action = action_map.get(log.id)
        data.append({
            'id':                   log.id,
            'type_code':            log.inspection_type,
            'type_label':           log.get_inspection_type_display(),
            'date':                 log.inspection_date.strftime('%Y-%m-%d'),
            'inspector':            log.inspector.name if log.inspector else '-',
            'status':               log.status,
            'status_label':         log.get_status_display(),
            'expected_action_date': log.expected_action_date.strftime('%Y-%m-%d') if log.expected_action_date else None,
            'note':                 log.note,
            'has_action':           log.id in action_ids,
            'action': {
                'actor':       action.actor.name if action and action.actor else '-',
                'action_date': action.action_date.strftime('%Y-%m-%d') if action else None,
                'note':        action.action_note if action else '',
            } if action else None,
        })

    latest = inspections.first()
    summary = None
    if latest:
        has_action = latest.id in action_ids
        if latest.status == 'normal':
            check_status  = '점검 완료'
            current_state = '정상'
        elif has_action:
            check_status  = '점검 완료'
            current_state = '조치 완료'
        else:
            check_status  = '점검 필요'
            current_state = '조치 필요'
        summary = {
            'check_status':   check_status,
            'last_inspected': latest.inspection_date.strftime('%Y-%m-%d'),
            'next_inspect':   latest.expected_action_date.strftime('%Y-%m-%d') if latest.expected_action_date else '-',
            'current_state':  current_state,
        }

    return JsonResponse({'ok': True, 'inspections': data, 'summary': summary})


@require_POST
def node_action_create(request, inspection_id):
    """위치 노드 조치 이력 등록 API"""
    inspection = get_object_or_404(InspectionLog, pk=inspection_id, device__device_type='loc')

    if ActionLog.objects.filter(inspection=inspection).exists():
        return JsonResponse({'ok': False, 'error': '이미 조치가 등록되었습니다.'}, status=400)

    action_date_str = request.POST.get('action_date', '').strip()
    action_note     = request.POST.get('action_note', '').strip()
    actor_name      = request.POST.get('actor', '').strip()

    try:
        action_date = datetime.strptime(action_date_str, '%Y.%m.%d').date()
    except (ValueError, TypeError):
        action_date = timezone.localdate()

    actor = User.objects.filter(name=actor_name).first() if actor_name else None

    ActionLog.objects.create(
        inspection=inspection,
        actor=actor,
        action_date=action_date,
        action_note=action_note,
    )
    return JsonResponse({'ok': True})


@manager_required
def node_inspect_create(request):
    """위치 노드 점검 이력 등록 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    device_id       = request.POST.get('device_id')
    inspect_type    = request.POST.get('inspect_type', '').strip()
    date_str        = request.POST.get('inspect_date', '').strip()
    inspector_name  = request.POST.get('inspector', '').strip()
    status_val      = request.POST.get('status', '').strip()
    action_date_str = request.POST.get('expected_action_date', '').strip()
    note            = request.POST.get('note', '').strip()

    device = get_object_or_404(Device, pk=device_id, device_type='loc')

    try:
        inspect_date = datetime.strptime(date_str, '%Y.%m.%d').date()
    except (ValueError, TypeError):
        inspect_date = timezone.localdate()

    action_date = None
    if action_date_str:
        try:
            action_date = datetime.strptime(action_date_str, '%Y.%m.%d').date()
        except ValueError:
            pass

    inspector = User.objects.filter(name=inspector_name).first() if inspector_name else None

    log = InspectionLog.objects.create(
        device=device,
        inspection_type=inspect_type,
        inspection_date=inspect_date,
        status=status_val,
        note=note,
        expected_action_date=action_date,
        inspector=inspector,
    )
    return JsonResponse({'ok': True, 'id': log.id})

# ===== 데이터 관리 =====
def _parse_date_range(request):
    """GET 파라미터에서 date_from / date_to를 파싱, 기본값 = 최근 7일"""
    today = timezone.localdate()
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


def _date_range_to_dt(date_from, date_to):
    """date 범위를 KST 기준 UTC datetime 범위로 변환 (measured_at 필터용)."""
    from zoneinfo import ZoneInfo
    kst = ZoneInfo('Asia/Seoul')
    dt_from = datetime(date_from.year, date_from.month, date_from.day, 0, 0, 0, tzinfo=kst)
    dt_to   = datetime(date_to.year,   date_to.month,   date_to.day,   23, 59, 59, 999999, tzinfo=kst)
    return dt_from, dt_to


@manager_required
def gas_data_list(request):
    """유해가스 센서 데이터 관리"""
    date_from, date_to = _parse_date_range(request)
    device_uid = request.GET.get('device_uid', '')
    sort       = request.GET.get('sort', 'new')
    page_num   = request.GET.get('page', 1)

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    dt_from, dt_to = _date_range_to_dt(date_from, date_to)
    qs = GasReading.objects.select_related('device').filter(
        measured_at__gte=dt_from,
        measured_at__lte=dt_to,
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


@manager_required
def gas_data_export(request):
    """유해가스 센서 데이터 CSV 내보내기"""
    date_from, date_to = _parse_date_range(request)
    device_uid = request.GET.get('device_uid', '')
    sort       = request.GET.get('sort', 'new')

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    dt_from, dt_to = _date_range_to_dt(date_from, date_to)
    qs = GasReading.objects.select_related('device').filter(
        measured_at__gte=dt_from,
        measured_at__lte=dt_to,
    ).order_by(ordering)
    if device_uid:
        qs = qs.filter(device__device_uid=device_uid)

    filename = f"gas_data_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['수집 시각(KST)', '장비명', 'CO2', 'O2', 'CO', 'H2S', 'NH3', 'VOC', 'NO2', 'O3', 'SO2'])
    for r in qs.iterator(chunk_size=500):
        def fmt(val, unit='ppm'):
            return f'{val:.1f} {unit}' if val is not None else '-'
        writer.writerow([
            to_korea_time_str(r.measured_at, '%Y-%m-%d %H:%M:%S'),
            r.device.device_uid,
            fmt(r.co2),
            fmt(r.o2, '%'),
            fmt(r.co),
            fmt(r.h2s),
            fmt(r.nh3),
            fmt(r.voc),
            fmt(r.no2),
            fmt(r.o3),
            fmt(r.so2),
        ])
    return response


@manager_required
def power_data_list(request):
    """스마트 전력 시스템 데이터 관리"""
    date_from, date_to = _parse_date_range(request)
    dt_from, dt_to = _date_range_to_dt(date_from, date_to)
    sort     = request.GET.get('sort', 'new')
    page_num = request.GET.get('page', 1)

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = PowerReading.objects.select_related('device').filter(
        measured_at__gte=dt_from,
        measured_at__lte=dt_to,
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


@manager_required
def power_data_export(request):
    """스마트 전력 시스템 데이터 CSV 내보내기"""
    date_from, date_to = _parse_date_range(request)
    dt_from, dt_to = _date_range_to_dt(date_from, date_to)
    sort = request.GET.get('sort', 'new')

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = PowerReading.objects.select_related('device').filter(
        measured_at__gte=dt_from,
        measured_at__lte=dt_to,
    ).order_by(ordering)

    filename = f"power_data_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['수집 시각(KST)', '장비명', '전력값(W)', '온도(℃)'])
    for r in qs.iterator(chunk_size=500):
        writer.writerow([
            to_korea_time_str(r.measured_at, '%Y-%m-%d %H:%M:%S'),
            r.device.device_uid,
            r.power_w if r.power_w >= 0 else '-',
            f'{r.temperature_c:.1f}' if r.temperature_c is not None else '-',
        ])
    return response


@manager_required
def node_data_list(request):
    """위치 노드 데이터 관리"""
    date_from, date_to = _parse_date_range(request)
    dt_from, dt_to = _date_range_to_dt(date_from, date_to)
    node_name = request.GET.get('node_name', '')
    sort      = request.GET.get('sort', 'new')
    page_num  = request.GET.get('page', 1)

    ordering = 'received_at' if sort == 'old' else '-received_at'
    # x__isnull=False: heartbeat 페이로드(좌표 null)는 제외하고 실제 측위 이벤트만 노출
    qs = NodeReading.objects.select_related('node').filter(
        received_at__gte=dt_from,
        received_at__lte=dt_to,
        x__isnull=False,
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


@manager_required
def node_data_export(request):
    """위치 노드 데이터 CSV 내보내기"""
    date_from, date_to = _parse_date_range(request)
    dt_from, dt_to = _date_range_to_dt(date_from, date_to)
    node_name = request.GET.get('node_name', '')
    sort      = request.GET.get('sort', 'new')

    ordering = 'received_at' if sort == 'old' else '-received_at'
    qs = NodeReading.objects.select_related('node').filter(
        received_at__gte=dt_from,
        received_at__lte=dt_to,
        x__isnull=False,
    ).order_by(ordering)
    if node_name:
        qs = qs.filter(node__node_name__icontains=node_name)

    filename = f"node_data_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['수신 시각(KST)', '장비명', '위치 좌표'])
    for r in qs.iterator(chunk_size=500):
        x_str = f'{r.x:.3f}' if r.x is not None else '-'
        y_str = f'{r.y:.3f}' if r.y is not None else '-'
        coord = f'{x_str} / {y_str}'
        writer.writerow([
            to_korea_time_str(r.received_at, '%Y-%m-%d %H:%M:%S'),
            r.node.node_name,
            coord,
        ])
    return response


@manager_required
def worker_data_list(request):
    """작업자 위치 데이터 관리"""
    date_from, date_to = _parse_date_range(request)
    dt_from, dt_to = _date_range_to_dt(date_from, date_to)
    worker_name = request.GET.get('worker_name', '')
    sort        = request.GET.get('sort', 'new')
    page_num    = request.GET.get('page', 1)

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = WorkerLocation.objects.select_related('worker').filter(
        measured_at__gte=dt_from,
        measured_at__lte=dt_to,
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


@manager_required
def worker_data_export(request):
    """작업자 위치 데이터 CSV 내보내기"""
    date_from, date_to = _parse_date_range(request)
    dt_from, dt_to = _date_range_to_dt(date_from, date_to)
    worker_name = request.GET.get('worker_name', '')
    sort        = request.GET.get('sort', 'new')

    ordering = 'measured_at' if sort == 'old' else '-measured_at'
    qs = WorkerLocation.objects.select_related('worker').filter(
        measured_at__gte=dt_from,
        measured_at__lte=dt_to,
    ).order_by(ordering)
    if worker_name:
        qs = qs.filter(worker__worker_name__icontains=worker_name)

    filename = f"worker_data_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['수신 시각(KST)', '작업자명', '위치 좌표'])
    for r in qs.iterator(chunk_size=500):
        writer.writerow([
            to_korea_time_str(r.measured_at, '%Y-%m-%d %H:%M:%S'),
            r.worker.worker_name,
            f'{r.x:.3f} / {r.y:.3f}',
        ])
    return response


@manager_required
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


@manager_required
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


@manager_required
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


@manager_required
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

@manager_required
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
            'modDate':       to_korea_time_str(n.updated_at, '%Y-%m-%d'),
        }
        for n in notices
    ]
    return render(request, 'admin/notice/notice_list.html', {
        'active_menu':  'notice',
        'notices_data': notices_data,
    })


@manager_required
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


@manager_required
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


@manager_required
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


@manager_required
def notice_attachment_download(request, pk):
    att = get_object_or_404(NoticeAttachment, pk=pk)
    return FileResponse(att.file.open('rb'), as_attachment=True, filename=att.original_name)


# ── 대시보드용 공지사항 (일반 사용자 열람) ────────────────────────────────

@login_required
def dashboard_notice_list(request):
    """대시보드 사이드바 공지사항 목록 페이지."""
    qs = (
        Notice.objects
        .filter(is_exposed=True)
        .select_related('author')
        .order_by('-created_at')
    )
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    start = page_obj.start_index()
    numbered = [(start + i, notice) for i, notice in enumerate(page_obj)]
    return render(request, 'dashboard/notice_list.html', {
        'notices':    page_obj,
        'page_obj':   page_obj,
        'numbered':   numbered,
        'total_count': paginator.count,
    })


@login_required
def dashboard_notice_detail(request, pk):
    """대시보드 공지사항 상세 페이지."""
    notice = get_object_or_404(
        Notice.objects.select_related('author').prefetch_related('attachments'),
        pk=pk, is_exposed=True,
    )
    Notice.objects.filter(pk=pk).update(view_count=db_models.F('view_count') + 1)
    notice.refresh_from_db(fields=['view_count'])

    prev_notice = Notice.objects.filter(pk__lt=pk, is_exposed=True).order_by('-pk').first()
    next_notice = Notice.objects.filter(pk__gt=pk, is_exposed=True).order_by('pk').first()

    return render(request, 'dashboard/notice_detail.html', {
        'notice':      notice,
        'prev_notice': prev_notice,
        'next_notice': next_notice,
    })

# ===== 메뉴 관리 =====
@admin_required
def menu_manage(request):
    """메뉴 관리 (슈퍼관리자 전용)"""
    return render(request, 'admin/menu_manage/menu_manage.html', {'active_menu': 'menu_manage'})

# ===== 알림/이벤트 관리 =====

@manager_required
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
            'modDate':   to_korea_time_str(p.updated_at, '%Y-%m-%d'),
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
            'modDate':   to_korea_time_str(policy.updated_at, '%Y-%m-%d'),
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

@manager_required
def event_history_list(request):
    from alerts.models import AlarmEvent

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
            'time':       to_korea_time_str(e.occurred_at, '%Y-%m-%d %H:%M:%S'),
            'date':       to_korea_time_str(e.occurred_at, '%Y-%m-%d'),
            'type':       EVENT_TYPE_LABEL.get(e.event_type, e.event_type),
            'target':     target,
            'policy':     e.rule.rule_name if e.rule else '-',
            'status':     STATUS_LABEL.get(e.event_status, e.event_status),
            'releasedAt': to_korea_time_str(e.closed_at, '%Y-%m-%d %H:%M:%S') if e.closed_at else '-',
            'content':    e.message or e.title,
            'memo':       e.title,
        })

    today = timezone.localdate().strftime('%Y-%m-%d')

    return render(request, 'admin/alarm/event_history_list.html', {
        'active_menu':  'alarm',
        'events_data':  events_data,
        'today':        today,
    })

@manager_required
def alarm_send_history_list(request):

    histories = AlarmSendHistory.objects.order_by('-sent_at')[:500]

    sends_data = [
        {
            'id':        h.pk,
            'time':      to_korea_time_str(h.sent_at, '%Y-%m-%d %H:%M:%S'),
            'date':      to_korea_time_str(h.sent_at, '%Y-%m-%d'),
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

    today = timezone.localdate().strftime('%Y-%m-%d')

    return render(request, 'admin/alarm/alarm_send_history_list.html', {
        'active_menu': 'alarm',
        'sends_data':  sends_data,
        'today':       today,
    })

# ===== 로그 및 연동 관리 =====
@manager_required
def system_log_list(request):
    """시스템 로그"""
    from core.models import ChangeLog
    qs = SystemLog.objects.order_by('-created_at')
    if log_type := request.GET.get('log_type'):
        qs = qs.filter(log_type=log_type)
    if q := request.GET.get('q'):
        qs = qs.filter(Q(message__icontains=q) | Q(source__icontains=q))
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    log_types = SystemLog.objects.values_list('log_type', flat=True).distinct()
    return render(request, 'admin/log/system_log_list.html', {
        'active_menu': 'log',
        'logs': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'log_types': log_types,
    })

@manager_required
def user_activity_log_list(request):
    """사용자 활동 로그"""
    from accounts.models import LoginHistory
    qs = LoginHistory.objects.select_related('user').order_by('-login_at')
    if user_id := request.GET.get('user_id'):
        qs = qs.filter(user_id=user_id)
    if result := request.GET.get('result'):
        qs = qs.filter(login_result=result)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'admin/log/user_activity_log_list.html', {
        'active_menu': 'log',
        'logs': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'users': User.objects.all(),
    })

@manager_required
def integration_log_list(request):
    """연동 로그"""
    from core.models import ChangeLog
    qs = ChangeLog.objects.order_by('-created_at')
    if target_type := request.GET.get('target_type'):
        qs = qs.filter(target_type=target_type)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'admin/log/integration_log_list.html', {
        'active_menu': 'log',
        'logs': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
    })

@manager_required
def map_edit_log_list(request):
    """지도 편집 로그"""
    from core.models import ChangeLog
    qs = ChangeLog.objects.filter(target_type__icontains='map').order_by('-created_at')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'admin/log/map_edit_log_list.html', {
        'active_menu': 'log',
        'logs': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
    })

# ===== 지도 관리 =====

@manager_required
def map_editor(request):
    """지도 편집 관리 — 첫 번째 floor의 전체 객체 조회 (미배치 포함)

    배치 판단 원칙: 객체의 floor_id 가 현재 floor와 일치하면 placed=True.
    이 단일 조건만으로 판단하여 디버깅과 로직 변경을 용이하게 한다.
    """

    # severity → 위험구역 코드 토큰 매핑 (이 함수 내부 전용)
    # 좌측 패널 표기 DG_<token>_<id> 에 사용
    SEVERITY_TOKEN_MAP = {
        'danger':  'RED',
        'warning': 'YEL',
        'safe':    'SAF',
    }

    # ── Floor 결정 (현재는 첫 번째 floor 고정, 추후 URL 파라미터로 전환 예정) ──
    floor = Floor.objects.first()
    if floor is None:
        context = {
            'objects': [],
            'total_count': 0,
            'placed_count': 0,
            'unplaced_count': 0,
            'floor': None,
            'no_floor_warning': True,
        }
        return render(request, 'admin/map/map.html', context)

    # ── 공통 필터: 현재 floor에 속하거나 floor가 NULL인 객체 ──
    floor_filter = Q(floor=floor) | Q(floor__isnull=True)

    objects = []

    # ── 1) 설비 (Equipment) ──
    for eq in Equipment.objects.filter(floor_filter):
        objects.append({
            'id':     eq.equipment_code,
            'pk':     eq.pk,            # P3-7: DB PK (PATCH 대상 매핑용)
            'type':   'facility',
            'name':   eq.equipment_name,
            'placed': eq.floor_id == floor.id,
            'badge':  '설비',
        })

    # ── 2) 유해가스 센서 / 3) 스마트 전력 시스템 ──
    # T1-β P1: pk = SensorLocation.pk (PATCH endpoint 일치). Device.device_code 는 표시용으로 device_map 에서 lookup.
    device_map = {d.id: d for d in Device.objects.filter(device_type__in=['gas', 'power'])}
    sl_filter = Q(floor=floor) | Q(floor__isnull=True)
    for sl in SensorLocation.objects.filter(sensor_type__in=['gas', 'power']).filter(sl_filter):
        dev = device_map.get(sl.device_id)
        if not dev:
            continue   # Device 가 없으면 orphan (Q6-3 보류 → 추후 정리)
        if sl.sensor_type == 'gas':
            type_key, badge = 'gas',   '유해가스 센서'
        else:
            type_key, badge = 'power', '스마트 전력 시스템'
        objects.append({
            'id':        dev.device_code,
            'pk':        sl.pk,            # T1-β P1: SensorLocation.pk (PATCH 대상)
            'type':      type_key,
            'name':      sl.device_name or dev.device_name,
            'placed':    sl.is_placed,     # T1-β Q1: is_placed 단일 진실 원천
            'badge':     badge,
            'is_active': dev.is_active,
            'conn_ok':   dev.status == 'active',
        })

    # ── 4) 위치 노드 (LocationNode) ──
    for node in LocationNode.objects.filter(floor_filter):
        objects.append({
            'id':     node.node_code,
            'pk':     node.pk,          # P3-7: DB PK (PATCH 대상 매핑용)
            'type':   'node',
            'name':   node.node_name,
            'placed': node.floor_id == floor.id,
            'badge':  '위치 노드',
        })

    # ── 5) 위험 구역 (Geofence) ──
    # 항상 배치 완료 (미배치 개념 없음). is_active=False (자동 비활성/수동 삭제) 는 좌측 패널에서 제외
    for gf in Geofence.objects.filter(floor=floor, is_active=True):
        severity_token = SEVERITY_TOKEN_MAP.get(gf.severity, 'UNK')
        objects.append({
            'id':     f'DG_{severity_token}_{gf.id}',
            'pk':     gf.pk,            # P3-7: DB PK (PATCH 대상 매핑용)
            'type':   'zone',
            'name':   gf.name,
            'placed': True,
            'badge':  '위험 구역',
        })

    # ── 카운트 계산 ──
    total_count    = len(objects)
    placed_count   = sum(1 for o in objects if o['placed'])
    unplaced_count = total_count - placed_count

    context = {
        'objects':         objects,
        'total_count':     total_count,
        'placed_count':    placed_count,
        'unplaced_count':  unplaced_count,
        'floor':           floor,
        'no_floor_warning': False,
    }
    return render(request, 'admin/map/map.html', context)