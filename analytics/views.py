from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from django.db.models import Avg, Max, Count
from datetime import timedelta, date

from accounts.decorators import role_required
from accounts.models import User
from data_processing.models import PressureFrame, Alert, Metrics


def _compute_risk(uid):
    """Simple heuristic risk score 0–10 based on recent pressure data."""
    now   = timezone.now()
    start = now - timedelta(hours=24)
    frames = PressureFrame.objects.filter(patient_id=uid, timestamp__gte=start)
    if not frames.exists():
        return 0, "No recent data."

    agg = frames.aggregate(avg_peak=Avg('peak_pressure'), max_peak=Max('peak_pressure'))
    alert_count = Alert.objects.filter(
        patient_id=uid, created_at__gte=start).count()
    flagged = frames.filter(is_flagged=True).count()
    total   = frames.count()
    flag_pct = (flagged / total * 100) if total else 0

    score = 0
    if agg['avg_peak'] > 800:  score += 3
    elif agg['avg_peak'] > 400: score += 1
    if agg['max_peak'] > 1500: score += 3
    elif agg['max_peak'] > 700: score += 1
    if alert_count > 10: score += 2
    elif alert_count > 3: score += 1
    if flag_pct > 20: score += 2
    elif flag_pct > 5: score += 1

    score = min(score, 10)
    if score >= 7:   label = "High risk — contact clinician immediately."
    elif score >= 4: label = "Moderate risk — monitor closely and reposition regularly."
    else:            label = "Low risk — pressure levels look acceptable."
    return score, label


@method_decorator([login_required, role_required('patient','clinician','admin')], name='dispatch')
class AnalyticsView(View):
    def get(self, request, patient_pk=None):
        if patient_pk:
            patient = get_object_or_404(User, pk=patient_pk, role='patient')
        else:
            patient = request.user

        uid = patient.pk
        risk_score, risk_label = _compute_risk(uid)

        # Last 7 days daily summary
        today = date.today()
        daily = []
        for i in range(6, -1, -1):
            d     = today - timedelta(days=i)
            start = timezone.make_aware(
                timezone.datetime.combine(d, timezone.datetime.min.time())
            )
            end = timezone.make_aware(
                timezone.datetime.combine(d, timezone.datetime.max.time())
            )
            agg = PressureFrame.objects.filter(
                patient_id=uid, timestamp__range=(start, end)
            ).aggregate(
                frames=Count('id'),
                max_peak=Max('peak_pressure'),
                avg_peak=Avg('peak_pressure'),
                avg_contact=Avg('contact_area_pct'),
            )
            alerts = Alert.objects.filter(patient_id=uid, timestamp__range=(start,end)).count()
            daily.append({
                'date':        d.strftime('%d %b'),
                'frames':      agg['frames'] or 0,
                'max_peak':    round(agg['max_peak'] or 0, 1),
                'avg_peak':    round(agg['avg_peak'] or 0, 1),
                'avg_contact': round(agg['avg_contact'] or 0, 1),
                'alerts':      alerts,
            })

        return render(request, 'analytics/analytics.html', {
            'patient':     patient,
            'risk_score':  risk_score,
            'risk_label':  risk_label,
            'daily':       daily,
        })
