import azure.functions as func
import logging
import json

app = func.FunctionApp()

PROCESS_TRACKER = {}

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
