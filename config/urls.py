import os

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse, HttpResponse
from monitoring import views as monitoring_views


def health_check(request):
    return JsonResponse({'status': 'ok'})


def metrics_view(request):
    """멀티프로세스(celery·consumer) 메트릭을 합산해 노출.

    PROMETHEUS_MULTIPROC_DIR가 설정되면 각 프로세스가 dir에 기록한 메트릭을
    MultiProcessCollector로 합산한다(celery/consumer의 icmp2_* 카운터 포함).
    미설정 시 기본 REGISTRY만 반환(단일 프로세스).
    """
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

