"""
시나리오 B-M 데이터로 Isolation Forest + Z-score 탐지 검증

사용법:
  python manage.py validate_isolation_forest
"""

from django.core.management.base import BaseCommand

GAS_FIELDS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']

SCENARIO_LABELS = {
    'ventilation_failure': 'B 환기불량',
    'oxygen_depletion':    'C 산소저하',
    'h2s_acute_leak':      'D H2S누출',
    'co_combustion':       'E CO연소이상',
    'voc_work_change':     'F VOC변화',
    'complex_anomaly':     'G 복합이상',
    'sensor_error':        'H 센서오류',
}


class Command(BaseCommand):
    help = "시나리오 B-M 데이터로 이상탐지 검증"

    def handle(self, *args, **options):
        from monitoring.models import GasReading
        from monitoring.anomaly import isolation
        from monitoring.anomaly.window import push, GAS_FIELDS as WF

        # 시나리오 A (정상) 데이터를 슬라이딩 윈도우에 먼저 채워두기
        self.stdout.write("▶ 슬라이딩 윈도우 초기화 (시나리오 A)...")
        normal_qs = GasReading.objects.filter(
            raw_payload__scenario='normal_operation',
        ).order_by('measured_at')

        for reading in normal_qs:
            push(reading.device.device_uid, reading)

        self.stdout.write(f"  정상 데이터 {normal_qs.count()}건 버퍼에 적재 완료")

        # 시나리오 B-M 검증
        self.stdout.write("\n▶ 시나리오 B-M 이상탐지 검증...")

        total_all = 0
        detected_all = 0

        for scenario_key, label in SCENARIO_LABELS.items():
            qs = GasReading.objects.filter(
                raw_payload__scenario=scenario_key,
                raw_payload__is_anomaly=True,
            ).order_by('measured_at')

            readings = list(qs)
            if not readings:
                self.stdout.write(f"  {label}: 데이터 없음")
                continue

            detected = 0
            for reading in readings:
                uid = reading.device.device_uid
                result = isolation.analyze(uid, reading)
                if result.get('is_anomaly'):
                    detected += 1

            total = len(readings)
            rate = detected / total * 100 if total else 0
            total_all += total
            detected_all += detected

            status = self.style.SUCCESS("✅") if rate >= 70 else self.style.WARNING("⚠️")
            self.stdout.write(
                f"  {status} {label}: {total}건 중 {detected}건 탐지 → {rate:.1f}%"
            )

        # 전체 요약
        overall = detected_all / total_all * 100 if total_all else 0
        self.stdout.write(f"\n전체 탐지율: {detected_all}/{total_all} → {overall:.1f}%")

        if overall >= 70:
            self.stdout.write(self.style.SUCCESS("Isolation Forest 검증 통과"))
        else:
            self.stdout.write(self.style.WARNING("탐지율 낮음 — 모델 재학습 권장"))
