from ..models import IndexGrid


class IndexGridReader:
    """
    IndexGrid 조회 전담.
    나중에 Redis로 교체 시 이 클래스만 수정.
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

    def get_full_grid(self, floor) -> list[IndexGrid]:
        """
        floor의 전체 IndexGrid 목록 반환.
        서버 시작 시 메모리 load용.
        grid_index 순서로 정렬.
        """
        return list(
            IndexGrid.objects.filter(floor=floor)
            .order_by("grid_index")
        )