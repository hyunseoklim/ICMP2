"""facilities 도메인 Django signal → Celery 태스크 bridge.

Floor.width/length 또는 FloorGrid.cell_size가 실제로 변경됐을 때만
handle_floor_dimensions_changed 태스크를 큐잉한다.

pre_save 단계에서 이전 값을 instance에 임시 저장(`_dims_changed`)하고
post_save에서 비교 결과를 활용한다. 무관 필드(예: floor_name) 변경에는
태스크를 큐잉하지 않아 IndexGrid 불필요 재생성을 차단한다.
"""
import logging
import threading

from django.db import transaction
from django.db.models import ProtectedError
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import Floor, FloorGrid
from .tasks import handle_floor_dimensions_changed

logger = logging.getLogger(__name__)

_FLOOR_DIMS = ("width", "length")
_FLOOR_GRID_DIMS = ("cell_size",)


def _detect_changes(sender, instance, tracked_fields) -> bool:
    """이전 DB 값과 비교해 tracked_fields 중 하나라도 변경됐는지 반환."""
    if instance.pk is None:
        return False
    try:
        old = sender.objects.only(*tracked_fields).get(pk=instance.pk)
    except sender.DoesNotExist:
        return False
    return any(
        getattr(old, f) != getattr(instance, f)
        for f in tracked_fields
    )


@receiver(pre_save, sender=Floor)
def _floor_pre_save(sender, instance, **kwargs):
    instance._dims_changed = _detect_changes(sender, instance, _FLOOR_DIMS)


@receiver(post_save, sender=Floor)
def _floor_post_save(sender, instance, created, **kwargs):
    if created:
        return
    if not getattr(instance, "_dims_changed", False):
        return
    floor_id = instance.id
    transaction.on_commit(
        lambda: handle_floor_dimensions_changed.delay(floor_id=floor_id)
    )


@receiver(pre_save, sender=FloorGrid)
def _floor_grid_pre_save(sender, instance, **kwargs):
    instance._dims_changed = _detect_changes(sender, instance, _FLOOR_GRID_DIMS)


@receiver(post_save, sender=FloorGrid)
def _floor_grid_post_save(sender, instance, created, **kwargs):
    if created:
        return
    if not getattr(instance, "_dims_changed", False):
        return
    floor_id = instance.floor_id
    transaction.on_commit(
        lambda: handle_floor_dimensions_changed.delay(floor_id=floor_id)
    )


# ─────────────────────────────────────────────────────────────────────
# LocationNode ↔ Device(device_type='loc') 양방향 자동 동기화
#
# - 두 모델이 책임 분리(LocationNode=좌표/지도, Device=담당자/점검/last_seen)된
#   상태에서 한쪽만 등록되어 다른 쪽 페이지에 보이지 않는 문제를 해결.
# - thread-local 가드(`_LN_DEV_SYNC`)로 cascade 시 무한 재귀 차단.
# - 삭제 시 한쪽이 PROTECT FK(InspectionLog, NodeReading)로 막히면
#   ProtectedError를 catch하고 경고만 남김 (트랜잭션 자체는 호출자가 결정).
# ─────────────────────────────────────────────────────────────────────

_LN_DEV_SYNC = threading.local()


def _ln_dev_syncing() -> bool:
    return getattr(_LN_DEV_SYNC, "active", False)


class _LnDevSyncGuard:
    def __enter__(self):
        _LN_DEV_SYNC.active = True

    def __exit__(self, *exc):
        _LN_DEV_SYNC.active = False


def _resolve_facility_for_node(node):
    """LocationNode.floor → Building.facility 체인. 없으면 첫 Facility로 fallback."""
    from facilities.models import Facility

    if node.floor_id and node.floor and node.floor.building_id:
        return node.floor.building.facility
    return Facility.objects.first()


# 모델 import는 함수 안에서 lazy로 처리 (signals.py 로딩 순서 영향 차단)
from facilities.models import LocationNode as _LocationNode  # noqa: E402
from monitoring.models import Device as _Device  # noqa: E402


