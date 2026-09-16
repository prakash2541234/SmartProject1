import django
import sys
from pathlib import Path
sys.path.append(str(Path('django').resolve()))
print('PATHS', sys.path[-3:])
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stl.settings')
django.setup()
from apis.moniter.azure.models import RequestPayload, APILog
print('RequestPayload count', RequestPayload.objects.count())
for obj in RequestPayload.objects.order_by('-updated_at')[:5]:
    print(obj.request_id, obj.status, obj.error_message)
print('\nAPILog count', APILog.objects.count())
for log in APILog.objects.order_by('-created_at')[:5]:
    print(log.request_id, log.status, log.message, log.generated_password)
