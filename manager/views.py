from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, ListView, UpdateView, DeleteView


from .mixins import AdminRequiredMixin, ManagerRequiredMixin, RoleRequiredMixin, DepartmentScopeMixin


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
# 지도 
def map_editor(request):
    """필터 펼친 상태"""
    return render(request, 'admin/map/map.html')