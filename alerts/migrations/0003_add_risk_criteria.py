from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0002_add_alarm_rule_updated_by'),
    ]

    operations = [
        migrations.CreateModel(
            name='RiskCriteria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stage_code', models.CharField(max_length=50, unique=True)),
                ('stage_name', models.CharField(max_length=100)),
                ('color_type', models.CharField(
                    choices=[('green', '녹색'), ('yellow', '황색'), ('orange', '주황'), ('red', '적색'), ('gray', '회색')],
                    default='gray', max_length=20,
                )),
                ('alert_emphasis', models.CharField(blank=True, default='', max_length=100)),
                ('priority', models.PositiveIntegerField(default=1)),
                ('is_active', models.BooleanField(default=True)),
                ('description', models.TextField(blank=True, default='')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.CharField(blank=True, default='', max_length=100)),
            ],
            options={
                'db_table': 'risk_criteria',
                'ordering': ['priority'],
            },
        ),
    ]
