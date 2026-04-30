"""
작업자 이동 경로 더미 데이터 생성 커맨드

사용법:
    python manage.py seed_worker_routes          # 경로 데이터 생성
    python manage.py seed_worker_routes --clear  # 기존 위치 데이터 삭제 후 생성
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from facilities.models import Worker, WorkerLocation, Floor, Building


ROUTES = {
    "이영희": {
        "desc": "아찔한 탈출 — safe → danger → safe",
        "path": [
            (2,  15),   # 안전구역 대기
            (6,  10),   # 위험구역 접근
            (8,   5),   # 위험구역 진입 (danger)
            (10,  5),   # 위험구역 중심
            (14,  5),   # 위험구역 이탈
            (20, 10),   # 안전구역 복귀 (safe)
        ]
    },
    "박민준": {
        "desc": "warning → danger → safe 순차 전환",
        "path": [
            (45,  2),   # 안전구역 대기
            (35,  3),   # 이동
            (26,  4),   # 주의구역 진입 (warning)
            (25,  5),   # 주의구역 중심
            (25, 12),   # 주의구역 이탈 후 이동
            (25, 14),   # 위험구역1 진입 (danger)
            (25, 15),   # 위험구역1 중심
            (30, 20),   # 위험구역1 이탈 (safe)
        ]
    },
    "최수진": {
        "desc": "안전구역만 이동 — 항상 safe (대조군)",
        "path": [
            (40,  5),   # 안전구역
            (45, 10),   # 안전구역
            (45, 20),   # 안전구역
            (40, 28),   # 안전구역
            (35, 15),   # 안전구역
        ]
    },
    "정도현": {
        "desc": "창고동 위험구역 체류 → 탈출 → safe",
        "path": [
            (15, 25),   # 위험구역 내부 (danger) — 현재 위치
            (12, 22),   # 위험구역 내부 체류
            (10, 20),   # 위험구역 이탈 (safe)
            (5,  15),   # 안전구역 이동
            (5,  28),   # 안전구역 복귀
        ]
    },
}


class Command(BaseCommand):
    help = '작업자 이동 경로 더미 데이터 생성'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='기존 WorkerLocation 데이터 삭제 후 생성',
        )

    def handle(self, *args, **options):
        # Floor 확인
        try:
            floor = Floor.objects.get(id=1)
        except Floor.DoesNotExist:
            self.stderr.write('Floor id=1 이 존재하지 않습니다.')
            return

        # 기존 데이터 삭제
        if options['clear']:
            deleted, _ = WorkerLocation.objects.filter(floor=floor).delete()
            self.stdout.write(f'기존 WorkerLocation {deleted}건 삭제 완료')

        # 작업자별 경로 생성
        now = timezone.now()
        total = 0

        for worker_name, route in ROUTES.items():
            try:
                worker = Worker.objects.get(
                    worker_name=worker_name,
                    current_state='on_duty',
                )
            except Worker.DoesNotExist:
                self.stderr.write(f'작업자 없음 (스킵): {worker_name}')
                continue

            path = route['path']
            self.stdout.write(f'\n[{worker_name}] {route["desc"]}')

            for step, (x, y) in enumerate(path):
                # 각 경로 포인트를 step * 10초 간격으로 생성
                # 가장 마지막 포인트가 가장 최신 (현재 위치)
                measured_at = now - timedelta(
                    seconds=(len(path) - 1 - step) * 10
                )

                loc = WorkerLocation.objects.create(
                    worker=worker,
                    floor=floor,
                    x=x,
                    y=y,
                    cell_no=f'{int(y)}-{int(x)}',
                    measured_at=measured_at,
                )
                total += 1
                self.stdout.write(
                    f'  step {step+1}/{len(path)}: ({x}, {y}) @ {measured_at.strftime("%H:%M:%S")}'
                )

        self.stdout.write(
            self.style.SUCCESS(f'\n완료 — 총 {total}건 WorkerLocation 생성')
        )