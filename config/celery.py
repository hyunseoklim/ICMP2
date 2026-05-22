import logging
import os

from celery import Celery
from celery.signals import worker_process_init

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

logger = logging.getLogger(__name__)


@worker_process_init.connect
def _load_ai_models(**kwargs):
    """각 Celery worker 프로세스 시작 시 AI 모델을 1회 로드한다 (STEP F).

    prefork worker는 자식 프로세스마다 본 시그널이 발생하므로 모델은
    프로세스당 1회만 메모리에 적재된다. 로드 실패가 worker 기동이나
    가스 인제스트 파이프라인을 막지 않도록 예외는 로깅만 한다.
    """
    try:
        from monitoring.ai.gas_if import load_models
        load_models()
    except Exception as exc:
        logger.error("AI 모델 로드 실패 (worker_process_init): %s", exc)
