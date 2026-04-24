class GridBoundaryHandler:
    """
    경계값 처리 전담.
    앱마다 정책이 다를 수 있으므로 분리.

    정책 변경 예:
        - 범위 초과 시 None 반환 (기본)
        - 범위 초과 시 마지막 셀로 clamp
        - 범위 초과 시 예외 발생

    앱마다 상속해서 정책 교체 가능.
    """

    def __init__(self, width_m: float, length_m: float):
        self.width_m  = float(width_m)
        self.length_m = float(length_m)

    def is_out_of_bounds(self, x_m: float, y_m: float) -> bool:
        """
        범위 초과 여부 확인.
        정확히 최대값(width_m, length_m)은 초과로 보지 않음.
        초과: x > width_m 또는 y > length_m
        """
        return float(x_m) > self.width_m or float(y_m) > self.length_m

    def clamp(self, x_m: float, y_m: float) -> tuple[float, float]:
        """
        정확히 최대값일 때 마지막 셀로 처리.
        예: x=10.0, width=10.0 → 9.9999...로 조정
            → 마지막 셀에 포함됨

        초과값은 이 메서드 호출 전에
        is_out_of_bounds()로 차단해야 함.
        """
        x_m = min(float(x_m), self.width_m  - 1e-9)
        y_m = min(float(y_m), self.length_m - 1e-9)
        return x_m, y_m