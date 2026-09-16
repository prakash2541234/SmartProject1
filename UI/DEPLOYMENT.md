# Django Azure App Service Deployment Guide

This Django project is now configured for Azure App Service deployment.

## Files Created/Modified for Production Readiness

✅ **requirements.txt** - Python dependencies  
✅ **web.config** - Azure IIS configuration  
✅ **.gitignore** - Git ignore rules  
✅ **runtime.txt** - Python version specification  
✅ **.env.example** - Environment variables template  
✅ **startup.sh** - Startup script for Azure  
✅ **settings.py** - Updated for production security  

## Pre-Deployment Checklist

### 1. Set Environment Variables in Azure Portal

In your Azure App Service Application Settings, add:

```
DEBUG = False
SECRET_KEY = <generate-a-new-secure-key>
ALLOWED_HOSTS = .azurewebsites.net,yourdomain.com
TOTAL_MONITORS = 7
MONITOR_1_NAME = Payload Verification
MONITOR_2_NAME = Subscription Creation
MONITOR_3_NAME = Service Principal Creation
MONITOR_4_NAME = Role Assignment
MONITOR_5_NAME = Virtual Network
MONITOR_6_NAME = KeyVault
MONITOR_7_NAME = Backup
```

**To generate a new SECRET_KEY:**
```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

### 2. Update Database (Important!)

Currently using SQLite, which is **NOT recommended for production**.

**Option A: Azure SQL Database**
```
DATABASE_URL = mssql://username:password@server.database.windows.net:1433/database_name
```

**Option B: PostgreSQL**
```
DATABASE_URL = postgresql://username:password@hostname:5432/dbname
```

**Option C: MySQL**
```
DATABASE_URL = mysql://username:password@hostname:3306/dbname
```

Then update `settings.py` to read DATABASE_URL:
```python
import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default='sqlite:///db.sqlite3'),
        conn_max_age=600
    )
}
```

### 3. Create a .env File Locally (Don't commit this!)

```
DEBUG=False
SECRET_KEY=your-generated-secret-key
ALLOWED_HOSTS=.azurewebsites.net,yourdomain.com
TOTAL_MONITORS=7
MONITOR_1_NAME=Payload Verification
MONITOR_2_NAME=Subscription Creation
MONITOR_3_NAME=Service Principal Creation
MONITOR_4_NAME=Role Assignment
MONITOR_5_NAME=Virtual Network
MONITOR_6_NAME=KeyVault
MONITOR_7_NAME=Backup
```

### 4. Test Locally Before Deployment

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Load environment variables
python -m decouple

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Test locally
python manage.py runserver
```

## Azure App Service Deployment Steps

### Via Azure CLI:

```bash
# Login to Azure
az login

# Create resource group
az group create --name myResourceGroup --location eastus

# Create App Service plan
az appservice plan create --name myAppServicePlan --resource-group myResourceGroup --sku B1 --is-linux

# Create web app
az webapp create --resource-group myResourceGroup --plan myAppServicePlan --name myDjangoApp --runtime "PYTHON|3.10"

# Deploy from local Git
cd c:\Users\TA25845\python\DeployDjango\UI
git init
git add .
git commit -m "Initial commit for Azure deployment"
az webapp up --name myDjangoApp --resource-group myResourceGroup --runtime "python:3.10"
```

### Via Azure Portal:

1. Create App Service → Select Python 3.10
2. Configure Startup Command: `bash startup.sh`
    - Alternative (direct Gunicorn with auto-detect):
    ```bash
    APP_DIR=/home/site/wwwroot; [ ! -f "$APP_DIR/manage.py" ] && [ -f "/home/site/wwwroot/UI/manage.py" ] && APP_DIR=/home/site/wwwroot/UI; gunicorn --chdir "$APP_DIR" --bind 0.0.0.0:8000 --timeout 600 --workers 4 UI.wsgi:application
    ```
3. Set Application Settings (environment variables)
4. Deploy code (git, zip, or git integration)

## Post-Deployment

1. Run migrations on Azure:
```bash
az webapp remote-build-from-url --resource-group myResourceGroup --name myDjangoApp --repo-url <your-git-repo>
```

2. Check logs:
```bash
az webapp log tail --resource-group myResourceGroup --name myDjangoApp
```

3. Collect static files on production (if needed):
```bash
az webapp ssh --resource-group myResourceGroup --name myDjangoApp
python manage.py collectstatic --noinput
```

## Important Security Notes

- ✅ DEBUG is set to False in production
- ✅ SECRET_KEY is read from environment variables
- ✅ ALLOWED_HOSTS is configurable
- ✅ HTTPS/SSL is enforced in production
- ✅ Security headers are set correctly
- ✅ WhiteNoise serves static files efficiently

## Troubleshooting

### Static Files Not Loading
- Run: `python manage.py collectstatic --noinput`
- Check STATIC_ROOT and STATIC_URL in settings.py
- Verify WhiteNoise middleware is installed
- `staticfiles/` is generated output from collectstatic; do not commit it to source control

### Database Errors
- Ensure DATABASE_URL is correctly set
- Run: `python manage.py migrate`
- Check database permissions

### Module Not Found Errors
- Ensure all packages in requirements.txt are installed
- Run: `pip install -r requirements.txt`

## Additional Resources

- [Django Deployment Checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/)
- [Azure App Service Django Documentation](https://docs.microsoft.com/en-us/azure/app-service/tutorial-python-postgresql-app)
- [Django WhiteNoise Documentation](http://whitenoise.evans.io/)

