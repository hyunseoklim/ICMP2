import os

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, JsonResponse
from monitoring import views as monitoring_views


def health_check(request):
    return JsonResponse({'status': 'ok'})


def metrics_view(request):
    """멀티프로세스 환경에서 모든 프로세스 메트릭을 합산해 반환"""
    from prometheus_client import generate_latest, CollectorRegistry, multiprocess, REGISTRY

    if os.environ.get('PROMETHEUS_MULTIPROC_DIR'):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest(REGISTRY)

    return HttpResponse(data, content_type='text/plain; version=0.0.4; charset=utf-8')


urlpatterns = [
    path('health/', health_check),
    path('metrics', metrics_view),
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

