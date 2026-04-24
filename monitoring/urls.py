from django.urls import path
from . import views

urlpatterns = [
    path("", views.monitoring_detail, name="monitoring_detail"),
    path("power/", views.power_detail, name="power_detail"),
    path("gas/", views.gas_detail, name="gas_detail"),
]
