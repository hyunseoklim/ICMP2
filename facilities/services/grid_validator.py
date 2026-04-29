class GridValidator:
    """
    유효성 검사 전담.
    기본 정책: 음수 차단.
    앱마다 상속해서 커스터마이징 가능.

    예:
        class SensorGridValidator(GridValidator):
            def validate(self, x_m, y_m):
                # 센서 앱 전용 추가 검사
                ...
    """

    def is_negative(self, value: float) -> bool:
        """단일 값이 음수인지 확인"""
        return float(value) < 0

    def validate(self, x_m: float, y_m: float) -> bool:
        """
        좌표값 유효성 확인.
        기본 정책: x, y 모두 0 이상이어야 함.

        반환:
            True  → 유효
            False → 무효 (음수)
        """
        if self.is_negative(x_m) or self.is_negative(y_m):
            return False
        return True