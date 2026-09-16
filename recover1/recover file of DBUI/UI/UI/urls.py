from django.contrib import admin
from django.urls import path
import App.views as views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('hello/', views.home, name='hello'),
    path('poll-lookup/', views.poll_lookup, name='poll_lookup'),
]