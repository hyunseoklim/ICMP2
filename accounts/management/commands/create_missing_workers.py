from django.core.management.base import BaseCommand
from accounts.models import User
from facilities.models import Worker


class Command(BaseCommand):
    help = '기존 User 중 Worker가 없는 계정에 Worker 레코드를 생성합니다.'

    def handle(self, *args, **options):
        users_without_worker = User.objects.filter(worker__isnull=True)
        created_count = 0

        for user in users_without_worker:
            worker_no = f'W{user.pk:05d}'
            # worker_no 충돌 방지
            if Worker.objects.filter(worker_no=worker_no).exists():
                worker_no = f'W{user.pk:05d}X'

            Worker.objects.create(
                user=user,
                worker_no=worker_no,
                worker_name=user.name or user.username,
                department=user.department,
                phone=user.phone,
            )
            created_count += 1
            self.stdout.write(f'  생성: {user.name}({user.username}) → {worker_no}')

        self.stdout.write(self.style.SUCCESS(f'\n완료: {created_count}명의 Worker 레코드 생성됨'))
