from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from django.db.models import Avg, Max, Count, Q
from datetime import timedelta, date

from accounts.decorators import role_required
from accounts.models import User
from data_processing.models import PressureFrame, Alert


def _day_summary(uid, day):
    
    start = timezone.make_aware(
        timezone.datetime.combine(day, timezone.datetime.min.time())
    )
    end = timezone.make_aware(
        timezone.datetime.combine(day, timezone.datetime.max.time())
    )
    agg = PressureFrame.objects.filter(
        patient_id=uid, timestamp__range=(start, end)
    ).aggregate(
        frames=Count('id'), max_peak=Max('peak_pressure'),
        avg_peak=Avg('peak_pressure'), avg_contact=Avg('contact_area_pct'),
        flagged=Count('id', filter=Q(is_flagged=True)),
    )
    alerts = Alert.objects.filter(patient_id=uid, timestamp__range=(start,end)).count()
    return {
        'frames':      agg['frames'] or 0,
        'max_peak':    round(agg['max_peak']    or 0, 1),
        'avg_peak':    round(agg['avg_peak']    or 0, 1),
        'avg_contact': round(agg['avg_contact'] or 0, 1),
        'flagged':     agg['flagged'] or 0,
        'alerts':      alerts,
    }


def _pct_change(new, old):
    if not old: return None
    return round((new - old) / old * 100, 1)


@method_decorator([login_required, role_required('patient','clinician','admin')], name='dispatch')
class ReportView(View):
    def get(self, request, patient_pk=None):
        if patient_pk:
            patient = get_object_or_404(User, pk=patient_pk, role='patient')
        else:
            patient = request.user

        uid       = patient.pk
        today     = date.today()
        yesterday = today - timedelta(days=1)

        today_data = _day_summary(uid, today)
        yest_data  = _day_summary(uid, yesterday)

        comparison = {
            'peak':    _pct_change(today_data['max_peak'],   yest_data['max_peak']),
            'contact': _pct_change(today_data['avg_contact'],yest_data['avg_contact']),
            'alerts':  _pct_change(today_data['alerts'],     yest_data['alerts']),
        }

        weekly = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            s = _day_summary(uid, d)
            weekly.append({'date': d.strftime('%d %b'), **s})

        recent_alerts = Alert.objects.filter(patient_id=uid).order_by('-created_at')[:20]

        return render(request, 'reports/report.html', {
            'patient':       patient,
            'today':         today,
            'yesterday':     yesterday,
            'today_data':    today_data,
            'yest_data':     yest_data,
            'comparison':    comparison,
            'weekly':        weekly,
            'recent_alerts': recent_alerts,
        })
