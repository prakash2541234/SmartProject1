"""This function is triggered by an HTTP request and returns
only the subscription name based on the input payload."""

import logging
import json
import random
import re
import azure.functions as func

REQUIRED_STLA_FIELDS = [
    "application_id",
    "environment",
    "sensitivity",
    "hle_usd",
    "support_email",
    "stla_global_business",
    "stla_global_subfunction",
    "multi_tenant",
    "application_source",
    "application_name"
]

REQUIRED_AZ_FIELDS = [
    "network_model",
    "azure_region",
    "network_domain"
]


def main(req: func.HttpRequest) -> func.HttpResponse:
    """Process payload and return only subscription name"""

    logging.info('Processing subscription name request.')

    try:
        request_payload = req.get_json()

        if "stla_parameters" not in request_payload:
            raise ValueError("Missing 'stla_parameters'")
        if "az_parameters" not in request_payload:
            raise ValueError("Missing 'az_parameters'")

        stla_params = request_payload.get("stla_parameters", {})
        az_params = request_payload.get("az_parameters", {})

        missing_stla = [f for f in REQUIRED_STLA_FIELDS if not stla_params.get(f)]
        if missing_stla:
            raise ValueError(f"Missing required stla_parameters fields: {missing_stla}")

        missing_az = [f for f in REQUIRED_AZ_FIELDS if not az_params.get(f)]
        if missing_az:
            raise ValueError(f"Missing required az_parameters fields: {missing_az}")

        app_id = stla_params.get("application_id")
        environment = stla_params.get("environment")
        sensitivity_tag = stla_params.get("sensitivity")

        subscription_name = f"sub-{get_application_id(app_id)}-{environment}-{get_sensitivity(sensitivity_tag)}-{random.randint(100, 999)}"

        return func.HttpResponse(
            body=json.dumps({"subscription_name": subscription_name}),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError as ve:
        logging.error(f"Validation Error: {str(ve)}")
        return func.HttpResponse(
            body=json.dumps({"error": str(ve)}),
            status_code=400,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error('Unexpected error occurred.', exc_info=True)
        return func.HttpResponse(
            body=json.dumps({
                "error": "Internal server error",
                "details": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )


def get_application_id(app_id):
    """Convert application id to short form"""
    app_id = app_id.lower()
    app_id = re.sub(r'[^a-z0-9]', '', app_id)
    return app_id


def get_sensitivity(sensitivity_tag):
    """Convert sensitivity tag to short form"""
    switch = {
        'standard': "std",
        'sensitive': "S3",
        'highly sensitive': "S4",
        'highlysensitive': "S4",
        'highly_sensitive': "S4",
        'highly-sensitive': "S4",
    }

    sensitivity = switch.get(sensitivity_tag.lower())

    if sensitivity is None:
        raise ValueError(f"Invalid sensitivity tag '{sensitivity_tag}'")

    return sensitivity