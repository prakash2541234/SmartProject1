import json
import random
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import azure.functions as func


PROJECT_ID = "ac3624cd-7a50-4e57-913d-ac36d92c2d86"
PROJECT_NAME = "AZGLZ_API_Platform"
DEFAULT_ACCOUNT = "STLA-LZ-DEVOPS"
DEFAULT_REPO_ID = "a562bf04-c7e6-432c-bc64-90ad8e5d7edf"
DEFAULT_REPO_NAME = "azglz_pipeline_network"


def _http_date_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_now_fractional() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_uri(uri: str) -> dict:
    if not uri:
        return {
            "account": DEFAULT_ACCOUNT,
            "project": PROJECT_NAME,
            "repo_id": DEFAULT_REPO_ID,
        }

    parsed = urlparse(uri)
    parts = [segment for segment in parsed.path.split("/") if segment]

    account = parts[0] if len(parts) > 0 else DEFAULT_ACCOUNT
    project = parts[1] if len(parts) > 1 else PROJECT_NAME

    repo_id = DEFAULT_REPO_ID
    if "repositories" in parts:
        idx = parts.index("repositories")
        if idx + 1 < len(parts):
            repo_id = parts[idx + 1]

    return {
        "account": account,
        "project": project,
        "repo_id": repo_id,
    }


