from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/floor/(?P<floor_id>\d+)/worker/$',   consumers.WorkerConsumer.as_asgi()),
    re_path(r'ws/floor/(?P<floor_id>\d+)/sensor/$',   consumers.SensorConsumer.as_asgi()),
    re_path(r'ws/floor/(?P<floor_id>\d+)/geofence/$', consumers.GeofenceConsumer.as_asgi()),
    re_path(r'ws/floor/(?P<floor_id>\d+)/forecast/$', consumers.ForecastConsumer.as_asgi()),
]