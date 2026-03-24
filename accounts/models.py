from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLES = [('patient','Patient'),('clinician','Clinician'),('admin','Admin')]
    role  = models.CharField(max_length=20, choices=ROLES, default='patient')

    def is_patient(self):   return self.role == 'patient'
    def is_clinician(self): return self.role == 'clinician'
    def is_admin_role(self):return self.role == 'admin'
    def display_name(self):
        return self.get_full_name().strip() or self.username
    def __str__(self): return f"{self.username} ({self.role})"


class PatientProfile(models.Model):
    user          = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')
    date_of_birth = models.DateField(null=True, blank=True)
    notes         = models.TextField(blank=True)
    clinician     = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_patients', limit_choices_to={'role':'clinician'})
    def __str__(self): return f"Profile({self.user.username})"


class ClinicianProfile(models.Model):
    user           = models.OneToOneField(User, on_delete=models.CASCADE, related_name='clinician_profile')
    department     = models.CharField(max_length=100, blank=True)
    license_number = models.CharField(max_length=50,  blank=True)
    def __str__(self): return f"ClinicianProfile({self.user.username})"
