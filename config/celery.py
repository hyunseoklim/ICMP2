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
    """각 Celery worker 프로세스 시작 시 AI 모델을 1회 로드한다.

    prefork worker는 자식 프로세스마다 본 시그널이 발생하므로 모델은
    프로세스당 1회만 메모리에 적재된다. 로드 실패가 worker 기동이나
    인제스트 파이프라인을 막지 않도록 예외는 로깅만 한다.

    로드 대상:
        - gas_if (STEP F — Isolation Forest)
        - power_forecast (STEP G — PredictionSubsystem warmup, Phase D M1-10)
          forecast 큐 worker에서 사용. default 큐 worker도 호출되나 무해
          (lazy 호출이라 첫 사용 시까지 비용 0).

    참고: power_if (STEP F)는 Phase D 결정 (a)로 비활성. 활성화 시
    monitoring/ai/power_if.py docstring 참조하여 본 함수에 호출 추가.
    """
    try:
        from monitoring.ai.gas_if import load_models
        load_models()
    except Exception as exc:
        logger.error("Gas IF 모델 로드 실패 (worker_process_init): %s", exc)

    # Phase D M1-10 — power forecast subsystem warmup (forecast 큐 worker)
    try:
        from monitoring.ai.power_forecast import _get_subsystem
        _get_subsystem()
    except Exception as exc:
        logger.warning("Power forecast subsystem warmup 실패: %s", exc)
