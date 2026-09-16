# api/urls.py

from django.urls import path
from .views import create_keyvault, get_status, get_logs

urlpatterns = [
    path('create-keyvault/', create_keyvault),
    path('status/<str:uuid>/', get_status),
    path('logs/<str:uuid>/', get_logs),
]