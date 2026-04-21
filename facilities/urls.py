from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

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
router.register(r'sensors', views.SensorDummyViewSet, basename='sensor')

urlpatterns = [
    path('api/', include(router.urls)),
    path('monitoring/', views.monitoring_view, name='monitoring'),
    path('', views.monitoring_view, name='index'),
]