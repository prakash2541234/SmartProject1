import json
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib import messages

from accounts.models import User
from accounts.decorators import role_required
from data_processing.models import PressureFrame, Alert, Comment, UploadSession
from data_processing.parser import generate_explanation


# ── Root redirect based on role ───────────────────────────────────────────────
@login_required
def home(request):
    r = request.user.role
    if r == 'admin':     return redirect('dashboard:admin_home')
    if r == 'clinician': return redirect('dashboard:clinician_home')
    return redirect('dashboard:patient_home')


# ═══════════════════════════════════════
#  PATIENT VIEWS
# ═══════════════════════════════════════

@method_decorator([login_required, role_required('patient')], name='dispatch')
class PatientDashboardView(View):
    def get(self, request):
        uid = request.user.pk
        stats = _patient_stats(uid)
        sessions = UploadSession.objects.filter(patient_id=uid).order_by('-created_at')[:10]
        alerts   = Alert.objects.filter(patient_id=uid).order_by('-created_at')[:5]
        latest_frame = PressureFrame.objects.filter(patient_id=uid).order_by('-timestamp').first()
        return render(request, 'patient/dashboard.html', {
            'stats': stats, 'sessions': sessions,
            'alerts': alerts, 'latest_frame': latest_frame,
        })


@method_decorator([login_required, role_required('patient')], name='dispatch')
class PatientAlertsView(View):
    def get(self, request):
        Alert.objects.filter(patient=request.user, is_read=False).update(is_read=True)
        alerts = Alert.objects.filter(patient=request.user)
        return render(request, 'patient/alerts.html', {'alerts': alerts})


@method_decorator([login_required, role_required('patient')], name='dispatch')
class PatientCommentsView(View):
    def get(self, request):
        comments = Comment.objects.filter(patient=request.user)
        frames   = PressureFrame.objects.filter(patient=request.user).order_by('-timestamp')[:50]
        return render(request, 'patient/comments.html', {'comments': comments, 'frames': frames})

    def post(self, request):
        text     = request.POST.get('text','').strip()
        frame_id = request.POST.get('frame_id') or None
        if text:
            frame = PressureFrame.objects.filter(pk=frame_id, patient=request.user).first() if frame_id else None
            Comment.objects.create(patient=request.user, frame=frame, text=text)
            messages.success(request, 'Comment submitted.')
        return redirect('dashboard:patient_comments')


# ═══════════════════════════════════════
#  CLINICIAN VIEWS
# ═══════════════════════════════════════

@method_decorator([login_required, role_required('clinician')], name='dispatch')
class ClinicianDashboardView(View):
    def get(self, request):
        patients = User.objects.filter(
            patient_profile__clinician=request.user).order_by('last_name')
        # Collect recent alerts across all assigned patients
        all_alerts = Alert.objects.filter(
            patient__patient_profile__clinician=request.user
        ).select_related('patient').order_by('-created_at')[:20]
        unread = all_alerts.filter(is_read=False).count()
        return render(request, 'clinician/dashboard.html', {
            'patients': patients,
            'all_alerts': all_alerts,
            'unread': unread,
        })


@method_decorator([login_required, role_required('clinician')], name='dispatch')
class ClinicianPatientView(View):
    def _check_access(self, request, patient):
        try:
            return patient.patient_profile.clinician == request.user
        except Exception:
            return False

    def get(self, request, pk):
        patient = get_object_or_404(User, pk=pk, role='patient')
        if not self._check_access(request, patient):
            messages.error(request, 'Patient not assigned to you.')
            return redirect('dashboard:clinician_home')
        stats        = _patient_stats(pk)
        frames       = PressureFrame.objects.filter(patient=patient).order_by('-timestamp')[:200]
        alerts       = Alert.objects.filter(patient=patient).order_by('-created_at')[:20]
        comments     = Comment.objects.filter(patient=patient)
        latest_frame = PressureFrame.objects.filter(patient=patient).order_by('-timestamp').first()
        sessions     = UploadSession.objects.filter(patient=patient)[:10]
        return render(request, 'clinician/patient_detail.html', {
            'patient': patient, 'stats': stats, 'frames': frames,
            'alerts': alerts, 'comments': comments,
            'latest_frame': latest_frame, 'sessions': sessions,
        })


