from django.urls import path, include

app_name = 'moniter'

urlpatterns = [
    path('react/', include('apis.moniter.react.urls')),
    path('azure/', include('apis.moniter.azure.urls')),
]