"""
python manage.py seed_monitoring
monitoring 앱 전용 시드 데이터
- Facility, Device, DeviceChannel, GasReading, PowerReading, ThresholdPolicy
- 위험/주의/정상 다양한 상태 포함
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
import random


class Command(BaseCommand):
    help = 'monitoring 앱 시드 데이터 생성'

    def handle(self, *args, **options):
        from facilities.models import Facility
        from monitoring.models import (
            Device, DeviceChannel,
            GasReading, PowerReading, PowerStatusReading,
            ThresholdPolicy,
        )

        self.stdout.write('monitoring 시드 데이터 생성 시작...')

        # ── 1. 사업장 ──────────────────────────────────────────
        facilities = []
        for code, name in [
            ('FAC-001', '제1공장'),
            ('FAC-002', '제2공장'),
            ('FAC-003', '창고동'),
        ]:
            f, _ = Facility.objects.get_or_create(
                facility_code=code,
                defaults={'facility_name': name, 'status': 'active'},
            )
            facilities.append(f)
        self.stdout.write(f'  사업장 {len(facilities)}개')

        # ── 2. 임계치 정책 ──────────────────────────────────────
        policy_data = [
            ('co',  'CO 임계치',  25.0,  200.0),
            ('h2s', 'H2S 임계치', 10.0,  15.0),
            ('co2', 'CO2 임계치', 1000.0, 5000.0),
            ('o2',  'O2 임계치',  18.0,  16.0),
            ('no2', 'NO2 임계치', 3.0,   5.0),
            ('so2', 'SO2 임계치', 2.0,   5.0),
            ('o3',  'O3 임계치',  0.06,  0.12),
            ('nh3', 'NH3 임계치', 25.0,  35.0),
            ('voc', 'VOC 임계치', 0.5,   1.0),
        ]
        for code, name, warn, danger in policy_data:
            ThresholdPolicy.objects.get_or_create(
                metric_code=code,
                defaults={
                    'action_type': 'alert',
                    'warning_min': 0,
                    'warning_max': warn,
                    'danger_min':  0,
                    'danger_max':  danger,
                    'is_active':   True,
                },
            )
        self.stdout.write(f'  임계치 정책 {len(policy_data)}개')

        # ── 3. 가스 센서 장비 ───────────────────────────────────
        gas_specs = [
            ('GAS-001', '압연동 가스센서',    facilities[0], 8081),
            ('GAS-002', '도장라인 가스센서',  facilities[0], 8082),
            ('GAS-003', '용접구역 가스센서',  facilities[1], 8083),
            ('GAS-004', '창고동 가스센서',    facilities[2], 8084),
        ]
        gas_devices = []
        for uid, name, facility, port in gas_specs:
            d, _ = Device.objects.get_or_create(
                device_uid=uid,
                defaults={
                    'device_name': name,
                    'device_type': 'gas',
                    'device_code': uid,
                    'facility':    facility,
                    'status':      'active',
                    'port':        port,
                },
            )
            gas_devices.append(d)
        self.stdout.write(f'  가스 센서 {len(gas_devices)}개')

        # ── 4. 전력 장비 ────────────────────────────────────────
        power_specs = [
            ('PWR-001', '제1공장 스마트파워', facilities[0], 8091),
            ('PWR-002', '제2공장 스마트파워', facilities[1], 8092),
        ]
        power_devices = []
        for uid, name, facility, port in power_specs:
            d, _ = Device.objects.get_or_create(
                device_uid=uid,
                defaults={
                    'device_name': name,
                    'device_type': 'power',
                    'device_code': uid,
                    'facility':    facility,
                    'status':      'active',
                    'port':        port,
                },
            )
            power_devices.append(d)
        self.stdout.write(f'  전력 장비 {len(power_devices)}개')

        # ── 5. 전력 채널 (slave 구조) ───────────────────────────
        channel_specs = [
            # (device_idx, channel_code, channel_name, rated_power_w)
            (0, 'slave01', '압연기 A',       800),
            (0, 'slave02', '압연기 B',       800),
            (0, 'slave11', 'CCTV 1번',       50),
            (0, 'slave12', 'CCTV 2번',       50),
            (0, 'slave21', '냉각팬 A',       500),
            (0, 'slave22', '냉각팬 B',       500),
            (0, 'slave31', '조명 A구역',     300),
            (0, 'slave32', '조명 B구역',     300),
            (0, 'slave41', '컨베이어 A',     600),
            (0, 'slave42', '컨베이어 B',     600),
            (0, 'slave51', '환기팬 A',       400),
            (0, 'slave52', '환기팬 B',       400),
            (0, 'slave61', '충전스테이션 A', 1000),
            (0, 'slave62', '충전스테이션 B', 1000),
            (0, 'slave71', '비상조명',        100),
            (0, 'slave72', '안전장치 전원',   200),

            (1, 'slave01', '도장 로봇 A',    900),
            (1, 'slave02', '도장 로봇 B',    900),
            (1, 'slave11', 'CCTV 3번',        50),
            (1, 'slave12', 'CCTV 4번',        50),
            (1, 'slave21', '집진기 A',        700),
            (1, 'slave22', '집진기 B',        700),
            (1, 'slave31', '조명 C구역',      300),
            (1, 'slave32', '조명 D구역',      300),
        ]
        channels = {}
        for dev_idx, code, name, rated_w in channel_specs:
            device = power_devices[dev_idx]
            ch, _ = DeviceChannel.objects.get_or_create(
                device=device,
                channel_code=code,
                defaults={
                    'channel_name':  name,
                    'rated_power_w': rated_w,
                    'is_active':     True,
                },
            )
            channels[(dev_idx, code)] = ch
        self.stdout.write(f'  전력 채널 {len(channels)}개')

        # ── 6. 가스 측정값 (위험/주의/정상 다양하게) ────────────
        # (device_idx, co, h2s, co2, o2, no2, so2, o3, nh3, voc, 설명)
        gas_readings = [
            # 위험 센서
            (0, 250.0, 18.0, 6000.0, 14.5, 1.0, 1.0, 0.03, 10.0, 0.3, '위험'),
            # 주의 센서
            (1, 30.0,  12.0, 1500.0, 17.0, 1.0, 1.0, 0.03, 10.0, 0.3, '주의'),
            # 정상 센서
            (2, 5.0,   2.0,  600.0,  20.8, 0.5, 0.5, 0.02, 5.0,  0.1, '정상'),
            # 복합 위험
            (3, 210.0, 8.0,  800.0,  15.5, 4.5, 1.5, 0.10, 30.0, 0.8, '복합주의'),
        ]
        for dev_idx, co, h2s, co2, o2, no2, so2, o3, nh3, voc, label in gas_readings:
            GasReading.objects.create(
                device=gas_devices[dev_idx],
                co=co, h2s=h2s, co2=co2, o2=o2,
                no2=no2, so2=so2, o3=o3, nh3=nh3, voc=voc,
                measured_at=timezone.now(),
            )
        self.stdout.write(f'  가스 측정값 {len(gas_readings)}개 (위험/주의/정상 포함)')

        # ── 7. 전력 측정값 ──────────────────────────────────────
        # (dev_idx, code, current_a, voltage_v, power_w, 상태)
        power_readings = [
            # 정상
            (0, 'slave01', 30,  220, 660,  '정상'),
            (0, 'slave02', 28,  220, 616,  '정상'),
            # 주의 (부하율 50~75%)
            (0, 'slave11', 0,   0,   0,   'OFF'),
            (0, 'slave12', 5,   220, 110,  '정상'),
            (0, 'slave21', 35,  220, 770,  '주의'),
            (0, 'slave22', 40,  220, 880,  '주의'),
            # 위험 (부하율 75% 초과)
            (0, 'slave31', 55,  220, 1210, '위험'),
            (0, 'slave32', 0,   0,   0,   'OFF'),
            # 통신불능
            (0, 'slave41', -1,  -1,  -1,  '통신불능'),
            (0, 'slave42', 25,  220, 550,  '정상'),
            # 부분오류
            (0, 'slave51', -1,  220, 400,  '부분오류'),
            (0, 'slave52', 20,  220, 440,  '정상'),
            (0, 'slave61', 80,  220, 1760, '위험'),
            (0, 'slave62', 0,   0,   0,   'OFF'),
            (0, 'slave71', 5,   220, 110,  '정상'),
            (0, 'slave72', 10,  220, 220,  '정상'),

            (1, 'slave01', 45,  220, 990,  '위험'),
            (1, 'slave02', 42,  220, 924,  '주의'),
            (1, 'slave11', 3,   220, 66,   '정상'),
            (1, 'slave12', -1,  -1,  -1,  '통신불능'),
            (1, 'slave21', 38,  220, 836,  '주의'),
            (1, 'slave22', 0,   0,   0,   'OFF'),
            (1, 'slave31', 15,  220, 330,  '정상'),
            (1, 'slave32', 12,  220, 264,  '정상'),
        ]
        for dev_idx, code, cur, vol, pwr, label in power_readings:
            ch = channels.get((dev_idx, code))
            if not ch:
                continue
            PowerReading.objects.create(
                device=power_devices[dev_idx],
                channel=ch,
                current_a=cur,
                voltage_v=vol,
                power_w=pwr,
                measured_at=timezone.now(),
            )
            # ON/OFF 상태 기록
            PowerStatusReading.objects.get_or_create(
                device=power_devices[dev_idx],
                channel=ch,
                defaults={
                    'status_value': 0 if (cur == 0 and vol == 0) else 255,
                    'received_at': timezone.now(),
                },
            )
        self.stdout.write(f'  전력 측정값 {len(power_readings)}개 (정상/주의/위험/통신불능/OFF 포함)')

        self.stdout.write(self.style.SUCCESS('\nmonitoring 시드 데이터 생성 완료!'))
        self.stdout.write('')
        self.stdout.write('실행 방법:')
        self.stdout.write('  python manage.py seed_monitoring')