@receiver(post_save, sender=_LocationNode)
def _ln_to_device_sync(sender, instance, created, **kwargs):
    if _ln_dev_syncing():
        return
    from monitoring.models import Device

    if instance.device_id is None:
        # 신규 또는 link 미설정 LocationNode → Device 자동 생성·연결
        facility = _resolve_facility_for_node(instance)
        if facility is None:
            logger.warning(
                "LocationNode %s: facility 미해결 → Device 동기화 스킵",
                instance.node_code,
            )
            return
        with _LnDevSyncGuard():
            dev = Device.objects.create(
                device_type='loc',
                device_code=instance.node_code,
                device_uid=instance.node_code,
                device_name=instance.node_name,
                facility=facility,
                floor=instance.floor,
                port=0,
                is_active=(instance.status == 'active'),
                status='active',
            )
            # .update()는 post_save를 발화시키지 않아 LocationNode 재귀 방지에 안전
            sender.objects.filter(pk=instance.pk).update(device=dev)
            instance.device = dev
        return

    # 기존 연결이 있는 경우 변경된 공유 필드만 Device로 전파
    dev = instance.device
    dirty = []
    if dev.device_name != instance.node_name:
        dev.device_name = instance.node_name
        dirty.append('device_name')
    if dev.floor_id != instance.floor_id:
        dev.floor_id = instance.floor_id
        dirty.append('floor')
    target_active = (instance.status == 'active')
    if dev.is_active != target_active:
        dev.is_active = target_active
        dirty.append('is_active')
    if dirty:
        with _LnDevSyncGuard():
            dev.save(update_fields=dirty)


@receiver(post_delete, sender=_LocationNode)
def _ln_to_device_delete(sender, instance, **kwargs):
    if _ln_dev_syncing():
        return
    if not instance.device_id:
        return
    with _LnDevSyncGuard():
        try:
            instance.device.delete()
        except ProtectedError:
            logger.warning(
                "Device(loc) pk=%s 삭제 보호됨 (InspectionLog 참조). LocationNode만 삭제됨.",
                instance.device_id,
            )


@receiver(post_save, sender=_Device)
def _device_to_ln_sync(sender, instance, created, **kwargs):
    if _ln_dev_syncing():
        return
    if instance.device_type != 'loc':
        return
    from facilities.models import LocationNode

    node = LocationNode.objects.filter(device_id=instance.pk).first()

    if node is None and created:
        with _LnDevSyncGuard():
            LocationNode.objects.create(
                node_code=instance.device_code,
                node_name=instance.device_name,
                floor=instance.floor,
                device=instance,
                status='active' if instance.is_active else 'inactive',
            )
        return

    if node is not None:
        dirty = []
        if node.node_name != instance.device_name:
            node.node_name = instance.device_name
            dirty.append('node_name')
        if node.floor_id != instance.floor_id:
            node.floor_id = instance.floor_id
            dirty.append('floor')
        target_status = 'active' if instance.is_active else 'inactive'
        if node.status != target_status:
            node.status = target_status
            dirty.append('status')
        if dirty:
            with _LnDevSyncGuard():
                node.save(update_fields=dirty)


@receiver(pre_delete, sender=_Device)
def _device_to_ln_delete(sender, instance, **kwargs):
    # pre_delete 사용 이유: LocationNode.device FK 가 on_delete=SET_NULL 이라
    # post_delete 시점에는 이미 LocationNode.device_id 가 NULL 로 풀려
    # reverse 조회가 실패한다. Device 삭제 직전에 link 가 살아 있는 동안 처리.
    if _ln_dev_syncing():
        return
    if instance.device_type != 'loc':
        return
    from facilities.models import LocationNode

    node = LocationNode.objects.filter(device_id=instance.pk).first()
    if node is None:
        return
    with _LnDevSyncGuard():
        try:
            node.delete()
        except ProtectedError:
            logger.warning(
                "LocationNode %s 삭제 보호됨 (NodeReading 참조). Device만 삭제됨.",
                node.node_code,
            )
