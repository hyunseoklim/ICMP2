class GridCoordinateToIndex:
    """
    좌표 → 인덱스 변환 전담.

    사용 시점: 실시간 위치값이 들어올 때
    목적: "이 좌표가 몇 번 셀인가" 판단
    """

    def __init__(self, cols: int, cell_size: float):
        self.cols      = cols
        self.cell_size = float(cell_size)

    def to_col_row(self, x_m: float, y_m: float) -> tuple[int, int]:
        """
        (x, y) → (col, row) 변환.

        기준:
            왼쪽 위 (0,0)
            x 증가 → col 증가 (가로 방향)
            y 증가 → row 증가 (세로 방향)

        예: cell_size=1.0일 때
            x=54.3 → col=54
            y=23.7 → row=23
        """
        col = int(float(x_m) // self.cell_size)
        row = int(float(y_m) // self.cell_size)
        return col, row

    def to_index(self, col: int, row: int) -> int:
        """
        (col, row) → grid_index 변환.

        방식: Row-Major (가로 우선)
            0번 줄: 0, 1, 2 ... cols-1
            1번 줄: cols, cols+1 ... 2*cols-1
            ...

        공식: index = (row * cols) + col

        예: cols=100일 때
            col=54, row=23 → (23 * 100) + 54 = 2354
        """
        return (row * self.cols) + col