#!/bin/bash
set -e

# Detect app directory (supports Oryx APP_PATH, /home/site/wwwroot, and nested /UI)
APP_DIR=""
CANDIDATE_DIRS=()

if [ -n "$APP_PATH" ]; then
	CANDIDATE_DIRS+=("$APP_PATH" "$APP_PATH/UI")
fi

CANDIDATE_DIRS+=("/home/site/wwwroot" "/home/site/wwwroot/UI")

for dir in "${CANDIDATE_DIRS[@]}"; do
	if [ -f "$dir/manage.py" ]; then
		APP_DIR="$dir"
		break
	fi
done

if [ -z "$APP_DIR" ]; then
	echo "Error: manage.py not found in expected locations."
	echo "Checked: ${CANDIDATE_DIRS[*]}"
	exit 1
fi

# Navigate to app directory
cd "$APP_DIR"
echo "Starting app from: $APP_DIR"

# Install dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Start Gunicorn server
export PYTHONPATH="$APP_DIR:$PYTHONPATH"
gunicorn --chdir "$APP_DIR" --bind 0.0.0.0:8000 --timeout 600 --workers 4 UI.wsgi:application
