import json
import azure.functions as func


def is_missing(value):
    return value is None or value == ""


def validate_backup(data: dict) -> dict:
    result = {
        "status": "success",
        "errors": [],
        "missing_fields": {},
        "details": {}
    }

    # 🔹 Extract output
    backup_status = data.get("backup_status")
    backup_message = data.get("backup_message")

    # 🔹 Extract input payload
    input_payload = data.get("input_payload", {})

    fields = {
        "subscription_id": input_payload.get("subscription_id"),
        "appid": input_payload.get("appid"),
        "environment": input_payload.get("environment"),
        "region": input_payload.get("region"),
        "redundancy": input_payload.get("redundancy"),
        "support_email": input_payload.get("support_email")
    }

    # 🔹 Validate backup output
    if is_missing(backup_status):
        result["status"] = "failed"
        result["errors"].append("backup_status is missing")

    elif backup_status != "success":
        result["status"] = "failed"
        result["errors"].append(f"Backup deployment failed with status: {backup_status}")

    if is_missing(backup_message):
        result["errors"].append("backup_message is missing")

    # 🔹 Validate input fields
    for key, value in fields.items():
        if is_missing(value):
            result["status"] = "failed"
            result["missing_fields"][key] = True
            result["errors"].append(f"{key} is missing")
        else:
            result["missing_fields"][key] = False

    # 🔹 Attach debug details
    result["details"] = {
        "backup_status": backup_status,
        "backup_message": backup_message,
        "validated_inputs": fields
    }

    return result


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    validation_result = validate_backup(body)

    return func.HttpResponse(
        json.dumps(validation_result, indent=2),
        status_code=200,
        mimetype="application/json"
    )