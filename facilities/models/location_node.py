from django.db import models

class LocationNode(models.Model):
    zone = models.ForeignKey('facilities.Zone', on_delete=models.CASCADE, related_name='location_nodes')
    node_name = models.CharField(max_length=100)
    node_code = models.CharField(max_length=50)
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    z = models.FloatField(default=0)
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
 



# class LocationNode(models.Model):
#     class Status(models.TextChoices):
#         ACTIVE = "active", "활성"
#         INACTIVE = "inactive", "비활성"

#     zone = models.ForeignKey(
#         "facilities.Zone", on_delete=models.CASCADE, related_name="location_nodes"
#     )
#     node_name = models.CharField(max_length=200)
#     node_code = models.CharField(max_length=50, unique=True)
#     x = models.FloatField()
#     y = models.FloatField()
#     z = models.FloatField(default=0)
#     status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

#     class Meta:
#         db_table = "location_nodes"
#         app_label = 'facilities'
#     def __str__(self):
#         return f"{self.node_name} ({self.node_code})"
