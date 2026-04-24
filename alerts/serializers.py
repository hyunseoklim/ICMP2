from rest_framework import serializers

from .models import AlarmEvent


class AlarmEventSerializer(serializers.ModelSerializer):
    sev_label    = serializers.CharField(source='get_severity_display', read_only=True)
    status_label = serializers.CharField(source='get_event_status_display', read_only=True)
    facility     = serializers.StringRelatedField()
    device       = serializers.StringRelatedField()
    worker       = serializers.StringRelatedField()
    occurred_at  = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model  = AlarmEvent
        fields = [
            'id', 'title', 'message',
            'severity', 'sev_label',
            'event_type', 'event_status', 'status_label',
            'occurred_at', 'facility', 'device', 'worker',
        ]
