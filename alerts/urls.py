from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register('api/events', views.AlarmEventViewSet, basename='alarm-event-api')

urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('events/<int:pk>/', views.event_detail, name='event_detail'),
    path('events/<int:pk>/status/', views.change_event_status_view, name='change_event_status'),
    path('history/', views.action_history, name='action_history'),
    path('', include(router.urls)),
    path('api/recent/', views.recent_alarms, name='recent_alarms'),
]
