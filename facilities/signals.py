"""facilities 도메인 Django signal → 도메인 이벤트 bridge.

Floor.width/length 또는 FloorGrid.cell_size가 실제로 변경됐을 때만
FloorDimensionsChanged 이벤트를 발행한다.

pre_save 단계에서 이전 값을 instance에 임시 저장(`_dims_changed`)하고
post_save에서 비교 결과를 활용한다. 무관 필드(예: floor_name) 변경에는
이벤트를 발행하지 않아 IndexGrid 불필요 재생성을 차단한다.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .events import FloorDimensionsChanged, publish
from .models import Floor, FloorGrid

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
        lambda: publish(FloorDimensionsChanged(floor_id=floor_id))
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
        lambda: publish(FloorDimensionsChanged(floor_id=floor_id))
    )
