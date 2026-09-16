import urllib.request
import json

endpoints = [
    ('HEALTH', 'http://localhost:8000/api/moniter/react/health/'),
    ('MESSAGES', 'http://localhost:8000/api/moniter/react/messages/'),
]

for name, url in endpoints:
    print('\n--- %s ---' % name)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            body = resp.read().decode('utf-8')
            print('Status:', status)
            try:
                parsed = json.loads(body)
                print(json.dumps(parsed, indent=2))
            except Exception:
                print(body)
    except Exception as e:
        print('ERROR:', e)
