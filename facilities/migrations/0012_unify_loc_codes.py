"""LocationNode·Device(loc) 코드를 LOC-XXX 형식으로 통일하고 id 순으로 재번호한다.

기존:
  - 시드 LocationNode.node_code = "LN-001" ... → Device.device_code = "LN-001",
    Device.device_uid = "LOC-LN-001"
  - UI 등록 Device.device_code = "001" ... → Device.device_uid = "LOC-001"
변경 후:
  - LocationNode.node_code = "LOC-001" ... (id 오름차순)
  - Device.device_code = Device.device_uid = "LOC-001" ... (LocationNode와 동일)
  - 미연결 Device(loc) 도 동일 순번 풀에서 함께 재번호.

unique 제약(device_uid·node_code) 충돌 회피를 위해 2-pass.
"""
from django.db import migrations


def _forward(apps, schema_editor):
    LocationNode = apps.get_model('facilities', 'LocationNode')
    Device = apps.get_model('monitoring', 'Device')

    # 1) LocationNode 재번호 (id 오름차순)
    nodes = list(LocationNode.objects.order_by('id'))
    # Pass A: 임시 prefix 로 충돌 회피
    for node in nodes:
        LocationNode.objects.filter(pk=node.pk).update(node_code=f'__TMP_LN_{node.pk}')
    # Pass B: 최종 LOC-XXX
    for idx, node in enumerate(nodes, start=1):
        LocationNode.objects.filter(pk=node.pk).update(node_code=f'LOC-{idx:03d}')

    # 2) Device(loc) 재번호
    #   - LocationNode 와 연결된 Device 는 node_code 와 동일 값 사용
    #   - 미연결 Device 는 LocationNode 다음 번호부터 부여
    linked_devs = []
    seen_dev_pks = set()
    for idx, node in enumerate(nodes, start=1):
        if node.device_id:
            linked_devs.append((node.device_id, idx))
            seen_dev_pks.add(node.device_id)

    orphan_devs = list(
        Device.objects.filter(device_type='loc')
        .exclude(pk__in=seen_dev_pks)
        .order_by('id')
        .values_list('pk', flat=True)
    )

    # Pass A: 임시값
    all_dev_pks = [pk for pk, _ in linked_devs] + list(orphan_devs)
    for pk in all_dev_pks:
        Device.objects.filter(pk=pk).update(
            device_uid=f'__TMP_LOC_{pk}',
            device_code=f'__TMP_LOC_{pk}',
        )
    # Pass B: 최종값
    for pk, idx in linked_devs:
        code = f'LOC-{idx:03d}'
        Device.objects.filter(pk=pk).update(device_uid=code, device_code=code)

    next_idx = len(nodes) + 1
    for pk in orphan_devs:
        code = f'LOC-{next_idx:03d}'
        Device.objects.filter(pk=pk).update(device_uid=code, device_code=code)
        next_idx += 1


class Migration(migrations.Migration):

    dependencies = [
        ('facilities', '0011_locationnode_device'),
        ('monitoring', '0010_alter_thresholdpolicy_action_type_alert_to_notify'),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
    ]
