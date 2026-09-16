#!/bin/bash
set -e

# Detect app directory (supports Oryx APP_PATH, /home/site/wwwroot, /tmp extraction paths, and nested /UI)
APP_DIR=""
CANDIDATE_DIRS=()

if [ -n "$APP_PATH" ]; then
	CANDIDATE_DIRS+=("$APP_PATH" "$APP_PATH/UI")
fi

CANDIDATE_DIRS+=("/home/site/wwwroot" "/home/site/wwwroot/UI" "/tmp/8d*" "/tmp/*" "/tmp/*/UI")

for dir in "${CANDIDATE_DIRS[@]}"; do
	for resolved in $dir; do
		if [ -f "$resolved/manage.py" ]; then
			APP_DIR="$resolved"
			break 2
		fi
		if [ -d "$resolved" ]; then
			FOUND_MANAGE=$(find "$resolved" -maxdepth 3 -type f -name "manage.py" 2>/dev/null | head -n 1)
			if [ -n "$FOUND_MANAGE" ]; then
				APP_DIR=$(dirname "$FOUND_MANAGE")
				break 2
			fi
		fi
	done
done

if [ -z "$APP_DIR" ]; then
	echo "Error: manage.py not found in expected locations."
	echo "Checked: ${CANDIDATE_DIRS[*]}"
	echo "Current working directory: $(pwd)"
	echo "Top-level files in /home/site/wwwroot:"
	ls -la /home/site/wwwroot 2>/dev/null || true
	exit 1
fi

# Navigate to app directory
cd "$APP_DIR"
echo "Starting app from: $APP_DIR"

# Detect Django WSGI module
WSGI_MODULE=""

if [ -f "$APP_DIR/manage.py" ]; then
	SETTINGS_MODULE=$(grep -oE "DJANGO_SETTINGS_MODULE', '[^']+|DJANGO_SETTINGS_MODULE\", \"[^\"]+" "$APP_DIR/manage.py" 2>/dev/null | head -n 1 | sed -E "s/.*['\"]([^'\"]+)['\"].*/\1/")
	if [ -n "$SETTINGS_MODULE" ]; then
		PROJECT_PACKAGE="${SETTINGS_MODULE%.settings}"
		if [ -f "$APP_DIR/$PROJECT_PACKAGE/wsgi.py" ]; then
			WSGI_MODULE="$PROJECT_PACKAGE.wsgi:application"
		fi
	fi
fi

if [ -z "$WSGI_MODULE" ]; then
	FOUND_WSGI=$(find "$APP_DIR" -maxdepth 3 -type f -name "wsgi.py" 2>/dev/null | head -n 1)
	if [ -n "$FOUND_WSGI" ]; then
		REL_WSGI=${FOUND_WSGI#"$APP_DIR"/}
		WSGI_MODULE="${REL_WSGI%.py}"
		WSGI_MODULE="${WSGI_MODULE//\//.}:application"
	fi
fi

if [ -z "$WSGI_MODULE" ]; then
	echo "Error: Could not determine WSGI module from $APP_DIR"
	find "$APP_DIR" -maxdepth 3 -type f -name "wsgi.py" 2>/dev/null || true
	exit 1
fi

echo "Using WSGI module: $WSGI_MODULE"

# Start Gunicorn server
export PYTHONPATH="$APP_DIR:$PYTHONPATH"
PORT="${PORT:-8000}"
exec gunicorn --chdir "$APP_DIR" --bind "0.0.0.0:${PORT}" --timeout 600 --workers "${GUNICORN_WORKERS:-2}" --access-logfile - --error-logfile - "$WSGI_MODULE"
