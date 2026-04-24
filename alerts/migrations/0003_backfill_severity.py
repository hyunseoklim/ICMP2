from django.db import migrations


SEVERITY_MAP = {
    'critical': 'danger',
    'high':     'danger',
    'medium':   'warning',
    'low':      'normal',
}


def forwards(apps, schema_editor):
    AlarmEvent = apps.get_model('alerts', 'AlarmEvent')
    for old, new in SEVERITY_MAP.items():
        AlarmEvent.objects.filter(severity=old).update(severity=new)


def backwards(apps, schema_editor):
    pass  # 역방향 복구 불필요


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0002_severity_3level'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
