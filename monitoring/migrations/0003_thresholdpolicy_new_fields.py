from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0002_add_threshold_audit_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='thresholdpolicy',
            name='category',
            field=models.CharField(max_length=50, default='TH_GAS'),
        ),
        migrations.AddField(
            model_name='thresholdpolicy',
            name='unit',
            field=models.CharField(max_length=20, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='thresholdpolicy',
            name='condition',
            field=models.CharField(max_length=10, default='이상'),
        ),
        migrations.AddField(
            model_name='thresholdpolicy',
            name='scope',
            field=models.CharField(max_length=200, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='thresholdpolicy',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
    ]
