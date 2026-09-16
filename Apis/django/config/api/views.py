from django.shortcuts import render

# Create your views here.
# api/views.py

from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import RequestTracker
import requests

@api_view(['POST'])
def create_keyvault(request):
    uuid = request.data.get("uuid")

    tracker = RequestTracker.objects.create(
        uuid=uuid,
        status="IN_PROGRESS",
        logs="Started\n"
    )

    try:
        apim_url = f"https://apimanagement-1.azure-api.net/keyvault/create-keyvault/{request.data['subscriptionId']}/{request.data['rg']}/{request.data['vaultName']}"

        body = {
            "location": request.data["location"],
            "properties": {
                "tenantId": "YOUR-TENANT-ID",
                "sku": {
                    "family": "A",
                    "name": "standard"
                },
                "accessPolicies": []
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": "YOUR_KEY"
        }

        response = requests.post(apim_url, json=body, headers=headers)

        tracker.logs += "APIM called\n"

        if response.status_code in [200, 201, 202]:
            tracker.status = "SUCCESS"
            tracker.logs += "KeyVault created\n"
        else:
            tracker.status = "FAILED"
            tracker.logs += response.text

    except Exception as e:
        tracker.status = "FAILED"
        tracker.logs += str(e)

    tracker.save()

    return Response({"uuid": uuid, "status": tracker.status})

@api_view(['GET'])
def get_status(request, uuid):
    tracker = RequestTracker.objects.get(uuid=uuid)
    return Response({"uuid": uuid, "status": tracker.status})

@api_view(['GET'])
def get_logs(request, uuid):
    tracker = RequestTracker.objects.get(uuid=uuid)
    return Response({"uuid": uuid, "logs": tracker.logs})