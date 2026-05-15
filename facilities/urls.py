from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import FloorGridSetupView
from .views import FloorGridSetupView, SensorLocationViewSet

router = DefaultRouter()
router.register(r'facilities', views.FacilityViewSet, basename='facility')
router.register(r'buildings', views.BuildingViewSet, basename='building')
router.register(r'floors', views.FloorViewSet, basename='floor')
router.register(r'floor-grids', views.FloorGridViewSet, basename='floorgrid')
router.register(r'zones', views.ZoneViewSet, basename='zone')
router.register(r'location-nodes', views.LocationNodeViewSet, basename='locationnode')
router.register(r'workers', views.WorkerViewSet, basename='worker')
router.register(r'worker-locations', views.WorkerLocationViewSet, basename='workerlocation')
router.register(r'geofences', views.GeofenceViewSet, basename='geofence')
router.register(r'equipments', views.EquipmentViewSet, basename='equipment')
router.register(r'sensor-locations', SensorLocationViewSet,        basename='sensor-location')


urlpatterns = [
    path('api/', include(router.urls)),
    path('api/floors/<int:floor_id>/grid-data/', views.floor_grid_data, name='floor-grid-data'),
    path('api/map-editor/bulk-save/', views.bulk_map_editor_save, name='map-editor-bulk-save'),   # T1-ε
    path('monitoring/', views.monitoring_view, name='map_monitoring'),
    path('', views.monitoring_view, name='index'),
    path("floors/<int:floor_id>/setup/", FloorGridSetupView.as_view(), name="floor-grid-setup"),
    path("workers/", views.worker_list, name="worker_list"),
]