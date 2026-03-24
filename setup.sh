#!/usr/bin/env bash
# ╔══════════════════════════════════════════╗
# ║  Graphene Trace — One-Command Setup      ║
# ║  Usage: bash setup.sh                    ║
# ╚══════════════════════════════════════════╝
set -e
cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     Graphene Trace Django Setup      ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 1. Create virtual environment
if [ ! -d "venv" ]; then
    echo "▶  Creating virtual environment..."
    python3 -m venv venv
    echo "   ✓ venv created"
else
    echo "   ~ venv already exists"
fi

# 2. Install dependencies
echo "▶  Installing dependencies (Django + numpy)..."
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet "Django>=4.2" numpy
echo "   ✓ Dependencies installed"

# 3. Copy CSV data if found next to this folder
PARENT="$(dirname "$(pwd)")"
for f in "$PARENT/GTLB-Data__1_.zip" "$PARENT/GTLB-Data.zip"; do
    if [ -f "$f" ]; then
        echo "▶  Copying $f..."
        cp "$f" "./GTLB-Data.zip"
        break
    fi
done
for d in "$PARENT/GTLB-Data"; do
    if [ -d "$d" ]; then
        echo "▶  Copying GTLB-Data folder..."
        cp -r "$d" .
        break
    fi
done

# 4. Run migrations
echo "▶  Running database migrations..."
venv/bin/python manage.py migrate --run-syncdb
echo "   ✓ Database ready"

# 5. Create admin superuser
echo "▶  Creating admin account (admin / admin123)..."
venv/bin/python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin','admin@graphenetrace.com','admin123', role='admin')
    print('   ✓ Admin created')
else:
    print('   ~ Admin already exists')
"

# 6. Seed sample data
echo "▶  Loading sample users and sensor data..."
venv/bin/python manage.py seed_data
echo ""

echo "╔══════════════════════════════════════╗"
echo "║  ✓ Setup complete!                   ║"
echo "║                                      ║"
echo "║  Start the server:                   ║"
echo "║    source venv/bin/activate          ║"
echo "║    python manage.py runserver        ║"
echo "║                                      ║"
echo "║  Then open:                          ║"
echo "║    http://127.0.0.1:8000             ║"
echo "║                                      ║"
echo "║  Admin: admin / admin123             ║"
echo "╚══════════════════════════════════════╝"
echo ""
