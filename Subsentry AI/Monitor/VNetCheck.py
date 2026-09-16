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


def validate_vnet_forward(data: dict) -> dict:
    result = {
        "status": "success",
        "failed_at": "",
        "root_cause": "",
        "message": "",
        "details": {}
    }

    # 🔹 STEP 0 → FINAL OUTPUT CHECK (Set_NWCreationStatus)
    nw_status = data.get("nw_status")
    vnet_name = data.get("vnet_name")

    create_input = ensure_dict(data.get("create_nw_input"))
    create_output = ensure_dict(data.get("create_nw_output"))
    parse_output = ensure_dict(data.get("parse_nw_output"))

    stla = ensure_dict(create_input.get("stla_parameters"))
    az = ensure_dict(create_input.get("az_parameters"))

    # ✅ FINAL SUCCESS
    if nw_status == "success" and not is_missing(vnet_name):
        result["message"] = "VNet created successfully"
        result["details"] = {"vnet_name": vnet_name}
        return result

    # 🔻 NOT SUCCESS → DEBUG FLOW STARTS

    # 🔹 STEP 1 → VALIDATE INPUT PAYLOAD
    required_inputs = {
        "subscription_id": create_input.get("subscription_id"),
        "stla.application_id": stla.get("application_id"),
        "stla.environment": stla.get("environment"),
        "az.network_model": az.get("network_model"),
        "az.azure_region": az.get("azure_region"),
        "az.network_config": az.get("network_config")
    }

    missing_inputs = [
        key for key, val in required_inputs.items() if is_missing(val)
    ]

    if missing_inputs:
        return {
            "status": "failed",
            "failed_at": "CREATE_NETWORK_INPUT",
            "root_cause": "MISSING_INPUT",
            "message": f"Missing required fields in input: {missing_inputs}",
            "details": {
                "missing_fields": missing_inputs,
                "input": create_input
            }
        }

    # 🔹 STEP 2 → CALL NETWORK API OUTPUT CHECK
    create_status = create_output.get("statusCode")

    if create_status != 200:
        return {
            "status": "failed",
            "failed_at": "CREATE_NETWORK_API",
            "root_cause": "API_FAILURE",
            "message": "Call_createnetwork-flow API failed",
            "details": {
                "statusCode": create_status,
                "response": create_output
            }
        }

    # 🔹 STEP 3 → PARSE OUTPUT VALIDATION
    parsed_status = parse_output.get("status")
    parsed_message = parse_output.get("message")
    parsed_details = ensure_dict(parse_output.get("details"))

    if is_missing(parsed_status) or is_missing(parsed_message):
        return {
            "status": "failed",
            "failed_at": "PARSE_NETWORK_OUTPUT",
            "root_cause": "INVALID_PARSE_RESPONSE",
            "message": "Parse_NWCreationStatus missing required fields",
            "details": {
                "parse_output": parse_output
            }
        }

    # 🔹 STEP 4 → SET_NWCreationStatus MAPPING CHECK
    # Expected vnet_name from create output OR parse output
    expected_vnet = (
        create_output.get("body", {}).get("vnet_name")
        or parsed_details.get("vnet_name")
    )

    if is_missing(vnet_name):
        return {
            "status": "failed",
            "failed_at": "SET_NETWORK_STATUS",
            "root_cause": "MAPPING_FAILED",
            "message": "Set_NWCreationStatus failed to map vnet_name",
            "details": {
                "expected_vnet_name": expected_vnet,
                "actual_vnet_name": vnet_name,
                "create_output": create_output,
                "parse_output": parse_output
            }
        }

    # 🔹 FALLBACK
    return {
        "status": "failed",
        "failed_at": "UNKNOWN_STAGE",
        "root_cause": "UNEXPECTED_BEHAVIOR",
        "message": "Unknown issue in network flow",
        "details": {
            "nw_status": nw_status,
            "vnet_name": vnet_name
        }
    }


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

        result = validate_vnet_forward(body)

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


def check_fields(data: dict, fields: list) -> list:
    missing = []
    for f in fields:
        if f not in data or data.get(f) in [None, ""]:
            missing.append(f)
    return missing