def _try_parse_push_body(body_text: str) -> dict:
    if not isinstance(body_text, str) or not body_text.strip():
        return {}

    try:
        return json.loads(body_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _extract_old_object_id(push_body: dict, fallback_text: str) -> str:
    ref_updates = push_body.get("refUpdates", []) if isinstance(push_body, dict) else []
    if isinstance(ref_updates, list) and ref_updates:
        item = ref_updates[0] if isinstance(ref_updates[0], dict) else {}
        value = str(item.get("oldObjectId", "") or "").strip()
        if value:
            return value

    match = re.search(r'"oldObjectId"\s*:\s*"([a-f0-9]{40})"', fallback_text or "")
    if match:
        return match.group(1)

    return ""


def _extract_ref_name(push_body: dict, fallback_text: str) -> str:
    ref_updates = push_body.get("refUpdates", []) if isinstance(push_body, dict) else []
    if isinstance(ref_updates, list) and ref_updates:
        item = ref_updates[0] if isinstance(ref_updates[0], dict) else {}
        value = str(item.get("name", "") or "").strip()
        if value:
            return value

    match = re.search(r'"name"\s*:\s*"(refs/heads/[^"]+)"', fallback_text or "")
    if match:
        return match.group(1)

    return "refs/heads/nonprod"


def _extract_comment(push_body: dict, fallback_text: str) -> str:
    commits = push_body.get("commits", []) if isinstance(push_body, dict) else []
    if isinstance(commits, list) and commits:
        item = commits[0] if isinstance(commits[0], dict) else {}
        value = str(item.get("comment", "") or "").strip()
        if value:
            return value

    match = re.search(r'"comment"\s*:\s*"([^"]+)"', fallback_text or "")
    if match:
        return match.group(1)

    return "Commiting config file for sub unknown"


def _extract_subscription_id(push_body: dict, comment: str, fallback_text: str) -> str:
    uuid_pattern = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

    changes = []
    commits = push_body.get("commits", []) if isinstance(push_body, dict) else []
    if isinstance(commits, list) and commits:
        first = commits[0] if isinstance(commits[0], dict) else {}
        changes = first.get("changes", []) if isinstance(first, dict) else []

    if isinstance(changes, list) and changes:
        first_change = changes[0] if isinstance(changes[0], dict) else {}
        item = first_change.get("item", {}) if isinstance(first_change, dict) else {}
        path = str(item.get("path", "") or "")
        match = re.search(uuid_pattern, path)
        if match:
            return match.group(0)

    match = re.search(uuid_pattern, comment or "")
    if match:
        return match.group(0)

    match = re.search(uuid_pattern, fallback_text or "")
    if match:
        return match.group(0)

    return "00000000-0000-0000-0000-000000000000"


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

    method = str(body.get("Method", "") or "").strip().upper()
    if method and method != "POST":
        return func.HttpResponse(
            body=json.dumps({"error": "body.Method must be POST"}),
            status_code=400,
            mimetype="application/json",
        )

    uri = str(body.get("Uri", "") or "").strip()
    body_text = str(body.get("Body", "") or "")
    push_body = _try_parse_push_body(body_text)

    parsed = _parse_uri(uri)

    queries = req_body.get("queries", {})
    account = ""
    if isinstance(queries, dict):
        account = str(queries.get("account", "") or "").strip()
    if not account:
        account = parsed["account"]

    project = parsed["project"]
    repo_id = parsed["repo_id"]

    old_object_id = _extract_old_object_id(push_body, body_text)
    ref_name = _extract_ref_name(push_body, body_text)
    comment = _extract_comment(push_body, body_text)
    subscription_id = _extract_subscription_id(push_body, comment, body_text)

    commit_id = uuid.uuid4().hex[:40]
    tree_id = uuid.uuid4().hex[:40]
    push_id = random.randint(12000, 99999)
    now = _iso_now()

    response = {
        "statusCode": 201,
        "headers": {
            "Cache-Control": "no-store, no-cache",
            "Pragma": "no-cache",
            "Access-Control-Expose-Headers": "Request-Context",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "X-TFS-ProcessId": str(uuid.uuid4()),
            "ActivityId": str(uuid.uuid4()),
            "X-TFS-Session": str(uuid.uuid4()),
            "X-VSS-E2EID": str(uuid.uuid4()),
            "X-VSS-SenderDeploymentId": "1f18445b-609a-73c1-2ae2-521b74b4c11d",
            "X-VSS-UserData": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2:ta25845@stellantis.com",
            "X-Frame-Options": "SAMEORIGIN,DENY",
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
            "commits": [
                {
                    "treeId": tree_id,
                    "commitId": commit_id,
                    "author": {
                        "name": "Chura Prakash",
                        "email": "ta25845@stellantis.com",
                        "date": now,
                    },
                    "committer": {
                        "name": "Chura Prakash",
                        "email": "ta25845@stellantis.com",
                        "date": now,
                    },
                    "comment": comment,
                    "parents": [old_object_id] if old_object_id else [],
                    "url": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/git/repositories/{repo_id}/commits/{commit_id}",
                }
            ],
            "refUpdates": [
                {
                    "repositoryId": repo_id,
                    "name": ref_name,
                    "oldObjectId": old_object_id,
                    "newObjectId": commit_id,
                }
            ],
            "repository": {
                "id": repo_id,
                "name": DEFAULT_REPO_NAME,
                "url": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/git/repositories/{repo_id}",
                "project": {
                    "id": PROJECT_ID,
                    "name": project,
                    "url": f"https://dev.azure.com/{account}/_apis/projects/{PROJECT_ID}",
                    "state": "wellFormed",
                    "revision": 68,
                    "visibility": "private",
                    "lastUpdateTime": "2025-07-10T18:48:04.877Z",
                },
                "size": 72837,
                "remoteUrl": f"https://{account}@dev.azure.com/{account}/{project}/_git/{DEFAULT_REPO_NAME}",
                "sshUrl": f"git@ssh.dev.azure.com:v3/{account}/{project}/{DEFAULT_REPO_NAME}",
                "webUrl": f"https://dev.azure.com/{account}/{project}/_git/{DEFAULT_REPO_NAME}",
                "isDisabled": False,
                "isInMaintenance": False,
            },
            "pushedBy": {
                "displayName": "Chura Prakash",
                "url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "_links": {
                    "avatar": {
                        "href": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
                    }
                },
                "id": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "uniqueName": "ta25845@stellantis.com",
                "imageUrl": f"https://dev.azure.com/{account}/_api/_common/identityImage?id=acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "descriptor": "aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
            },
            "pushId": push_id,
            "date": _iso_now_fractional(),
            "url": f"https://dev.azure.com/{account}/{project}/_apis/git/repositories/{repo_id}/pushes/{push_id}",
            "_links": {
                "self": {
                    "href": f"https://dev.azure.com/{account}/{project}/_apis/git/repositories/{repo_id}/pushes/{push_id}",
                },
                "repository": {
                    "href": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/git/repositories/{repo_id}",
                },
                "commits": {
                    "href": f"https://dev.azure.com/{account}/_apis/git/repositories/{repo_id}/pushes/{push_id}/commits",
                },
                "pusher": {
                    "href": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                },
                "refs": {
                    "href": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/git/repositories/{repo_id}/refs/heads/nonprod",
                },
            },
            "input_subscription_id": subscription_id,
        },
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=201,
        mimetype="application/json",
    )
