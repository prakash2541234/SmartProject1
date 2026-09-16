"""
URL configuration for stl project.

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
from django.urls import path, include
from apis.moniter.react.views import (
    StatusUpdateAPIView,
    StartProcessAPIView,
    ProcessStatusAPIView,
    get_status,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/monitor/', include('apis.moniter.urls')),
    path('api/moniter/', include('apis.moniter.urls')),
    path('api/start-process/', StartProcessAPIView.as_view(), name='start-process-direct'),
    path('api/process-status/', ProcessStatusAPIView.as_view(), name='process-status-direct'),
    path('api/process-status/<str:ritm_number>/', ProcessStatusAPIView.as_view(), name='process-status-detail-direct'),
    path('api/status-update/', StatusUpdateAPIView.as_view(), name='status-update'),
    path('api/status/<str:ritm_number>/', get_status, name='status-detail'),
]