def extract_vnet_names(parse_output: dict) -> list:
    vnet_names = []

    details = parse_output.get("details", {})

    # Extract from vnets
    for v in details.get("vnets", []):
        if isinstance(v, dict) and "name" in v:
            vnet_names.append(v["name"])

    # Extract from subnets
    for s in details.get("subnets", []):
        if isinstance(s, dict) and "vnet_name" in s:
            vnet_names.append(s["vnet_name"])

    return list(set(vnet_names))


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Monitor 5 - VNet Root Cause Validation Started")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    # 🔹 Extract stages
    set_status = body.get("set_nw_status", {})
    parse_output = body.get("parse_nw_output", {})
    create_output = body.get("create_network_output", {})
    create_input = body.get("create_network_input", {})

    result = {
        "level": None,
        "error_stage": None,
        "final_error": None,
        "action": None,
        "vnet_name": None,
        "debug_path": []
    }

    # ==========================================
    # 🔹 Step 1: Check SetNWCreationStatus
    # ==========================================
    result["debug_path"].append("check_set_status")

    missing_set = check_fields(set_status, ["status", "vnet_name"])

    if not missing_set:
        result["level"] = "SUCCESS"
        result["vnet_name"] = set_status.get("vnet_name")
        result["final_error"] = None
        result["action"] = "No action required"
        result["debug_path"].append("set_status_success")

        return func.HttpResponse(json.dumps(result), status_code=200)

    result["debug_path"].append(f"set_missing_{missing_set}")

    # ==========================================
    # 🔹 Step 2: Check ParseNWCreationStatus
    # ==========================================
    result["debug_path"].append("check_parse_output")

    missing_parse = check_fields(parse_output, ["status", "message"])

    if not missing_parse:
        # 🔥 NEW: Deep validation for vnet mismatch
        vnet_names = extract_vnet_names(parse_output)

        if len(vnet_names) > 1:
            result["level"] = "DATA_MISMATCH"
            result["error_stage"] = "parse_nw_output"
            result["final_error"] = f"VNet name mismatch detected: {vnet_names}"
            result["action"] = "Ensure consistent vnet_name across VNet and subnet definitions"
            result["debug_path"].append("vnet_name_mismatch")

            return func.HttpResponse(json.dumps(result), status_code=200)

        # ✅ Parse has valid data → STOP here
        result["level"] = "SET_FAILED"
        result["error_stage"] = "set_nw_status"
        result["final_error"] = "SetNWCreationStatus failed to get correct data from ParseNWCreationStatus"
        result["action"] = "Check mapping between Parse and Set"
        result["debug_path"].append("parse_has_data_stop")

        return func.HttpResponse(json.dumps(result), status_code=200)

    result["debug_path"].append(f"parse_missing_{missing_parse}")

    # ==========================================
    # 🔹 Step 3: Check CreateNetwork Output
    # ==========================================
    result["debug_path"].append("check_create_output")

    missing_create_output = check_fields(create_output, ["status", "message"])

    if not missing_create_output:
        # ✅ Create output has data → STOP here
        result["level"] = "PARSE_FAILED"
        result["error_stage"] = "parse_nw_output"
        result["final_error"] = "ParseNWCreationStatus failed to get data from CreateNetwork output"
        result["action"] = "Fix Parse logic"
        result["debug_path"].append("create_output_has_data_stop")

        return func.HttpResponse(json.dumps(result), status_code=200)

    result["debug_path"].append(f"create_output_missing_{missing_create_output}")

    # ==========================================
    # 🔹 Step 4: Check CreateNetwork Input
    # ==========================================
    result["debug_path"].append("check_create_input")

    body_input = create_input.get("body", {})
    network_config = body_input.get("az_parameters", {}).get("network_config", [])

    vnet_present = False
    if isinstance(network_config, list) and len(network_config) > 0:
        vnet_present = "vnet_name" in network_config[0]

    if vnet_present:
        # ✅ Input is correct → issue is in output
        result["level"] = "CREATE_OUTPUT_FAILED"
        result["error_stage"] = "create_network_output"
        result["final_error"] = "CreateNetwork output is not generated properly"
        result["action"] = "Check CreateNetwork execution logs"
        result["debug_path"].append("input_ok_output_failed")

    else:
        # ❌ Input itself is wrong
        result["level"] = "INPUT_PAYLOAD_FAILED"
        result["error_stage"] = "create_network_input"
        result["final_error"] = "CreateNetwork input payload missing vnet_name"
        result["action"] = "Fix Logic App input payload"
        result["debug_path"].append("input_missing_vnet")

    return func.HttpResponse(json.dumps(result), status_code=200)

"""