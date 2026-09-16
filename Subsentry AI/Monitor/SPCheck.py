import json
import azure.functions as func

def is_missing(value):
    return value is None or value == ""


def ensure_dict(value):
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}

    return {}


def validate_sp_forward(data: dict) -> dict:
    result = {
        "status": "success",
        "failed_at": "",
        "root_cause": "",
        "message": "",
        "details": {}
    }

    sp_status = data.get("sp_status")
    sp_name = data.get("sp_name")

    create_input = ensure_dict(data.get("create_sp_input"))
    create_output = ensure_dict(data.get("create_sp_response"))
    parse_output = ensure_dict(data.get("parse_sp_output"))

    sp_params = ensure_dict(create_input.get("sp_parameters"))
    req_params = ensure_dict(create_input.get("request_parameters"))

    if sp_status == "success" and not is_missing(sp_name):
        result["message"] = "SP created successfully"
        result["details"] = {
            "sp_name": sp_name
        }
        return result

    required_inputs = {
        "application_id": sp_params.get("application_id"),
        "environment": sp_params.get("environment"),
        "subscription_id": sp_params.get("subscription_id"),
        "subscription_role": sp_params.get("subscription_role"),
        "sp_owners": req_params.get("sp_owners")
    }

    missing_inputs = [
        key for key, val in required_inputs.items() if is_missing(val)
    ]

    if missing_inputs:
        result["status"] = "failed"
        result["failed_at"] = "CREATE_SP_INPUT"
        result["root_cause"] = "MISSING_INPUT"
        result["message"] = (
            f"Missing required input fields in Call_CreateSP_function: {missing_inputs}"
        )
        result["details"] = {
            "missing_fields": missing_inputs
        }
        return result

    create_status = create_output.get("statusCode")

    if create_status != 200:
        result["status"] = "failed"
        result["failed_at"] = "CREATE_SP_API"
        result["root_cause"] = "API_FAILURE"
        result["message"] = "CreateSP API failed"
        result["details"] = {
            "statusCode": create_status,
            "response": create_output
        }
        return result

    parsed_status = parse_output.get("status")
    parsed_sp_name = ensure_dict(parse_output.get("details")).get("sp_name")

    if is_missing(parsed_status) or is_missing(parsed_sp_name):
        result["status"] = "failed"
        result["failed_at"] = "PARSE_SP_OUTPUT"
        result["root_cause"] = "INVALID_RESPONSE_FORMAT"
        result["message"] = (
            "CreateSP response missing required fields for ParseSPOutput"
        )
        result["details"] = {
            "parse_output": parse_output
        }
        return result

    result["status"] = "failed"
    result["failed_at"] = "SET_SP_STATUS"
    result["root_cause"] = "MAPPING_FAILED"
    result["message"] = (
        "SetSPStatus failed to map values correctly"
    )
    result["details"] = {
        "expected_sp_name": parsed_sp_name,
        "actual_sp_name": sp_name
    }

    return result

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        try:
            body = req.get_json()
        except Exception as e:
            return func.HttpResponse(
                json.dumps({
                    "status": "failed",
                    "error": "INVALID_JSON",
                    "message": str(e)
                }),
                status_code=400,
                mimetype="application/json"
            )

        result = validate_sp_forward(body)

        return func.HttpResponse(
            json.dumps(result, indent=2),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        return func.HttpResponse(
            json.dumps({
                "status": "failed",
                "error": "INTERNAL_SERVER_ERROR",
                "message": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )
    

"""import json
import logging
import azure.functions as func

# ---------------------------
# Helper Functions
# ---------------------------

def ensure_dict(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return value if isinstance(value, dict) else {}

def response(payload, code=200):
    return func.HttpResponse(
        json.dumps(payload, indent=2),
        status_code=code,
        mimetype="application/json"
    )

# ---------------------------
# Main Function
# ---------------------------

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()

        # 🔥 Normalize all inputs
        setsp_output = ensure_dict(data.get("sp_status"))
        sp_name = data.get("sp_name")

        parse_output = ensure_dict(data.get("parse_sp_output"))
        create_response = ensure_dict(data.get("create_sp_response"))
        input_payload = ensure_dict(data.get("create_sp_input"))

        subscription_id = data.get("subscription_id")

        result = {
            "level": None,
            "stage": None,
            "message": None,
            "missing_fields": [],
            "debug_path": []
        }

        # --------------------------------------------------
        # ✅ STEP 1: CHECK SetSPStatus (FINAL OUTPUT)
        # --------------------------------------------------
        result["debug_path"].append("checking_SetSPStatus")

        if not data.get("sp_status") or not sp_name:
            result["debug_path"].append("SetSPStatus_missing")

            # --------------------------------------------------
            # 🔍 STEP 2: CHECK ParseSPOutput
            # --------------------------------------------------
            result["debug_path"].append("checking_ParseSPOutput")

            parse_status = parse_output.get("status")
            parsed_sp_name = parse_output.get("details", {}).get("sp_name")

            if not parse_status or not parsed_sp_name:
                result["debug_path"].append("ParseSPOutput_missing")

                # --------------------------------------------------
                # 🔍 STEP 3: CHECK CreateSP API
                # --------------------------------------------------
                result["debug_path"].append("checking_CreateSP_API")

                if not create_response or create_response.get("statusCode") != 200:
                    result["debug_path"].append("CreateSP_failed")

                    # --------------------------------------------------
                    # 🔍 STEP 4: CHECK INPUT PAYLOAD
                    # --------------------------------------------------
                    result["debug_path"].append("checking_input_payload")

                    sp_params = input_payload.get("sp_parameters", {})

                    required_fields = [
                        "application_id",
                        "environment",
                        "subscription_id"
                    ]

                    missing = [f for f in required_fields if not sp_params.get(f)]

                    if missing:
                        result["level"] = "PAYLOAD_FAILED"
                        result["stage"] = "INPUT_VALIDATION"
                        result["message"] = "Missing required input payload fields"
                        result["missing_fields"] = missing
                        return response(result)

                    # If payload is fine but API failed
                    result["level"] = "SP_CREATION_FAILED"
                    result["stage"] = "CREATE_SP_API"
                    result["message"] = "Create SP API failed despite valid payload"
                    return response(result)

                # If API passed but parse failed
                result["level"] = "SP_CREATION_FAILED"
                result["stage"] = "PARSE_OUTPUT"
                result["message"] = "ParseSPOutput failed to extract required fields"
                return response(result)

            # If parse passed but SetSPStatus failed
            result["level"] = "SP_CREATION_FAILED"
            result["stage"] = "SET_SP_STATUS"
            result["message"] = "SetSPStatus failed to map SP details"
            return response(result)

        # --------------------------------------------------
        # ✅ SUCCESS CASE
        # --------------------------------------------------
        result["debug_path"].append("success")

        result["level"] = "SUCCESS"
        result["stage"] = "COMPLETED"
        result["message"] = "SP created successfully"
        result["sp_name"] = sp_name

        return response(result)

    except Exception as e:
        logging.exception("Error in validation function")

        return response({
            "level": "ERROR",
            "message": str(e)
        }, 500)"""