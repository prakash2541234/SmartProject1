from django.db import models
from django.conf import settings


class UploadSession(models.Model):
    STATUS = [('pending','Pending'),('processing','Processing'),('done','Done'),('error','Error')]
    patient     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='upload_sessions')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='uploads_made')
    filename    = models.CharField(max_length=255)
    date_label  = models.CharField(max_length=20, blank=True)
    frame_count = models.IntegerField(default=0)
    status      = models.CharField(max_length=20, choices=STATUS, default='pending')
    error_msg   = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return f"{self.filename} ({self.status})"


class PressureFrame(models.Model):
    """One 32×32 sensor frame. matrix_data = flat list of 1024 ints stored as JSON."""
    patient          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pressure_frames')
    session          = models.ForeignKey(UploadSession, on_delete=models.CASCADE, related_name='frames')
    frame_index      = models.IntegerField()
    timestamp        = models.DateTimeField(db_index=True)
    matrix_data      = models.JSONField()
    peak_pressure    = models.FloatField(default=0)
    contact_area_pct = models.FloatField(default=0)
    avg_pressure     = models.FloatField(default=0)
    is_flagged       = models.BooleanField(default=False)
    class Meta:
        ordering = ['timestamp']
        indexes  = [models.Index(fields=['patient','timestamp']),
                    models.Index(fields=['session','frame_index'])]
    def __str__(self): return f"Frame {self.frame_index} @ {self.timestamp}"


class Metrics(models.Model):
    """Daily aggregated metrics per patient."""
    patient         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='metrics')
    date            = models.DateField()
    max_peak        = models.FloatField(default=0)
    avg_peak        = models.FloatField(default=0)
    avg_contact_pct = models.FloatField(default=0)
    total_frames    = models.IntegerField(default=0)
    alert_count     = models.IntegerField(default=0)
    computed_at     = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ('patient','date')
        ordering = ['-date']


class Alert(models.Model):
    SEVERITY = [('info','Info'),('warning','Warning'),('critical','Critical')]
    patient    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alerts')
    frame      = models.ForeignKey(PressureFrame, on_delete=models.SET_NULL, null=True, related_name='alerts')
    timestamp  = models.DateTimeField()
    severity   = models.CharField(max_length=20, choices=SEVERITY, default='warning')
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['patient','is_read'])]
    def __str__(self): return f"[{self.severity}] {self.patient.username}"


class Comment(models.Model):
    """Patient comment → clinician reply thread."""
    patient         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
    frame           = models.ForeignKey(PressureFrame, on_delete=models.SET_NULL, null=True, blank=True, related_name='comments')
    timestamp       = models.DateTimeField(auto_now_add=True)
    text            = models.TextField()
    clinician_reply = models.TextField(blank=True)
    reply_by        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='replies_made')
    reply_at        = models.DateTimeField(null=True, blank=True)
    class Meta: ordering = ['-timestamp']
    def __str__(self): return f"Comment by {self.patient.username}"
