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
    "application_name",
]

REQUIRED_AZ_FIELDS = [
    "network_model",
    "azure_region",
    "network_domain",
]


def validate_process_create_sub_payload(request_payload: dict) -> None:
    if not isinstance(request_payload, dict):
        raise ValueError("Payload must be a JSON object")

    if "stla_parameters" not in request_payload:
        raise ValueError("Missing 'stla_parameters'")

    if "az_parameters" not in request_payload:
        raise ValueError("Missing 'az_parameters'")

    stla_params = request_payload.get("stla_parameters", {})
    az_params = request_payload.get("az_parameters", {})

    if not isinstance(stla_params, dict):
        raise ValueError("'stla_parameters' must be an object")

    if not isinstance(az_params, dict):
        raise ValueError("'az_parameters' must be an object")

    missing_stla = [field for field in REQUIRED_STLA_FIELDS if not stla_params.get(field)]
    if missing_stla:
        raise ValueError(f"Missing required stla_parameters fields: {missing_stla}")

    missing_az = [field for field in REQUIRED_AZ_FIELDS if not az_params.get(field)]
    if missing_az:
        raise ValueError(f"Missing required az_parameters fields: {missing_az}")
