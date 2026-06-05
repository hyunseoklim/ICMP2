import logging
import os

from celery import Celery
from celery.signals import (
    before_task_publish,
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_process_init,
)

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


# ──────────────────────────────────────────────────────────────────────────────
# Task 상태 추적 (TaskLog)
# ──────────────────────────────────────────────────────────────────────────────
# Beat 스케줄러가 60초/30초/매일 반복 실행하는 태스크는 제외.
# 알람·예측 파이프라인에서 핵심 흐름을 담당하는 태스크만 추적한다.
#
# ※ 가스 ingest는 Redis Stream(consume_gas_stream mgmt cmd)으로 소비하므로
#   celery task가 아니다 → 시그널 미발화 → 추적 대상에서 제외(staged 결정).
#   추적은 celery 큐로 도는 forecast(2) + 알림(4)만.
_TRACKED_TASKS = {
    'alerts.tasks.forecast_gas_task',
    'alerts.tasks.forecast_power_task',
    'alerts.tasks.send_all_notifications',
    'alerts.tasks.send_slack_notification',
    'alerts.tasks.send_discord_notification',
    'alerts.tasks.push_websocket_alert',
}


@before_task_publish.connect
def on_before_task_publish(sender, headers, **kwargs):
    """Django에서 .delay()/apply_async 호출 직후 → PENDING 기록.

    FastAPI의 send_task()는 Django ORM이 없는 경량 Celery 클라이언트라
    이 시그널이 발화하지 않는다. 추적 대상(forecast·알림)은 모두 Django
    프로세스에서 발행되므로 PENDING부터 정상 기록된다.
    """
    if sender not in _TRACKED_TASKS:
        return
    task_id = headers.get('id')
    if not task_id:
        return
    try:
        from alerts.models import TaskLog
        TaskLog.objects.create(task_id=task_id, task_name=sender)
    except Exception as exc:
        logger.warning("TaskLog PENDING 기록 실패: %s", exc)


@task_prerun.connect
def on_task_prerun(task_id, task, **kwargs):
    """Celery worker가 task를 집어서 실행 시작 → STARTED 갱신."""
    if task.name not in _TRACKED_TASKS:
        return
    try:
        from alerts.models import TaskLog
        from django.utils import timezone
        TaskLog.objects.update_or_create(
            task_id=task_id,
            defaults={
                'task_name': task.name,
                'status': TaskLog.Status.STARTED,
                'started_at': timezone.now(),
            },
        )
    except Exception as exc:
        logger.warning("TaskLog STARTED 갱신 실패: %s", exc)


@task_postrun.connect
def on_task_postrun(task_id, task, state, **kwargs):
    """task 실행 완료(SUCCESS) → completed_at 기록.

    FAILURE는 task_failure 시그널이, RETRY는 task_retry 시그널이 각각 처리.
    RETRY 시 completed_at을 찍으면 재시도 중인 태스크가 완료된 것처럼 보이는
    오해를 유발하므로 여기서는 SUCCESS만 처리한다.
    """
    if task.name not in _TRACKED_TASKS:
        return
    if state in ('FAILURE', 'RETRY'):
        return
    try:
        from alerts.models import TaskLog
        from django.utils import timezone
        TaskLog.objects.filter(task_id=task_id).update(
            status=TaskLog.Status.SUCCESS,
            completed_at=timezone.now(),
        )
    except Exception as exc:
        logger.warning("TaskLog SUCCESS 갱신 실패: %s", exc)


@task_failure.connect
def on_task_failure(task_id, exception, sender, **kwargs):
    """재시도 소진 후 최종 실패 → FAILURE + 에러 메시지 갱신."""
    if sender.name not in _TRACKED_TASKS:
        return
    try:
        from alerts.models import TaskLog
        from django.utils import timezone
        TaskLog.objects.filter(task_id=task_id).update(
            status=TaskLog.Status.FAILURE,
            error=f"{type(exception).__name__}: {exception}",
            completed_at=timezone.now(),
        )
    except Exception as exc:
        logger.warning("TaskLog FAILURE 갱신 실패: %s", exc)


@task_retry.connect
def on_task_retry(request, reason, **kwargs):
    """재시도 발생 → RETRY + 재시도 사유 갱신."""
    if request.task not in _TRACKED_TASKS:
        return
    try:
        from alerts.models import TaskLog
        TaskLog.objects.filter(task_id=request.id).update(
            status=TaskLog.Status.RETRY,
            error=str(reason),
        )
    except Exception as exc:
        logger.warning("TaskLog RETRY 갱신 실패: %s", exc)
