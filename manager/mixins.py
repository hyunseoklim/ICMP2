from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


class AdminRequiredMixin(AccessMixin):
    """
    user_type == 'admin' 만 접근 허용
    - 모든 데이터 조회 가능
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.user_type != "admin":
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ManagerRequiredMixin(AccessMixin):
    """
    user_type == 'admin' 또는 'manager' 접근 허용
    - admin  : 전체 조회
    - manager: 본인 부서 데이터만 조회 (get_queryset에서 필터)
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.user_type not in ("admin", "manager"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin(ManagerRequiredMixin):
    """
    Role 코드 기반 접근 제어 Mixin (admin/manager 전용)

    사용법:
        class MyView(RoleRequiredMixin, ListView):
            required_role = 'inventory_view'   # roles.role_code 값

    required_role 를 지정하지 않으면 user_type 체크만 수행합니다.
    """
    required_role = None

    def dispatch(self, request, *args, **kwargs):
        # 1단계: user_type 체크 (부모 Mixin)
        result = super().dispatch(request, *args, **kwargs)

        # 2단계: role_code 체크
        if self.required_role:
            has_role = request.user.user_roles.filter(
                role__role_code=self.required_role
            ).exists()
            if not has_role:
                raise PermissionDenied

        return result


# ────────────────────────────────────────────
# 뷰에서 queryset 분기용 헬퍼 믹스인
# ────────────────────────────────────────────

class DepartmentScopeMixin:
    """
    admin  → 전체 queryset
    manager→ 본인 부서(department) 기준으로 자동 필터

    사용법:
        class SomeView(ManagerRequiredMixin, DepartmentScopeMixin, ListView):
            department_field = 'worker__department'  # queryset 필터 필드명

    department_field 기본값은 'department' 입니다.
    """
    department_field = "department"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.user_type == "admin":
            return qs  # 전체

        if user.user_type == "manager" and user.department:
            return qs.filter(**{self.department_field: user.department})

        # worker 는 ManagerRequiredMixin 에서 이미 차단되지만 방어 코드
        return qs.none()