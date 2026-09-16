import json
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import azure.functions as func


PROJECT_ID = "ac3624cd-7a50-4e57-913d-ac36d92c2d86"
DEFAULT_PROJECT_NAME = "AZGLZ_API_Platform"
DEFAULT_ACCOUNT = "STLA-LZ-DEVOPS"
DEFAULT_REPO_ID = "a562bf04-c7e6-432c-bc64-90ad8e5d7edf"
DEFAULT_REPO_NAME = "azglz_pipeline_network"
DEFAULT_METHOD = "GET"
DEFAULT_RELATIVE_URI = (
    "https://dev.azure.com/STLA-LZ-DEVOPS/AZGLZ_API_Platform/_apis/git/"
    "repositories/a562bf04-c7e6-432c-bc64-90ad8e5d7edf/commits?"
    "searchCriteria.$top=1&searchCriteria.itemVersion.version=nonprod"
)


def _http_date_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_first_present(req_body: dict, *field_names: str) -> str:
    for field_name in field_names:
        value = req_body.get(field_name)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return ""


def _parse_devops_uri(uri: str, branch: str = None, project_name: str = None) -> dict:
    if not uri:
        return {
            "account": DEFAULT_ACCOUNT,
            "project": project_name or DEFAULT_PROJECT_NAME,
            "repo_id": DEFAULT_REPO_ID,
            "branch": branch or "nonprod",
            "top": "1",
        }

    parsed = urlparse(uri)
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    account = parts[0] if len(parts) > 0 else DEFAULT_ACCOUNT
    project = project_name or (parts[1] if len(parts) > 1 else DEFAULT_PROJECT_NAME)

    repo_id = DEFAULT_REPO_ID
    if "repositories" in parts:
        idx = parts.index("repositories")
        if idx + 1 < len(parts):
            repo_id = parts[idx + 1]

    return {
        "account": account,
        "project": project,
        "repo_id": repo_id,
        "branch": branch or query.get("searchCriteria.itemVersion.version", ["nonprod"])[0],
        "top": query.get("searchCriteria.$top", ["1"])[0],
    }


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

    organization_name = _get_first_present(
        req_body,
        "Organization Name",
        "organization_name",
        "account",
    ) or DEFAULT_ACCOUNT
    method = _get_first_present(req_body, "Method", "method") or DEFAULT_METHOD
    relative_uri = _get_first_present(
        req_body,
        "Relative URI",
        "RelativeUri",
        "relative_uri",
        "Uri",
        "uri",
    ) or DEFAULT_RELATIVE_URI

    if method.upper() != DEFAULT_METHOD:
        return func.HttpResponse(
            body=json.dumps(
                {
                    "status": "FAILED",
                    "error": "Method must be GET.",
                    "expected": DEFAULT_METHOD,
                    "received": method,
                },
                indent=2,
            ),
            status_code=400,
            mimetype="application/json",
        )

    uri_info = _parse_devops_uri(relative_uri)

    account = organization_name or uri_info["account"] or DEFAULT_ACCOUNT
    repo_id = uri_info["repo_id"]
    project = uri_info["project"]
    branch_final = uri_info["branch"]
    top = uri_info["top"]

    commit_id = uuid.uuid4().hex[:40]

    response = {
        "statusCode": 200,
        "headers": {
            "Cache-Control": "no-store, no-cache",
            "Pragma": "no-cache",
            "Transfer-Encoding": "chunked",
            "Vary": "Accept-Encoding",
            "Access-Control-Expose-Headers": "Request-Context",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "X-TFS-ProcessId": str(uuid.uuid4()),
            "ActivityId": str(uuid.uuid4()),
            "X-TFS-Session": str(uuid.uuid4()),
            "X-VSS-E2EID": str(uuid.uuid4()),
            "X-VSS-SenderDeploymentId": "1f18445b-609a-73c1-2ae2-521b74b4c11d",
            "X-VSS-UserData": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2:prakashmc@stellantis.com",
            "X-Frame-Options": "SAMEORIGIN,DENY",
            "Link": f"<{commit_id}>;rel=\"startingCommitId\",<https://dev.azure.com/_apis/git/repositories/{repo_id}/commits>;rel=\"next\"",
            "Request-Context": "appId=cid-v1:0cc0e688-cf14-42b5-9911-f427a40700f1",
            "X-Content-Type-Options": "nosniff,nosniff",
            "X-Cache": "CONFIG_NOCACHE",
            "x-ms-request-id": str(uuid.uuid4()),
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
            "Content-Type": "application/json; charset=utf-8; api-version=7.1",
            "Expires": "-1",
        },
        "body": {
            "count": 1,
            "organization_name": account,
            "method": method.upper(),
            "relative_uri": relative_uri,
            "repository_name": DEFAULT_REPO_NAME,
            "branch": branch_final,
            "project": project,
            "top": top,
            "value": [
                {
                    "commitId": commit_id,
                    "author": {
                        "name": "Chura Prakash",
                        "email": "prakashmc@stellantis.com",
                        "date": _iso_now(),
                    },
                    "committer": {
                        "name": "Chura Prakash",
                        "email": "prakashmc@stellantis.com",
                        "date": _iso_now(),
                    },
                    "comment": f"Commiting config file for organization {account}",
                    "changeCounts": {
                        "Add": 1,
                        "Edit": 0,
                        "Delete": 0,
                    },
                    "url": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/git/repositories/{repo_id}/commits/{commit_id}",
                    "remoteUrl": f"https://dev.azure.com/{account}/{project}/_git/{DEFAULT_REPO_NAME}/commit/{commit_id}",
                }
            ],
        },
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=200,
        mimetype="application/json",
    )
