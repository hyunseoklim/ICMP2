class GridCellGenerator:
    """
    전체 셀 목록 생성 전담.

    사용 시점: Floor 생성 시 1회만
    목적: IndexGrid bulk_create에 넘길 목록 생성
    분리 이유: subindex 등 확장 대비,
              FloorGridService와 생명주기가 다름
    """

    def __init__(self, total_cells: int, cols: int, rows : int):
        self.total_cells = total_cells
        self.cols        = cols
        self.rows        = rows

    def generate(self) -> list[dict]:
        """
        0 ~ total_cells-1 순회하여
        각 index마다 col, row를 계산한 목록 반환.

        total_cells가 얼마든 반복문이 자동 처리.
        수동 수정 불필요.

        반환 예 (cols=100, total_cells=5000):
        [
            {"grid_index": 0,    "col": 0,  "row": 0 },
            {"grid_index": 1,    "col": 1,  "row": 0 },
            {"grid_index": 100,  "col": 0,  "row": 1 },
            ...
            {"grid_index": 4999, "col": 99, "row": 49},
        ]
        """
        return [
            {
                "grid_index": index,
                "col"       : index % self.cols,
                "row"       : index // self.cols,
            }
            for index in range(self.total_cells)
        ]