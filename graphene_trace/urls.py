from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('',          RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('accounts/', include('accounts.urls',       namespace='accounts')),
    path('dashboard/',include('dashboard.urls',      namespace='dashboard')),
    path('data/',     include('data_processing.urls', namespace='data_processing')),
    path('analytics/',include('analytics.urls',      namespace='analytics')),
    path('reports/',  include('reports.urls',        namespace='reports')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
