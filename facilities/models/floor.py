from django.db import models


class Floor(models.Model):
    building = models.ForeignKey(
        "facilities.Building", on_delete=models.CASCADE, related_name="floors"
    )
    floor_name = models.CharField(max_length=100)
    floor_no = models.IntegerField()

    class Meta:
        db_table = "floors"
        unique_together = ("building", "floor_no")
        verbose_name = '층'
        verbose_name_plural = '층 목록'
        ordering = ["floor_no"]
        app_label = 'facilities'

    def __str__(self):
        return f"{self.building.building_name} {self.floor_name}"
    

class FloorGrid(models.Model):
    """
    층 단위 meshgrid 설정.
    운영자가 cell_width / cell_height 를 지정하면
    cols = img_width / cell_width, rows = img_height / cell_height 로 격자 수를 계산한다.
    창고 등의 구역을 직접 설정할 때 이 데이터를 활용 
    z축까지 포함해서 데이터를 받을 필요가 있음(국민대 작업 예정이나 어떻게 들어올지 몰라 임의 구성함)
    """
    floor = models.OneToOneField(Floor, on_delete=models.CASCADE, related_name='grid')
    cell_width = models.PositiveIntegerField(default=50, help_text='셀 가로 크기 (px)')
    cell_height = models.PositiveIntegerField(default=50, help_text='셀 세로 크기 (px)')
    cols = models.PositiveIntegerField(default=20, help_text='가로 셀 수')
    rows = models.PositiveIntegerField(default=20, help_text='세로 셀 수')
    img_width = models.PositiveIntegerField(default=1000, help_text='기준 이미지 가로 (px)')
    img_height = models.PositiveIntegerField(default=1000, help_text='기준 이미지 세로 (px)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'floor_grids'
        verbose_name = '층 격자 설정'
        app_label = 'facilities'
 
    def __str__(self):
        return f'{self.floor} 격자 ({self.cols}*{self.rows})'
