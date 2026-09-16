import json
import re
import random
import string
import logging
import azure.functions as func


def get_clean_app_id(appid: str) -> str:
    appid = appid.lower()
    appid = re.sub(r'[^a-z0-9\-]', '', appid)
    return appid


def generate_sp_name(application_id: str, environment: str) -> str:
    clean_app_id = get_clean_app_id(application_id)

    random_suffix = ''.join(
        random.choices(string.ascii_lowercase + string.digits, k=5)
    )

    return f"sp-azf-{clean_app_id}-{environment}-{random_suffix}"


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("SP Name generation triggered")

    try:
        body = req.get_json()

        # -------------------------------
        # SP PARAMETERS VALIDATION
        # -------------------------------
        sp_params = body.get("sp_parameters", {})
        application_id = sp_params.get("application_id")
        environment = sp_params.get("environment")
        subscription_id = sp_params.get("subscription_id")

        if not application_id or not environment or not subscription_id:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "application_id, environment, and subscription_id are required",
                    "details": {}
                }),
                status_code=400
            )

        # -------------------------------
        # REQUEST PARAMETERS VALIDATION
        # -------------------------------
        request_params = body.get("request_parameters", {})
        sp_owners = request_params.get("sp_owners")

        logging.info(f"Raw sp_owners: {sp_owners}, Type: {type(sp_owners)}")

        # 🔥 FIX: Handle string → list conversion
        if isinstance(sp_owners, str):
            try:
                sp_owners = json.loads(sp_owners)
                logging.info("Converted sp_owners string to list")
            except Exception as e:
                logging.error(f"Failed to parse sp_owners string: {e}")
                sp_owners = None

        # Final validation
        if (
            not sp_owners or
            not isinstance(sp_owners, list) or
            not all(isinstance(owner, str) for owner in sp_owners)
        ):
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "sp_owners is required and must be a list of strings",
                    "details": {
                        "received_type": str(type(sp_owners)),
                        "received_value": sp_owners
                    }
                }),
                status_code=400
            )

        # -------------------------------
        # GENERATE SP NAME
        # -------------------------------
        sp_name = generate_sp_name(application_id, environment)

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": "Service principal name generated successfully",
                "details": {
                    "sp_name": sp_name,
                    "application_id": application_id,
                    "environment": environment,
                    "subscription_id": subscription_id,
                    "sp_owners": sp_owners
                }
            }),
            status_code=200
        )

    except ValueError:
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": "Invalid JSON payload",
                "details": {}
            }),
            status_code=400
        )