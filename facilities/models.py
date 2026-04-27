import os
from uuid import uuid4
from django.db import models



class Facility(models.Model):
    facility_name = models.CharField(max_length=100)
    facility_code = models.CharField(max_length=50, unique=True)
    address = models.CharField(max_length=255, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('active', '운영중'), ('inactive', '비운영'), ('maintenance', '점검중')],
        default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'facilities'
        verbose_name = '사업장'
        verbose_name_plural = '사업장 목록'
        app_label = 'facilities'
 
    def __str__(self):
        return self.facility_name
 
class Building(models.Model):
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.CASCADE, related_name="buildings"
    )
    building_name = models.CharField(max_length=200)
    building_code = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "buildings"
        verbose_name = '건물'
        verbose_name_plural = '건물 목록'
        unique_together = ("facility", "building_code")
        app_label = 'facilities'

    def __str__(self):
        return f"{self.facility.facility_name} - {self.building_name}"



def floor_plan_path(instance, filename):
    ext = filename.split('.')[-1]
    f_no = instance.floor_no if instance.floor_no is not None else '0'
    filename = f"floor_{f_no}_{uuid4().hex}.{ext}"
    return os.path.join('facilities/floor_plans/', filename)


class Floor(models.Model):
    building = models.ForeignKey(
        "facilities.Building", on_delete=models.CASCADE, related_name="floors"
    )
    floor_name = models.CharField(max_length=100)
    floor_no = models.IntegerField()
    plan_image = models.ImageField(
        upload_to=floor_plan_path,
        null=True,
        blank=True,
        help_text="해당 층의 도면 이미지"
    )
    width = models.IntegerField(null = False, blank= False, help_text="건물 가로 길이(m)")
    length = models.IntegerField(null = False, blank= False, help_text="건물 세로 길이(m)")
    height = models.IntegerField(null=True, blank=True, help_text="층고(m) - 추후 사용")

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
    층의 격자 설정값 저장.
    cell_size: 격자 한 칸의 실제 크기 (meter 단위)
    """
    floor = models.OneToOneField(
        "facilities.Floor",
        on_delete=models.CASCADE,
        related_name="grid"
    )
    cell_size = models.FloatField(
        default=1.0,
        help_text="격자 한 칸의 실제 크기 (m)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "floor_grids"
        verbose_name = '층 격자 설정'
        verbose_name_plural = '층 격자 설정 목록'
        app_label = 'facilities'

    def __str__(self):
        return f"{self.floor} 격자 (cell_size={self.cell_size}m)"


class IndexGrid(models.Model):
    """
    공용 좌표계.
 
    Floor 생성 시 전체 격자 셀을 일괄 생성하며 이후 변경되지 않음.
    모든 앱(센서, 작업자 등)이 동일한 IndexGrid를 FK로 참조하여
    같은 좌표계 위에서 각자의 상태를 관리함.
 
    col, row를 저장하는 이유:
        역산(grid_index → col, row) 없이 바로 확인 가능
        공간 변경 시 데이터 정합성 확인용
 
    snap_x/y, x_ratio/y_ratio는 저장하지 않음:
        필요 시 GridPointSnapper로 계산
        DB 중복 저장 불필요
    """
    floor = models.ForeignKey(
        "facilities.Floor",
        on_delete=models.CASCADE,
        related_name="index_grids"
    )
    grid_index = models.IntegerField(
        help_text="격자 고유 번호 (Row-Major, 왼쪽 위부터 가로 순번)"
    )
    col = models.IntegerField(
        help_text="열 번호 (x 방향, 0부터 시작)"
    )
    row = models.IntegerField(
        help_text="행 번호 (y 방향, 0부터 시작)"
    )
 
    class Meta:
        db_table = "index_grids"
        unique_together = (("floor", "grid_index"),)
        indexes = [
            models.Index(fields=["floor", "grid_index"]),
            models.Index(fields=["floor", "col", "row"]),
        ]
        verbose_name = '격자 인덱스'
        verbose_name_plural = '격자 인덱스 목록'
        app_label = 'facilities'
 
    def __str__(self):
        return f"{self.floor} - grid_index={self.grid_index} (col={self.col}, row={self.row})"
    


class Geofence(models.Model):
    """
    위험구역. 원형으로만 관리한다.
    center_x, center_y 는 이미지 기준 픽셀 좌표.
    radius 는 픽셀 단위.
    curl 로 center_x/center_y/radius 를 PATCH 하면
    프론트에서 CSS transition 으로 원이 부드럽게 이동/확산한다.
    """
    SEVERITY_CHOICES = [
        ('danger', '위험'),
        ('warning', '주의'),
        ('safe', '안전'),
    ]
 
    zone = models.ForeignKey(
        'facilities.Zone', on_delete=models.SET_NULL, null=True, blank=True, related_name='geofences'
    )
    floor = models.ForeignKey('facilities.Floor', on_delete=models.CASCADE, related_name='geofences')
    name = models.CharField(max_length=100)
    center_x = models.FloatField(help_text='원 중심 x (px)')
    center_y = models.FloatField(help_text='원 중심 y (px)')
    radius = models.FloatField(help_text='반지름 (px)')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='danger') 
    # monitoting forienkey 참조 필요 
    description = models.TextField(blank=True)
    # monitoting forienkey 참조 필요 또는 변경(위험 요인)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'geofences'
        verbose_name = '위험구역'
        verbose_name_plural = '위험구역 목록'
        app_label = 'facilities'  
 
    def __str__(self):
        return f'{self.name} ({self.severity})'



class LocationNode(models.Model):
    zone = models.ForeignKey('facilities.Zone', on_delete=models.CASCADE, related_name='location_nodes')
    node_name = models.CharField(max_length=100)
    node_code = models.CharField(max_length=50)
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    z = models.FloatField(default=0, null=True)
    status = models.CharField(
        max_length=20,
        choices=[('active', '활성'), ('inactive', '비활성')],
        default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'location_nodes'
        verbose_name = '위치 노드'
        app_label = 'facilities'
 
    def __str__(self):
        return f'{self.zone.zone_name} - {self.node_name}'

class WorkerLocation(models.Model):
    """
    작업자 위치. cell_no 는 'row-col' 형식 문자열로 저장한다 (예: '3-5').
    """
    worker = models.ForeignKey('facilities.Worker', on_delete=models.CASCADE, related_name='locations')
    facility = models.ForeignKey('facilities.Facility', on_delete=models.SET_NULL, null=True, blank=True)
    building = models.ForeignKey('facilities.Building', on_delete=models.SET_NULL, null=True, blank=True)
    floor = models.ForeignKey('facilities.Floor', on_delete=models.SET_NULL, null=True, blank=True)
    zone = models.ForeignKey('facilities.Zone', on_delete=models.SET_NULL, null=True, blank=True)
    cell_no = models.CharField(max_length=20, blank=True, help_text="'row-col' 형식 예: '3-5'")
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    z = models.FloatField(null=True, blank=True) #z에 대한 값이 없으므로 일단은 null
    measured_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'worker_locations'
        verbose_name = '작업자 위치'
        ordering = ['-measured_at']
 
    def __str__(self):
        return f'{self.worker.worker_name} @ ({self.x}, {self.y})'
    
class Worker(models.Model):
    worker_no = models.CharField(max_length=50, unique=True)
    worker_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('on_duty', '근무중'), ('off_duty', '비근무'), ('danger', '위험')],
        default='on_duty',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'workers'
        verbose_name = '작업자'
        verbose_name_plural = '작업자 목록'
        app_label = 'facilities'
 
    def __str__(self):
        return f'{self.worker_no} {self.worker_name}'
    
class Zone(models.Model):
    """
    운영자가 meshgrid 위에서 셀 범위를 지정하여 구역 이름을 부여한다.
    cell_row_start/end, cell_col_start/end 로 직사각형 범위를 저장한다.
    이건 관리자 페이지로 빼버리고 해당 내용은 별도로 관리 반영
    """
    ZONE_TYPE_CHOICES = [
        ('work', '작업구역'),
        ('storage', '창고'),
        ('rest', '휴게구역'),
        ('utility', '설비구역'),
        ('passage', '통로'),
        ('etc', '기타'),
    ]
 
    floor = models.ForeignKey('facilities.Floor', on_delete=models.CASCADE, related_name='zones')
    zone_name = models.CharField(max_length=100)
    zone_type = models.CharField(max_length=20, choices=ZONE_TYPE_CHOICES, default='work')
    cell_row_start = models.PositiveIntegerField(default=0)
    cell_row_end = models.PositiveIntegerField(default=0)
    cell_col_start = models.PositiveIntegerField(default=0)
    cell_col_end = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, default='#378ADD', help_text='지도 표시 색상 hex')
    status = models.CharField(
        max_length=20,
        choices=[('active', '활성'), ('inactive', '비활성')],
        default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'zones'
        verbose_name = '구역'
        verbose_name_plural = '구역 목록'
        app_label = 'facilities'
 
    def __str__(self):
        return f'{self.floor} - {self.zone_name}'
    
class Equipment(models.Model):
    floor = models.ForeignKey('facilities.Floor',on_delete=models.SET_NULL,null= True, related_name='equipments')
    zone = models.ForeignKey("facilities.Zone",on_delete=models.SET_NULL, null= True )
    equipment_name = models.CharField(max_length=20)  # "냉각 설비 2호"
    equipment_code = models.CharField(max_length=20)  # "B-02"
    width  = models.FloatField(null=True, blank=True, help_text='장비 가로 크기(m)')
    height = models.FloatField(null=True, blank=True, help_text='장비 세로 크기(m)')
    center_x = models.FloatField(null=True, blank=True, help_text='장비 중심점 x 좌표(m)')
    center_y = models.FloatField(null=True, blank=True, help_text='장비 중심점 y 좌표(m)')
    rotation = models.IntegerField(default=0,           help_text='회전 각도 (0/45/90/.../315)')
    status = models.CharField(
    max_length=20,
    choices=[('active', '운영중'), ('inactive', '비운영'), ('maintenance', '점검중')],
    default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text='생성 날짜')
    updated_at = models.DateTimeField(auto_now=True, help_text='업데이트 내역')
    is_placed = models.BooleanField(default=False, help_text='지도 배치 완료 여부')

    class Meta:
        db_table = 'equipments'
        verbose_name = '설비'
        verbose_name_plural = '설비 목록'
        app_label = 'facilities'

    def __str__(self):
        return f"[{self.equipment_code}] {self.equipment_name}"
 



 




