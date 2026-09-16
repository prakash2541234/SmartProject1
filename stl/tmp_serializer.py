import sys
from pathlib import Path
sys.path.append(str(Path('django').resolve()))
from apis.moniter.serializers import CreateUserSerializer
payload = {
  'displayName': 'name',
  'userPrincipalName': 'name@churaprakash2541gmail.onmicrosoft.com',
  'mailNickname': 'name',
  'forceChangePasswordNextSignIn': True,
  'accountEnabled': True,
  'tenantId': '',
  'dryRun': False,
}
serializer = CreateUserSerializer(data=payload)
print('valid', serializer.is_valid())
print('errors', serializer.errors)
