"""LocationNode ↔ Device(device_type='loc') 일회 데이터 동기화.

문제: 두 모델이 별도로 운영되어 한쪽에만 등록된 노드가 다른 페이지에 표시되지 않음.

해결:
  1) 기존 device_type='loc' Device 중 LocationNode와 연결되지 않은 행을 폐기.
  2) LocationNode 각 행에 대해 동일 코드의 Device(loc)를 생성하고 OneToOneField 연결.

이후로는 signals(`facilities/signals.py`)가 양방향 자동 동기화를 유지하므로
이 명령은 한 번만 실행하면 된다.

사용:
    docker compose exec django python manage.py sync_loc_devices
    docker compose exec django python manage.py sync_loc_devices --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "LocationNode ↔ Device(loc) 데이터를 1:1로 정렬한다 (일회용)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='실제 변경 없이 계획만 출력',
        )

    def handle(self, *args, **options):
        from facilities.models import Facility, LocationNode
        from facilities.signals import _LnDevSyncGuard  # signals 재발화 방지
        from monitoring.models import Device

        dry = options['dry_run']
        prefix = '[DRY-RUN] ' if dry else ''

        # 사전 상태 ──────────────────────────────────
        orphan_devices = Device.objects.filter(
            device_type='loc',
            location_node__isnull=True,
        )
        unlinked_nodes = LocationNode.objects.filter(device__isnull=True)

        self.stdout.write(self.style.NOTICE(
            f"동기화 전: LocationNode 미연결={unlinked_nodes.count()}건, "
            f"Device(loc) 고아={orphan_devices.count()}건"
        ))

        for dev in orphan_devices:
            self.stdout.write(
                f"  - 폐기 예정 Device(loc): code={dev.device_code!r} "
                f"uid={dev.device_uid!r} name={dev.device_name!r}"
            )

        facility_fallback = Facility.objects.first()
        if facility_fallback is None and unlinked_nodes.exists():
            self.stdout.write(self.style.ERROR(
                "Facility 가 하나도 없어 Device(loc) 생성 불가. 중단."
            ))
            return

        # 실행 ──────────────────────────────────────
        if dry:
            for node in unlinked_nodes:
                self.stdout.write(
                    f"  + 생성 예정 Device(loc): code={node.node_code!r} "
                    f"name={node.node_name!r}"
                )
            self.stdout.write(self.style.WARNING(
                f"\n{prefix}계획만 출력. 실제 적용은 --dry-run 없이 재실행."
            ))
            return

        with transaction.atomic(), _LnDevSyncGuard():
            # 1) 고아 Device(loc) 폐기
            deleted_count = 0
            for dev in orphan_devices:
                try:
                    dev.delete()
                    deleted_count += 1
                except Exception as e:  # PROTECT 등
                    self.stdout.write(self.style.ERROR(
                        f"  ! Device {dev.device_code} 삭제 실패: {e}"
                    ))

            # 2) LocationNode 각각에 Device(loc) 동기 생성 + 연결
            created_count = 0
            for node in unlinked_nodes:
                # facility 해결
                if node.floor_id and node.floor and node.floor.building_id:
                    facility = node.floor.building.facility
                else:
                    facility = facility_fallback

                dev = Device.objects.create(
                    device_type='loc',
                    device_code=node.node_code,
                    device_uid=node.node_code,
                    device_name=node.node_name,
                    facility=facility,
                    floor=node.floor,
                    port=0,
                    is_active=(node.status == 'active'),
                    status='active',
                )
                # signals 재발화 방지를 위해 .update() 사용
                LocationNode.objects.filter(pk=node.pk).update(device=dev)
                created_count += 1
                self.stdout.write(
                    f"  ✓ {node.node_code} ↔ Device(pk={dev.pk}) 연결"
                )

        # 사후 상태 ──────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f"\n동기화 완료: 폐기 {deleted_count}건, 생성·연결 {created_count}건"
        ))

        # 검증 출력
        ln_total = LocationNode.objects.count()
        ln_linked = LocationNode.objects.filter(device__isnull=False).count()
        dv_total = Device.objects.filter(device_type='loc').count()
        dv_linked = Device.objects.filter(
            device_type='loc', location_node__isnull=False
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f"검증: LocationNode {ln_linked}/{ln_total} 연결, "
            f"Device(loc) {dv_linked}/{dv_total} 연결"
        ))
