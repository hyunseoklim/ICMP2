"""
Celery 비동기 태스크

ARIMA는 statsmodels fit() 호출이 느려서 HTTP 응답을 블로킹할 수 있음.
ingest_gas() 수신 즉시 .delay()로 워커에 위임해 응답 지연 방지.

Z-score, Change Point, Isolation Forest inference는 빠르므로 동기 유지.
"""
import calendar
import logging
from datetime import date

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def run_arima_task(self, device_uid: str, reading_id: int):
    """
    ARIMA 예측 비동기 실행.
    reading_id로 DB에서 GasReading을 다시 조회해 분석.
    """
    try:
        from monitoring.models import GasReading
        from monitoring.anomaly.arima import analyze as arima_analyze
        from alerts.services import trigger_arima_alarms
        from monitoring.models import Device

        reading = GasReading.objects.select_related('device').get(id=reading_id)
        device  = reading.device

        results = arima_analyze(device_uid, reading)
        if results:
            trigger_arima_alarms(device, results)

        logger.debug("ARIMA 완료: %s reading_id=%d results=%d", device_uid, reading_id, len(results))
    except Exception as exc:
        logger.warning("ARIMA 태스크 실패 (%s): %s", device_uid, exc)
        raise self.retry(exc=exc)


@shared_task
def retrain_isolation_forest(device_uid: str):
    """
    Isolation Forest 재학습.
    슬라이딩 윈도우 데이터가 충분히 쌓인 후 주기적으로 호출.
    """
    try:
        from monitoring.anomaly.isolation import train
        success = train(device_uid)
        logger.debug("IF 재학습: %s success=%s", device_uid, success)
        return success
    except Exception as exc:
        logger.warning("IF 재학습 실패 (%s): %s", device_uid, exc)
        return False


# ── 데이터 보관 주기 실행 엔진 ────────────────────────────

# device_type + data_category → 삭제 대상 모델과 날짜 필드
_RETENTION_TARGETS = {
    ('gas',   'raw'):       ('monitoring.GasReading',      'measured_at', 'origin_days'),
    ('power', 'raw'):       ('monitoring.PowerReading',    'measured_at', 'origin_days'),
    ('node',  'location'):  ('monitoring.NodeReading',     'received_at', 'origin_days'),
    ('gas',   'event'):     ('alerts.AlarmEvent',          'occurred_at', 'history_days'),
    ('power', 'event'):     ('alerts.AlarmEvent',          'occurred_at', 'history_days'),
    ('gas',   'aggregate'): ('monitoring.DeviceStatusLog', 'occurred_at', 'history_days'),
}


def _schedule_due(schedule: str, today: date) -> bool:
    """오늘이 delete_schedule 기준 실행일인지 확인."""
    if schedule == 'daily':
        return True
    if schedule == 'monthly_1':
        return today.day == 1
    if schedule == 'monthly_15':
        return today.day == 15
    if schedule == 'monthly_last':
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.day == last_day
    if schedule == 'quarterly':
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.month in (3, 6, 9, 12) and today.day == last_day
    return False


@shared_task
def execute_retention_policies():
    """
    DataRetentionPolicy 설정에 따라 오래된 데이터 삭제.
    Celery Beat으로 매일 00:10에 자동 실행.
    수동 실행: python manage.py shell -c "from monitoring.tasks import execute_retention_policies; execute_retention_policies()"
    """
    from django.apps import apps
    from manager.models import DataRetentionPolicy

    today   = timezone.localdate()
    now     = timezone.now()
    report  = []

    policies = DataRetentionPolicy.objects.filter(is_active=True)

    for policy in policies:
        if not _schedule_due(policy.delete_schedule, today):
            continue

        key = (policy.device_type, policy.data_category)
        target = _RETENTION_TARGETS.get(key)
        if target is None:
            continue

        model_path, date_field, days_field = target
        app_label, model_name = model_path.split('.')
        try:
            Model = apps.get_model(app_label, model_name)
        except LookupError:
            continue

        days      = getattr(policy, days_field, 0) or 0
        cutoff    = now - timezone.timedelta(days=days)
        qs        = Model.objects.filter(**{f"{date_field}__lt": cutoff})
        deleted, _ = qs.delete()

        msg = f"{model_name} ({policy.get_device_type_display()}/{policy.get_data_category_display()}): {deleted}건 삭제 (기준 {days}일)"
        logger.info("[retention] %s", msg)
        report.append(msg)

    logger.info("[retention] 완료: %d개 정책 실행, %d줄", policies.count(), len(report))
    return report
