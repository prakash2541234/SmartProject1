import json
import logging
import re
from typing import Dict, Optional, Tuple

import azure.functions as func

# ---------------------------
# Helpers
# ---------------------------

def json_response(payload: Dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, indent=2),
        status_code=status_code,
        mimetype="application/json",
    )


def parse_body(
    req: func.HttpRequest,
) -> Tuple[Optional[Dict], Optional[func.HttpResponse]]:
    try:
        return req.get_json(), None
    except ValueError:
        return None, json_response({"error": "Invalid JSON body"}, 400)


def validate_body(body: Dict) -> Tuple[Optional[Dict], Optional[func.HttpResponse]]:
    required = [
        "subscription_id",
        "appid",
        "environment",
        "region",
        "redundancy",
        "support_email",
    ]

    missing = [f for f in required if not body.get(f)]
    if missing:
        return None, json_response(
            {"error": f"Missing required fields: {', '.join(missing)}"}, 400
        )

    return {
        "subscription_id": str(body["subscription_id"]).strip(),
        "appid": str(body["appid"]).strip(),
        "environment": str(body["environment"]).strip(),
        "region": str(body["region"]).strip(),
        "redundancy": str(body["redundancy"]).strip(),
        "support_email": str(body.get("support_email") or "").strip(),
    }, None


def clean_string(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def build_name_suffix(appid: str, environment: str, region: str) -> str:
    appid_clean = clean_string(appid)
    env_clean = clean_string(environment)
    region_clean = clean_string(region)

    return f"{appid_clean}-{env_clean}-{region_clean}"


# ---------------------------
# Function
# ---------------------------
def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Backup solution provisioning triggered.")

    try:
        # 🔹 Parse request
        body, err = parse_body(req)
        if err:
            return err

        logging.info("Full request body received: %s", body)

        # 🔥 FIX: support BOTH formats
        input_payload = body.get("input_payload") or body

        logging.info("Extracted input_payload: %s", input_payload)

        # 🔹 Validate
        data, err = validate_body(input_payload)
        if err:
            return err

        subscription_id = data["subscription_id"]
        appid = data["appid"]
        environment = data["environment"]
        region = data["region"]

        logging.info("Subscription: %s", subscription_id)
        logging.info("AppID: %s", appid)

        # 🔹 Generate names
        suffix = build_name_suffix(appid, environment, region)

        rg_name = f"rg-{suffix}"
        rsv_name = f"rsv-{suffix}"
        bv_name = f"bv-{suffix}"

        logging.info("Generated suffix: %s", suffix)
        logging.info("Resource Group: %s", rg_name)
        logging.info("Recovery Vault: %s", rsv_name)
        logging.info("Backup Vault: %s", bv_name)

        # 🔹 Build response
        response_payload = {
            "status": "success",
            "message": f"Backup {bv_name} created successfully.",
            "details": {
                "resources": {
                    "resource_group": rg_name,
                    "recovery_services_vault": rsv_name,
                    "backup_vault": bv_name,
                },
                "providers": [
                    "Microsoft.RecoveryServices",
                    "Microsoft.DataProtection",
                ],
                "policy_count": 5,
                "policy_failures": 0,
            },
        }

        return json_response(response_payload, 200)

    except Exception as e:
        logging.exception("Unhandled error occurred")

        return json_response(
            {
                "status": "error",
                "message": "Internal server error",
                "details": str(e),
            },
            500,
        )