@method_decorator([login_required, role_required('clinician')], name='dispatch')
class ClinicianReplyView(View):
    def post(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        reply   = request.POST.get('reply','').strip()
        if reply:
            comment.clinician_reply = reply
            comment.reply_by = request.user
            comment.reply_at = timezone.now()
            comment.save()
            messages.success(request, 'Reply sent.')
        return redirect('dashboard:clinician_patient', pk=comment.patient.pk)


@method_decorator([login_required, role_required('clinician')], name='dispatch')
class ClinicianAlertsView(View):
    def get(self, request):
        alerts = Alert.objects.filter(
            patient__patient_profile__clinician=request.user
        ).select_related('patient').order_by('-created_at')
        Alert.objects.filter(
            patient__patient_profile__clinician=request.user, is_read=False
        ).update(is_read=True)
        return render(request, 'clinician/alerts.html', {'alerts': alerts})


# ═══════════════════════════════════════
#  ADMIN VIEWS
# ═══════════════════════════════════════

@method_decorator([login_required, role_required('admin')], name='dispatch')
class AdminDashboardView(View):
    def get(self, request):
        return render(request, 'admin_panel/dashboard.html', {
            'all_users':     User.objects.all().order_by('role','last_name'),
            'total_frames':  PressureFrame.objects.count(),
            'total_alerts':  Alert.objects.count(),
            'total_sessions':UploadSession.objects.count(),
        })


# ═══════════════════════════════════════
#  JSON API ENDPOINTS (for Chart.js / heatmap)
# ═══════════════════════════════════════

@login_required
def api_metrics(request):
    """Time-series data for charts. ?hours=1|6|24 &patient_id=N"""
    uid   = _resolve_patient(request)
    hours = int(request.GET.get('hours', 6))
    end   = timezone.now()
    start = end - timedelta(hours=hours)
    frames = PressureFrame.objects.filter(
        patient_id=uid, timestamp__range=(start, end)
    ).order_by('timestamp').values(
        'timestamp','peak_pressure','contact_area_pct','avg_pressure','is_flagged')

    return JsonResponse({
        'labels':        [f['timestamp'].strftime('%H:%M:%S') for f in frames],
        'peak_pressure': [f['peak_pressure']    for f in frames],
        'contact_area':  [f['contact_area_pct'] for f in frames],
        'avg_pressure':  [f['avg_pressure']     for f in frames],
        'flags':         [f['is_flagged']       for f in frames],
    })


@login_required
def api_frame(request, pk):
    """Return matrix JSON for a single frame."""
    frame = get_object_or_404(PressureFrame, pk=pk)
    if request.user.role == 'patient' and frame.patient != request.user:
        return JsonResponse({'error':'forbidden'}, status=403)
    return JsonResponse({
        'id': frame.pk,
        'timestamp': str(frame.timestamp),
        'matrix': frame.matrix_data,
        'peak_pressure':    frame.peak_pressure,
        'contact_area_pct': frame.contact_area_pct,
        'avg_pressure':     frame.avg_pressure,
        'is_flagged':       frame.is_flagged,
    })


@login_required
def api_frames_list(request):
    """List of frame ids for the playback timeline. ?session_id=N &patient_id=N"""
    uid        = _resolve_patient(request)
    session_id = request.GET.get('session_id')
    qs = PressureFrame.objects.filter(patient_id=uid).order_by('timestamp')
    if session_id:
        qs = qs.filter(session_id=session_id)
    else:
        qs = qs.order_by('-timestamp')[:1000]
    return JsonResponse(
        [{'id': f.pk, 'timestamp': str(f.timestamp), 'peak': f.peak_pressure}
         for f in qs], safe=False)


@login_required
def api_explanation(request):
    uid   = _resolve_patient(request)
    frame = PressureFrame.objects.filter(patient_id=uid).order_by('-timestamp').first()
    if not frame:
        return JsonResponse({'text': 'No data uploaded yet. Use the Upload page to add CSV files.'})
    recent = Alert.objects.filter(
        patient_id=uid,
        created_at__gte=timezone.now()-timedelta(hours=24)
    ).count()
    text = generate_explanation(
        frame.peak_pressure, frame.contact_area_pct, frame.avg_pressure, recent)
    return JsonResponse({'text': text})


@login_required
def api_alert_count(request):
    uid = _resolve_patient(request)
    count = Alert.objects.filter(patient_id=uid, is_read=False).count()
    return JsonResponse({'count': count})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_patient(request):
    """Allow clinicians/admins to pass ?patient_id= to view another patient's data."""
    if request.user.role in ('clinician','admin'):
        pid = request.GET.get('patient_id')
        if pid:
            return int(pid)
    return request.user.pk


def _patient_stats(uid):
    from django.db.models import Max, Avg, Count, Sum
    agg = PressureFrame.objects.filter(patient_id=uid).aggregate(
        total_frames=Count('id'),
        max_peak=Max('peak_pressure'),
        avg_peak=Avg('peak_pressure'),
        avg_contact=Avg('contact_area_pct'),
        flagged=Sum('is_flagged'),
    )
    alert_count = Alert.objects.filter(patient_id=uid).count()
    return {
        'total_frames': agg['total_frames'] or 0,
        'max_peak':     round(agg['max_peak']   or 0, 1),
        'avg_peak':     round(agg['avg_peak']   or 0, 1),
        'avg_contact':  round(agg['avg_contact']or 0, 1),
        'flagged':      agg['flagged'] or 0,
        'alert_count':  alert_count,
    }
