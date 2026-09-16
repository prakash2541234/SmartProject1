import azure.functions as func
import logging
import json

app = func.FunctionApp()

def _json_response(payload: dict, status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json"
    )

def _get_json_body(req: func.HttpRequest):
    try:
        return req.get_json(), None
    except ValueError as e:
        return None, str(e)

@app.route(
    route="SPCheck",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def SPCheck(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing SPCheck request...")

    try:
        data, error = _get_json_body(req)

        if error:
            return _json_response({
                "status": "failed",
                "stage": "SPCheck",
                "reason": "Invalid JSON",
                "details": error,
                "action": "Check previous Logic App step output format"
            }, 400)
        
        if not data:
            return _json_response({
                "status": "failed",
                "stage": "SPCheck",
                "reason": "Empty payload",
                "action": "Upstream step (Service_Principal) did not send data"
            }, 400)

        logging.info(f"Payload received: {data}")

        required_fields = [
            "u_catalog_task_sysid",
            "u_ritm_number",
            "SP_name"
        ]

        missing_fields = [
            field for field in required_fields
            if field not in data or data[field] is None
        ]

        if missing_fields:
            return _json_response({
                "status": "failed",
                "stage": "SPCheck",
                "reason": "Missing required fields",
                "missing_fields": missing_fields,
                "received_payload": data,
                "root_cause": "Upstream step did not send required fields",
                "check": {
                    "step": "Service_Principal (Logic App)",
                    "expected_field": "SP_name",
                    "possible_issue": [
                        "SP_name not mapped correctly",
                        "Service_Principal step output is empty",
                        "Wrong dynamic content used"
                    ]
                }
            }, 400)

        if not isinstance(data["SP_name"], str) or not data["SP_name"].strip():
            return _json_response({
                "status": "failed",
                "stage": "SPCheck",
                "reason": "Invalid SP_name",
                "value_received": data["SP_name"],
                "root_cause": "Service_Principal step sent empty or invalid SP_name",
                "fix": "Ensure SP_name is non-empty string in Logic App"
            }, 400)

        return _json_response({
            "status": "success",
            "stage": "SPCheck",
            "message": "Payload validated successfully",
            "validated_data": data
        }, 200)

    except Exception as e:
        logging.error(f"Error processing SPCheck request: {str(e)}")
        return _json_response({
            "status": "failed",
            "stage": "SPCheck",
            "reason": "Unhandled exception",
            "error": str(e)
        }, 500)