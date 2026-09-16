from django.db import models
from django.db import models

class APILog(models.Model):
    request_id = models.CharField(max_length=100)
    status = models.CharField(max_length=50)
    message = models.TextField()
    generated_password = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)  # ✅ keep only this

    def __str__(self):
        return f"APILog(request_id={self.request_id}, status={self.status}, message={self.message})"

class ManagedServicePrincipal(models.Model):
    service_principal_id = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=256, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (
            f"ManagedServicePrincipal(service_principal_id={self.service_principal_id}, "
            f"display_name={self.display_name})"
        )

class RequestPayload(models.Model):
    request_id = models.CharField(max_length=100, unique=True)
    process_name = models.CharField(max_length=100)

    input_payload = models.JSONField(null=True, blank=True)
    output_payload = models.JSONField(null=True, blank=True)

    status = models.CharField(max_length=50)
    error_message = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    