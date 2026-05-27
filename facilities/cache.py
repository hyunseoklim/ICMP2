"""facilities 도메인 캐시 키·TTL·무효화 진입점.

캐시 키 네이밍과 무효화 로직을 단일 진입점에서 관리한다.
events/handlers.py와 repositories에서만 import.
"""
from django.core.cache import cache

INDEX_GRID_TTL = 3600


def index_grid_cache_key(floor_id: int) -> str:
    return f"facilities:index_grid:floor:{floor_id}"


def floor_grid_response_cache_key(floor_id: int) -> str:
    return f"facilities:floor_grid_response:floor:{floor_id}"


def invalidate_floor(floor_id: int) -> None:
    cache.delete(index_grid_cache_key(floor_id))
    cache.delete(floor_grid_response_cache_key(floor_id))
