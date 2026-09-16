from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('process/', views.process_images, name='process_images'),
    path('encryption/', views.encryption_view, name='encryption'),
    path('decryption/', views.decryption_view, name='decryption'),
]