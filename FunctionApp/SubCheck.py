import azure.functions as func
import logging
import json
import os
from datetime import datetime
from azure.data.tables import TableServiceClient

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

# ✅ Sanitize entity helper
def sanitize_entity(entity: dict) -> dict:
    # Convert all string values to lowercase
    for key, value in entity.items():
        if isinstance(value, str):
            entity[key] = value.lower()
    return entity

@app.route(
    route="SubCheck",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def SubCheck(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing SubCheck request...")

    try:
        data, error = _get_json_body(req)

        # ❌ Invalid JSON
        if error:
            return _json_response({
                "message": "Invalid JSON format",
                "error": error
            }, 400)

        # ❌ Empty body
        if not data:
            return _json_response({
                "message": "Payload not received"
            }, 400)

        logging.info(f"Payload received: {data}")

        # ✅ Required fields
        required_fields = [
            "u_catalog_task_sysid",
            "u_ritm_number",
            "u_SubName"
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

        # ✅ Field validations
        if not isinstance(data["u_catalog_task_sysid"], str) or not data["u_catalog_task_sysid"].strip():
            return _json_response({"message": "Invalid 'u_catalog_task_sysid'"}, 400)

        if not isinstance(data["u_ritm_number"], str) or not data["u_ritm_number"].strip():
            return _json_response({"message": "Invalid 'u_ritm_number'"}, 400)

        if not isinstance(data["u_SubName"], str) or not data["u_SubName"].strip():
            return _json_response({
                "message": "Invalid 'u_SubName'. It must be a non-empty string."
            }, 400)

        logging.info("All fields validated successfully")

        # =====================================================
        # 🔥 STORE INTO AZURE TABLE STORAGE
        # =====================================================
        # Use the shared storage account and table created by the app
        connection_string = os.getenv("AzureWebJobsStorage")
        table_name = os.getenv("TABLE_NAME", "FunctionLogs")

        try:
            service = TableServiceClient.from_connection_string(connection_string)
            table_client = service.get_table_client(table_name)

            # Create table if not exists
            try:
                table_client.create_table()
            except Exception:
                pass

            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            entity = {
                "PartitionKey": data["u_ritm_number"],
                "RowKey": f"{data['u_catalog_task_sysid']}_subcheck_{timestamp}",

                # Custom fields
                "CatalogTaskSysId": data["u_catalog_task_sysid"],
                "SubscriptionName": data["u_SubName"],
                "Status": "Success",
                "CreatedAt": datetime.utcnow().isoformat()
            }

            entity = sanitize_entity(entity)
            table_client.upsert_entity(entity=entity)

            logging.info("Data stored successfully in Table Storage")

        except Exception as storage_error:
            logging.error(f"Storage error: {str(storage_error)}")
            return _json_response({
                "message": "Failed to store data",
                "error": str(storage_error)
            }, 500)

        # ✅ Success
        return _json_response({
            "message": "SubCheck completed and stored successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.error(f"Error processing SubCheck request: {str(e)}")
        return _json_response({
            "message": "An error occurred while processing the request",
            "error": str(e)
        }, 500)
