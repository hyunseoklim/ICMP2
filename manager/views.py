import re
from datetime import datetime, date

from django.core.paginator import Paginator
from django.db.models import Q, Count, Max, Case, When, IntegerField, Value, Subquery, OuterRef, DateField
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_GET

from accounts.models import User, Department, Position
from facilities.models import Equipment, LocationNode, Facility
from monitoring.models import Device, InspectionLog, ActionLog
from core.models import CommonCode, SystemLog
from .mixins import AdminRequiredMixin, ManagerRequiredMixin, RoleRequiredMixin, DepartmentScopeMixin


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
    if is_active := request.GET.get('is_active'):
        qs = qs.filter(is_active=(is_active == 'true'))
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
        'positions': Position.objects.filter(is_active=True),
        'base_params': base_params,
    })

def user_bulk_delete(request):
    if request.method != 'POST':
        return redirect('user_list')
    ids = request.POST.getlist('selected_ids')
    if ids:
        count = User.objects.filter(pk__in=ids).count()
        User.objects.filter(pk__in=ids).delete()
        messages.success(request, f'{count}명의 사용자가 삭제되었습니다.')
    return redirect('user_list')


def user_bulk_lock(request):
    if request.method != 'POST':
        return redirect('user_list')
    ids = request.POST.getlist('selected_ids')
    if ids:
        count = User.objects.filter(pk__in=ids).update(is_active=False)
        messages.success(request, f'{count}명의 계정이 잠금 처리되었습니다.')
    return redirect('user_list')


def user_bulk_unlock(request):
    if request.method != 'POST':
        return redirect('user_list')
    ids = request.POST.getlist('selected_ids')
    if ids:
        count = User.objects.filter(pk__in=ids).update(is_active=True)
        messages.success(request, f'{count}명의 계정 잠금이 해제되었습니다.')
    return redirect('user_list')


def user_create(request):
    """사용자 등록"""
    if request.method == 'POST':
        name       = request.POST.get('name', '').strip()
        username   = request.POST.get('username', '').strip()
        password1  = request.POST.get('password1', '')
        password2  = request.POST.get('password2', '')
        department = request.POST.get('department')
        user_type  = request.POST.get('user_type', 'worker')
        position   = request.POST.get('position', '')
        is_active  = request.POST.get('is_active', 'true') == 'true'
        email      = request.POST.get('email', '').strip()
        phone      = request.POST.get('phone', '').strip()

        errors = []
        if not name:
            errors.append('사용자명을 입력하세요.')
        if not username:
            errors.append('아이디를 입력하세요.')
        if User.objects.filter(username=username).exists():
            errors.append(f'이미 사용 중인 아이디입니다: {username}')
        if not password1:
            errors.append('비밀번호를 입력하세요.')
        if password1 != password2:
            errors.append('비밀번호가 일치하지 않습니다.')
        if not user_type:
            errors.append('권한을 선택하세요.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'admin/users/user_list.html', {
                'active_menu': 'account',
                'departments': Department.objects.all(),
                'positions': Position.objects.filter(is_active=True),
                'create_errors': errors,
                'show_create_modal': True,
            })

        user = User(
            username=username,
            name=name,
            user_type=user_type,
            position=position,
            is_active=is_active,
            email=email,
            phone=phone,
        )
        if department:
            user.department_id = int(department)
        if user_type == 'admin':
            user.is_staff = True
        user.set_password(password1)
        user.save()

        messages.success(request, f'사용자 "{name}"({username})이 등록되었습니다.')
        return redirect('user_list')

    return render(request, 'admin/users/user_create.html', {
        'active_menu': 'account',
        'departments': Department.objects.all(),
        'positions': Position.objects.filter(is_active=True),
    })

def user_create_error(request):
    """사용자 등록 - 유효성 에러"""
    return render(request, 'admin/users/user_create_error.html', {
        'active_menu': 'account',
        'departments': Department.objects.all(),
    })

def user_detail(request):
    """사용자 정보 조회"""
    return render(request, 'admin/users/user_detail.html', {
        'active_menu': 'account',
        'departments': Department.objects.all(),
    })

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
        target_user.is_active  = request.POST.get('is_active', 'true') == 'true'

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
        'positions': Position.objects.filter(is_active=True),
    })

def logout_complete(request):
    """로그아웃 완료"""
    return render(request, 'admin/users/logout_complete.html', {'active_menu': 'account'})

def user_list_filter(request):
    """필터 펼친 상태"""
    return render(request, 'admin/users/user_list_filter_open.html', {'active_menu': 'account'})

# ===== 직위 관리 =====
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
def org_list(request):
    """조직 관리 메인 페이지"""
    departments = Department.objects.annotate(member_count=Count('users')).order_by('name')
    return render(request, 'admin/organizations/org_list.html', {
        'active_menu': 'account',
        'departments': departments,
    })


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
    dept.save(update_fields=['leader'])
    messages.success(request, f'{user.name}을(를) {dept.name}의 조직장으로 임명했습니다.')
    return redirect('org_list')


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
    dept.save(update_fields=['leader'])
    messages.success(request, f'{prev_name}의 조직장 직위가 해제되었습니다.')
    return redirect('org_list')


