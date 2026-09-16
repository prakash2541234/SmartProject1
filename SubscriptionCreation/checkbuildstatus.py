import json
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import azure.functions as func


PROJECT_ID = "ac3624cd-7a50-4e57-913d-ac36d92c2d86"
DEFAULT_PROJECT_NAME = "AZGLZ_API_Platform"
DEFAULT_REPOSITORY_ID = "b18e1d14-4276-4b41-b4e0-193000f45566"
DEFAULT_REPOSITORY_NAME = "azglz_pipeline_createsub"
DEFAULT_BUILD_DEFINITION_ID = 48
DEFAULT_BUILD_DEFINITION_NAME = "CI_azglz_pipeline_createsub_nonprod"

BUILD_PROFILES = {
    7482: {
        "definition_id": 54,
        "definition_name": "CI_azglz_pipeline_createnetwork_nonprod",
        "repository_id": "a562bf04-c7e6-432c-bc64-90ad8e5d7edf",
        "repository_name": "azglz_pipeline_network",
        "parameters": json.dumps(
            {"netconfig_filename": "ae2f7f34-3754-4867-942f-fdd4766beefd"},
            separators=(",", ":"),
        ),
        "source_version": "14c7dd80d2b1903dfc86bf3ed7bc8b4b316946ac",
    },
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def _http_date_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _parse_build_uri(uri: str) -> dict:
    if not uri:
        return {
            "organization": "",
            "project_name": DEFAULT_PROJECT_NAME,
            "build_id": 0,
        }

    parsed = urlparse(uri)
    parts = [segment for segment in parsed.path.split("/") if segment]

    organization = parts[0] if len(parts) > 0 else ""
    project_name = parts[1] if len(parts) > 1 else DEFAULT_PROJECT_NAME

    build_id = 0
    if "builds" in parts:
        idx = parts.index("builds")
        if idx + 1 < len(parts):
            build_part = parts[idx + 1]
            try:
                build_id = int(re.sub(r"[^0-9]", "", build_part) or 0)
            except ValueError:
                build_id = 0

    return {
        "organization": organization,
        "project_name": project_name,
        "build_id": build_id,
    }


def _build_definition_name(definition_id: int) -> str:
    mapping = {
        48: "CI_azglz_pipeline_createsub_nonprod",
        54: "CI_azglz_pipeline_createnetwork_nonprod",
    }
    return mapping.get(definition_id, f"CI_Pipeline_{definition_id}")


def _build_profile(build_id: int) -> dict:
    profile = BUILD_PROFILES.get(build_id)
    if profile:
        return profile

    return {
        "definition_id": DEFAULT_BUILD_DEFINITION_ID,
        "definition_name": DEFAULT_BUILD_DEFINITION_NAME,
        "repository_id": DEFAULT_REPOSITORY_ID,
        "repository_name": DEFAULT_REPOSITORY_NAME,
        "parameters": json.dumps({"subscription_name": ""}, separators=(",", ":")),
        "source_version": uuid.uuid4().hex[:40],
    }


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Check Build Status function triggered")

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

    connector_body = req_body.get("body", {})
    if not isinstance(connector_body, dict):
        return func.HttpResponse(
            body=json.dumps({"error": "'body' must be an object"}),
            status_code=400,
            mimetype="application/json",
        )

    uri = str(connector_body.get("Uri", "") or "").strip()
    method = str(connector_body.get("Method", "") or "").strip().upper()
    if method and method != "GET":
        return func.HttpResponse(
            body=json.dumps({"error": "body.Method must be GET"}),
            status_code=400,
            mimetype="application/json",
        )

    uri_info = _parse_build_uri(uri)

    queries = req_body.get("queries", {})
    account = ""
    if isinstance(queries, dict):
        account = str(queries.get("account", "") or "").strip()

    if not account:
        account = uri_info["organization"] or "STLA-LZ-DEVOPS"

    project_name = uri_info["project_name"] or DEFAULT_PROJECT_NAME
    build_id = uri_info["build_id"]
    if build_id <= 0:
        build_id = 7000

    now_iso = _iso_now()

    queue_time = now_iso
    start_time = now_iso
    last_changed_date = now_iso

    source_branch = "refs/heads/nonprod"
    plan_id = str(uuid.uuid4())

    profile = _build_profile(build_id)
    definition_id = profile["definition_id"]
    definition_name = profile.get("definition_name") or _build_definition_name(definition_id)
    parameters = profile["parameters"]
    source_version = profile["source_version"]
    repository_id = profile["repository_id"]
    repository_name = profile["repository_name"]

    status = "completed"

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
            "X-VSS-UserData": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2:SG07341@stellantis.com",
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
            "Content-Type": "application/json; charset=utf-8; api-version=7.2-preview.7",
            "Expires": "-1",
        },
        "body": {
            "_links": {
                "self": {
                    "href": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/build/Builds/{build_id}",
                },
                "web": {
                    "href": f"https://dev.azure.com/{account}/{PROJECT_ID}/_build/results?buildId={build_id}",
                },
                "sourceVersionDisplayUri": {
                    "href": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/build/builds/{build_id}/sources",
                },
                "timeline": {
                    "href": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/build/builds/{build_id}/Timeline",
                },
                "badge": {
                    "href": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/build/status/{definition_id}",
                },
            },
            "properties": {},
            "tags": [],
            "validationResults": [],
            "plans": [
                {
                    "planId": plan_id,
                }
            ],
            "triggerInfo": {},
            "id": build_id,
            "buildNumber": str(build_id),
            "status": status,
            "queueTime": queue_time,
            "startTime": start_time,
            "url": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/build/Builds/{build_id}",
            "definition": {
                "drafts": [],
                "id": definition_id,
                "name": definition_name,
                "url": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/build/Definitions/{definition_id}?revision=2",
                "uri": f"vstfs:///Build/Definition/{definition_id}",
                "path": "\\CI_Pipelines",
                "type": "build",
                "queueStatus": "enabled",
                "revision": 2,
                "project": {
                    "id": PROJECT_ID,
                    "name": project_name,
                    "url": f"https://dev.azure.com/{account}/_apis/projects/{PROJECT_ID}",
                    "state": "wellFormed",
                    "revision": 68,
                    "visibility": "private",
                    "lastUpdateTime": "2025-07-10T18:48:04.877Z",
                },
            },
            "project": {
                "id": PROJECT_ID,
                "name": project_name,
                "url": f"https://dev.azure.com/{account}/_apis/projects/{PROJECT_ID}",
                "state": "wellFormed",
                "revision": 68,
                "visibility": "private",
                "lastUpdateTime": "2025-07-10T18:48:04.877Z",
            },
            "uri": f"vstfs:///Build/Build/{build_id}",
            "sourceBranch": source_branch,
            "sourceVersion": source_version,
            "queue": {
                "id": 63,
                "name": "Azure Pipelines",
                "pool": {
                    "id": 9,
                    "name": "Azure Pipelines",
                    "isHosted": True,
                },
            },
            "priority": "normal",
            "reason": "manual",
            "requestedFor": {
                "displayName": "SANDEEP RAO",
                "url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "_links": {
                    "avatar": {
                        "href": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
                    }
                },
                "id": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "uniqueName": "SG07341@stellantis.com",
                "imageUrl": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
                "descriptor": "aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
            },
            "requestedBy": {
                "displayName": "SANDEEP RAO",
                "url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "_links": {
                    "avatar": {
                        "href": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
                    }
                },
                "id": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "uniqueName": "SG07341@stellantis.com",
                "imageUrl": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
                "descriptor": "aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
            },
            "lastChangedDate": last_changed_date,
            "lastChangedBy": {
                "displayName": "Microsoft.VisualStudio.Services.TFS",
                "url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/00000002-0000-8888-8000-000000000000",
                "_links": {
                    "avatar": {
                        "href": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/s2s.MDAwMDAwMDItMDAwMC04ODg4LTgwMDAtMDAwMDAwMDAwMDAwQDJjODk1OTA4LTA0ZTAtNDk1Mi04OWZkLTU0YjAwNDZkNjI4OA",
                    }
                },
                "id": "00000002-0000-8888-8000-000000000000",
                "uniqueName": "00000002-0000-8888-8000-000000000000@2c895908-04e0-4952-89fd-54b0046d6288",
                "imageUrl": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/s2s.MDAwMDAwMDItMDAwMC04ODg4LTgwMDAtMDAwMDAwMDAwMDAwQDJjODk1OTA4LTA0ZTAtNDk1Mi04OWZkLTU0YjAwNDZkNjI4OA",
                "descriptor": "s2s.MDAwMDAwMDItMDAwMC04ODg4LTgwMDAtMDAwMDAwMDAwMDAwQDJjODk1OTA4LTA0ZTAtNDk1Mi04OWZkLTU0YjAwNDZkNjI4OA",
            },
            "parameters": parameters,
            "orchestrationPlan": {
                "planId": plan_id,
            },
            "logs": {
                "id": 0,
                "type": "Container",
                "url": f"https://dev.azure.com/{account}/{PROJECT_ID}/_apis/build/builds/{build_id}/logs",
            },
            "repository": {
                "id": repository_id,
                "type": "TfsGit",
                "name": repository_name,
                "url": f"https://dev.azure.com/{account}/{project_name}/_git/{repository_name}",
                "clean": None,
                "checkoutSubmodules": False,
            },
            "retainedByRelease": False,
            "triggeredByBuild": None,
            "appendCommitMessageToRunName": True,
        },
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=200,
        mimetype="application/json",
    )
