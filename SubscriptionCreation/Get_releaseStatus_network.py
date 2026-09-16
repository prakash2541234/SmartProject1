import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import azure.functions as func


PROJECT_ID = "ac3624cd-7a50-4e57-913d-ac36d92c2d86"
PROJECT_NAME = "AZGLZ_API_Platform"
RELEASE_DEF_ID = 7
RELEASE_DEF_NAME = "Release_azglz_pipeline_createnetwork_nonprod"
BUILD_DEF_ID = 54
BUILD_DEF_NAME = "CI_azglz_pipeline_createnetwork_nonprod"
BUILD_ID = 7482
REPOSITORY_ID = "a562bf04-c7e6-432c-bc64-90ad8e5d7edf"
REPOSITORY_NAME = "azglz_pipeline_network"
NETWORKCONFIG_FILENAME = "ae2f7f34-3754-4867-942f-fdd4766beefd"
SOURCE_VERSION = "14c7dd80d2b1903dfc86bf3ed7bc8b4b316946ac"
USER_ID = "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2"
USER_NAME = "Chura Prakash"
USER_UNIQUE = "ta25845@stellantis.com"


def _http_date_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def _parse_uri(uri: str) -> dict:
    if not uri:
        return {
            "account": "STLA-LZ-DEVOPS",
            "project": PROJECT_NAME,
            "release_id": 169,
        }

    parsed = urlparse(uri)
    parts = [segment for segment in parsed.path.split("/") if segment]

    account = parts[0] if len(parts) > 0 else "STLA-LZ-DEVOPS"
    project = parts[1] if len(parts) > 1 else PROJECT_NAME

    release_id = 169
    if "releases" in parts:
        idx = parts.index("releases")
        if idx + 1 < len(parts):
            value = re.sub(r"[^0-9]", "", parts[idx + 1])
            if value:
                release_id = int(value)

    return {
        "account": account,
        "project": project,
        "release_id": release_id,
    }


def _identity(account: str) -> dict:
    avatar = f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy"
    return {
        "displayName": USER_NAME,
        "url": f"https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/{USER_ID}",
        "_links": {"avatar": {"href": avatar}},
        "id": USER_ID,
        "uniqueName": USER_UNIQUE,
        "imageUrl": avatar,
        "descriptor": "aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
    }


