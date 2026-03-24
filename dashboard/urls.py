from django.urls import path
from . import views

app_name = 'dashboard'
urlpatterns = [
    path('',                              views.home,                          name='home'),
    # Patient
    path('patient/',                      views.PatientDashboardView.as_view(),name='patient_home'),
    path('patient/alerts/',               views.PatientAlertsView.as_view(),   name='patient_alerts'),
    path('patient/comments/',             views.PatientCommentsView.as_view(),  name='patient_comments'),
    # Clinician
    path('clinician/',                    views.ClinicianDashboardView.as_view(),name='clinician_home'),
    path('clinician/patient/<int:pk>/',   views.ClinicianPatientView.as_view(), name='clinician_patient'),
    path('clinician/alerts/',             views.ClinicianAlertsView.as_view(),  name='clinician_alerts'),
    path('clinician/reply/<int:pk>/',     views.ClinicianReplyView.as_view(),   name='clinician_reply'),
    # Admin
    path('admin/',                        views.AdminDashboardView.as_view(),   name='admin_home'),
    # JSON API
    path('api/metrics/',                  views.api_metrics,      name='api_metrics'),
    path('api/frame/<int:pk>/',           views.api_frame,        name='api_frame'),
    path('api/frames/',                   views.api_frames_list,  name='api_frames_list'),
    path('api/explanation/',              views.api_explanation,  name='api_explanation'),
    path('api/alert-count/',              views.api_alert_count,  name='api_alert_count'),
]
