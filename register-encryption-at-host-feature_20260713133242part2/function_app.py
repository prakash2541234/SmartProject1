import azure.functions as func
import logging
import json
import os
from azure.identity import DefaultAzureCredential
import requests

app = func.FunctionApp()

@app.route(route="registerEncryptionAtHost", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def register_encryption_at_host(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Processing EncryptionAtHost registration request.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )

    subscription_id = req_body.get('subscriptionId')
    if not subscription_id:
        return func.HttpResponse(
            json.dumps({"error": "subscriptionId is required"}),
            status_code=400,
            mimetype="application/json"
        )

    try:
        credential = DefaultAzureCredential()
        token = credential.get_token("https://management.azure.com/.default").token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Register Microsoft.Compute provider if not already registered
        provider_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Compute?api-version=2021-04-01"
        provider_response = requests.post(f"{provider_url}/register", headers=headers)
        if provider_response.status_code not in [200, 201]:
            logging.error(f"Provider registration failed: {provider_response.text}")
            return func.HttpResponse(
                json.dumps({"error": "Failed to register Microsoft.Compute provider", "details": provider_response.text}),
                status_code=provider_response.status_code,
                mimetype="application/json"
            )

        # Register EncryptionAtHost feature
        feature_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Features/providers/Microsoft.Compute/features/EncryptionAtHost/register?api-version=2021-07-01"
        feature_response = requests.post(feature_url, headers=headers)

        if feature_response.status_code == 201:
            logging.info(f"Successfully registered EncryptionAtHost for subscription {subscription_id}")
            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "EncryptionAtHost feature registered successfully",
                    "subscriptionId": subscription_id,
                    "response": feature_response.json()
                }),
                status_code=201,
                mimetype="application/json"
            )
        else:
            logging.error(f"Feature registration failed: {feature_response.text}")
            return func.HttpResponse(
                json.dumps({"error": "Failed to register EncryptionAtHost feature", "details": feature_response.text}),
                status_code=feature_response.status_code,
                mimetype="application/json"
            )

    except Exception as e:
        logging.exception("Unexpected error during registration")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )