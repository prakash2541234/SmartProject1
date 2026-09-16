import json
import azure.functions as func


def is_missing(value):
    return value is None or value == ""


def validate_kv(data: dict) -> dict:
    result = {
        "status": "success",
        "errors": [],
        "missing_fields": {},
        "details": {}
    }

    # ==========================================
    # 🔹 Extract Inputs
    # ==========================================
    kv_status = data.get("kv_status")
    kv_name = data.get("kv_name")

    raw_kv_response = data.get("raw_kv_response", {})
    parsed_kv_output = data.get("parsed_kv_output", {})
    input_payload = data.get("input_payload", {})

    subscription_id = input_payload.get("subscription_id")
    appid = input_payload.get("appid")
    environment = input_payload.get("environment")
    region = input_payload.get("region")

    # ==========================================
    # 🔹 Step 1: Validate KV Output (Final Step)
    # ==========================================
    if is_missing(kv_status) or kv_status != "success":
        result["status"] = "failed"

        if is_missing(kv_status):
            result["errors"].append("kv_status is missing")
        else:
            result["errors"].append(f"KV creation failed with status: {kv_status}")

        if is_missing(kv_name):
            result["errors"].append("keyvault_name is missing")
            result["missing_fields"]["kv_name"] = True

        # ==========================================
        # 🔹 Step 2: Check Parsed KV Output
        # ==========================================
        parse_status = parsed_kv_output.get("status")
        parse_message = parsed_kv_output.get("message")

        if is_missing(parse_status) or is_missing(parse_message):
            result["errors"].append(
                "ParseKVOutput failed to receive proper data from CreateKV function"
            )
            result["missing_fields"]["parsed_kv_output"] = True

        else:
            result["errors"].append(
                "KV step failed to map values from ParseKVOutput"
            )
            result["details"]["issue"] = "KV_MAPPING_FAILED"
            return result

        # ==========================================
        # 🔹 Step 3: Check Raw KV Response
        # ==========================================
        raw_status = raw_kv_response.get("status")
        raw_message = raw_kv_response.get("message")

        if not is_missing(raw_status) and not is_missing(raw_message):
            result["errors"].append(
                "ParseKVOutput failed to map data from CreateKV response"
            )
            result["details"]["issue"] = "PARSE_MAPPING_FAILED"
            return result

        result["errors"].append("CreateKV function did not return proper response")
        result["missing_fields"]["raw_kv_response"] = True

        # ==========================================
        # 🔹 Step 4: Validate Input Payload
        # ==========================================
        fields = {
            "subscription_id": subscription_id,
            "appid": appid,
            "environment": environment,
            "region": region
        }

        for key, value in fields.items():
            if is_missing(value):
                result["missing_fields"][key] = True
                result["errors"].append(f"{key} is missing")
            else:
                result["missing_fields"][key] = False

        if any(result["missing_fields"].values()):
            result["errors"].append(
                "CreateKV failed due to invalid input payload"
            )
            result["details"]["issue"] = "INPUT_PAYLOAD_FAILED"
        else:
            result["errors"].append(
                "CreateKV execution failed even though input payload is correct"
            )
            result["details"]["issue"] = "CREATE_KV_FAILED"

    # ==========================================
    # 🔹 Success Case
    # ==========================================
    else:
        result["details"]["message"] = "KeyVault created successfully"
        result["details"]["kv_name"] = kv_name

    # ==========================================
    # 🔹 Always Attach Debug Info
    # ==========================================
    result["details"]["debug"] = {
        "kv_status": kv_status,
        "kv_name": kv_name,
        "parsed_kv_output": parsed_kv_output,
        "raw_kv_response": raw_kv_response,
        "input_payload": input_payload
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

    validation_result = validate_kv(body)

    return func.HttpResponse(
        json.dumps(validation_result, indent=2),
        status_code=200,
        mimetype="application/json"
    )