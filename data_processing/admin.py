from django.contrib import admin
from .models import UploadSession, PressureFrame, Alert, Comment, Metrics

@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ('filename','patient','status','frame_count','created_at')
    list_filter  = ('status',)

@admin.register(PressureFrame)
class PressureFrameAdmin(admin.ModelAdmin):
    list_display  = ('patient','timestamp','peak_pressure','contact_area_pct','is_flagged')
    list_filter   = ('is_flagged','patient')
    readonly_fields = ('matrix_data',)

@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('patient','severity','timestamp','is_read')
    list_filter  = ('severity','is_read')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('patient','timestamp','text')

admin.site.register(Metrics)
