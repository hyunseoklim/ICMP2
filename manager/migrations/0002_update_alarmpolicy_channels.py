from django.db import migrations


def update_alarm_policy_channels(apps, schema_editor):
    AlarmPolicy = apps.get_model('manager', 'AlarmPolicy')
    AlarmPolicy.objects.filter(name='가스 경보 알림').update(
        channels='앱, 관제 실시간 알림, Slack, Discord'
    )
    AlarmPolicy.objects.filter(name='전력 이상 알림').update(
        channels='앱, Slack, Discord'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('manager', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(update_alarm_policy_channels, migrations.RunPython.noop),
    ]
