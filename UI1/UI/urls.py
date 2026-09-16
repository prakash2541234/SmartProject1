from django.urls import path
import App.views as views

urlpatterns = [
    path('', views.dashboard),
    path('health', views.health),
    path('assets/dashboard.css', views.dashboard_css),
    path('api/process-status/', views.process_status),
    path('api/get-status/', views.get_status),
    path('hello/', views.hello),
]