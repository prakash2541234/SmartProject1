import os
import json
import random
import re
import logging
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def getenv(environment):
    """Convert environment to standardized short form"""
    env_mapping = {
        "production": "prod",
        "prod": "prod",
        "non-production": "np",
        "nonproduction": "np",
        "non-prod": "np",
        "nonprod": "np",
        "np": "np",
        "development": "np",
        "dev": "np",
        "testing": "np",
        "test": "np",
        "staging": "np",
        "stage": "np",
    }
    return env_mapping.get(environment.lower(), "prod")


def get_clean_app_id(appid):
    """Convert application id to a short clean form"""
    appid = appid.lower()
    appid = re.sub(r"[^a-z0-9]", "", appid)
    return appid


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Key Vault name generator API triggered.")

    try:
        # Parse request
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON body"}),
                status_code=400,
                mimetype="application/json",
            )

        required_fields = ["subscription_id", "appid", "environment", "region"]
        missing_fields = [field for field in required_fields if not req_body.get(field)]

        if missing_fields:
            return func.HttpResponse(
                json.dumps(
                    {"error": f"Missing required fields: {', '.join(missing_fields)}"}
                ),
                status_code=400,
                mimetype="application/json",
            )

        # Extract inputs
        sub_id = req_body["subscription_id"]
        region = req_body["region"].strip()
        appid = get_clean_app_id(req_body["appid"])
        env = getenv(req_body["environment"])

        # Generate names
        random_num = random.randint(100, 999)
        kv_name = f"kv-{appid}-{env}-{random_num}"
        rg_name = f"rg-{appid}-keyvaults"

        # Mock tenant (since we are NOT calling Azure)
        tenant_id = os.environ.get("ShiftupTenantId", "mock-tenant-id")

        # Success response (same structure as original)
        response_payload = {
            "status": "success",
            "message": f"Key Vault name {kv_name} generated successfully",
            "details": {
                "keyvault_name": kv_name,
                "resource_group": rg_name,
                "region": region,
                "subscription_id": sub_id,
                "tenant_id": tenant_id,
                "vault_uri": f"https://{kv_name}.vault.azure.net/"
            },
        }

        return func.HttpResponse(
            json.dumps(response_payload, indent=4),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "error",
                    "message": "Failed to generate Key Vault name",
                    "details": {"detailed_error": str(e)},
                }
            ),
            status_code=500,
            mimetype="application/json",
        )