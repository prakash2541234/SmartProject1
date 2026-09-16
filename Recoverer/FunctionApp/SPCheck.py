import azure.functions as func
import logging
import json

app = func.FunctionApp()

# ✅ Common JSON response helper
def _json_response(payload: dict, status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json"
    )

# ✅ Common JSON parser
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

        # ❌ Invalid JSON
        if error:
            return _json_response({
                "message": "Invalid JSON format",
                "error": error
            }, 400)

        # ❌ Empty payload
        if not data:
            return _json_response({
                "message": "Payload not received"
            }, 400)

        logging.info(f"Payload received: {data}")

        # ✅ Required fields
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
            logging.info(f"Missing fields: {missing_fields}")
            return _json_response({
                "message": "Payload is missing required fields",
                "missing_fields": missing_fields
            }, 400)

        # ✅ Field validations
        if not isinstance(data["u_catalog_task_sysid"], str) or not data["u_catalog_task_sysid"].strip():
            return _json_response({
                "message": "Invalid 'u_catalog_task_sysid'"
            }, 400)

        if not isinstance(data["u_ritm_number"], str) or not data["u_ritm_number"].strip():
            return _json_response({
                "message": "Invalid 'u_ritm_number'"
            }, 400)

        if not isinstance(data["SP_name"], str) or not data["SP_name"].strip():
            return _json_response({
                "message": "Invalid 'SP_name'. It must be a non-empty string."
            }, 400)

        logging.info("All fields validated successfully")

        # ✅ Success
        return _json_response({
            "message": "Payload validated successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.error(f"Error processing SPCheck request: {str(e)}")
        return _json_response({
            "message": "An error occurred while processing the request",
            "error": str(e)
        }, 500)