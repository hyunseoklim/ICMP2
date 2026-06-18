"""alerts 앱 핵심 로직 테스트.

발표 핵심 주장에 대한 회귀 안전망:
    1. 가스 임계치 → AlarmEvent 생성/갱신/자동종료 (check_gas_thresholds)
    2. 전력 부하율 → AlarmEvent 생성 + 5분 중복 방지 (check_power_thresholds)
    3. 이벤트 상태 전이 + EventHistory 기록 (change_event_status)
    4. Celery 시그널 → TaskLog 상태 추적 (config/celery.py 핸들러)
    5. Task 상태 조회 API (/alerts/api/tasks/)

실행 (DB_HOST=db 이므로 컨테이너 내부에서):
    docker compose exec django python manage.py test alerts
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from facilities.models import Facility
from monitoring.models import Device, DeviceChannel, GasReading

from .models import AlarmEvent, AlarmRule, EventHistory, TaskLog
from .services import (
    change_event_status,
    check_gas_thresholds,
    check_power_thresholds,
)


def _create_facility():
    return Facility.objects.create(facility_name='테스트 사업장', facility_code='FAC-TEST')


def _create_device(facility, device_type='gas', uid='TEST-DEV-001'):
    return Device.objects.create(
        facility=facility,
        device_type=device_type,
        device_code='001',
        device_uid=uid,
        device_name='테스트 장비',
        port=502,
    )


def _gas_reading(device, **values):
    """지정한 가스 필드만 채운 GasReading 생성. 나머지는 None."""
    return GasReading.objects.create(
        device=device,
        measured_at=timezone.now(),
        **values,
    )


class NotificationMockMixin:
    """create_alarm_event가 호출하는 send_all_notifications.delay를 차단.

    테스트 중 실제 Redis 브로커로 task가 발행되어 라이브 워커가
    테스트 DB의 event_id를 소비하는 오염을 막는다.
    """

    def setUp(self):
        super().setUp()
        patcher = patch('alerts.tasks.send_all_notifications.delay')
        self.mock_notify = patcher.start()
        self.addCleanup(patcher.stop)


# ──────────────────────────────────────────────────────────
# 1. 가스 임계치 → AlarmEvent (STEP B)
# ──────────────────────────────────────────────────────────

class CheckGasThresholdsTests(NotificationMockMixin, TestCase):
    """ThresholdPolicy 미등록 상태 → DEFAULT_THRESHOLDS 폴백 기준.

    DEFAULT_THRESHOLDS: co=(주의 25, 위험 200), h2s=(10, 15) 등
    """

    @classmethod
    def setUpTestData(cls):
        cls.facility = _create_facility()
        cls.device = _create_device(cls.facility)
        cls.rule = AlarmRule.objects.create(
            rule_name='가스 임계치',
            rule_type=AlarmRule.RuleType.THRESHOLD,
        )

    def test_danger_threshold_creates_danger_event(self):
        reading = _gas_reading(self.device, co=250.0)

        check_gas_thresholds(self.device, reading)

        event = AlarmEvent.objects.get()
        self.assertEqual(event.severity, AlarmEvent.Severity.DANGER)
        self.assertEqual(event.event_status, AlarmEvent.EventStatus.OPEN)
        self.assertEqual(event.event_type, AlarmEvent.EventType.GAS)
        self.assertIn('[가스]', event.title)
        self.assertIn('CO', event.title)
        # 알림 발송 task가 큐잉되었는지 (mock으로 차단된 상태)
        self.mock_notify.assert_called_once_with(event.id)

    def test_warning_threshold_creates_warning_event(self):
        reading = _gas_reading(self.device, co=30.0)  # 주의(25) 이상, 위험(200) 미만

        check_gas_thresholds(self.device, reading)

        event = AlarmEvent.objects.get()
        self.assertEqual(event.severity, AlarmEvent.Severity.WARNING)

    def test_normal_reading_creates_nothing(self):
        reading = _gas_reading(self.device, co=5.0)

        check_gas_thresholds(self.device, reading)

        self.assertEqual(AlarmEvent.objects.count(), 0)
        self.mock_notify.assert_not_called()

    def test_open_event_is_updated_not_duplicated(self):
        """이상 지속 시 open 이벤트 갱신 — 중복 생성 방지의 핵심."""
        check_gas_thresholds(self.device, _gas_reading(self.device, co=30.0))
        first = AlarmEvent.objects.get()

        check_gas_thresholds(self.device, _gas_reading(self.device, co=250.0))

        self.assertEqual(AlarmEvent.objects.count(), 1)
        first.refresh_from_db()
        # 갱신 시 severity 격상(주의→위험) + 대표값 갱신
        self.assertEqual(first.severity, AlarmEvent.Severity.DANGER)
        self.assertEqual(first.current_value, 250.0)
        self.assertIsNotNone(first.last_seen_at)
        # 알림은 최초 생성 시 1회만
        self.mock_notify.assert_called_once()

    def test_normal_recovery_closes_open_event_with_history(self):
        """정상 복귀 → 자동 closed + EventHistory 기록."""
        check_gas_thresholds(self.device, _gas_reading(self.device, co=250.0))
        event = AlarmEvent.objects.get()

        check_gas_thresholds(self.device, _gas_reading(self.device, co=5.0))

        event.refresh_from_db()
        self.assertEqual(event.event_status, AlarmEvent.EventStatus.CLOSED)
        self.assertIsNotNone(event.closed_at)
        history = EventHistory.objects.get(alarm_event=event)
        self.assertEqual(history.action_type, 'close')
        self.assertIn('정상 복귀', history.action_note)

    def test_bad_quality_flag_is_skipped(self):
        """quality_flag != ok → 판단 자체를 건너뜀 (오탐 방지)."""
        reading = _gas_reading(self.device, co=250.0, quality_flag='comm_err')

        check_gas_thresholds(self.device, reading)

        self.assertEqual(AlarmEvent.objects.count(), 0)

    def test_inactive_rule_is_skipped(self):
        self.rule.is_active = False
        self.rule.save()

        check_gas_thresholds(self.device, _gas_reading(self.device, co=250.0))

        self.assertEqual(AlarmEvent.objects.count(), 0)


# ──────────────────────────────────────────────────────────
# 2. 전력 부하율 → AlarmEvent + 5분 중복 방지
# ──────────────────────────────────────────────────────────

class CheckPowerThresholdsTests(NotificationMockMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.facility = _create_facility()
        cls.device = _create_device(cls.facility, device_type='power', uid='TEST-PWR-001')
        cls.channel = DeviceChannel.objects.create(
            device=cls.device,
            channel_code=DeviceChannel.ChannelCode.SLAVE01,
            channel_name='압연기 전원',
            rated_power_w=1000,
        )
        cls.rule = AlarmRule.objects.create(
            rule_name='전력 부하율',
            rule_type=AlarmRule.RuleType.POWER,
        )

    def test_load_75_percent_creates_danger(self):
        check_power_thresholds(self.device, self.channel, power_w=750.0)

        event = AlarmEvent.objects.get()
        self.assertEqual(event.severity, AlarmEvent.Severity.DANGER)
        self.assertEqual(event.event_type, AlarmEvent.EventType.POWER)
        self.assertEqual(event.channel, self.channel)
        self.assertIn('부하율 75%', event.title)

    def test_load_50_percent_creates_warning(self):
        check_power_thresholds(self.device, self.channel, power_w=500.0)

        event = AlarmEvent.objects.get()
        self.assertEqual(event.severity, AlarmEvent.Severity.WARNING)

    def test_load_below_50_percent_creates_nothing(self):
        check_power_thresholds(self.device, self.channel, power_w=499.0)

        self.assertEqual(AlarmEvent.objects.count(), 0)

    def test_zero_or_negative_power_is_skipped(self):
        check_power_thresholds(self.device, self.channel, power_w=0)
        check_power_thresholds(self.device, self.channel, power_w=-1)

        self.assertEqual(AlarmEvent.objects.count(), 0)

    def test_duplicate_within_5min_is_suppressed(self):
        """5분 이내 동일 채널 open 이벤트 존재 → 신규 생성 안 함 (dedup 핵심)."""
        check_power_thresholds(self.device, self.channel, power_w=800.0)
        check_power_thresholds(self.device, self.channel, power_w=900.0)

        self.assertEqual(AlarmEvent.objects.count(), 1)
        self.mock_notify.assert_called_once()

    def test_open_event_older_than_5min_allows_new_event(self):
        """dedup 윈도우는 5분 — 그 이전 open 이벤트는 차단하지 않음."""
        check_power_thresholds(self.device, self.channel, power_w=800.0)
        old = AlarmEvent.objects.get()
        AlarmEvent.objects.filter(pk=old.pk).update(
            occurred_at=timezone.now() - timedelta(minutes=10),
        )

        check_power_thresholds(self.device, self.channel, power_w=800.0)

        self.assertEqual(AlarmEvent.objects.count(), 2)


# ──────────────────────────────────────────────────────────
# 3. 이벤트 상태 전이 (open → acknowledged → closed → reopen)
# ──────────────────────────────────────────────────────────

class ChangeEventStatusTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.facility = _create_facility()
        cls.rule = AlarmRule.objects.create(
            rule_name='가스 임계치',
            rule_type=AlarmRule.RuleType.THRESHOLD,
        )
        cls.user = get_user_model().objects.create_user(
            username='operator', password='test-pass-1234',
        )

    def setUp(self):
        self.event = AlarmEvent.objects.create(
            rule=self.rule,
            facility=self.facility,
            event_type=AlarmEvent.EventType.GAS,
            severity=AlarmEvent.Severity.DANGER,
            title='[가스] CO 농도 이상 감지',
        )

    def test_acknowledge_records_user_and_history(self):
        change_event_status(self.event, 'acknowledged', user=self.user, action_note='현장 확인 중')

        self.event.refresh_from_db()
        self.assertEqual(self.event.event_status, 'acknowledged')
        self.assertEqual(self.event.acknowledged_by, self.user)
        self.assertIsNotNone(self.event.acknowledged_at)
        history = EventHistory.objects.get(alarm_event=self.event)
        self.assertEqual(history.action_type, 'acknowledge')
        self.assertEqual(history.action_by, self.user)

    def test_close_sets_closed_at(self):
        change_event_status(self.event, 'closed', user=self.user)

        self.event.refresh_from_db()
        self.assertEqual(self.event.event_status, 'closed')
        self.assertIsNotNone(self.event.closed_at)

    def test_reopen_clears_closed_at(self):
        change_event_status(self.event, 'closed', user=self.user)
        change_event_status(self.event, 'open', user=self.user)

        self.event.refresh_from_db()
        self.assertEqual(self.event.event_status, 'open')
        self.assertIsNone(self.event.closed_at)
        self.assertEqual(
            EventHistory.objects.filter(alarm_event=self.event).count(), 2,
        )

    def test_invalid_transition_raises_value_error(self):
        """open → open 은 허용되지 않는 전환."""
        with self.assertRaises(ValueError):
            change_event_status(self.event, 'open')
        # 실패한 전환은 이력을 남기지 않음
        self.assertEqual(EventHistory.objects.count(), 0)


# ──────────────────────────────────────────────────────────
# 4. Celery 시그널 → TaskLog 상태 추적
#    (브로커 없이 config/celery.py 핸들러를 직접 호출)
# ──────────────────────────────────────────────────────────

TRACKED = 'alerts.tasks.ingest_gas_task'


def _task(name=TRACKED):
    """task_prerun/postrun 시그널의 task 인자 대역."""
    return SimpleNamespace(name=name)


class TaskLogSignalTests(TestCase):

    def test_before_publish_creates_pending(self):
        from config.celery import on_before_task_publish

        on_before_task_publish(sender=TRACKED, headers={'id': 'tid-1'})

        log = TaskLog.objects.get(task_id='tid-1')
        self.assertEqual(log.status, TaskLog.Status.PENDING)
        self.assertEqual(log.task_name, TRACKED)

    def test_untracked_task_is_ignored(self):
        from config.celery import on_before_task_publish

        on_before_task_publish(sender='alerts.tasks.cleanup_old_data', headers={'id': 'tid-x'})

        self.assertEqual(TaskLog.objects.count(), 0)

    def test_prerun_updates_to_started(self):
        from config.celery import on_before_task_publish, on_task_prerun

        on_before_task_publish(sender=TRACKED, headers={'id': 'tid-2'})
        on_task_prerun(task_id='tid-2', task=_task())

        log = TaskLog.objects.get(task_id='tid-2')
        self.assertEqual(log.status, TaskLog.Status.STARTED)
        self.assertIsNotNone(log.started_at)

    def test_prerun_without_pending_creates_started(self):
        """FastAPI send_task() 경로 — before_task_publish 시그널이 발화하지
        않아 PENDING 없이 STARTED부터 기록되는 동작을 보장 (update_or_create).
        """
        from config.celery import on_task_prerun

        on_task_prerun(task_id='tid-3', task=_task())

        log = TaskLog.objects.get(task_id='tid-3')
        self.assertEqual(log.status, TaskLog.Status.STARTED)

    def test_postrun_success_sets_completed_at(self):
        from config.celery import on_task_postrun, on_task_prerun

        on_task_prerun(task_id='tid-4', task=_task())
        on_task_postrun(task_id='tid-4', task=_task(), state='SUCCESS')

        log = TaskLog.objects.get(task_id='tid-4')
        self.assertEqual(log.status, TaskLog.Status.SUCCESS)
        self.assertIsNotNone(log.completed_at)

    def test_postrun_skips_failure_and_retry_states(self):
        """FAILURE/RETRY는 전용 시그널이 처리 — postrun이 SUCCESS로 덮어쓰면 안 됨."""
        from config.celery import on_task_postrun, on_task_prerun

        on_task_prerun(task_id='tid-5', task=_task())
        on_task_postrun(task_id='tid-5', task=_task(), state='RETRY')

        log = TaskLog.objects.get(task_id='tid-5')
        self.assertEqual(log.status, TaskLog.Status.STARTED)

    def test_failure_records_error_message(self):
        from config.celery import on_task_failure, on_task_prerun

        on_task_prerun(task_id='tid-6', task=_task())
        on_task_failure(task_id='tid-6', exception=ValueError('boom'), sender=_task())

        log = TaskLog.objects.get(task_id='tid-6')
        self.assertEqual(log.status, TaskLog.Status.FAILURE)
        self.assertEqual(log.error, 'ValueError: boom')
        self.assertIsNotNone(log.completed_at)

    def test_retry_records_reason(self):
        from config.celery import on_task_prerun, on_task_retry

        on_task_prerun(task_id='tid-7', task=_task())
        request = SimpleNamespace(task=TRACKED, id='tid-7')
        on_task_retry(request=request, reason='ConnectionError: redis down')

        log = TaskLog.objects.get(task_id='tid-7')
        self.assertEqual(log.status, TaskLog.Status.RETRY)
        self.assertIn('redis down', log.error)


# ──────────────────────────────────────────────────────────
# 5. Task 상태 조회 API
# ──────────────────────────────────────────────────────────

class TaskStatusApiTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.log = TaskLog.objects.create(
            task_id='api-tid-1',
            task_name=TRACKED,
            status=TaskLog.Status.SUCCESS,
        )

    def test_task_status_returns_single_log(self):
        url = reverse('task_status', args=['api-tid-1'])
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['status'], 'SUCCESS')
        self.assertEqual(body['task_name'], 'ingest_gas_task')  # 짧은 이름
        self.assertEqual(body['task_name_full'], TRACKED)

    def test_unknown_task_id_returns_404(self):
        url = reverse('task_status', args=['no-such-task'])
        res = self.client.get(url)

        self.assertEqual(res.status_code, 404)

    def test_task_list_filters_by_status(self):
        TaskLog.objects.create(
            task_id='api-tid-2',
            task_name=TRACKED,
            status=TaskLog.Status.FAILURE,
            error='ValueError: boom',
        )

        res = self.client.get(reverse('task_list'), {'status': 'failure'})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['results'][0]['task_id'], 'api-tid-2')
