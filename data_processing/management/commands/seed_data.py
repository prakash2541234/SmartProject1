"""
management/commands/seed_data.py

Django management command to seed the database with sample users
and ingest the GTLB sensor CSV files.

Usage (from project root):
    python manage.py seed_data
    python manage.py seed_data --csv-dir path/to/GTLB-Data
    python manage.py seed_data --csv-zip path/to/GTLB-Data.zip
"""
import io, os, glob, zipfile
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

# ── Mapping: CSV user-hash → Django user info ──────────────
USER_MAP = {
    '1c0fd777': ('alice',  'alice123',  'Alice',  'Johnson'),
    '71e66ab3': ('bob',    'bob123',    'Bob',    'Smith'),
    '543d4676': ('carol',  'carol123',  'Carol',  'Williams'),
    'd13043b3': ('david',  'david123',  'David',  'Brown'),
    'de0e9b2c': ('eve',    'eve123',    'Eve',    'Davis'),
}

CLINICIANS = [
    ('dr_jones', 'jones123', 'Dr',  'Jones'),
    ('dr_patel', 'patel123', 'Dr',  'Patel'),
]


class Command(BaseCommand):
    help = 'Seed database: create sample users and ingest GTLB CSV data'

    def add_arguments(self, parser):
        parser.add_argument('--csv-dir', default=None, help='Path to GTLB-Data/ folder')
        parser.add_argument('--csv-zip', default=None, help='Path to GTLB-Data zip file')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== Graphene Trace — Seed Data ===\n'))

        # ── 1. Clinicians ─────────────────────────────────────
        clinician_objs = []
        for uname, pw, first, last in CLINICIANS:
            u, created = User.objects.get_or_create(username=uname, defaults={
                'email': f'{uname}@clinic.com', 'first_name': first,
                'last_name': last, 'role': 'clinician'})
            if created:
                u.set_password(pw); u.save()
                from accounts.models import ClinicianProfile
                ClinicianProfile.objects.get_or_create(user=u, defaults={'department':'Wound Care'})
                self.stdout.write(f'  ✓ Clinician: {uname}')
            else:
                self.stdout.write(f'  ~ Clinician exists: {uname}')
            clinician_objs.append(u)

        # ── 2. Patients ────────────────────────────────────────
        patient_map = {}
        for i, (uid_hash, (uname, pw, first, last)) in enumerate(USER_MAP.items()):
            clinician = clinician_objs[i % len(clinician_objs)]
            u, created = User.objects.get_or_create(username=uname, defaults={
                'email': f'{uname}@patient.com', 'first_name': first,
                'last_name': last, 'role': 'patient'})
            if created:
                u.set_password(pw); u.save()
                from accounts.models import PatientProfile
                PatientProfile.objects.get_or_create(user=u, defaults={'clinician': clinician})
                self.stdout.write(f'  ✓ Patient: {uname} → {clinician.username}')
            else:
                self.stdout.write(f'  ~ Patient exists: {uname}')
            patient_map[uid_hash] = u

        # ── 3. Find CSVs ───────────────────────────────────────
        csv_list = self._find_csvs(options)
        if not csv_list:
            self.stdout.write(self.style.WARNING(
                '\n  No CSV files found. Generating synthetic data instead…'))
            csv_list = self._synthetic_csvs()

        # ── 4. Ingest ──────────────────────────────────────────
        self.stdout.write(f'\n  Found {len(csv_list)} CSV file(s). Ingesting…\n')
        from data_processing.views import ingest_csv
        from data_processing.parser import parse_filename

        for fname, raw_bytes in csv_list:
            try:
                uid_hash, _ = parse_filename(fname)
            except ValueError:
                self.stdout.write(f'  ✗ Skip {fname} (bad filename)')
                continue

            patient = patient_map.get(uid_hash)
            if not patient:
                uname = f'patient_{uid_hash[:6]}'
                patient, created = User.objects.get_or_create(username=uname, defaults={
                    'email': f'{uname}@patient.com',
                    'first_name': 'Patient', 'last_name': uid_hash[:6], 'role': 'patient'})
                if created:
                    patient.set_password('pass123'); patient.save()
                    from accounts.models import PatientProfile
                    PatientProfile.objects.get_or_create(user=patient, defaults={'clinician': clinician_objs[0]})
                patient_map[uid_hash] = patient

            from data_processing.models import UploadSession
            already = UploadSession.objects.filter(
                patient=patient, filename=fname, status='done').exists()
            if already:
                self.stdout.write(f'  ~ Already ingested {fname}')
                continue

            self.stdout.write(f'  Processing {fname}…', ending=' ')
            try:
                session = ingest_csv(fname, raw_bytes, patient, User.objects.filter(role='admin').first() or patient)
                self.stdout.write(self.style.SUCCESS(f'✓ ({session.frame_count} frames)'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ {e}'))

        # ── 5. Summary ─────────────────────────────────────────
        from data_processing.models import PressureFrame, Alert
        self.stdout.write(self.style.SUCCESS(f'''
=== Done ===
  Users:   {User.objects.count()}
  Frames:  {PressureFrame.objects.count()}
  Alerts:  {Alert.objects.count()}

Login credentials:
  Admin:      admin / admin123
  Clinician:  dr_jones / jones123
  Clinician:  dr_patel / patel123
  Patient:    alice / alice123
  Patient:    bob   / bob123
  Patient:    carol / carol123
  Patient:    david / david123
  Patient:    eve   / eve123
'''))

    # ── Helpers ───────────────────────────────────────────────

    def _find_csvs(self, options):
        csv_dir = options.get('csv_dir')
        csv_zip = options.get('csv_zip')

        # Auto-detect if not specified
        if not csv_dir and not csv_zip:
            base = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            for candidate in [
                os.path.join(base, 'GTLB-Data'),
                os.path.join(os.path.dirname(base), 'GTLB-Data'),
            ]:
                if os.path.isdir(candidate):
                    csv_dir = candidate; break

            for candidate in [
                os.path.join(base, 'GTLB-Data.zip'),
                os.path.join(base, 'GTLB-Data__1_.zip'),
                os.path.join(os.path.dirname(base), 'GTLB-Data__1_.zip'),
            ]:
                if os.path.isfile(candidate):
                    csv_zip = candidate; break

        results = []
        if csv_dir and os.path.isdir(csv_dir):
            for path in sorted(glob.glob(os.path.join(csv_dir, '*.csv'))):
                with open(path, 'rb') as f:
                    results.append((os.path.basename(path), f.read()))
        elif csv_zip and os.path.isfile(csv_zip):
            with zipfile.ZipFile(csv_zip) as zf:
                for name in zf.namelist():
                    if name.lower().endswith('.csv') and '__MACOSX' not in name:
                        results.append((os.path.basename(name), zf.read(name)))
        return results

    def _synthetic_csvs(self):
        """Generate minimal synthetic data if no real CSVs found."""
        import random
        results = []
        for uid_hash in USER_MAP:
            for date in ['20251011', '20251012', '20251013']:
                rows = []
                for _ in range(100):            # 100 frames
                    for r in range(32):
                        vals = []
                        for c in range(32):
                            if 14<=r<=28 and 8<=c<=24:
                                dist = ((r-21)**2+(c-16)**2)**0.5
                                v = max(0, int(800-dist*35 + random.gauss(0,60)))
                                v = min(4095, v)
                            else:
                                v = random.randint(0,15) if random.random()<0.04 else 0
                            vals.append(str(v))
                        rows.append(','.join(vals)+'\n')
                results.append((f'{uid_hash}_{date}.csv', ''.join(rows).encode()))
        return results
