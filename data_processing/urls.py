from django.urls import path
from . import views

app_name = 'data_processing'
urlpatterns = [
    path('upload/',                          views.UploadView.as_view(), name='upload'),
    path('upload/patient/<int:patient_pk>/', views.UploadView.as_view(), name='upload_for_patient'),
]
