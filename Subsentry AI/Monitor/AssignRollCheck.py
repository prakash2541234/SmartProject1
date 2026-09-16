import json
import logging
import azure.functions as func


def validate_parse_payload(parse_output: dict) -> list:
    required_fields = [
        "subscription_id",
        "subscription_access",
        "request_parameters",
        "status",
        "message"
    ]

    missing = []
    for field in required_fields:
        if field not in parse_output or parse_output.get(field) in [None, ""]:
            missing.append(field)

    return missing


def validate_assignroles_output(output: dict) -> list:
    required_fields = [
        "subscription_id",
        "subscription_access",
        "request_parameters"
    ]

    missing = []
    for field in required_fields:
        if field not in output or output.get(field) in [None, ""]:
            missing.append(field)

    return missing


def validate_assignroles_input(input_payload: dict) -> list:
    required_fields = [
        "subscription_id",
        "subscription_access",
        "request_parameters"
    ]

    missing = []
    for field in required_fields:
        if field not in input_payload or input_payload.get(field) in [None, ""]:
            missing.append(field)

    return missing


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Validate AssignRole Payload function triggered.")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({
                "status": "failed",
                "message": "Invalid JSON input"
            }),
            status_code=400,
            mimetype="application/json"
        )

    parse_output = body.get("parse_assignrole_output", {})
    assignroles_output = body.get("call_assignroles_output", {})
    assignroles_input = body.get("call_assignroles_input", {})

    # 🔹 Step 1: Validate ParseAssignRoleOutput
    parse_missing = validate_parse_payload(parse_output)

    if not parse_missing:
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": "ParseAssignRoleOutput payload received correctly"
            }),
            status_code=200,
            mimetype="application/json"
        )

    # 🔹 Step 2: Validate call_assignroles output
    output_missing = validate_assignroles_output(assignroles_output)

    if output_missing:
        # 🔹 Step 3: Validate input payload
        input_missing = validate_assignroles_input(assignroles_input)

        if input_missing:
            return func.HttpResponse(
                json.dumps({
                    "status": "failed",
                    "error_stage": "call_assignroles_input",
                    "message": "Input payload missing required fields",
                    "missing_fields": input_missing
                }),
                status_code=400,
                mimetype="application/json"
            )
        else:
            return func.HttpResponse(
                json.dumps({
                    "status": "failed",
                    "error_stage": "call_assignroles_output",
                    "message": "call_assignroles is not returning proper output",
                    "missing_fields": output_missing
                }),
                status_code=500,
                mimetype="application/json"
            )

    # 🔹 Fallback (unexpected case)
    return func.HttpResponse(
        json.dumps({
            "status": "failed",
            "message": "Unknown validation error",
            "parse_missing_fields": parse_missing
        }),
        status_code=500,
        mimetype="application/json"
    )