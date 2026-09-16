from django.db import models

# Create your models here.
class RequestTracker(models.Model):
    uuid = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=50)
    logs = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)