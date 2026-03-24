import io
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from accounts.models import User
from accounts.decorators import role_required
from .models import UploadSession, PressureFrame, Alert
from .parser import (parse_filename, date_str_to_dt, parse_csv_frames,
                     analyse_frame, check_alert, frames_to_timestamps,
                     extract_csvs_from_zip)


def ingest_csv(csv_name, csv_bytes, patient, uploader):
    """Core ingestion: parse CSV → bulk insert frames + alerts."""
    threshold = getattr(settings, 'PRESSURE_ALERT_THRESHOLD', 500)
    ct        = getattr(settings, 'CONTACT_THRESHOLD', 50)
    mp        = getattr(settings, 'MIN_REGION_PIXELS', 10)

    try:
        _, date_str = parse_filename(csv_name)
        base_dt = timezone.make_aware(date_str_to_dt(date_str), timezone.utc)
    except Exception:
        base_dt   = timezone.now()
        date_str  = ''

    session = UploadSession.objects.create(
        patient=patient, uploaded_by=uploader,
        filename=csv_name, date_label=date_str, status='processing')

    try:
        text       = csv_bytes.decode('utf-8', errors='replace')
        frames     = parse_csv_frames(io.StringIO(text))
        timestamps = frames_to_timestamps(
            base_dt.replace(tzinfo=None), len(frames), interval_sec=5)

        frame_objs, flagged_indices = [], []
        for i, (flat, ts) in enumerate(zip(frames, timestamps)):
            m = analyse_frame(flat, ct, mp)
            flagged, sev, msg = check_alert(m['peak_pressure'], threshold)
            aware_ts = timezone.make_aware(ts, timezone.utc)
            pf = PressureFrame(
                patient=patient, session=session,
                frame_index=i, timestamp=aware_ts,
                matrix_data=flat,
                peak_pressure=m['peak_pressure'],
                contact_area_pct=m['contact_area_pct'],
                avg_pressure=m['avg_pressure'],
                is_flagged=flagged)
            frame_objs.append(pf)
            if flagged:
                flagged_indices.append((i, aware_ts, sev, msg))

        PressureFrame.objects.bulk_create(frame_objs, batch_size=500)

        if flagged_indices:
            saved = {f.frame_index: f for f in
                     PressureFrame.objects.filter(session=session)}
            Alert.objects.bulk_create([
                Alert(patient=patient, frame=saved.get(idx),
                      timestamp=ts, severity=sev, message=msg)
                for idx, ts, sev, msg in flagged_indices
            ], batch_size=500)

        session.frame_count = len(frames)
        session.status = 'done'
        session.save()
    except Exception as e:
        session.status = 'error'
        session.error_msg = str(e)
        session.save()
        raise
    return session


@method_decorator(login_required, name='dispatch')
class UploadView(View):
    """Upload CSV/ZIP. Patient → own data. Clinician → specify patient_pk."""
    template_name = 'data_processing/upload.html'

    def _patient(self, request, patient_pk=None):
        if patient_pk:
            return get_object_or_404(User, pk=patient_pk, role='patient')
        return request.user

    def get(self, request, patient_pk=None):
        patient  = self._patient(request, patient_pk)
        sessions = UploadSession.objects.filter(patient=patient)
        return render(request, self.template_name,
                      {'patient': patient, 'sessions': sessions})

    def post(self, request, patient_pk=None):
        patient = self._patient(request, patient_pk)
        files   = request.FILES.getlist('csv_files')
        if not files:
            messages.error(request, 'No files selected.')
            return redirect(request.path)

        count = 0
        for f in files:
            raw  = f.read()
            name = f.name
            csv_list = extract_csvs_from_zip(raw) if name.lower().endswith('.zip') else [(name, raw)]
            for csv_name, csv_bytes in csv_list:
                try:
                    ingest_csv(csv_name, csv_bytes, patient, request.user)
                    count += 1
                except Exception as e:
                    messages.error(request, f'Error in {csv_name}: {e}')

        if count:
            messages.success(request, f'Processed {count} file(s) successfully.')

        role = request.user.role
        if role == 'clinician':
            return redirect('dashboard:clinician_patient', pk=patient.pk)
        if role == 'admin':
            return redirect('dashboard:admin_home')
        return redirect('dashboard:patient_home')
