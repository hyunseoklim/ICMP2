class GridIndexToCoordinate:
    """
    인덱스 → 좌표 변환 전담.

    사용 시점: snap_x/y, ratio 계산이 필요할 때
    목적: 렌더링/표시를 위한 위치 계산
    """

    def __init__(self, cols: int):
        self.cols = cols

    def to_col_row(self, index: int) -> tuple[int, int]:
        """
        grid_index → (col, row) 역산.

        공식:
            col = index % cols  (나머지)
            row = index // cols (몫)

        예: cols=100일 때
            index=2354 → col=2354%100=54, row=2354//100=23
        """
        col = index % self.cols
        row = index // self.cols
        return col, row