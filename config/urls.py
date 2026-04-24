"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.contrib.auth import views as auth_views


def _stub(request):
    return HttpResponse('<h2 style="font-family:sans-serif;padding:40px">준비 중입니다.</h2>')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('alerts/', include('alerts.urls')),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    # 다른 앱 URL 스텁 (각 앱 개발 시 교체 예정)
    path('safety/mysafety/', _stub, name='mysafety_detail'),
    path('monitoring/workers/', _stub, name='worker_list'),
    path('monitoring/gas/', _stub, name='gas_detail'),
    path('monitoring/power/', _stub, name='power_detail'),
    path('monitoring/', _stub, name='monitoring_detail'),
]
