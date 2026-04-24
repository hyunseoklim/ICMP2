from django.urls import path
from . import views

urlpatterns = [
    path("mysafety/", views.mysafety_detail, name="mysafety_detail"),
    path("mysafety/vr/", views.mysafety_vr, name="mysafety_vr"),
    path("mysafety/history/", views.mysafety_history, name="mysafety_history"),
    path("mysafety/history/download/", views.mysafety_history_download, name="mysafety_history_download"),
    path("mysafety/worker/<int:worker_id>/calendar/", views.mysafety_worker_calendar, name="mysafety_worker_calendar"),
]
