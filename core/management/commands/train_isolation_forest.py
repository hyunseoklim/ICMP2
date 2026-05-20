"""
시나리오 A (정상운영) 데이터로 Isolation Forest 초기 학습 후 파일 저장

사용법:
  python manage.py train_isolation_forest              # 전체 가스 장비
  python manage.py train_isolation_forest --device GAS-001  # 특정 장비만
"""

from django.core.management.base import BaseCommand

GAS_FIELDS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']
MIN_SAMPLES = 20


def _build_feature_row(reading):
    """9개 가스 raw값 → 9차원 feature 벡터."""
    return [float(getattr(reading, gas, None) or 0.0) for gas in GAS_FIELDS]


class Command(BaseCommand):
    help = "시나리오 A 정상 데이터로 Isolation Forest 초기 학습"

    def add_arguments(self, parser):
        parser.add_argument(
            '--device', type=str,
            help='특정 device_uid만 학습 (기본: 전체 가스 장비)',
        )

    def handle(self, *args, **options):
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            self.stderr.write("scikit-learn 미설치 — pip install scikit-learn")
            return

        try:
            import joblib  # noqa: F401
        except ImportError:
            self.stderr.write("joblib 미설치 — pip install joblib")
            return

        from monitoring.models import Device, GasReading
        from monitoring.anomaly import isolation

        target_uid = options.get('device')

        gas_devices = Device.objects.filter(device_type='gas')
        if target_uid:
            gas_devices = gas_devices.filter(device_uid=target_uid)

        if not gas_devices.exists():
            self.stderr.write("학습 대상 가스 장비 없음")
            return

        for device in gas_devices:
            uid = device.device_uid
            self.stdout.write(f"▶ {uid} 학습 시작...")

            qs = GasReading.objects.filter(
                device=device,
                quality_flag='ok',
                raw_payload__scenario='normal_operation',
            ).order_by('measured_at')

            readings = list(qs)
            if not readings:
                self.stdout.write(
                    f"  {uid}: 시나리오 A 데이터 없음 "
                    "— python manage.py generate_scenario_data 먼저 실행"
                )
                continue

            matrix = []
            for reading in readings:
                row = _build_feature_row(reading)
                if len(row) == len(GAS_FIELDS):
                    matrix.append(row)

            if len(matrix) < MIN_SAMPLES:
                self.stdout.write(
                    f"  {uid}: 유효 샘플 부족 ({len(matrix)}건, 최소 {MIN_SAMPLES} 필요)"
                )
                continue

            model = IsolationForest(
                n_estimators=100,
                contamination=0.05,
                random_state=42,
                n_jobs=1,
            )
            model.fit(matrix)

            # isolation.py 메모리에 주입 + 파일 저장
            isolation._models[uid] = {'model': model, 'trained': True}
            saved = isolation.save_model(uid)

            if saved:
                self.stdout.write(self.style.SUCCESS(
                    f"  {uid}: 완료 ({len(matrix)}샘플, 파일 저장됨)"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"  {uid}: 학습 완료 ({len(matrix)}샘플), 파일 저장 실패"
                ))

        self.stdout.write(self.style.SUCCESS("Isolation Forest 초기 학습 완료"))
