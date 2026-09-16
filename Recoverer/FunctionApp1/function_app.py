import azure.functions as func
import logging
import json

app = func.FunctionApp()

@app.route(
    route="storelogs",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def storelogs(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing request. Waiting for JSON payload...")

    try:
        # Try to read JSON payload
        try:
            data = req.get_json()
        except ValueError as e:
            logging.warning("Invalid JSON format")
            return func.HttpResponse(
                json.dumps({
                    "message": "Invalid JSON format",
                    "error": str(e)
                }),
                status_code=400,
                mimetype="application/json"
            )

        # ❌ If payload is empty or None
        if not data:
            logging.warning("Payload not received")
            return func.HttpResponse(
                json.dumps({
                    "message": "Payload not received"
                }),
                status_code=400,
                mimetype="application/json"
            )

        logging.info(f"Payload received: {data}")

        # ✅ Required fields (same as your working script)
        required_fields = [
            "u_catalog_task_sysid",
            "u_ritm_number",
            "u_state",
            "u_result"
        ]

        # ✅ Missing fields validation (same logic)
        missing_fields = [
            field for field in required_fields
            if field not in data or data[field] is None
        ]

        if missing_fields:
            logging.warning(f"Missing fields in payload: {missing_fields}")
            return func.HttpResponse(
                json.dumps({
                    "message": "Payload is missing required fields",
                    "missing_fields": missing_fields
                }),
                status_code=400,
                mimetype="application/json"
            )

        # ✅ Success response
        return func.HttpResponse(
            json.dumps({
                "message": "Payload received successfully",
                "data": data
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.exception("Error processing request")
        return func.HttpResponse(
            json.dumps({
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )
