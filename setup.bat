@echo off
REM ╔══════════════════════════════════════╗
REM ║  Graphene Trace — Windows Setup     ║
REM ║  Usage: Double-click or run cmd     ║
REM ╚══════════════════════════════════════╝
cd /d "%~dp0"
echo.
echo ============================================
echo   Graphene Trace Django Setup (Windows)
echo ============================================
echo.

REM 1. Create venv
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM 2. Install deps
echo Installing Django and numpy...
venv\Scripts\pip install --quiet --upgrade pip
venv\Scripts\pip install --quiet "Django>=4.2" numpy

REM 3. Copy data if present
if exist "..\GTLB-Data__1_.zip" (
    echo Copying CSV data...
    copy "..\GTLB-Data__1_.zip" ".\GTLB-Data.zip"
)

REM 4. Migrate
echo Running migrations...
venv\Scripts\python manage.py migrate --run-syncdb

REM 5. Create admin
echo Creating admin user...
venv\Scripts\python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); U.objects.filter(username='admin').exists() or U.objects.create_superuser('admin','admin@graphenetrace.com','admin123',role='admin')"

REM 6. Seed data
echo Loading sample data...
venv\Scripts\python manage.py seed_data

echo.
echo ============================================
echo  Setup complete!
echo.
echo  Run:  venv\Scripts\activate
echo        python manage.py runserver
echo.
echo  Open: http://127.0.0.1:8000
echo  Admin: admin / admin123
echo ============================================
pause
