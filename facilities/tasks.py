"""facilities 도메인 Celery 태스크.

Floor/FloorGrid 변경 시 후속 처리(IndexGrid 재생성, 캐시 무효화)를
Celery 태스크로 직접 큐잉한다. Redis Pub/Sub은 사용하지 않는다 —
구독 윈도우 사이의 gap에서 메시지가 영구 소실될 수 있기 때문이다.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def handle_floor_grid_changed(floor_id: int) -> None:
    """IndexGrid가 floor 단위로 변경된 뒤 관련 캐시를 무효화한다."""
    from .cache import invalidate_floor

    logger.info("handle_floor_grid_changed floor_id=%s", floor_id)
    invalidate_floor(floor_id)


@shared_task
def deactivate_stale_geofences() -> int:
    """STALE 가스센서의 자동 지오펜스를 비활성화한다 (celery beat 주기 호출).

    데이터 수신이 끊긴 가스센서의 danger/warning 지오펜스가 지도에 영구히
    남는 문제를 막는다. 실제 판단·비활성화·broadcast는 geofence_service에 위임.
    """
    from .services.geofence_service import deactivate_stale_geofences as _sweep

    n = _sweep()
    if n:
        logger.info("deactivate_stale_geofences: %s개 비활성화", n)
    return n


@shared_task
def deactivate_stale_workers() -> int:
    """위치 수신이 끊긴 on_duty 작업자를 off_duty로 정리한다 (celery beat 주기 호출).

    데이터가 끊긴 작업자가 지도/현황에 '근무 중'(+위험)으로 유령처럼 남는 것을 막는다.
    실제 판단·정리는 geofence_checker.deactivate_stale_workers에 위임.
    """
    from .services.geofence_checker import deactivate_stale_workers as _sweep

    n = _sweep()
    if n:
        logger.info("deactivate_stale_workers: %s명 off_duty 정리", n)
    return n


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def handle_floor_dimensions_changed(self, floor_id: int) -> None:
    """Floor.width/length 또는 FloorGrid.cell_size 변경 후 IndexGrid를 재생성한다."""
    from .models import Floor
    from .services.floor_grid_maker import regenerate_index_grid_for_floor

    logger.info("handle_floor_dimensions_changed floor_id=%s", floor_id)
    try:
        floor = Floor.objects.get(id=floor_id)
    except Floor.DoesNotExist:
        logger.warning("Floor id=%s not found; skip regenerate", floor_id)
        return

    try:
        regenerate_index_grid_for_floor(floor)
    except Exception as exc:
        logger.error("handle_floor_dimensions_changed 실패 — floor_id=%s: %s", floor_id, exc)
        raise self.retry(exc=exc)
