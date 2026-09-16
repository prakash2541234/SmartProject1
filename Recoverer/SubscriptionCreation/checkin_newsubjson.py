import logging
import json
import uuid
import re
from datetime import datetime, timezone
import azure.functions as func


def extract_subscription_name(body_dict: dict) -> str:
    """Extract subscription name from Body's comment field."""
    body_str = body_dict.get("Body", "")
    if isinstance(body_str, str):
        match = re.search(r'commiting subscription ([\w\-]+) json', body_str)
        if match:
            return match.group(1)
    return "unknown-sub"


def extract_file_path_name(body_dict: dict) -> str:
    """Extract subscription name from file path in Body."""
    body_str = body_dict.get("Body", "")
    if isinstance(body_str, str):
        match = re.search(r'/subscriptions-data/([\w\-]+)\.json', body_str)
        if match:
            return match.group(1)
    return "unknown-sub"


def parse_uri(uri: str) -> dict:
    """Parse DevOps API URI to extract organization, project, repo, branch."""
    if not uri:
        return {
            "organization": "mock-org",
            "project": "mock-project",
            "repository_id": "mock-repo",
            "branch": "main",
        }

    parts = uri.split("/")
    organization = ""
    project = ""
    repository_id = ""
    
    try:
        if "dev.azure.com" in uri:
            organization = parts[3]
            project = parts[4]
            
            if "repositories" in parts:
                repo_index = parts.index("repositories")
                if repo_index + 1 < len(parts):
                    repository_id = parts[repo_index + 1].split("?")[0]
    except (IndexError, ValueError):
        pass

    return {
        "organization": organization or "mock-org",
        "project": project or "mock-project",
        "repository_id": repository_id or "mock-repo",
        "branch": "nonprod",
    }


def extract_old_object_id(body_dict: dict) -> str:
    """Extract oldObjectId from Body's refUpdates."""
    body_str = body_dict.get("Body", "")
    if isinstance(body_str, str):
        match = re.search(r'"oldObjectId":\s*"([a-f0-9]+)"', body_str)
        if match:
            return match.group(1)
    return ""


