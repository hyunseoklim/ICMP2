class GridPointSnapper:
    """
    중심점(snap) + ratio 계산 전담.

    사용 시점: snap_x/y 또는 ratio가 필요한 경우에만 호출
    목적: 렌더링 위치 결정
    분리 이유: 정책 변경 시 이 클래스만 교체
        예: 격자 중앙 → 왼쪽 위로 변경 시
            get_snap_point()만 수정

    snap_x/y와 ratio를 단일 클래스에서 처리하는 이유:
        ratio는 snap_x/y를 기반으로 계산
        항상 함께 사용되는 경우가 많음
        → 단일 로직으로 관리
    """

    def __init__(self, cell_size: float):
        self.cell_size = float(cell_size)

    def get_snap_point(self, col: int, row: int) -> tuple[float, float]:
        """
        (col, row) → (snap_x, snap_y) 계산.

        현재 정책: 격자 중앙
        공식:
            snap_x = (col * cell_size) + (cell_size / 2)
            snap_y = (row * cell_size) + (cell_size / 2)

        예: cell_size=1.0일 때
            col=54, row=23
            → snap_x = (54 * 1.0) + 0.5 = 54.5
            → snap_y = (23 * 1.0) + 0.5 = 23.5
        """
        snap_x = (col * self.cell_size) + (self.cell_size / 2.0)
        snap_y = (row * self.cell_size) + (self.cell_size / 2.0)
        return snap_x, snap_y

    def get_ratio(
        self,
        snap_x  : float,
        snap_y  : float,
        width_m : float,
        length_m: float,
    ) -> tuple[float, float]:
        """
        (snap_x, snap_y) → (x_ratio, y_ratio) 계산.

        공식:
            x_ratio = snap_x / width_m
            y_ratio = snap_y / length_m

        예:
            snap_x=54.5, width_m=100  → x_ratio=0.545
            snap_y=23.5, length_m=50  → y_ratio=0.470
        """
        x_ratio = round(snap_x / float(width_m),  4)
        y_ratio = round(snap_y / float(length_m), 4)
        return x_ratio, y_ratio