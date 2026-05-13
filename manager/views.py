from datetime import timedelta

# ⚠️ 임시: 운영 전 일괄 권한 정책으로 교체 예정 — map_editor 함수 페이지 진입 차단 전용
# API ViewSet 등 다른 경로는 별도 단계에서 보호 적용
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Count, Q, Exists, OuterRef
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, ListView, UpdateView, DeleteView


from .mixins import AdminRequiredMixin, ManagerRequiredMixin, RoleRequiredMixin, DepartmentScopeMixin
from facilities.models import (
    Floor, Equipment, LocationNode, Geofence, SensorLocation,
) # map 관련 모델 추가함
from monitoring.models import Device # map 관련 모델 추가함

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

# ⚠️ 임시 권한 차단 — 운영 전 일괄 권한 정책 적용 시 교체 예정
# 사유: 다른 팀원이 권한 관련 데코레이터·믹스인을 추가 중일 수 있어
#       지금은 최소 범위(map_editor 페이지 진입)만 차단함.
# 향후 작업 (TODO — 운영 전 일괄):
#   - manager 전체 view 함수에 통일된 권한 데코레이터/믹스인 적용
#   - facilities API ViewSet 에 permission_classes 적용 (IsAdminOrReadOnly 등)
#   - manager/mixins.py 의 AdminRequiredMixin 슈퍼유저 우회 보강
#   - 거부 응답을 redirect(302) → PermissionDenied(403) 으로 통일할지 결정
@login_required
@user_passes_test(lambda u: u.is_superuser or getattr(u, 'user_type', None) == 'admin')
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
            'id':     dev.device_code,
            'pk':     sl.pk,            # T1-β P1: SensorLocation.pk (PATCH 대상)
            'type':   type_key,
            'name':   sl.device_name or dev.device_name,
            'placed': sl.is_placed,     # T1-β Q1: is_placed 단일 진실 원천
            'badge':  badge,
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