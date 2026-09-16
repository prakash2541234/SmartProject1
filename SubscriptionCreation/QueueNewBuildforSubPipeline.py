import logging
import json
import uuid
import re
from datetime import datetime, timezone
import azure.functions as func


def extract_subscription_name_from_params(params_str: str) -> str:
    """Extract subscription_name from parameters JSON string."""
    try:
        if isinstance(params_str, str):
            params_obj = json.loads(params_str)
            if isinstance(params_obj, dict):
                return str(params_obj.get("subscription_name", "unknown-sub")).strip()
    except (json.JSONDecodeError, ValueError):
        pass
    return "unknown-sub"


def get_build_definition_name(build_def_id: str) -> str:
    """Map build definition ID to pipeline name."""
    build_def_map = {
        "48": "CI_azglz_pipeline_createsub_nonprod",
        "49": "CI_azglz_pipeline_createsub_prod",
        "50": "CI_azglz_pipeline_createsub_dev",
    }
    return build_def_map.get(build_def_id, f"CI_Pipeline_{build_def_id}")


def normalize_branch(branch: str) -> str:
    """Normalize branch name to refs/heads/ format."""
    branch = str(branch or "main").strip()
    if not branch.startswith("refs/"):
        return f"refs/heads/{branch}"
    return branch


