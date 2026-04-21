from django.db import models

class WorkerLocation(models.Model):
    """
    작업자 위치. cell_no 는 'row-col' 형식 문자열로 저장한다 (예: '3-5').
    x, y, z 는 이미지 기준 픽셀 좌표.
    """
    worker = models.ForeignKey('facilities.Worker', on_delete=models.CASCADE, related_name='locations')
    facility = models.ForeignKey('facilities.Facility', on_delete=models.SET_NULL, null=True, blank=True)
    building = models.ForeignKey('facilities.Building', on_delete=models.SET_NULL, null=True, blank=True)
    floor = models.ForeignKey('facilities.Floor', on_delete=models.SET_NULL, null=True, blank=True)
    zone = models.ForeignKey('facilities.Zone', on_delete=models.SET_NULL, null=True, blank=True)
    cell_no = models.CharField(max_length=20, blank=True, help_text="'row-col' 형식 예: '3-5'")
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    z = models.FloatField(default=0)
    measured_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'worker_locations'
        verbose_name = '작업자 위치'
        ordering = ['-measured_at']
 
    def __str__(self):
        return f'{self.worker.worker_name} @ ({self.x}, {self.y})'
    

# class WorkerLocation(models.Model):
#     worker = models.ForeignKey(
#         "facilities.Worker", on_delete=models.CASCADE, related_name="locations"
#     )
#     facility = models.ForeignKey(
#         "facilities.Facility", on_delete=models.CASCADE, related_name="worker_locations"
#     )
#     building = models.ForeignKey(
#         "facilities.Building", on_delete=models.SET_NULL, null=True, blank=True, related_name="worker_locations"
#     )
#     floor = models.ForeignKey(
#         "facilities.Floor", on_delete=models.SET_NULL, null=True, blank=True, related_name="worker_locations"
#     )
#     zone = models.ForeignKey(
#         "facilities.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="worker_locations"
#     )
#     x = models.FloatField(null=True, blank=True)
#     y = models.FloatField(null=True, blank=True)
#     z = models.FloatField(null=True, blank=True)
#     measured_at = models.DateTimeField()

#     class Meta:
#         db_table = "worker_locations"
#         ordering = ["-measured_at"]
#         app_label = 'facilities'
#     def __str__(self):
#         return f"{self.worker.worker_name} @ {self.measured_at}"