def extract_base64_content(body_dict: dict) -> str:
    """Extract base64 content from Body's newContent."""
    body_str = body_dict.get("Body", "")
    if isinstance(body_str, str):
        match = re.search(r'"content":\s*"([A-Za-z0-9+/=]+)"', body_str)
        if match:
            return match.group(1)
    return ""


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Checkin New Subscription JSON function triggered.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON payload"}),
            status_code=400,
            mimetype="application/json"
        )

    if not isinstance(req_body, dict):
        return func.HttpResponse(
            json.dumps({"error": "Payload must be a JSON object"}),
            status_code=400,
            mimetype="application/json"
        )

    # Validate required fields
    required_fields = {
        "subscription_name": str,
        "subscription_mgmtgroup": str,
        "subscription_tags": dict,
        "commitId": str,
        "commit_comment": str,
    }

    missing_fields = []
    for field, expected_type in required_fields.items():
        if field not in req_body:
            missing_fields.append(field)
            continue

        value = req_body.get(field)
        if not isinstance(value, expected_type):
            missing_fields.append(f"{field} (expected {expected_type.__name__})")
            continue

        if expected_type is str and not str(value).strip():
            missing_fields.append(field)
        if expected_type is dict and not value:
            missing_fields.append(field)

    if missing_fields:
        return func.HttpResponse(
            body=json.dumps({
                "error": "runing got failed, because of missing field",
                "missing_payload": missing_fields
            }),
            status_code=400,
            mimetype="application/json",
        )

    try:
        # Extract payload values
        subscription_name = str(req_body.get("subscription_name", "")).strip()
        subscription_mgmtgroup = str(req_body.get("subscription_mgmtgroup", "")).strip()
        subscription_tags = req_body.get("subscription_tags", {})
        commit_id_old = str(req_body.get("commitId", "")).strip()
        commit_comment = str(req_body.get("commit_comment", "")).strip()

        # Extract environment from subscription_tags
        environment = ""
        if isinstance(subscription_tags, dict):
            environment = str(subscription_tags.get("stla_environment", "")).strip().lower()

        new_commit_id = uuid.uuid4().hex
        tree_id = uuid.uuid4().hex
        push_id = int(uuid.uuid4().int % 100000)

        now_utc = datetime.now(timezone.utc)
        timestamp_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
        timestamp_display = now_utc.strftime("%a, %d %b %Y %H:%M:%S GMT")

        # Set defaults for DevOps info
        account = "STLA-LZ-DEVOPS"
        project_info = {
            "organization": account,
            "project": "AZGLZ_API_Platform",
            "repository_id": "a562bf04-c7e6-432c-bc64-90ad8e5d7edf",
            "branch": environment or "nonprod",
        }

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
        "Access-Control-Expose-Headers": "Request-Context",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-TFS-ProcessId": str(uuid.uuid4()),
        "ActivityId": str(uuid.uuid4()),
        "X-TFS-Session": str(uuid.uuid4()),
        "X-VSS-E2EID": str(uuid.uuid4()),
        "X-VSS-SenderDeploymentId": "1f18445b-609a-73c1-2ae2-521b74b4c11d",
        "X-VSS-UserData": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2:SG07341@stellantis.com",
        "X-Frame-Options": "SAMEORIGIN,DENY",
        "Request-Context": "appId=cid-v1:0cc0e688-cf14-42b5-9911-f427a40700f1",
        "X-Content-Type-Options": "nosniff,nosniff",
        "X-Cache": "CONFIG_NOCACHE",
        "Date": timestamp_display,
        "Content-Type": "application/json; charset=utf-8; api-version=7.1",
        "Expires": "-1",
    }

    project_id = "ac3624cd-7a50-4e57-913d-ac36d92c2d86"
    repo_id = project_info["repository_id"]
    repo_name = "azglz_pipeline_createsub"

    response = {
        "statusCode": 201,
        "headers": mock_headers,
        "body": {
            "commits": [
                {
                    "treeId": tree_id,
                    "commitId": new_commit_id,
                    "author": {
                        "name": "Chura Prakash",
                        "email": "prakash@stellantis.com",
                        "date": timestamp_iso,
                    },
                    "committer": {
                        "name": "Chura Prakash",
                        "email": "prakash@stellantis.com",
                        "date": timestamp_iso,
                    },
                    "comment": commit_comment,
                    "parents": [commit_id_old] if commit_id_old else [],
                    "url": (
                        f"https://dev.azure.com/{account}/{project_id}"
                        f"/_apis/git/repositories/{repo_id}/commits/{new_commit_id}"
                    ),
                    "input_subscription_name": subscription_name,
                    "input_subscription_mgmtgroup": subscription_mgmtgroup,
                    "input_environment": environment or "nonprod",
                }
            ],
            "refUpdates": [
                {
                    "repositoryId": repo_id,
                    "name": f"refs/heads/{environment or 'nonprod'}",
                    "oldObjectId": commit_id_old,
                    "newObjectId": new_commit_id,
                }
            ],
            "repository": {
                "id": repo_id,
                "name": repo_name,
                "url": (
                    f"https://dev.azure.com/{account}/{project_id}"
                    f"/_apis/git/repositories/{repo_id}"
                ),
                "project": {
                    "id": project_id,
                    "name": project_info["project"],
                    "url": (
                        f"https://dev.azure.com/{account}/_apis/projects/{project_id}"
                    ),
                    "state": "wellFormed",
                    "revision": 68,
                    "visibility": "private",
                    "lastUpdateTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z",
                },
                "size": 94346,
                "remoteUrl": (
                    f"https://{account}@dev.azure.com/{account}/{project_info['project']}"
                    f"/_git/{repo_name}"
                ),
                "sshUrl": (
                    f"prakash.dev.azure.com:v3/{account}/{project_info['project']}/{repo_name}"
                ),
                "webUrl": (
                    f"https://dev.azure.com/{account}/{project_info['project']}/_git/{repo_name}"
                ),
                "isDisabled": False,
                "isInMaintenance": False,
            },
            "pushedBy": {
                "displayName": "Chura Prakash",
                "url": (
                    "https://spsprodneu1.vssps.visualstudio.com/"
                    "A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/"
                    "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2"
                ),
                "_links": {
                    "avatar": {
                        "href": (
                            f"https://dev.azure.com/{account}"
                            "/_apis/GraphProfile/MemberAvatars/"
                            "aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy"
                        )
                    }
                },
                "id": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "uniqueName": "SG07341@stellantis.com",
                "imageUrl": (
                    f"https://dev.azure.com/{account}/_api/_common/identityImage"
                    "?id=acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2"
                ),
                "descriptor": "aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
            },
            "pushId": push_id,
            "date": timestamp_iso,
            "url": (
                f"https://dev.azure.com/{account}/{project_info['project']}"
                f"/_apis/git/repositories/{repo_id}/pushes/{push_id}"
            ),
            "_links": {
                "self": {
                    "href": (
                        f"https://dev.azure.com/{account}/{project_info['project']}"
                        f"/_apis/git/repositories/{repo_id}/pushes/{push_id}"
                    )
                },
                "repository": {
                    "href": (
                        f"https://dev.azure.com/{account}/{project_id}"
                        f"/_apis/git/repositories/{repo_id}"
                    )
                },
                "commits": {
                    "href": (
                        f"https://dev.azure.com/{account}/_apis/git/repositories"
                        f"/{repo_id}/pushes/{push_id}/commits"
                    )
                },
                "pusher": {
                    "href": (
                        "https://spsprodneu1.vssps.visualstudio.com/"
                        "A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/"
                        "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2"
                    )
                },
                "refs": {
                    "href": (
                        f"https://dev.azure.com/{account}/{project_id}"
                        f"/_apis/git/repositories/{repo_id}/refs/heads/{environment or 'nonprod'}"
                    )
                },
            },
        },
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=201,
        mimetype="application/json"
    )
