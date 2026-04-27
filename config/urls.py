from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
 

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('facilities.urls')),
]



if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# urlpatterns = [
#     path('admin/', admin.site.urls),
#     path('', include('dashboard.urls')),
#     path('accounts/', include('accounts.urls')),
#     path('safety/', include('safety.urls')),
#     path('facilities', include('facilities.urls')),
#     path('monitoring/', include('monitoring.urls')),
#     path('alerts/', include('alerts.urls')),
# ]