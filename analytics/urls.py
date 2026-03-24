from django.urls import path
from . import views

app_name = 'analytics'
urlpatterns = [
    path('',                          views.AnalyticsView.as_view(), name='overview'),
    path('patient/<int:patient_pk>/', views.AnalyticsView.as_view(), name='patient_analytics'),
]