def org_member_select(request):
    """구성원 선택 (모달이 org_list에 통합됨, URL 하위호환 유지)"""
    return redirect('org_list')

def org_dept_move(request):
    """부서 이동 모달"""
    return render(request, 'admin/organizations/org_dept_move.html', {'active_menu': 'account'})

def org_confirm(request):
    """재확인 모달"""
    return render(request, 'admin/organizations/org_confirm.html', {'active_menu': 'account'})

# ===== 공통 코드 관리 =====
def code_list(request):
    """공통 코드 관리 메인 페이지"""
    group_codes = CommonCode.objects.values('group_code').distinct().order_by('group_code')
    selected_group = request.GET.get('group_code')
    codes = CommonCode.objects.filter(group_code=selected_group) if selected_group else CommonCode.objects.none()
    return render(request, 'admin/codes/code_list.html', {
        'active_menu': 'reference',
        'group_codes': group_codes,
        'codes': codes,
        'selected_group': selected_group,
    })

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
    """작업 전 안전 점검 체크리스트 관리"""
    return render(request, 'admin/safety_checklist/safety_checklist_list.html', {'active_menu': 'safety'})

# ===== VR 교육 관리 =====
def vr_education_list(request):
    """VR 교육 관리 - 메인 + 수정 모달 통합"""
    return render(request, 'admin/vr_education/vr_education_list.html', {'active_menu': 'safety'})

# ===== 설비 관리 =====
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
            return JsonResponse({'ok': False, 'error': '이미 등록된 장비 ID입니다.'}, status=400)

        note_full = (f'MAC: {mac}\n' + note if mac else note)

        device = Device.objects.create(
            facility=facility,
            device_type=db_type,
            device_uid=device_uid,
            device_code=f'{next_num:03d}',
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
    note_full = (f'MAC: {mac}\n' + note if mac else note)
    device.note = note_full

    if install_date_str:
        try:
            device.installed_at = datetime.strptime(install_date_str, '%Y.%m.%d')
        except ValueError:
            pass

    device.save()
    return JsonResponse({'ok': True})


def gas_bulk_delete(request):
    """유해가스 센서 일괄 삭제 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    ids = request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'ok': False, 'error': '삭제할 항목을 선택해주세요.'}, status=400)

    count, _ = Device.objects.filter(pk__in=ids, device_type='gas').delete()
    return JsonResponse({'ok': True, 'count': count})


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
        inspect_date = date.today()

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
        action_date = date.today()

    actor = User.objects.filter(name=actor_name).first() if actor_name else None

    ActionLog.objects.create(
        inspection=inspection,
        actor=actor,
        action_date=action_date,
        action_note=action_note,
    )
    return JsonResponse({'ok': True})

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

def power_bulk_delete(request):
    """스마트 전력 시스템 일괄 삭제 API"""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    ids = request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'ok': False, 'error': '삭제할 항목을 선택해주세요.'}, status=400)
    count, _ = Device.objects.filter(pk__in=ids, device_type='power').delete()
    return JsonResponse({'ok': True, 'count': count})


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
        action_date = date.today()

    actor = User.objects.filter(name=actor_name).first() if actor_name else None

    ActionLog.objects.create(
        inspection=inspection,
        actor=actor,
        action_date=action_date,
        action_note=action_note,
    )
    return JsonResponse({'ok': True})


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
        inspect_date = date.today()

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


def node_list(request):
    """위치 노드 관리 메인 페이지"""
    sort_map = {
        'node_id_asc':  'device_code',
        'node_id_desc': '-device_code',
        'recv_new':     '-last_seen_at',
        'recv_old':     'last_seen_at',
        'inspect_new':  '-last_inspected_at',
        'inspect_old':  'last_inspected_at',
        'manager_asc':  'manager__name',
        'manager_desc': '-manager__name',
    }
    sort_key = request.GET.get('sort', 'node_id_asc')
    order_by = sort_map.get(sort_key, 'device_code')

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
    """위치 노드 일괄 삭제"""
    ids_raw = request.POST.get('ids', '')
    ids = [i for i in ids_raw.split(',') if i.strip().isdigit()]
    count, _ = Device.objects.filter(pk__in=ids, device_type='loc').delete()
    return JsonResponse({'ok': True, 'deleted': count})


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
        action_date = date.today()

    actor = User.objects.filter(name=actor_name).first() if actor_name else None

    ActionLog.objects.create(
        inspection=inspection,
        actor=actor,
        action_date=action_date,
        action_note=action_note,
    )
    return JsonResponse({'ok': True})


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
        inspect_date = date.today()

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
def map_editor(request):
    """지도 편집 관리"""
    return render(request, 'admin/map/map.html')
