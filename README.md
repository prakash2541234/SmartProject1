# Graphene Trace — Sensore Django Platform

A full Django web application for the Graphene Trace MedTech startup.
Processes 32×32 pressure sensor data from the **Sensore** smart mat
to prevent pressure ulcers.

---

## Quick Start (3 commands)

```bash
# Mac / Linux
bash setup.sh

# Windows
setup.bat

# Then run:
source venv/bin/activate          # Windows: venv\Scripts\activate
python manage.py runserver
# Open: http://127.0.0.1:8000
```

---

## Manual Setup

```bash
cd graphene_django

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate

# Install requirements
pip install "Django>=4.2" numpy

# (Optional) place GTLB-Data/ folder or GTLB-Data.zip in project root

# Run migrations
python manage.py migrate

# Create admin superuser
python manage.py createsuperuser --username admin
# or use the shell:
python manage.py shell -c "
from django.contrib.auth import get_user_model
U = get_user_model()
U.objects.create_superuser('admin','admin@gt.com','admin123', role='admin')
"

# Seed sample users + ingest CSV data
python manage.py seed_data
# Custom data location:
python manage.py seed_data --csv-zip /path/to/GTLB-Data.zip
python manage.py seed_data --csv-dir /path/to/GTLB-Data/

# Run development server
python manage.py runserver
```

---

## Login Credentials (after seed_data)

| Role       | Username  | Password  |
|------------|-----------|-----------|
| Admin      | admin     | admin123  |
| Clinician  | dr_jones  | jones123  |
| Clinician  | dr_patel  | patel123  |
| Patient    | alice     | alice123  |
| Patient    | bob       | bob123    |
| Patient    | carol     | carol123  |
| Patient    | david     | david123  |
| Patient    | eve       | eve123    |

---

## Project Structure

```
graphene_django/
├── manage.py
├── requirements.txt
├── setup.sh  /  setup.bat
│
├── graphene_trace/          ← Django project config
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── accounts/                ← Auth: custom User + profiles
│   ├── models.py            User, PatientProfile, ClinicianProfile
│   ├── views.py             Login, logout, user CRUD
│   ├── decorators.py        @role_required
│   └── templates/accounts/
│
├── dashboard/               ← All dashboards + JSON API
│   ├── views.py             Patient/Clinician/Admin dashboards
│   ├── urls.py              + /api/metrics/ /api/frame/ /api/frames/
│   └── templates/
│       ├── patient/         dashboard, alerts, comments
│       ├── clinician/       dashboard, patient_detail, alerts
│       └── admin_panel/     dashboard
│
├── data_processing/         ← CSV ingestion + sensor models
│   ├── models.py            UploadSession, PressureFrame, Alert, Comment
│   ├── parser.py            CSV parser, PPI, contact area, alerts
│   ├── views.py             Upload view (patient + clinician)
│   └── management/commands/seed_data.py
│
├── analytics/               ← Risk scoring + 7-day breakdown
│   └── views.py
│
├── reports/                 ← Daily HTML report (today vs yesterday)
│   └── views.py
│
├── static/
│   ├── css/main.css         Dark medical dashboard theme
│   └── js/
│       ├── heatmap.js       Canvas 32×32 renderer + playback
│       └── charts.js        Chart.js line graphs
│
└── templates/
    └── base.html            Sidebar layout base template
```

---

## Features

### Patient Dashboard
- 32×32 heatmap rendered on HTML5 Canvas — thermal colour scale
- **Playback timeline** — scrub or auto-play frames at 5fps
- Session selector — switch between CSV upload sessions
- Live metrics: Peak Pressure, Contact Area %, Average Pressure
- Time-range charts: 1h / 6h / 24h (Chart.js)
- Plain-English pressure explanation
- Alert log with severity (info / warning / critical)
- Comment system with clinician reply thread

### Clinician Dashboard
- Patient list (only assigned patients)
- Upload CSVs on behalf of a patient
- Aggregated alert feed across all patients
- Reply to patient comments in-thread
- Full heatmap + charts per patient

### Admin Panel
- Create / edit / delete users (patient, clinician, admin)
- Assign patients to clinicians
- System-wide statistics

### Analytics
- Heuristic risk score 0–10 (based on last 24h data)
- 7-day daily breakdown table + bar chart

### Reports
- Today vs yesterday comparison (peak, contact, alerts)
- Day-on-day % change indicators
- 7-day trend chart
- Printable HTML output

---

## Tech Stack

| Layer      | Technology                              |
|------------|-----------------------------------------|
| Backend    | Python 3.10+, Django 4.2+               |
| Database   | SQLite (development)                    |
| Frontend   | HTML5, CSS3, Vanilla JavaScript         |
| Charts     | Chart.js 4.4 (CDN)                      |
| Fonts      | Google Fonts (DM Sans, Space Grotesk)   |
| Analysis   | NumPy (BFS flood-fill PPI algorithm)    |

---

## CSV Data Format

Files named: `<user_id_hash>_<YYYYMMDD>.csv`  
Example: `1c0fd777_20251011.csv`

- No header row
- Each **frame** = 32 consecutive rows × 32 comma-separated values
- Values: 0–4095 (0 = no pressure, 4095 = saturation)
- Frames are assigned timestamps starting at midnight on the file date,
  spaced 5 seconds apart

---

## Configuration (settings.py)

```python
PRESSURE_ALERT_THRESHOLD = 500   # Alert trigger level (0-4095)
CONTACT_THRESHOLD        = 50    # Min value to count as contact pixel
MIN_REGION_PIXELS        = 10    # Min connected pixels for PPI calc
```
