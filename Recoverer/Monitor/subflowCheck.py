import json
import azure.functions as func
import re
from datetime import datetime

# =========================
# REQUIRED FIELDS
# =========================
REQUIRED_FIELDS = [
    "subscription_name",
    "subscription_mgmtgroup",
    "subscription_tags"
]

REQUIRED_TAG_FIELDS = [
    "stla_application_id",
    "stla_hle_usd",
    "stla_support_email",
    "stla_environment",
    "stla_global_business",
    "stla_global_subfunction",
    "stla_sensitivity",
    "stla_multi_tenant",
    "stla_purchase_date",
    "stla_region",
    "stla_network_domain",
    "stla_model_deployment",
    "stla_application_source",
    "stla_application_name"
]

# =========================
# GUID VALIDATION
# =========================
def is_valid_guid(value):
    regex = r'^[0-9a-fA-F\-]{36}$'
    return isinstance(value, str) and re.match(regex, value)


# =========================
# RESPONSE BUILDER
# =========================
def build_response(stage, status, message, details=None):
    return {
        "workflow": "subscription_creation",
        "stage": stage,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "message": message,
        "details": details or {}
    }


# =========================
# MAIN FUNCTION
# =========================
def main(req: func.HttpRequest) -> func.HttpResponse:

    # =========================
    # STEP 0: READ BODY
    # =========================
    try:
        body = req.get_json()
    except Exception:
        return func.HttpResponse(
            json.dumps(build_response("INPUT_VALIDATION", "FAILED", "Invalid JSON payload")),
            status_code=400,
            mimetype="application/json"
        )

    sub_payload = body.get("sub_payload")

    if not isinstance(sub_payload, dict):
        return func.HttpResponse(
            json.dumps(build_response(
                "INPUT_VALIDATION",
                "FAILED",
                "sub_payload is missing or invalid",
                {"received": sub_payload}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 1: INPUT VALIDATION
    # =========================
    missing_fields = []

    for field in REQUIRED_FIELDS:
        if not sub_payload.get(field):
            missing_fields.append(field)

    tags = sub_payload.get("subscription_tags")

    if isinstance(tags, dict):
        for tag in REQUIRED_TAG_FIELDS:
            if not tags.get(tag):
                missing_fields.append(f"subscription_tags.{tag}")
    else:
        missing_fields.append("subscription_tags (invalid or not object)")

    if missing_fields:
        return func.HttpResponse(
            json.dumps(build_response(
                "INPUT_VALIDATION",
                "FAILED",
                "Missing or invalid payload fields",
                {"missing_fields": missing_fields}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 2: REPO VALIDATION
    # =========================
    repo_value = body.get("repo_azglz_pipeline_createsub")

    if not repo_value or not is_valid_guid(repo_value):
        return func.HttpResponse(
            json.dumps(build_response(
                "REPO_VALIDATION",
                "FAILED",
                "Invalid or missing repo GUID",
                {"value_received": repo_value}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 3: QUERY VALIDATION
    # =========================
    query_status = body.get("query_last_commit_status")
    query_output = body.get("query_last_commit_output")

    if query_status != "Succeeded":
        return func.HttpResponse(
            json.dumps(build_response(
                "QUERY_VALIDATION",
                "FAILED",
                "Query_last_commit failed",
                {"status": query_status}
            )),
            status_code=400,
            mimetype="application/json"
        )

    try:
        commits = query_output.get("body", {}).get("value", [])

        if not commits:
            raise Exception("No commits found")

        latest_commit = commits[0]

        commit_id = latest_commit.get("commitId")
        if not commit_id:
            raise Exception("commitId missing")

    except Exception as e:
        return func.HttpResponse(
            json.dumps(build_response(
                "QUERY_OUTPUT_VALIDATION",
                "FAILED",
                "Invalid query output",
                {"error": str(e)}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 4: CHECKIN VALIDATION
    # =========================
    checkin_status = body.get("checkin_newsubjson_status")
    checkin_output = body.get("checkin_newsubjson_output")

    if checkin_status != "Succeeded":
        return func.HttpResponse(
            json.dumps(build_response(
                "CHECKIN_VALIDATION",
                "FAILED",
                "checkin_newsubjson failed",
                {"status": checkin_status}
            )),
            status_code=400,
            mimetype="application/json"
        )

    try:
        if not isinstance(checkin_output, dict):
            raise Exception("Invalid checkin output")

        if checkin_output.get("statusCode") != 201:
            raise Exception("Expected statusCode 201")

        commits = checkin_output.get("body", {}).get("commits", [])

        if not commits:
            raise Exception("No commits in checkin output")

        latest_commit = commits[0]

        checkin_commit_id = latest_commit.get("commitId")
        input_sub_name = latest_commit.get("input_subscription_name")
        parent_commit = latest_commit.get("parents", [None])[0]

        if not checkin_commit_id:
            raise Exception("Missing commitId")

        if input_sub_name != sub_payload.get("subscription_name"):
            raise Exception("Subscription mismatch")

        if parent_commit != commit_id:
            raise Exception("Commit chain broken")

    except Exception as e:
        return func.HttpResponse(
            json.dumps(build_response(
                "CHECKIN_OUTPUT_VALIDATION",
                "FAILED",
                "Invalid checkin output",
                {"error": str(e)}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 5: BUILD QUEUE VALIDATION
    # =========================
    build_status = body.get("QueueNewBuildforSubPipeline_status")
    build_output = body.get("QueueNewBuildforSubPipeline_output")

    if build_status != "Succeeded":
        return func.HttpResponse(
            json.dumps(build_response(
                "BUILD_QUEUE_VALIDATION",
                "FAILED",
                "QueueNewBuildforSubPipeline failed",
                {"status": build_status}
            )),
            status_code=400,
            mimetype="application/json"
        )

    try:
        if not isinstance(build_output, dict):
            raise Exception("Invalid build output")

        if build_output.get("statusCode") != 200:
            raise Exception("Expected statusCode 200")

        outer_body = build_output.get("body", {})
        inner_body = outer_body.get("body", {})

        build_id = inner_body.get("id")
        build_state = inner_body.get("status")
        build_sub_name = inner_body.get("input_subscription_name")
        
        if not build_id:
            raise Exception("Missing build ID")

        if build_state not in ["notStarted", "inProgress"]:
            raise Exception(f"Unexpected build state: {build_state}")

        if build_sub_name != sub_payload.get("subscription_name"):
            raise Exception("Subscription mismatch in build")

    except Exception as e:
        return func.HttpResponse(
            json.dumps(build_response(
                "BUILD_QUEUE_OUTPUT_VALIDATION",
                "FAILED",
                "Invalid build queue output",
                {"error": str(e)}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # SUCCESS
    # =========================
    return func.HttpResponse(
        json.dumps(build_response(
            "VALIDATION_COMPLETE",
            "SUCCESS",
            "All validations passed",
            {
                "subscription_name": sub_payload.get("subscription_name"),
                "query_commit_id": commit_id,
                "checkin_commit_id": checkin_commit_id,
                "build_id": build_id,
                "build_status": build_state
            }
        )),
        status_code=200,
        mimetype="application/json"
    )


"""import json
import azure.functions as func
import re
from datetime import datetime

# =========================
# REQUIRED FIELDS
# =========================
REQUIRED_FIELDS = [
    "subscription_name",
    "subscription_mgmtgroup",
    "subscription_tags"
]

REQUIRED_TAG_FIELDS = [
    "stla_application_id",
    "stla_hle_usd",
    "stla_support_email",
    "stla_environment",
    "stla_global_business",
    "stla_global_subfunction",
    "stla_sensitivity",
    "stla_multi_tenant",
    "stla_purchase_date",
    "stla_region",
    "stla_network_domain",
    "stla_model_deployment",
    "stla_application_source",
    "stla_application_name"
]

# =========================
# GUID VALIDATION
# =========================
def is_valid_guid(value):
    regex = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
    return isinstance(value, str) and re.match(regex, value) is not None


# =========================
# RESPONSE BUILDER
# =========================
def build_response(stage, status, message, details=None):
    return {
        "workflow": "subscription_creation",
        "stage": stage,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "message": message,
        "details": details or {}
    }




# =========================
# MAIN FUNCTION
# =========================
def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except Exception:
        return func.HttpResponse(
            json.dumps(build_response("INPUT_VALIDATION", "FAILED", "Invalid JSON payload")),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 0: EXTRACT PAYLOAD
    # =========================
    sub_payload = body.get("sub_payload")

    if not isinstance(sub_payload, dict):
        return func.HttpResponse(
            json.dumps(build_response(
                "INPUT_VALIDATION", "FAILED",
                "sub_payload is missing or invalid",
                {"received": sub_payload}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 1: INPUT VALIDATION
    # =========================
    missing_fields = []

    for field in REQUIRED_FIELDS:
        if not sub_payload.get(field):
            missing_fields.append(field)

    tags = sub_payload.get("subscription_tags")

    if isinstance(tags, dict):
        for tag in REQUIRED_TAG_FIELDS:
            if not tags.get(tag):
                missing_fields.append(f"subscription_tags.{tag}")
    else:
        missing_fields.append("subscription_tags (invalid or not object)")

    if missing_fields:
        return func.HttpResponse(
            json.dumps(build_response(
                "INPUT_VALIDATION", "FAILED",
                "Missing or invalid payload fields",
                {"missing_fields": missing_fields}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 2: REPO VALIDATION
    # =========================
    repo_value = body.get("repo_azglz_pipeline_createsub")

    if not repo_value:
        return func.HttpResponse(
            json.dumps(build_response(
                "REPO_VALIDATION", "FAILED",
                "repo_azglz_pipeline_createsub is missing",
                {"value_received": repo_value}
            )),
            status_code=400,
            mimetype="application/json"
        )

    if not is_valid_guid(repo_value):
        return func.HttpResponse(
            json.dumps(build_response(
                "REPO_VALIDATION", "FAILED",
                "Invalid GUID format",
                {"value_received": repo_value}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 3: QUERY VALIDATION
    # =========================
    query_status = body.get("query_last_commit_status")
    query_output = body.get("query_last_commit_output")

    if query_status != "Succeeded":
        return func.HttpResponse(
            json.dumps(build_response(
                "QUERY_VALIDATION", "FAILED",
                "Query_last_commit failed",
                {"status": query_status}
            )),
            status_code=400,
            mimetype="application/json"
        )

    try:
        commits = query_output.get("body", {}).get("value", [])
        latest_commit = commits[0]

        commit_id = latest_commit.get("commitId")
        comment = latest_commit.get("comment")

        if not commit_id:
            raise Exception("commitId missing")

    except Exception as e:
        return func.HttpResponse(
            json.dumps(build_response(
                "QUERY_OUTPUT_VALIDATION", "FAILED",
                "Invalid query output",
                {"error": str(e)}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 4: CHECKIN VALIDATION
    # =========================
    checkin_status = body.get("checkin_newsubjson_status")
    checkin_output = body.get("checkin_newsubjson_output")

    if checkin_status != "Succeeded":
        return func.HttpResponse(
            json.dumps(build_response(
                "CHECKIN_VALIDATION", "FAILED",
                "checkin_newsubjson action failed",
                {"status": checkin_status}
            )),
            status_code=400,
            mimetype="application/json"
        )

    try:
        if checkin_output.get("statusCode") != 201:
            raise Exception("Checkin did not return 201")

        commits = checkin_output.get("body", {}).get("commits", [])
        latest_commit = commits[0]

        checkin_commit_id = latest_commit.get("commitId")
        input_sub_name = latest_commit.get("input_subscription_name")
        parent_commit = latest_commit.get("parents", [None])[0]

        if not checkin_commit_id:
            raise Exception("commitId missing in checkin")

        if input_sub_name != sub_payload.get("subscription_name"):
            raise Exception("Subscription name mismatch in checkin")

        # Commit chain validation
        if parent_commit != commit_id:
            raise Exception("Checkin not based on latest commit")

    except Exception as e:
        return func.HttpResponse(
            json.dumps(build_response(
                "CHECKIN_OUTPUT_VALIDATION", "FAILED",
                "Invalid checkin output structure",
                {"error": str(e)}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # STEP 5: BUILD QUEUE VALIDATION (NEW)
    # =========================
    build_status = body.get("QueueNewBuildforSubPipeline_status")
    build_output = body.get("QueueNewBuildforSubPipeline_output")

    if build_status != "Succeeded":
        return func.HttpResponse(
            json.dumps(build_response(
                "BUILD_QUEUE_VALIDATION", "FAILED",
                "QueueNewBuildforSubPipeline action failed",
                {"status": build_status}
            )),
            status_code=400,
            mimetype="application/json"
        )

    try:
        if build_output.get("statusCode") != 200:
            raise Exception("Build queue did not return 200")

        build_body = build_output.get("body", {})

        build_id = build_body.get("id")
        build_state = build_body.get("status")
        build_sub_name = build_body.get("input_subscription_name")

        if not build_id:
            raise Exception("Build ID missing")

        if build_state not in ["notStarted", "inProgress"]:
            raise Exception(f"Unexpected build status: {build_state}")

        # Cross validation
        if build_sub_name != sub_payload.get("subscription_name"):
            raise Exception("Subscription mismatch in build queue")

    except Exception as e:
        return func.HttpResponse(
            json.dumps(build_response(
                "BUILD_QUEUE_OUTPUT_VALIDATION", "FAILED",
                "Invalid build queue output",
                {"error": str(e)}
            )),
            status_code=400,
            mimetype="application/json"
        )

    # =========================
    # FINAL SUCCESS
    # =========================
    return func.HttpResponse(
        json.dumps(build_response(
            "VALIDATION_COMPLETE",
            "SUCCESS",
            "All validations passed",
            {
                "subscription_name": sub_payload.get("subscription_name"),
                "query_commit_id": commit_id,
                "checkin_commit_id": checkin_commit_id,
                "build_id": build_id,
                "build_status": build_state
            }
        )),
        status_code=200,
        mimetype="application/json"
    )
"""