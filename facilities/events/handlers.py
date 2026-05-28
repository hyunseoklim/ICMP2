"""facilities 도메인 이벤트 핸들러.

각 이벤트 타입에 대한 처리 함수와, 구독자가 호출할 dispatch 함수를 정의한다.
"""
import logging

from .definitions import FloorDimensionsChanged, FloorGridChanged

logger = logging.getLogger(__name__)


def on_floor_grid_changed(event: FloorGridChanged) -> None:
    from ..cache import invalidate_floor

    logger.info("on_floor_grid_changed floor_id=%s", event.floor_id)
    invalidate_floor(event.floor_id)


def on_floor_dimensions_changed(event: FloorDimensionsChanged) -> None:
    from ..models import Floor
    from ..services.floor_grid_maker import regenerate_index_grid_for_floor

    logger.info("on_floor_dimensions_changed floor_id=%s", event.floor_id)
    try:
        floor = Floor.objects.get(id=event.floor_id)
    except Floor.DoesNotExist:
        logger.warning("Floor id=%s not found; skip regenerate", event.floor_id)
        return
    regenerate_index_grid_for_floor(floor)


_HANDLERS = {
    "FloorGridChanged": (FloorGridChanged, on_floor_grid_changed),
    "FloorDimensionsChanged": (FloorDimensionsChanged, on_floor_dimensions_changed),
}


def dispatch(payload: dict) -> None:
    type_name = payload.pop("type", None)
    if type_name not in _HANDLERS:
        logger.warning("Unknown event type: %s", type_name)
        return
    event_cls, handler = _HANDLERS[type_name]
    try:
        event = event_cls(**payload)
    except TypeError:
        logger.exception("Invalid payload for %s: %s", type_name, payload)
        return
    try:
        handler(event)
    except Exception:
        logger.exception("Handler %s failed for event %s", handler.__name__, event)
