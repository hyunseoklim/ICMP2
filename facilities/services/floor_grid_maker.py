import math

from .grid_validator           import GridValidator
from .grid_boundary_handler    import GridBoundaryHandler
from .grid_coordinate_to_index import GridCoordinateToIndex
from .grid_index_to_coordinate import GridIndexToCoordinate
from .grid_cell_generator      import GridCellGenerator
from .grid_point_snapper       import GridPointSnapper


class FloorGridService:
    """
    조립만 담당.
    직접 계산하지 않음.
    각 담당 클래스에 순서대로 위임.

    Args:
        floor: Floor 모델 인스턴스
    """

    def __init__(self, floor):
        self.floor    = floor
        cell_size     = float(floor.grid.cell_size)
        width_m       = float(floor.width)
        length_m      = float(floor.length)
        cols          = math.ceil(width_m  / cell_size)
        rows          = math.ceil(length_m / cell_size)
        total_cells   = cols * rows

        # 담당자 준비
        self.validator = GridValidator()
        self.boundary  = GridBoundaryHandler(width_m, length_m)
        self.to_index  = GridCoordinateToIndex(cols, cell_size)
        self.to_coord  = GridIndexToCoordinate(cols)
        self.generator = GridCellGenerator(total_cells, cols, rows)
        self.snapper   = GridPointSnapper(cell_size)

        # snap/ratio 계산 시 필요
        self._width_m  = width_m
        self._length_m = length_m

    # ── Floor 생성 시 1회만 ───────────────────────────────

    def generate_all_cells(self) -> list[dict]:
        """
        전체 셀 목록 생성.
        IndexGridWriter.bulk_create()에 넘길 목록 반환.

        반환 예:
        [
            {"grid_index": 0,    "col": 0,  "row": 0 },
            {"grid_index": 1,    "col": 1,  "row": 0 },
            ...
            {"grid_index": 4999, "col": 99, "row": 49},
        ]
        """
        return self.generator.generate()

    # ── 실시간 위치 수신 시 ───────────────────────────────

    def get_grid_index(self, x_m: float, y_m: float) -> int | None:
        """
        위치값(m) → grid_index 변환.
        유효성 검사 → 경계값 처리 → 좌표 변환 → 인덱스 산출 순서.

        반환:
            int  → 유효한 grid_index
            None → 유효하지 않은 좌표 (음수 또는 범위 초과)
        """
        # 1. 유효성 검사
        if not self.validator.validate(x_m, y_m):
            return None

        # 2. 범위 초과 확인
        if self.boundary.is_out_of_bounds(x_m, y_m):
            return None

        # 3. 경계값 처리 (정확히 최대값인 경우)
        x_m, y_m = self.boundary.clamp(x_m, y_m)

        # 4. 좌표 → (col, row)
        col, row = self.to_index.to_col_row(x_m, y_m)

        # 5. (col, row) → grid_index
        return self.to_index.to_index(col, row)

    # ── snap/ratio 필요 시에만 ────────────────────────────

    def get_snap_point(self, index: int) -> dict:
        """
        grid_index → snap_x, snap_y 계산.
        필요한 경우에만 호출.

        반환 예:
        {
            "snap_x": 54.5,
            "snap_y": 23.5,
        }
        """
        col, row = self.to_coord.to_col_row(index)
        snap_x, snap_y = self.snapper.get_snap_point(col, row)
        return {
            "snap_x": snap_x,
            "snap_y": snap_y,
        }

    def get_snap_with_ratio(self, index: int) -> dict:
        """
        grid_index → snap_x, snap_y, x_ratio, y_ratio 계산.
        snap과 ratio 모두 필요한 경우에만 호출.

        반환 예:
        {
            "snap_x"  : 54.5,
            "snap_y"  : 23.5,
            "x_ratio" : 0.545,
            "y_ratio" : 0.470,
        }
        """
        col, row = self.to_coord.to_col_row(index)
        snap_x, snap_y = self.snapper.get_snap_point(col, row)
        x_ratio, y_ratio = self.snapper.get_ratio(
            snap_x, snap_y,
            self._width_m, self._length_m
        )
        return {
            "snap_x"  : snap_x,
            "snap_y"  : snap_y,
            "x_ratio" : x_ratio,
            "y_ratio" : y_ratio,
        }