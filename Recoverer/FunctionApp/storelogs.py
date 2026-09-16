import logging
import json
import azure.functions as func

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


# =========================================================
# ✅ 1. STORE LOGS FUNCTION (UNCHANGED ✅)
# =========================================================
@app.route(
    route="storelogs",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def storelogs(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing storelogs request...")

    try:
        data, error = _get_json_body(req)

        if error:
            return _json_response({
                "message": "Invalid JSON format",
                "error": error
            }, 400)

        if not data:
            return _json_response({
                "message": "Payload not received"
            }, 400)

        logging.info(f"Payload received: {data}")

        required_fields = [
            "u_catalog_task_sysid",
            "u_ritm_number",
            "u_state",
            "u_result"
        ]

        missing_fields = []

        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)

        if missing_fields:
            return _json_response({
                "message": "Payload is missing required fields",
                "missing_fields": missing_fields
            }, 400)

        return _json_response({
            "message": "Payload received successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.exception("Error in storelogs")
        return _json_response({"error": str(e)}, 500)

"""
import azure.functions as func
import logging
import json
import os
from datetime import datetime
from azure.data.tables import TableServiceClient, TableClient, UpdateMode

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
    route="storelogs",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def storelogs(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing storelogs request...")

    try:
        data, error = _get_json_body(req)

        if error:
            return _json_response({
                "message": "Invalid JSON format",
                "error": error
            }, 400)

        if not data:
            return _json_response({
                "message": "Payload not received"
            }, 400)

        logging.info(f"Payload received: {data}")

        # ✅ Required fields
        required_fields = [
            "u_catalog_task_sysid",
            "u_ritm_number",
            "u_state",
            "u_result"
        ]

        missing_fields = [
            field for field in required_fields
            if field not in data or data[field] is None
        ]

        if missing_fields:
            return _json_response({
                "message": "Payload is missing required fields",
                "missing_fields": missing_fields
            }, 400)

        # =====================================================
        # 🔥 STORE INTO AZURE TABLE STORAGE
        # =====================================================
        try:
            connection_string = os.getenv("AzureWebJobsStorage")
            table_name = "FunctionExecutionLogs"

            service = TableServiceClient.from_connection_string(connection_string)
            table_client = service.get_table_client(table_name)

            # Create table if not exists
            try:
                table_client.create_table()
            except:
                pass

            entity = {
                "PartitionKey": data["u_catalog_task_sysid"],  # group by task
                "RowKey": f"{datetime.utcnow().isoformat()}",
                "RITM": data["u_ritm_number"],
                "State": data["u_state"],
                "Result": data["u_result"],
                "Timestamp": datetime.utcnow().isoformat()
            }

            table_client.create_entity(entity=entity)

            logging.info("Log stored successfully in Table Storage")

        except Exception as storage_error:
            logging.error(f"Storage error: {str(storage_error)}")
            return _json_response({
                "message": "Failed to store log in storage",
                "error": str(storage_error)
            }, 500)

        # =====================================================
        # ✅ SUCCESS RESPONSE
        # =====================================================
        return _json_response({
            "message": "Log stored successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.exception("Error in storelogs")
        return _json_response({
            "message": "Internal server error",
            "error": str(e)
        }, 500)"""