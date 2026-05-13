from django.contrib import admin
from .models import CommonCode

@admin.register(CommonCode)
class CommonCodeAdmin(admin.ModelAdmin):
    list_display = ('group_code', 'code', 'code_name', 'is_active', 'updated_at', 'updated_by')
    list_filter = ('group_code', 'is_active')
    search_fields = ('group_code', 'code', 'code_name')
