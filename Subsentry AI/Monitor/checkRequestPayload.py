import azure.functions as func
import logging
import json
from typing import Any, Dict, List


# =========================
# VALIDATION HELPERS
# =========================

REQUIRED_TOP_LEVEL_KEYS = (
    "stla_parameters",
    "subscription_access",
    "az_parameters",
    "request_parameters",
)

REQUIRED_STLA_KEYS = (
    "application_id",
    "hle_usd",
    "support_email",
    "environment",
    "stla_global_business",
    "stla_global_subfunction",
    "sensitivity",
    "multi_tenant",
    "stla_region",
    "application_source",
    "application_name",
)

REQUIRED_SUBSCRIPTION_ACCESS_KEYS = ("manager", "standard", "view")
REQUIRED_NETWORK_CONFIG_KEYS = ("vnet", "region", "network_domain", "subnets")
REQUIRED_SUBNET_KEYS = ("fe", "be", "GatewaySubnet")
REQUIRED_REQUESTER_KEYS = ("first_name", "last_name", "user_id")


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _require_mapping(parent: Dict[str, Any], key: str, errors: List[str]) -> Dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"'{key}' must be an object.")
        return {}
    return value


def _require_list(parent: Dict[str, Any], key: str, errors: List[str]) -> List[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        errors.append(f"'{key}' must be an array.")
        return []
    return value


def _require_string(parent: Dict[str, Any], key: str, errors: List[str]) -> None:
    value = parent.get(key)
    if not _is_non_empty_string(value):
        errors.append(f"'{key}' is required and must be a non-empty string.")


# 🔥 Auto-convert string → bool
def _require_bool(parent: Dict[str, Any], key: str, errors: List[str]) -> bool:
    value = parent.get(key)

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        if value.lower() == "true":
            parent[key] = True
            return True
        elif value.lower() == "false":
            parent[key] = False
            return False

    errors.append(f"'{key}' must be a boolean (true/false).")
    return False


def _validate_required_strings(parent: Dict[str, Any], keys: tuple[str, ...], errors: List[str]) -> None:
    for key in keys:
        _require_string(parent, key, errors)


# =========================
# MAIN VALIDATION FUNCTION
# =========================

def validate_process_create_sub_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Request payload must be a JSON object.")

    errors: List[str] = []

    # Top-level check
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in payload:
            errors.append(f"Missing top-level object: '{key}'.")

    stla = _require_mapping(payload, "stla_parameters", errors)
    access = _require_mapping(payload, "subscription_access", errors)
    az = _require_mapping(payload, "az_parameters", errors)
    req = _require_mapping(payload, "request_parameters", errors)

    # STLA
    if stla:
        _validate_required_strings(stla, REQUIRED_STLA_KEYS, errors)
        _require_bool(stla, "multi_tenant", errors)

    # Subscription Access
    if access:
        _validate_required_strings(access, REQUIRED_SUBSCRIPTION_ACCESS_KEYS, errors)

    # Azure Parameters
    if az:
        _validate_required_strings(az, ("azure_region", "network_domain", "network_model"), errors)

        # Network Config
        network_config = _require_list(az, "network_config", errors)
        if not network_config:
            errors.append("'network_config' must contain at least one item.")
        else:
            for i, item in enumerate(network_config):
                if not isinstance(item, dict):
                    errors.append(f"'network_config[{i}]' must be an object.")
                    continue

                _validate_required_strings(item, REQUIRED_NETWORK_CONFIG_KEYS[:-1], errors)

                subnets = _require_mapping(item, "subnets", errors)
                if subnets:
                    _validate_required_strings(subnets, REQUIRED_SUBNET_KEYS, errors)

        # Backup Config
        backup = _require_mapping(az, "backup_config", errors)
        if backup:
            if _require_bool(backup, "backup_enabled", errors):
                _validate_required_strings(
                    backup,
                    ("backup_replication_config", "replication_region"),
                    errors,
                )

        # SP Config
        sp = _require_mapping(az, "sp_config", errors)
        if sp:
            if _require_bool(sp, "sp_requested", errors):
                owners = sp.get("sp_owners")
                if not isinstance(owners, list) or not owners:
                    errors.append("'sp_owners' must be a non-empty list.")
                else:
                    for i, owner in enumerate(owners):
                        if not _is_non_empty_string(owner):
                            errors.append(f"'sp_owners[{i}]' must be a valid string.")

    # Request Parameters
    if req:
        _validate_required_strings(req, ("ritm_number", "catalog_task_sysid"), errors)

        requester = _require_mapping(req, "requester", errors)
        if requester:
            _validate_required_strings(requester, REQUIRED_REQUESTER_KEYS, errors)

    # Final error handling
    if errors:
        raise ValueError("Payload validation failed: " + "; ".join(errors))

    return payload


# =========================
# AZURE FUNCTION ENTRY POINT
# =========================

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing subscription payload validation request...")

    try:
        payload = req.get_json()

        logging.info("Incoming payload:")
        logging.info(json.dumps(payload))

        validated_payload = validate_process_create_sub_payload(payload)

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": "Payload validation successful",
                "data": validated_payload
            }),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError as ve:
        logging.error(f"Validation failed: {str(ve)}")

        return func.HttpResponse(
            json.dumps({
                "message": "Payload validation failed.",
                "error_details": str(ve)
            }),
            status_code=400,
            mimetype="application/json"
        )

    except Exception as e:
        logging.exception("Unexpected error occurred")

        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": "Internal server error",
                "details": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )