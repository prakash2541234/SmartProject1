from django.contrib import admin
from django.urls import path
import App.views as views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home),
    path('hello/', views.home),
]