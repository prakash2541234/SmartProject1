import json
import uuid
from datetime import datetime, timezone

import azure.functions as func


PROJECT_ID = "ac3624cd-7a50-4e57-913d-ac36d92c2d86"
DEFAULT_ACCOUNT = "STLA-LZ-DEVOPS"
DEFAULT_BUILD_DEF_ID = 54
DEFAULT_BUILD_DEF_NAME = "CI_azglz_pipeline_createnetwork_nonprod"


def _http_date_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _iso_now_fractional() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _normalize_branch(branch: str) -> str:
    branch = str(branch or "nonprod").strip()
    if branch.startswith("refs/"):
        return branch
    return f"refs/heads/{branch}"


def _extract_netconfig_filename(parameters_text: str) -> str:
    if not isinstance(parameters_text, str) or not parameters_text.strip():
        return ""

    try:
        payload = json.loads(parameters_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""

    if not isinstance(payload, dict):
        return ""

    value = payload.get("netconfig_filename")
    if value is None:
        return ""

    return str(value).strip()


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            body=json.dumps({"error": "Invalid JSON payload"}),
            status_code=400,
            mimetype="application/json",
        )

    if not isinstance(req_body, dict):
        return func.HttpResponse(
            body=json.dumps({"error": "Payload must be a JSON object"}),
            status_code=400,
            mimetype="application/json",
        )

    body = req_body.get("body", {})
    if not isinstance(body, dict):
        return func.HttpResponse(
            body=json.dumps({"error": "'body' must be an object"}),
            status_code=400,
            mimetype="application/json",
        )

    queries = req_body.get("queries", {})
    if not isinstance(queries, dict):
        queries = {}

    account = str(queries.get("account", "") or "").strip() or DEFAULT_ACCOUNT

    build_def_id_text = str(queries.get("buildDefId", "") or "").strip() or str(DEFAULT_BUILD_DEF_ID)
    try:
        build_def_id = int(build_def_id_text)
    except ValueError:
        build_def_id = DEFAULT_BUILD_DEF_ID

    source_branch_input = str(body.get("sourceBranch", "") or "").strip() or "nonprod"
    source_branch = _normalize_branch(source_branch_input)

    parameters_text = str(body.get("parameters", "") or "").strip()
    netconfig_filename = _extract_netconfig_filename(parameters_text)

    build_id = 7482
    queue_time = _iso_now_fractional()

    response = {
        "statusCode": 200,
        "headers": {
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
            "Date": _http_date_now(),
            "Content-Type": "application/json; charset=utf-8",
            "Expires": "-1",
        },
        "body": {
            "id": build_id,
            "buildNumber": str(build_id),
            "sourceBranch": source_branch,
            "sourceVersion": None,
            "status": "notStarted",
            "priority": "normal",
            "queueTime": queue_time,
            "startTime": "0001-01-01T00:00:00",
            "finishTime": "0001-01-01T00:00:00",
            "reason": "manual",
            "result": None,
            "requestedFor": {
                "uniqueName": "prakashmc@stellantis.com",
            },
            "parameters": parameters_text,
            "definition": {
                "id": build_def_id,
                "name": DEFAULT_BUILD_DEF_NAME,
            },
            "_links": {
                "web": {
                    "href": f"https://dev.azure.com/{account}/{PROJECT_ID}/_build/results?buildId={build_id}",
                }
            },
            "input_netconfig_filename": netconfig_filename,
        },
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=200,
        mimetype="application/json",
    )
