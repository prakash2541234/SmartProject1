import json
import os
import uuid
from datetime import datetime

import azure.functions as func
from azure.data.tables import TableServiceClient


def validate_payload_fields(payload: dict) -> list:
    required_fields = {
        "stla_parameters": [
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
        ],
        "subscription_access": ["manager", "standard", "view"],
        "az_parameters": {
            "azure_region": None,
            "network_domain": None,
            "network_model": None,
            "network_config": [
                "vnet_name",
                "vnet",
                "region",
                "network_domain",
                "subnets",
            ],
            "backup_config": [
                "backup_enabled",
                "backup_replication_config",
                "replication_region",
            ],
            "sp_config": ["sp_requested", "sp_owners"],
        },
        "request_parameters": {
            "requester": ["first_name", "last_name", "user_id"],
            "ritm_number": None,
            "catalog_task_sysid": None,
        },
    }

    missing_fields = []

    def is_empty(value):
        return value is None or value == "" or value == [] or value == {}

    def is_enabled(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1", "y"}
        return bool(value)

    def check_fields(data, fields, parent_key=""):
        if not isinstance(data, dict):
            missing_fields.append(parent_key.rstrip("."))
            return

        if isinstance(fields, dict):
            for key, subfields in fields.items():
                if key not in data:
                    missing_fields.append(f"{parent_key}{key}")
                    continue

                value = data.get(key)

                if subfields is None:
                    if is_empty(value):
                        missing_fields.append(f"{parent_key}{key}")
                    continue

                if key == "network_config":
                    if not isinstance(value, list) or not value:
                        missing_fields.append(f"{parent_key}{key}")
                        continue

                    for index, item in enumerate(value):
                        if not isinstance(item, dict):
                            missing_fields.append(f"{parent_key}{key}[{index}]")
                            continue

                        for field in subfields:
                            if field not in item or is_empty(item.get(field)):
                                missing_fields.append(
                                    f"{parent_key}{key}[{index}].{field}"
                                )
                    continue

                if key == "sp_config":
                    if not isinstance(value, dict):
                        missing_fields.append(f"{parent_key}{key}")
                        continue

                    requested = value.get("sp_requested")
                    if is_empty(requested):
                        missing_fields.append(f"{parent_key}{key}.sp_requested")
                        continue

                    if not is_enabled(requested):
                        continue

                    if "sp_owners" not in value or is_empty(value.get("sp_owners")):
                        missing_fields.append(f"{parent_key}{key}.sp_owners")
                    continue

                check_fields(value, subfields, f"{parent_key}{key}.")

        elif isinstance(fields, list):
            if isinstance(data, list):
                for index, item in enumerate(data):
                    if isinstance(item, dict):
                        for field in fields:
                            if field not in item or is_empty(item.get(field)):
                                missing_fields.append(f"{parent_key}[{index}].{field}")
                    else:
                        missing_fields.append(f"{parent_key}[{index}]")
            elif isinstance(data, dict):
                for field in fields:
                    if field not in data or is_empty(data.get(field)):
                        missing_fields.append(f"{parent_key}{field}")
            else:
                for field in fields:
                    missing_fields.append(f"{parent_key}{field}")

    check_fields(payload, required_fields)
    return missing_fields


def insert_into_table_storage(
    application_name: str,
    payload_json: str,
    status: str,
    missing_fields: list,
) -> None:
    connection_string = os.getenv("TABLE_STORAGE_CONNECTION_STRING","")
    table_name = os.getenv("TABLE_STORAGE_TABLE_NAME", "subscriptioncreation")

    if not connection_string:
        raise ValueError("TABLE_STORAGE_CONNECTION_STRING is not configured")

    service_client = TableServiceClient.from_connection_string(connection_string)
    try:
        service_client.create_table_if_not_exists(table_name=table_name)
    except TypeError:
        try:
            service_client.create_table_if_not_exists(table_name)
        except AttributeError:
            try:
                service_client.create_table(table_name=table_name)
            except TypeError:
                service_client.create_table(table_name)

    table_client = service_client.get_table_client(table_name=table_name)

    entity = {
        "PartitionKey": application_name or "UNKNOWN",
        "RowKey": str(uuid.uuid4()),
        "application_name": application_name or "",
        "payload": payload_json,
        "status": status,
        "missing_fields": json.dumps(missing_fields),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    table_client.create_entity(entity=entity)


def main(req: func.HttpRequest) -> func.HttpResponse:
    raw_body = req.get_body().decode("utf-8", errors="replace")

    try:
        payload = req.get_json()
    except ValueError:
        try:
            insert_into_table_storage(
                application_name="INVALID_JSON",
                payload_json=raw_body,
                status="FAILED",
                missing_fields=["Invalid JSON"],
            )
        except Exception as storage_error:
            return func.HttpResponse(
                json.dumps({"error": f"Storage failure: {storage_error}"}),
                status_code=500,
                mimetype="application/json",
            )

        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    missing_fields = validate_payload_fields(payload)
    application_name = (
        payload.get("stla_parameters", {}).get("application_name", "UNKNOWN")
        if isinstance(payload, dict)
        else "UNKNOWN"
    )
    status = "VALID" if not missing_fields else "FAILED"

    try:
        insert_into_table_storage(
            application_name=application_name,
            payload_json=json.dumps(payload),
            status=status,
            missing_fields=missing_fields,
        )
    except Exception as storage_error:
        return func.HttpResponse(
            json.dumps({"error": f"Storage failure: {storage_error}"}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps(
            {
                "valid": not missing_fields,
                "missing_fields": missing_fields,
            }
        ),
        status_code=200,
        mimetype="application/json",
    )
