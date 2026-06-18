from django.core.cache import cache

from ..cache import INDEX_GRID_TTL, index_grid_cache_key
from ..models import IndexGrid


class IndexGridReader:
    """
    IndexGrid 조회 전담.
    get_full_grid는 Redis 캐시. 미스 시 DB 조회 후 캐시 set.
    """

    def get_by_index(self, floor, grid_index: int) -> IndexGrid | None:
        """
        grid_index로 단건 조회.
        UNIQUE 인덱스(floor, grid_index)로 즉시 조회.
        """
        return IndexGrid.objects.filter(
            floor=floor,
            grid_index=grid_index,
        ).first()

    def get_by_col_row(self, floor, col: int, row: int) -> IndexGrid | None:
        """
        (col, row)로 단건 조회.
        """
        return IndexGrid.objects.filter(
            floor=floor,
            col=col,
            row=row,
        ).first()

    def get_full_grid(self, floor) -> dict:
        """
        floor의 전체 IndexGrid 반환 (캐시 우선).

        반환 구조:
            {
                "cells": [{"grid_index": int, "col": int, "row": int}, ...],
                "cols":  int,    # max(col) + 1
                "rows":  int,    # max(row) + 1
                "total": int,    # len(cells)
            }
        IndexGrid가 없으면 total=0, cells=[], cols=0, rows=0.
        """
        key = index_grid_cache_key(floor.id)
        cached = cache.get(key)
        if cached is not None:
            return cached

        cells = list(
            IndexGrid.objects.filter(floor=floor)
            .order_by("grid_index")
            .values("grid_index", "col", "row")
        )
        if cells:
            cols = max(c["col"] for c in cells) + 1
            rows = max(c["row"] for c in cells) + 1
        else:
            cols = 0
            rows = 0
        result = {
            "cells": cells,
            "cols": cols,
            "rows": rows,
            "total": len(cells),
        }
        cache.set(key, result, INDEX_GRID_TTL)
        return result
