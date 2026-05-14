from django.contrib import admin
from .models import ChangeLog
from .models import CommonCode


@admin.register(ChangeLog)
class ChangeLogAdmin(admin.ModelAdmin):
    """T1-δ G1: 변경 이력 조회 (read-only)."""
    list_display = ['created_at', 'actor_id', 'target_type', 'target_id', 'action_type']
    list_filter  = ['action_type', 'target_type']
    search_fields = ['target_id', 'actor_id']
    readonly_fields = [
        'actor_id', 'target_type', 'target_id',
        'action_type', 'before_data', 'after_data', 'created_at',
    ]
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False   # admin 에서 직접 추가 금지 (로그 무결성)

@admin.register(CommonCode)
class CommonCodeAdmin(admin.ModelAdmin):
    list_display = ('group_code', 'code', 'code_name', 'is_active', 'updated_at', 'updated_by')
    list_filter = ('group_code', 'is_active')
    search_fields = ('group_code', 'code', 'code_name')

