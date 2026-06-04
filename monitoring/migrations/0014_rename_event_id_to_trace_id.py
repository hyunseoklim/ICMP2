from django.db import migrations


class Migration(migrations.Migration):
    """event_id → trace_id 리네임 (계보 추적 키 의미 명확화 + AlarmEvent PK와 동명이의 해소).
    데이터 보존 RenameField (컬럼/인덱스/제약 자동 승계).
    """

    dependencies = [
        ('monitoring', '0013_alter_detectionresult_stage'),
    ]

    operations = [
        migrations.RenameField('gasreading', 'event_id', 'trace_id'),
        migrations.RenameField('powerreading', 'event_id', 'trace_id'),
        migrations.RenameField('detectionresult', 'event_id', 'trace_id'),
        migrations.RenameField('droplog', 'event_id', 'trace_id'),
    ]
