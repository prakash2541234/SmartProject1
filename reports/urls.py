from django.urls import path
from . import views

app_name = 'reports'
urlpatterns = [
    path('',                          views.ReportView.as_view(), name='report'),
    path('patient/<int:patient_pk>/', views.ReportView.as_view(), name='patient_report'),
]
