from django.contrib import admin

from .models import AlarmEvent, AlarmRule, EventHistory, NotificationTemplate


@admin.register(AlarmRule)
class AlarmRuleAdmin(admin.ModelAdmin):
    list_display = ('rule_name', 'rule_type', 'action_type', 'is_active')
    list_filter = ('rule_type', 'action_type', 'is_active')
    search_fields = ('rule_name',)


@admin.register(AlarmEvent)
class AlarmEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'severity', 'event_type', 'event_status', 'facility', 'occurred_at')
    list_filter = ('severity', 'event_type', 'event_status')
    search_fields = ('title', 'message')
    ordering = ('-occurred_at',)


@admin.register(EventHistory)
class EventHistoryAdmin(admin.ModelAdmin):
    list_display = ('alarm_event', 'action_type', 'action_by', 'action_at')
    list_filter = ('action_type',)
    ordering = ('-action_at',)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('template_name', 'channel_type', 'is_active')
    list_filter = ('channel_type', 'is_active')
