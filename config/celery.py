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
          무상태 joblib 모델 파일 1개를 프로세스당 1회 적재(멱등·DB접근 없음).
          가스 인제스트(STEP F)가 default 큐 worker에서 실행되므로 모든
          worker에서 로드하는 것이 맞다.

    여기서 *하지 않는* 것 — power_forecast(STEP G) 워밍업:
        PredictionSubsystem 워밍업은 첫 _get_subsystem() 호출 시 DB 백필
        (채널 × 200 readings × ARIMA 적합)을 강제하는 *상태기*다. 이를 전역
        worker_process_init에 두면 default 큐 worker의 prefork 자식마다
        백필이 중복 실행되어 기동 시 전 코어가 폭주한다(게다가 default
        worker는 forecast 큐를 소비하지 않아 전량 헛일). 따라서 사전
        워밍업을 두지 않고, forecast 전용 worker(--concurrency=1)가 첫
        forecast 작업을 받을 때 run_forecast → _get_subsystem()으로 1회만
        lazy 초기화하도록 위임한다(gas_forecast와 동일 정책).

    참고: power_if (STEP F)는 Phase D 결정 (a)로 비활성. 활성화 시
    monitoring/ai/power_if.py docstring 참조하여 본 함수에 호출 추가.
    """
    try:
        from monitoring.ai.gas_if import load_models
        load_models()
    except Exception as exc:
        logger.error("Gas IF 모델 로드 실패 (worker_process_init): %s", exc)
