import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('icmp2')

# Redis를 브로커와 결과 백엔드로 사용
app.config_from_object('django.conf:settings', namespace='CELERY')

# 모든 앱의 tasks.py 자동 탐색
app.autodiscover_tasks()
