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
]