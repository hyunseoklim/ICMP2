from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0002_add_alarm_rule_updated_by'),
    ]

    # RiskCriteria 테이블은 0002_riskcriteria_alarmrule_updated_by에서 이미 생성됨
    operations = []
