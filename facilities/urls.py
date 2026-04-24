from django.urls import path
from . import views

urlpatterns = [
    path("workers/", views.worker_list, name="worker_list"),
]