def _release_profile(release_id: int) -> dict:
    if release_id == 169:
        return {
            "release_name": "Release-9",
            "env_id": 176,
            "approval_id": 500,
            "deploy_step_id": 501,
            "deployment_id": 179,
            "phase_id": 177,
            "definition_environment_id": 9,
        }

    return {
        "release_name": f"Release-{max(1, release_id - 160)}",
        "env_id": release_id + 7,
        "approval_id": release_id + 331,
        "deploy_step_id": release_id + 332,
        "deployment_id": release_id + 10,
        "phase_id": release_id + 8,
        "definition_environment_id": 9,
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

    body = req_body.get("body", {})
    if not isinstance(body, dict):
        return func.HttpResponse(
            body=json.dumps({"error": "'body' must be an object"}),
            status_code=400,
            mimetype="application/json",
        )

    method = str(body.get("Method", "") or "").strip().upper()
    if method and method != "GET":
        return func.HttpResponse(
            body=json.dumps({"error": "body.Method must be GET"}),
            status_code=400,
            mimetype="application/json",
        )

    uri = str(body.get("Uri", "") or "").strip()
    uri_data = _parse_uri(uri)

    queries = req_body.get("queries", {})
    account = ""
    if isinstance(queries, dict):
        account = str(queries.get("account", "") or "").strip()
    if not account:
        account = uri_data["account"]

    project = uri_data["project"] or PROJECT_NAME
    release_id = uri_data["release_id"]

    profile = _release_profile(release_id)
    release_name = profile["release_name"]
    env_id = profile["env_id"]
    approval_id = profile["approval_id"]
    deploy_step_id = profile["deploy_step_id"]
    deployment_id = profile["deployment_id"]
    phase_id = profile["phase_id"]
    definition_environment_id = profile["definition_environment_id"]

    now = _iso_now()
    run_plan_id = str(uuid.uuid4())

    vsrm_release = f"https://vsrm.dev.azure.com/{account}/{PROJECT_ID}/_apis/Release/releases/{release_id}"
    web_release = f"https://dev.azure.com/{account}/{PROJECT_ID}/_release?releaseId={release_id}&_a=release-summary"
    vsrm_release_def = f"https://vsrm.dev.azure.com/{account}/{PROJECT_ID}/_apis/Release/definitions/{RELEASE_DEF_ID}"
    web_release_def = f"https://dev.azure.com/{account}/{PROJECT_ID}/_release?definitionId={RELEASE_DEF_ID}"

    identity = _identity(account)

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
            "X-VSS-SenderDeploymentId": "8f621d6f-32f0-25f9-a53c-de2f5a56c371",
            "X-VSS-UserData": f"{USER_ID}:{USER_UNIQUE}",
            "X-Frame-Options": "SAMEORIGIN,DENY",
            "Request-Context": "appId=cid-v1:fcc1f6d7-bc4e-4041-a931-269cb5b8a31b",
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
            "id": release_id,
            "name": release_name,
            "status": "active",
            "createdOn": now,
            "modifiedOn": now,
            "modifiedBy": identity,
            "createdBy": identity,
            "createdFor": identity,
            "environments": [
                {
                    "id": env_id,
                    "releaseId": release_id,
                    "name": "Terraform Apply",
                    "status": "succeeded",
                    "variables": {},
                    "variableGroups": [],
                    "preDeployApprovals": [
                        {
                            "id": approval_id,
                            "revision": 1,
                            "approvalType": "preDeploy",
                            "createdOn": now,
                            "modifiedOn": now,
                            "status": "approved",
                            "comments": "",
                            "isAutomated": True,
                            "isNotificationOn": False,
                            "trialNumber": 1,
                            "attempt": 1,
                            "rank": 1,
                            "release": {"id": release_id, "name": release_name, "url": vsrm_release, "_links": {}},
                            "releaseDefinition": {
                                "id": RELEASE_DEF_ID,
                                "name": RELEASE_DEF_NAME,
                                "path": "\\azglz_pipelines_release",
                                "projectReference": None,
                                "url": vsrm_release_def,
                                "_links": {},
                            },
                            "releaseEnvironment": {
                                "id": env_id,
                                "name": "Terraform Apply",
                                "url": f"{vsrm_release}/environments/{env_id}",
                                "_links": {},
                            },
                            "url": f"https://vsrm.dev.azure.com/{account}/{PROJECT_ID}/_apis/Release/approvals/{approval_id}",
                        }
                    ],
                    "postDeployApprovals": [],
                    "preApprovalsSnapshot": {
                        "approvals": [{"rank": 1, "isAutomated": True, "isNotificationOn": False, "id": 0}],
                        "approvalOptions": {
                            "requiredApproverCount": None,
                            "releaseCreatorCanBeApprover": False,
                            "autoTriggeredAndPreviousEnvironmentApprovedCanBeSkipped": False,
                            "enforceIdentityRevalidation": False,
                            "timeoutInMinutes": 0,
                            "executionOrder": "beforeGates",
                        },
                    },
                    "postApprovalsSnapshot": {
                        "approvals": [{"rank": 1, "isAutomated": True, "isNotificationOn": False, "id": 0}],
                        "approvalOptions": {
                            "requiredApproverCount": None,
                            "releaseCreatorCanBeApprover": False,
                            "autoTriggeredAndPreviousEnvironmentApprovedCanBeSkipped": False,
                            "enforceIdentityRevalidation": False,
                            "timeoutInMinutes": 0,
                            "executionOrder": "afterSuccessfulGates",
                        },
                    },
                    "deploySteps": [
                        {
                            "id": deploy_step_id,
                            "deploymentId": deployment_id,
                            "attempt": 1,
                            "reason": "automated",
                            "status": "inProgress",
                            "operationStatus": "PhaseInProgress",
                            "releaseDeployPhases": [
                                {
                                    "id": phase_id,
                                    "phaseId": str(phase_id),
                                    "name": "Agent job",
                                    "rank": 1,
                                    "phaseType": "agentBasedDeployment",
                                    "status": "inProgress",
                                    "runPlanId": run_plan_id,
                                    "deploymentJobs": [
                                        {
                                            "job": {
                                                "id": 0,
                                                "timelineRecordId": str(uuid.uuid4()),
                                                "name": "Agent job",
                                                "status": "pending",
                                                "rank": 1,
                                                "issues": [],
                                                "logUrl": "",
                                            },
                                            "tasks": [],
                                        }
                                    ],
                                    "manualInterventions": [],
                                    "startedOn": now,
                                }
                            ],
                            "requestedBy": identity,
                            "requestedFor": identity,
                            "queuedOn": now,
                            "lastModifiedBy": {
                                "displayName": "Microsoft.VisualStudio.Services.ReleaseManagement",
                                "id": "0000000d-0000-8888-8000-000000000000",
                                "uniqueName": "0000000d-0000-8888-8000-000000000000@2c895908-04e0-4952-89fd-54b0046d6288",
                                "descriptor": "s2s.MDAwMDAwMGQtMDAwMC04ODg4LTgwMDAtMDAwMDAwMDAwMDAwQDJjODk1OTA4LTA0ZTAtNDk1Mi04OWZkLTU0YjAwNDZkNjI4OA",
                            },
                            "lastModifiedOn": now,
                            "hasStarted": True,
                            "tasks": [],
                            "runPlanId": "00000000-0000-0000-0000-000000000000",
                            "issues": [],
                        }
                    ],
                    "rank": 1,
                    "definitionEnvironmentId": definition_environment_id,
                    "environmentOptions": {
                        "emailNotificationType": "OnlyOnFailure",
                        "emailRecipients": "release.environment.owner;release.creator",
                        "skipArtifactsDownload": False,
                        "timeoutInMinutes": 0,
                        "enableAccessToken": False,
                        "publishDeploymentStatus": True,
                        "badgeEnabled": False,
                        "autoLinkWorkItems": False,
                        "pullRequestDeploymentEnabled": False,
                    },
                    "demands": [],
                    "conditions": [{"name": "ReleaseStarted", "conditionType": "event", "value": "", "result": True}],
                    "createdOn": now,
                    "modifiedOn": now,
                    "workflowTasks": [],
                    "deployPhasesSnapshot": [],
                    "owner": {
                        "displayName": "Chura Prakash (EXTERNAL)",
                        "url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/9b407520-159d-683b-9bf8-39368b173494",
                        "_links": {"avatar": {"href": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.OWI0MDc1MjAtMTU5ZC03ODNiLTliZjgtMzkzNjhiMTczNDk0"}},
                        "id": "9b407520-159d-683b-9bf8-39368b173494",
                        "uniqueName": "ta25845@inetpsa.com",
                        "imageUrl": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.OWI0MDc1MjAtMTU5ZC03ODNiLTliZjgtMzkzNjhiMTczNDk0",
                        "descriptor": "aad.OWI0MDc1MjAtMTU5ZC03ODNiLTliZjgtMzkzNjhiMTczNDk0",
                    },
                    "schedules": [],
                    "release": {"id": release_id, "name": release_name, "url": vsrm_release, "_links": {"web": {"href": web_release}, "self": {"href": vsrm_release}}},
                    "releaseDefinition": {"id": RELEASE_DEF_ID, "name": RELEASE_DEF_NAME, "path": "\\azglz_pipelines_release", "projectReference": None, "url": vsrm_release_def, "_links": {"web": {"href": web_release_def}, "self": {"href": vsrm_release_def}}},
                    "releaseCreatedBy": identity,
                    "triggerReason": "ReleaseStarted",
                    "processParameters": {},
                    "preDeploymentGatesSnapshot": {"id": 0, "gatesOptions": None, "gates": []},
                    "postDeploymentGatesSnapshot": {"id": 0, "gatesOptions": None, "gates": []},
                }
            ],
            "variables": {"networkconfig_filename": {"value": NETWORKCONFIG_FILENAME, "allowOverride": True}},
            "variableGroups": [],
            "artifacts": [
                {
                    "sourceId": f"{PROJECT_ID}:{BUILD_DEF_ID}",
                    "type": "Build",
                    "alias": "_CI_azglz_pipeline_createnetwork_nonprod",
                    "definitionReference": {
                        "artifactSourceDefinitionUrl": {"id": f"https://dev.azure.com/{account}/_permalink/_build/index?collectionId=14701dc5-c1a7-45ec-8939-b07c45381221&projectId={PROJECT_ID}&definitionId={BUILD_DEF_ID}", "name": ""},
                        "branches": {"id": "nonprod", "name": "nonprod"},
                        "buildUri": {"id": f"vstfs:///Build/Build/{BUILD_ID}", "name": None},
                        "definition": {"id": str(BUILD_DEF_ID), "name": BUILD_DEF_NAME},
                        "IsMultiDefinitionType": {"id": "False", "name": "False"},
                        "IsXamlBuildArtifactType": {"id": "False", "name": None},
                        "project": {"id": PROJECT_ID, "name": project},
                        "repository.provider": {"id": "TfsGit", "name": None},
                        "repository": {"id": REPOSITORY_ID, "name": REPOSITORY_NAME},
                        "requestedFor": {"id": USER_NAME, "name": None},
                        "requestedForId": {"id": USER_ID, "name": None},
                        "sourceVersion": {"id": SOURCE_VERSION, "name": None},
                        "version": {"id": str(BUILD_ID), "name": str(BUILD_ID)},
                        "branch": {"id": "refs/heads/nonprod", "name": "refs/heads/nonprod"},
                        "artifactSourceVersionUrl": {"id": f"https://dev.azure.com/{account}/_permalink/_build/index?collectionId=14701dc5-c1a7-45ec-8939-b07c45381221&projectId={PROJECT_ID}&buildId={BUILD_ID}", "name": ""},
                    },
                    "isPrimary": True,
                    "isRetained": True,
                }
            ],
            "releaseDefinition": {
                "id": RELEASE_DEF_ID,
                "name": RELEASE_DEF_NAME,
                "path": "\\azglz_pipelines_release",
                "projectReference": None,
                "url": vsrm_release_def,
                "_links": {"self": {"href": vsrm_release_def}, "web": {"href": web_release_def}},
            },
            "releaseDefinitionRevision": 4,
            "description": "",
            "reason": "continuousIntegration",
            "releaseNameFormat": "Release-$(rev:r)",
            "keepForever": False,
            "definitionSnapshotRevision": 1,
            "logsContainerUrl": f"{vsrm_release}/logs",
            "url": vsrm_release,
            "_links": {"self": {"href": vsrm_release}, "web": {"href": web_release}},
            "tags": [],
            "triggeringArtifactAlias": None,
            "projectReference": {"id": PROJECT_ID, "name": None},
            "properties": {},
        },
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=200,
        mimetype="application/json",
    )
