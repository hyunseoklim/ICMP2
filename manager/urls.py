from django.urls import path
from . import views



urlpatterns = [
    path('', views.user_list, name='user_list'),
    path('create/', views.user_create, name='user_create'),
    path('create/error/', views.user_create_error, name='user_create_error'),
    path('detail/', views.user_detail, name='user_detail'),
    path('edit/', views.user_edit, name='user_edit'),
    path('logout/complete/', views.logout_complete, name='logout_complete'),
    path('filter/', views.user_list_filter, name='user_list_filter'),
    path('facilities/', views.facility_list, name='facility_list'),
    path('gas/', views.gas_list, name='gas_list'),
    path('power/', views.power_list, name='power_list'),
    path('node/', views.node_list, name='node_list'),
    path('data/gas/', views.gas_data_list, name='gas_data_list'),
    path('data/power/', views.power_data_list, name='power_data_list'),
    path('data/node/', views.node_data_list, name='node_data_list'),
    path('data/worker/', views.worker_data_list, name='worker_data_list'),
    path('data/retention/', views.retention_list, name='retention_list'),
    path('notice/', views.notice_list, name='notice_list'),
    path('notice/detail/', views.notice_detail, name='notice_detail'),
    path('notice/create/', views.notice_create, name='notice_create'),
    path('notice/edit/', views.notice_edit, name='notice_edit'),
]