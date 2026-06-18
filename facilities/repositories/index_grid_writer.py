from django.db import transaction

from ..models import IndexGrid


class IndexGridWriter:
    """
    IndexGrid 저장/삭제 전담.
    사용 시점: Floor 생성 시, 공간 변경 시.
    커밋 성공 후 handle_floor_grid_changed 태스크를 큐잉한다.
    """

    def bulk_create(self, floor, cells: list[dict]) -> None:
        """
        전체 셀 목록을 IndexGrid 테이블에 일괄 저장.
        이미 존재하는 경우 skip (ignore_conflicts=True).

        Args:
            floor: Floor 모델 인스턴스
            cells: FloorGridService.generate_all_cells() 반환값
                   [{"grid_index": 0, "col": 0, "row": 0}, ...]
        """
        IndexGrid.objects.bulk_create(
            [
                IndexGrid(
                    floor      = floor,
                    grid_index = cell["grid_index"],
                    col        = cell["col"],
                    row        = cell["row"],
                )
                for cell in cells
            ],
            ignore_conflicts=True,
        )
        floor_id = floor.id
        transaction.on_commit(lambda: self._queue_grid_changed(floor_id))

    def delete_by_floor(self, floor) -> int:
        """
        floor의 전체 IndexGrid 삭제.
        공간 변경(재생성) 시 사용.

        반환: 삭제된 레코드 수
        """
        deleted_count, _ = IndexGrid.objects.filter(floor=floor).delete()
        floor_id = floor.id
        transaction.on_commit(lambda: self._queue_grid_changed(floor_id))
        return deleted_count

    @staticmethod
    def _queue_grid_changed(floor_id: int) -> None:
        from ..tasks import handle_floor_grid_changed
        handle_floor_grid_changed.delay(floor_id=floor_id)
