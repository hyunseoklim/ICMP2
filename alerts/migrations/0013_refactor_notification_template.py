from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0012_add_task_log'),
    ]

    operations = [
        # Notification 모델 테이블 삭제
        migrations.DeleteModel(
            name='Notification',
        ),

        # notification_templates 기존 email/sms/push 레코드 정리
        migrations.RunSQL(
            sql="DELETE FROM notification_templates WHERE channel_type IN ('email', 'sms', 'push');",
            reverse_sql=migrations.RunSQL.noop,
        ),

        # NotificationTemplate channel_type choices 변경 + title_template blank 허용
        migrations.AlterField(
            model_name='notificationtemplate',
            name='channel_type',
            field=models.CharField(
                choices=[
                    ('slack',     'Slack'),
                    ('discord',   'Discord'),
                    ('websocket', '관제 실시간 알림'),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='notificationtemplate',
            name='title_template',
            field=models.CharField(max_length=300, blank=True),
        ),
    ]