def parse_project_name(path: str) -> str:
    """Extract project name from path."""
    if not path:
        return "AZGLZ_API_Platform"
    
    parts = [p for p in path.split("/") if p]
    if parts:
        return parts[0]
    return "AZGLZ_API_Platform"


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Queue New Build for Subscription Pipeline triggered.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    if not isinstance(req_body, dict):
        return func.HttpResponse(
            body=json.dumps({"error": "Payload must be a JSON object"}),
            status_code=400,
            mimetype="application/json"
        )

    missing_fields = []
    validation_details = []

    # ── Root level ──────────────────────────────────────────────────────────
    body = req_body.get("body")
    if not isinstance(body, dict):
        missing_fields.append("body")
        validation_details.append("'body' object is missing or not a valid JSON object")
        body = {}

    queries = req_body.get("queries")
    if not isinstance(queries, dict):
        missing_fields.append("queries")
        validation_details.append("'queries' object is missing or not a valid JSON object")
        queries = {}

    path_value = req_body.get("path")
    if path_value is None or str(path_value).strip() == "":
        missing_fields.append("path")
        validation_details.append("'path' is missing or empty in root payload")

    # ── body fields ─────────────────────────────────────────────────────────
    required_body_fields = {
        "sourceBranch": "Target branch for the pipeline build (e.g. 'nonprod', 'prod')",
        "parameters":   "Pipeline parameters as a JSON string containing 'subscription_name'",
    }
    for field, description in required_body_fields.items():
        value = body.get(field)
        if value is None or str(value).strip() == "":
            missing_fields.append(f"body.{field}")
            validation_details.append(f"'body.{field}' is missing or empty — expected: {description}")

    # ── parameters inner field ───────────────────────────────────────────────
    parameters_raw = body.get("parameters", "")
    if parameters_raw and str(parameters_raw).strip():
        try:
            params_obj = json.loads(parameters_raw)
            if not isinstance(params_obj, dict):
                missing_fields.append("body.parameters (invalid format)")
                validation_details.append("'body.parameters' must be a JSON object string, not a plain value")
            else:
                sub_name = params_obj.get("subscription_name")
                if not sub_name or str(sub_name).strip() == "":
                    missing_fields.append("body.parameters.subscription_name")
                    validation_details.append("'subscription_name' is missing or empty inside 'body.parameters'")
        except (json.JSONDecodeError, ValueError):
            missing_fields.append("body.parameters (invalid JSON)")
            validation_details.append("'body.parameters' could not be parsed as JSON — ensure it is a valid JSON string")

    # ── queries fields ──────────────────────────────────────────────────────
    required_query_fields = {
        "buildDefId": "Build definition ID (e.g. '48' for nonprod, '49' for prod, '50' for dev)",
        "account":    "Azure DevOps account name (e.g. 'STLA-LZ-DEVOPS')",
    }
    for field, description in required_query_fields.items():
        value = queries.get(field)
        if value is None or str(value).strip() == "":
            missing_fields.append(f"queries.{field}")
            validation_details.append(f"'queries.{field}' is missing or empty — expected: {description}")

    # ── Return clear error if anything is missing ────────────────────────────
    if missing_fields:
        logging.warning(f"Validation failed. Missing fields: {missing_fields}")
        return func.HttpResponse(
            body=json.dumps(
                {
                    "status": "FAILED",
                    "error": "Request failed due to missing or invalid input payload fields.",
                    "missing_fields": missing_fields,
                    "details": validation_details,
                    "hint": (
                        "Please provide all required fields. "
                        "Check 'missing_fields' for the list of missing inputs "
                        "and 'details' for what each field should contain."
                    ),
                },
                indent=2
            ),
            status_code=400,
            mimetype="application/json"
        )

    try:
        source_branch = str(body.get("sourceBranch", "") or "").strip() or "nonprod"
        parameters_str = str(body.get("parameters", "") or "").strip()
        path = str(req_body.get("path", "") or "").strip()
        logging.info(f"Received payload — sourceBranch: {source_branch}, path: {path}, buildDefId: {queries.get('buildDefId')}, account: {queries.get('account')}")
        
        build_def_id = str(queries.get("buildDefId", "") or "").strip() or "48"
        account = str(queries.get("account", "") or "").strip() or "STLA-LZ-DEVOPS"

        subscription_name = extract_subscription_name_from_params(parameters_str)
        build_def_name = get_build_definition_name(build_def_id)
        normalized_branch = normalize_branch(source_branch)
        project_name = parse_project_name(path)

        # Generate build ID (random 4-5 digit number to simulate real build IDs)
        build_id = int(uuid.uuid4().int % 100000)
        if build_id < 1000:
            build_id += 7000

        now_utc = datetime.now(timezone.utc)
        queue_time = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
        timestamp_display = now_utc.strftime("%a, %d %b %Y %H:%M:%S GMT")

        project_id = "ac3624cd-7a50-4e57-913d-ac36d92c2d86"

    except Exception as e:
        logging.error(f"Error processing request: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=400,
            mimetype="application/json"
        )

    mock_headers = {
        "Cache-Control": "no-store, no-cache",
        "Pragma": "no-cache",
        "Transfer-Encoding": "chunked",
        "Vary": "Accept-Encoding",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "x-ms-request-id": str(uuid.uuid4()),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "x-ms-environment-id": "55d60176ea225406",
        "x-ms-subscription-id": "4D7ABF2F-06F7-4912-93C0-C2C837032C73",
        "x-ms-dlp-re": "-|-",
        "x-ms-dlp-gu": "-|-",
        "x-ms-dlp-ef": "-|-/-|-|-|-",
        "x-ms-mip-sl": "-|-|-|-",
        "x-ms-au-caller-id": "859970b9-71a0-4ffa-8c37-53306431ea71",
        "x-ms-au-creator-id": "a5a92eec-ee65-4171-bc51-0d646c7b440f",
        "Timing-Allow-Origin": "*",
        "x-ms-apihub-cached-response": "true",
        "x-ms-apihub-obo": "false",
        "Date": timestamp_display,
        "Content-Type": "application/json; charset=utf-8",
        "Expires": "-1",
    }

    response = {
        "statusCode": 200,
        "headers": mock_headers,
        "body": {
            "id": build_id,
            "buildNumber": str(build_id),
            "sourceBranch": normalized_branch,
            "sourceVersion": None,
            "status": "notStarted",
            "priority": "normal",
            "queueTime": queue_time,
            "startTime": "0001-01-01T00:00:00",
            "finishTime": "0001-01-01T00:00:00",
            "reason": "manual",
            "result": None,
            "requestedFor": {
                "uniqueName": "prakash@stellantis.com"
            },
            "parameters": parameters_str,
            "definition": {
                "id": int(build_def_id),
                "name": build_def_name
            },
            "_links": {
                "web": {
                    "href": (
                        f"https://dev.azure.com/{account}/{project_id}/"
                        f"_build/results?buildId={build_id}"
                    )
                }
            },
            "input_subscription_name": subscription_name,
            "input_source_branch": source_branch,
            "input_build_def_id": build_def_id,
            "input_account": account,
        }
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=200,
        mimetype="application/json"
    )
