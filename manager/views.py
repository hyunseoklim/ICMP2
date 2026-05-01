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
    return render(request, 'admin/users/user_list.html')

def user_create(request):
    """사용자 등록 모달"""
    return render(request, 'admin/users/user_create.html')

def user_create_error(request):
    """사용자 등록 - 유효성 에러"""
    return render(request, 'admin/users/user_create_error.html')

def user_detail(request):
    """사용자 정보 조회"""
    return render(request, 'admin/users/user_detail.html')

def user_edit(request):
    """사용자 정보 수정"""
    return render(request, 'admin/users/user_edit.html')

def logout_complete(request):
    """로그아웃 완료"""
    return render(request, 'admin/users/logout_complete.html')

def user_list_filter(request):
    """필터 펼친 상태"""
    return render(request, 'admin/users/user_list_filter_open.html')

# 지도 
def map_editor(request):
    """필터 펼친 상태"""
    return render(request, 'admin/map/map.html')