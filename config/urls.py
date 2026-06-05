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

    구조: 각 컨테이너(역할)는 부모 dir 하위 **자기 subdir**에만 기록한다
    (entrypoint가 PROMETHEUS_MULTIPROC_DIR=<부모>/<역할>로 설정). 컨테이너마다
    메인 PID가 1이라 같은 dir 공유 시 counter_1.db가 충돌하므로 subdir로 분리한다.

    집계: 부모의 모든 subdir `*/*.db`를 한 파일 리스트로 모아 **단일**
    MultiProcessCollector.merge(files)로 병합한다. merge는 파일 *내용의 KEY*
    (metric_name·labels)로 합치므로, 서로 다른 subdir의 동명 파일(counter_1.db)도
    경로가 달라 별개 파일로 정상 집계된다(복사·리네임·다중 collector 불필요).

    ※ 전제: gauge live* 모드는 파일명 pid로 dedup하므로, **여러 subdir에 동일 pid의
      gauge live* 파일이 동시에 생기면** 부정확해질 수 있다. 현재 gauge는
      django_prometheus(단일 컨테이너)에서만 발생 → 단일 subdir라 안전. 운영 중
      다른 컨테이너가 gauge를 내기 시작하면 아래 경고 로그로 드러나며, 그때
      서비스별 /metrics + Prometheus 다중 scrape(P6)로 전환한다.
    """
    import glob
    import logging
    from prometheus_client import generate_latest, CollectorRegistry, multiprocess, REGISTRY

    mp_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR')
    if not mp_dir:
        return HttpResponse(generate_latest(REGISTRY),
                            content_type='text/plain; version=0.0.4; charset=utf-8')

    parent = os.path.dirname(mp_dir.rstrip('/'))          # <부모> (예: /tmp/prometheus_multiproc)
    files = glob.glob(os.path.join(parent, '*', '*.db'))  # 전 subdir의 per-process 파일

    # gauge live* 전제 검증 — 2개 이상 subdir에 같은 gauge live 파일명이 있으면 경고
    gauge_live = {}
    for f in files:
        base = os.path.basename(f)
        if base.startswith('gauge_live'):
            gauge_live.setdefault(base, []).append(os.path.dirname(f))
    dup = {k: v for k, v in gauge_live.items() if len(v) > 1}
    if dup:
        logging.getLogger(__name__).warning(
            "multiproc gauge live* 파일이 여러 subdir에 중복 — 집계 부정확 가능, "
            "P6(서비스별 /metrics) 전환 필요: %s", dup,
        )

    registry = CollectorRegistry()

    class _MergeAllSubdirs:
        def collect(self):
            return multiprocess.MultiProcessCollector.merge(files, accumulate=True)

    registry.register(_MergeAllSubdirs())
    return HttpResponse(generate_latest(registry),
                        content_type='text/plain; version=0.0.4; charset=utf-8')


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

