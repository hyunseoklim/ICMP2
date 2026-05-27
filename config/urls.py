from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from monitoring import views as monitoring_views


def health_check(request):
    return JsonResponse({'status': 'ok'})
 

urlpatterns = [
    path('health/', health_check),
    path('', include('django_prometheus.urls')),
    path('admin/', admin.site.urls),
    path('monitoring/api/gas-readings/', monitoring_views.ingest_gas),
    path('monitoring/api/power-readings/', monitoring_views.ingest_power),
    path('monitoring/api/node-readings/', monitoring_views.ingest_node),
    
    path('', include('dashboard.urls')),
    path('accounts/', include('accounts.urls')),
    path('safety/', include('safety.urls')),
    path('facilities/', include('facilities.urls')),
    path('monitoring/', include('monitoring.urls')),
    path('alerts/', include('alerts.urls')),    
    path('manager/', include('manager.urls')),

] 


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

