import logging
import json
import azure.functions as func

app = func.FunctionApp()

# Define PROCESS_TRACKER at the top of the file
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
            logging.info(f"Missing fields: {missing_fields}")
            return _json_response({
                "message": "Payload is missing required fields",
                "missing_fields": missing_fields
            }, 400)

        # ✅ Field validations (AFTER presence check)
        if not isinstance(data["u_catalog_task_sysid"], str) or not data["u_catalog_task_sysid"].strip():
            return _json_response({
                "message": "Invalid 'u_catalog_task_sysid'"
            }, 400)

        if not isinstance(data["u_ritm_number"], str) or not data["u_ritm_number"].strip():
            return _json_response({
                "message": "Invalid 'u_ritm_number'"
            }, 400)

        if not isinstance(data["u_SubName"], str) or not data["u_SubName"].strip():
            return _json_response({
                "message": "Invalid 'u_SubName'. It must be a non-empty string."
            }, 400)

        logging.info("All fields validated successfully")

        # ✅ Success
        return _json_response({
            "message": "Payload validated successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.error(f"Error processing SubCheck request: {str(e)}")
        return _json_response({
            "message": "An error occurred while processing the request",
            "error": str(e)
        }, 500)
        
@app.route(
    route="RollCheck",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def RollCheck(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing RollCheck request...")

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
            "Roll_name"
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

        if not isinstance(data["Roll_name"], str) or not data["Roll_name"].strip():
            return _json_response({
                "message": "Invalid 'Roll_name'"
            }, 400)

        logging.info("All fields validated successfully")

        # ✅ Success
        return _json_response({
            "message": "Payload validated successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.error(f"Error processing RollCheck request: {str(e)}")
        return _json_response({
            "message": "An error occurred while processing the request",
            "error": str(e)
        }, 500)

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
        
@app.route(
    route="KVCheck",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def KVCheck(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing KVCheck request...")

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
            "KV_name"
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

        if not isinstance(data["KV_name"], str) or not data["KV_name"].strip():
            return _json_response({
                "message": "Invalid 'KV_name'. It must be a non-empty string."
            }, 400)

        logging.info("All fields validated successfully")

        # ✅ Success
        return _json_response({
            "message": "Payload validated successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.error(f"Error processing KVCheck request: {str(e)}")
        return _json_response({
            "message": "An error occurred while processing the request",
            "error": str(e)
        }, 500)
        
@app.route(
    route="BUCheck",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def BUCheck(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing BUCheck request...")

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
            "BackUP"
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

        if not isinstance(data["BackUP"], str) or not data["BackUP"].strip():
            return _json_response({
                "message": "Invalid 'BackUP'. It must be a non-empty string."
            }, 400)

        logging.info("All fields validated successfully")

        # ✅ Success
        return _json_response({
            "message": "Payload validated successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.error(f"Error processing BUCheck request: {str(e)}")
        return _json_response({
            "message": "An error occurred while processing the request",
            "error": str(e)
        }, 500)
        
@app.route(
    route="VNetCheck",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def VNetCheck(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing VNetCheck request...")

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
            "Vnet"
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

        # ✅ Field validations (AFTER presence check)
        if not isinstance(data["u_catalog_task_sysid"], str) or not data["u_catalog_task_sysid"].strip():
            return _json_response({
                "message": "Invalid 'u_catalog_task_sysid'"
            }, 400)

        if not isinstance(data["u_ritm_number"], str) or not data["u_ritm_number"].strip():
            return _json_response({
                "message": "Invalid 'u_ritm_number'"
            }, 400)

        if not isinstance(data["Vnet"], str) or not data["Vnet"].strip():
            return _json_response({
                "message": "Invalid 'Vnet'. It must be a non-empty string."
            }, 400)

        logging.info("All fields validated successfully")

        # ✅ Success
        return _json_response({
            "message": "Payload validated successfully",
            "data": data
        }, 200)

    except Exception as e:
        logging.error(f"Error processing VNetCheck request: {str(e)}")
        return _json_response({
            "message": "An error occurred while processing the request",
            "error": str(e)
        }, 500)    

@app.route(
    route="workflowTracker",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def workflow_tracker(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing workflow tracking request...")

    try:
        data, error = _get_json_body(req)

        if error:
            return _json_response({"error": error}, 400)

        if not data:
            return _json_response({"message": "Empty payload"}, 400)

        # ✅ Common identifiers
        task_id = data.get("u_catalog_task_sysid")
        ritm = data.get("u_ritm_number")

        if not task_id or not ritm:
            return _json_response({
                "message": "Missing required identifiers"
            }, 400)

        # 🔥 Initialize tracker if not exists
        if task_id not in PROCESS_TRACKER:
            PROCESS_TRACKER[task_id] = {
                "subscription": False,
                "role": False,
                "service_principal": False,
                "key_vault": False,
                "backup": False
            }

        tracker = PROCESS_TRACKER[task_id]

        # =====================================================
        # 🔥 NEW LOGIC: HANDLE BOTH MODES
        # =====================================================

        # ✅ Mode 1: FINAL PAYLOAD (ALL STEPS TOGETHER)
        if any(k in data for k in ["u_SubName", "RollAssign", "SP_name", "KV_name", "BackUP"]):

            if "u_SubName" in data:
                tracker["subscription"] = True

            if "RollAssign" in data:
                tracker["role"] = True

            if "SP_name" in data:
                tracker["service_principal"] = True

            if "KV_name" in data:
                tracker["key_vault"] = True

            if "BackUP" in data:
                tracker["backup"] = True

            logging.info("Processed final combined payload")

        # ✅ Mode 2: SINGLE STEP PAYLOAD (FUTURE SUPPORT)
        else:
            step_type = None

            if "u_SubName" in data:
                step_type = "subscription"
            elif "RollAssign" in data:
                step_type = "role"
            elif "SP_name" in data:
                step_type = "service_principal"
            elif "KV_name" in data:
                step_type = "key_vault"
            elif "BackUP" in data:
                step_type = "backup"

            if step_type:
                tracker[step_type] = True
                logging.info(f"Processed step: {step_type}")
            else:
                return _json_response({
                    "message": "Unknown payload type"
                }, 400)

        logging.info(f"Tracker state: {tracker}")

        # =====================================================
        # ✅ FINAL STATUS CHECK
        # =====================================================
        all_done = all(tracker.values())

        if all_done:
            return _json_response({
                "message": "All steps completed",
                "status": "completed",
                "tracker": tracker
            }, 200)
        else:
            return _json_response({
                "message": "Workflow in progress",
                "status": "in_progress",
                "tracker": tracker
            }, 200)

    except Exception as e:
        logging.exception("Error in workflowTracker")
        return _json_response({"error": str(e)}, 500)