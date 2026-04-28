"""
python manage.py seed_dummy
더미 데이터 생성 커맨드. 중복 실행 시 기존 데이터를 덮어쓰지 않고 get_or_create 사용.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import random


class Command(BaseCommand):
    help = '더미 데이터 생성 (Facility, Device, Worker, AlarmRule, AlarmEvent, EventHistory)'

    def handle(self, *args, **options):
        from accounts.models import User
        from facilities.models import Facility, Building, Worker
        from monitoring.models import Device, DeviceChannel, ThresholdPolicy
        from alerts.models import AlarmRule, AlarmEvent, EventHistory

        self.stdout.write('더미 데이터 생성 시작...')

        # ── 0. 테스트 계정 ─────────────────────────────────────────────────
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'name': '관리자',
                'user_type': 'admin',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        admin_user.user_type = 'admin'
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.set_password('admin1234!')
        admin_user.save()

        worker_user, _ = User.objects.get_or_create(
            username='worker1',
            defaults={
                'name': '김철수',
                'user_type': 'worker',
            },
        )
        worker_user.set_password('worker1234!')
        worker_user.save()

        manager_user, _ = User.objects.get_or_create(
            username='manager1',
            defaults={
                'name': '현장관리자',
                'user_type': 'manager',
                'is_staff': True,
            },
        )
        manager_user.set_password('manager1234!')
        manager_user.save()

        self.stdout.write('  테스트 계정 3개 (admin / worker1 / manager1)')

        # ── 1. 사업장 ──────────────────────────────────────────────────────
        facilities = []
        for code, name in [('FAC001', '제1공장'), ('FAC002', '제2공장'), ('FAC003', '창고동')]:
            f, _ = Facility.objects.get_or_create(
                facility_code=code,
                defaults={'facility_name': name },
            )
            facilities.append(f)
        self.stdout.write(f'  사업장 {len(facilities)}개')

        # ── 2. 건물 ────────────────────────────────────────────────────────
        buildings = []
        for facility in facilities:
            b, _ = Building.objects.get_or_create(
                facility=facility,
                building_code='B01',
                defaults={'building_name': f'{facility.facility_name} 본관'},
            )
            buildings.append(b)
        self.stdout.write(f'  건물 {len(buildings)}개')

        # ── 3. 임계치 정책 ─────────────────────────────────────────────────
        policy_data = [
            {'metric_code': 'co',    'warning_max': 50.0,  'danger_max': 100.0},
            {'metric_code': 'h2s',   'warning_max': 5.0,   'danger_max': 10.0},
            {'metric_code': 'current_value', 'warning_max': 80.0, 'danger_max': 100.0},
            {'metric_code': 'power_value',   'warning_max': 90.0, 'danger_max': 110.0},
        ]
        policies = {}
        for p in policy_data:
            obj, _ = ThresholdPolicy.objects.get_or_create(
                metric_code=p['metric_code'],
                defaults={**p, 'action_type': 'alert', 'is_active': True},
            )
            policies[p['metric_code']] = obj
        self.stdout.write(f'  임계치 정책 {len(policies)}개')

        # ── 4. 장비 ────────────────────────────────────────────────────────
        devices = []
        device_specs = [
            ('GAS-001', '가스센서-A', 'gas', facilities[0]),
            ('GAS-002', '가스센서-B', 'gas', facilities[0]),
            ('GAS-003', '가스센서-C', 'gas', facilities[1]),
            ('PWR-001', '전력계-A',   'power', facilities[0]),
            ('PWR-002', '전력계-B',   'power', facilities[1]),
            ('PWR-003', '전력계-C',   'power', facilities[2]),
        ]
        for uid, name, dtype, facility in device_specs:
            d, _ = Device.objects.get_or_create(
                device_uid=uid,
                defaults={
                    'device_name': name,
                    'device_type': dtype,
                    'facility': facility,
                    'port': 502,
                },
            )
            devices.append(d)
        self.stdout.write(f'  장비 {len(devices)}개')

        # ── 5. 채널 ────────────────────────────────────────────────────────
        channel_specs = [
            (devices[0], 1, 'co',  'CO',  'gas'),
            (devices[0], 2, 'h2s', 'H2S', 'gas'),
            (devices[1], 1, 'co',  'CO',  'gas'),
            (devices[3], 1, 'current_value', '전류', 'power'),
            (devices[3], 2, 'power_value',   '전력', 'power'),
        ]
        for dev, ch_no, code, ch_name, ch_type in channel_specs:
            DeviceChannel.objects.get_or_create(
                device=dev, channel_code=code,
                defaults={'channel_name': ch_name},
            )
        self.stdout.write('  채널 생성 완료')

        # ── 6. 작업자 ──────────────────────────────────────────────────────
        workers = []
        worker_specs = [
            ('W001', '김철수'), ('W002', '이영희'), ('W003', '박민준'),
            ('W004', '최수진'), ('W005', '정도현'),
        ]
        for i, (no, name) in enumerate(worker_specs):
            w, _ = Worker.objects.get_or_create(
                worker_no=no,
                defaults={'worker_name': name, 'current_state': 'on_duty'},
            )
            workers.append(w)

        # worker1 계정 → 김철수(W001) 연결
        if not workers[0].user:
            workers[0].user = worker_user
            workers[0].save()

        # admin 계정 → 이영희(W002) 연결
        Worker.objects.filter(user=admin_user).update(user=None)
        if not workers[1].user:
            workers[1].user = admin_user
            workers[1].save()

        self.stdout.write(f'  작업자 {len(workers)}명 (worker1→김철수, admin→이영희 연결)')

        # ── 7. 알람 규칙 ───────────────────────────────────────────────────
        rules = []
        rule_specs = [
            ('CO 임계치 초과 규칙',    'threshold', policies['co']),
            ('H2S 임계치 초과 규칙',   'threshold', policies['h2s']),
            ('전류 임계치 초과 규칙',  'threshold', policies['current_value']),
            ('전력 이상 감지 규칙',    'power',     policies['power_value']),
            ('센서 데이터 누락 규칙',  'missing',   None),
            ('장비 오프라인 감지 규칙','offline',   None),
        ]
        for name, rtype, policy in rule_specs:
            r, _ = AlarmRule.objects.get_or_create(
                rule_name=name,
                defaults={
                    'rule_type': rtype,
                    'action_type': 'notify',
                    'is_active': True,
                    'threshold_policy': policy,
                },
            )
            rules.append(r)
        self.stdout.write(f'  알람 규칙 {len(rules)}개')

        # ── 8. 알람 이벤트 ─────────────────────────────────────────────────
        now = timezone.now()
        event_specs = [
            # (rule_idx, facility_idx, device_idx, worker_idx, severity, event_type, status, hours_ago, title, message)
            (0, 0, 0, None, 'danger',  'gas',      'open',
             0.5, 'CO 농도 위험 수준 초과',
             '제1공장 가스센서-A에서 CO 농도 152ppm 감지. 허용 기준(100ppm) 초과.'),
            (1, 0, 0, 2,   'warning', 'gas',      'acknowledged',
             2,   'H2S 경고 수준 감지',
             '가스센서-A CH2에서 H2S 7.3ppm 감지. 경고 임계치(5ppm) 초과. 작업자 박민준 인근 위치.'),
            (3, 1, 3, None, 'danger', 'power',    'open',
             1,   '제2공장 전력계 이상',
             '전력계-B에서 순간 과전력 감지. 정격 대비 118% 부하 발생.'),
            (4, 0, 1, None, 'warning', 'device',   'open',
             3,   '가스센서-B 데이터 누락',
             '가스센서-B(GAS-002)에서 5분 이상 데이터 수신 없음.'),
            (5, 2, 5, None, 'warning', 'device',   'acknowledged',
             5,   '창고동 전력계 오프라인',
             '전력계-C(PWR-003)가 오프라인 상태로 전환됨. 네트워크 연결 확인 필요.'),
            (2, 0, 3, None, 'normal',  'power',    'closed',
             24,  '전류 임계치 경고',
             '전력계-A 전류값 83A 감지. 경고 임계치(80A) 소폭 초과. 이후 정상 복귀.'),
            (0, 1, 2, 0,   'danger',  'gas',      'open',
             0.2, 'CO 긴급 경보',
             '제2공장 가스센서-C에서 CO 농도 210ppm 감지. 즉각 대피 조치 필요.'),
            (1, 0, 0, 3,   'warning', 'gas',      'open',
             4,   'H2S 주의 수준 감지',
             '가스센서-A에서 H2S 3.1ppm 감지. 주의 단계. 환기 실시 권고.'),
            (5, 0, 0, None, 'warning', 'device',   'open',
             6,   '가스센서-A 간헐적 오프라인',
             '가스센서-A(GAS-001)가 주기적으로 응답 없음. 펌웨어 점검 필요.'),
            (3, 2, 5, 4,   'normal',  'power',    'closed',
             48,  '창고동 전력 미세 이상',
             '전력계-C에서 미세 전압 변동 감지. 조치 후 정상 복귀.'),
        ]

        created_events = []
        for spec in event_specs:
            ri, fi, di, wi, severity, etype, status, hours_ago, title, msg = spec
            worker = workers[wi] if wi is not None else None
            ev, created = AlarmEvent.objects.get_or_create(
                title=title,
                defaults={
                    'rule':         rules[ri],
                    'facility':     facilities[fi],
                    'device':       devices[di],
                    'worker':       worker,
                    'severity':     severity,
                    'event_type':   etype,
                    'event_status': status,
                    'message':      msg,
                    'occurred_at':  now - timedelta(hours=hours_ago),
                    'acknowledged_at': now - timedelta(hours=hours_ago - 0.3) if status in ('acknowledged', 'closed') else None,
                    'closed_at':    now - timedelta(hours=hours_ago - 1) if status == 'closed' else None,
                },
            )
            created_events.append(ev)

        self.stdout.write(f'  알람 이벤트 {len(created_events)}개')

        # ── 9. 조치 이력 ───────────────────────────────────────────────────
        for ev in created_events:
            if ev.event_status in ('acknowledged', 'closed'):
                EventHistory.objects.get_or_create(
                    alarm_event=ev,
                    action_type='acknowledge',
                    defaults={'action_note': '현장 확인 후 조치 착수'},
                )
            if ev.event_status == 'closed':
                EventHistory.objects.get_or_create(
                    alarm_event=ev,
                    action_type='close',
                    defaults={'action_note': '조치 완료 및 정상 복귀 확인'},
                )

        self.stdout.write('  조치 이력 생성 완료')
        self.stdout.write(self.style.SUCCESS('더미 데이터 생성 완료!'))
