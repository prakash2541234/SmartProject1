import logging
import json
import azure.functions as func
from datetime import datetime
from azure.data.tables import TableServiceClient

app = func.FunctionApp()

PROCESS_TRACKER = {}

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
# ✅ STORAGE CLIENT SETUP
# =========================================================
import os

CONNECTION_STRING = os.getenv("AzureWebJobsStorage")
TABLE_NAME = os.getenv("TABLE_NAME", "FunctionLogs")

table_service = TableServiceClient.from_connection_string(CONNECTION_STRING)
table_client = table_service.get_table_client(TABLE_NAME)

# Create table if not exists
try:
    table_client.create_table()
except Exception:
    pass


# =========================================================
# ✅ ENTITY SANITIZATION HELPER
# =========================================================
def sanitize_entity(entity: dict) -> dict:
    import json
    for key, value in entity.items():
        if isinstance(value, (dict, list)):
            entity[key] = json.dumps(value)
    return entity


# =========================================================
# ✅ STORE LOGS FUNCTION (UPDATED 🚀)
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

        # =========================================================
        # ✅ INSERT INTO TABLE STORAGE
        # =========================================================
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        entity = {
            "PartitionKey": data["u_ritm_number"],   # group by RITM
            "RowKey": f"{data['u_catalog_task_sysid']}_storelogs_{timestamp}",
            "StepName": "StoreLogs",
            "CatalogTaskSysId": data["u_catalog_task_sysid"],
            "State": data["u_state"],
            "Result": data["u_result"],
            "TimestampUTC": datetime.utcnow().isoformat()
        }

        entity = sanitize_entity(entity)
        table_client.upsert_entity(entity)

        return _json_response({
            "message": "Log stored successfully",
            "data": entity
        }, 200)

    except Exception as e:
        logging.exception("Error in storelogs")
        return _json_response({"error": str(e)}, 500)
    
"""import logging
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
