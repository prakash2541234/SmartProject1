# Minimal Django Hello World - Azure App Service Deployment

This project is configured to deploy as a minimal Django app that returns:

Hello, World!

## Current Setup

- Root route is defined in `UI/urls.py` and mapped to `App.views.hello`.
- Response is returned from `App/views.py`.
- App startup is handled by `startup.sh` using Gunicorn.
- Runtime is pinned in `runtime.txt`.
- Dependencies are listed in `requirements.txt`.

## Required Azure App Service Settings

Add these in Azure Portal → App Service → Configuration → Application settings:

- `DJANGO_SECRET_KEY` = a strong random secret
- `DJANGO_DEBUG` = `false`

Optional:

- `DJANGO_ALLOWED_HOSTS` = `yourdomain.com,.azurewebsites.net`

Notes:

- `WEBSITE_HOSTNAME` is provided by Azure automatically.
- HTTPS redirect is enabled automatically when `DJANGO_DEBUG=false`.

## Startup Command

In Azure App Service, set Startup Command to:

`bash startup.sh`

## Deployment Steps

1. Push the repository to GitHub.
2. In Azure App Service, open Deployment Center.
3. Connect your GitHub repo/branch.
4. Save and trigger deployment.
5. Confirm logs show Gunicorn started successfully.

## Quick Local Validation

Use these commands from project root:

```powershell
.\venv\Scripts\Activate.ps1
python manage.py check
python manage.py shell -c "from django.test import Client; r=Client().get('/', secure=True); print(r.status_code); print(r.content.decode())"
```

Expected output includes:

- `200`
- `Hello, World!`

## Troubleshooting

- If deployment fails to boot, check App Service Log Stream.
- If you see host errors, set `DJANGO_ALLOWED_HOSTS` with your hostname.
- If you see 301 redirects locally, that is expected when `DJANGO_DEBUG=false`.
