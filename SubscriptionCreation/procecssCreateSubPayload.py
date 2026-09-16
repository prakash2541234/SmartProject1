"""This function is triggered by an HTTP request and returns
the full subscription creation payload including name, management group, and tags."""

import logging
import json
import random
import re
from datetime import date
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
    """Process payload and return full subscription creation payload"""

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
        azure_region = az_params.get("azure_region")
        network_model = az_params.get("network_model")
        network_domain = az_params.get("network_domain")

        sensitivity_short = get_sensitivity(sensitivity_tag)
        subscription_name = f"sub-{get_application_id(app_id)}-{environment}-{sensitivity_short}-{random.randint(100, 999)}"
        subscription_mgmtgroup = get_mgmt_group(environment, sensitivity_short)

        response_payload = {
            "subscription_name": subscription_name,
            "subscription_mgmtgroup": subscription_mgmtgroup,
            "subscription_tags": {
                "stla_application_id": app_id,
                "stla_hle_usd": stla_params.get("hle_usd"),
                "stla_support_email": stla_params.get("support_email"),
                "stla_environment": environment,
                "stla_global_business": stla_params.get("stla_global_business"),
                "stla_global_subfunction": stla_params.get("stla_global_subfunction"),
                "stla_sensitivity": sensitivity_tag,
                "stla_multi_tenant": stla_params.get("multi_tenant"),
                "stla_purchase_date": date.today().isoformat(),
                "stla_region": azure_region,
                "stla_network_domain": network_domain,
                "stla_model_deployment": network_model,
                "stla_application_source": stla_params.get("application_source"),
                "stla_application_name": stla_params.get("application_name")
            }
        }

        return func.HttpResponse(
            body=json.dumps(response_payload),
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


def get_mgmt_group(environment, sensitivity_short):
    """Derive management group based on environment and sensitivity"""
    env = environment.lower()
    return f"mg-{env}-{sensitivity_short}"


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