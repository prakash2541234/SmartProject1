import json
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import azure.functions as func


PROJECT_ID = "ac3624cd-7a50-4e57-913d-ac36d92c2d86"
COLLECTION_ID = "14701dc5-c1a7-45ec-8939-b07c45381221"
RELEASE_PROFILES = {
    "5": {
        "build_def_id": "48",
        "build_def_name": "CI_azglz_pipeline_createsub_nonprod",
        "release_def_name": "Release_azglz_pipeline_createsub - NonProd",
        "repo_alias": "_CI_azglz_pipeline_createsub-nonprod",
        "variable_name": "subscription_name",
        "default_value": "unknown-sub",
        "default_build_id": 7457,
        "default_release_id": 157,
        "default_release_name": "Release-45",
        "definition_environment_id": 7,
        "environment_id": 164,
    },
    "7": {
        "build_def_id": "54",
        "build_def_name": "CI_azglz_pipeline_createnetwork_nonprod",
        "release_def_name": "Release_azglz_pipeline_createnetwork_nonprod",
        "repo_alias": "_CI_azglz_pipeline_createnetwork_nonprod",
        "variable_name": "networkconfig_filename",
        "default_value": "unknown-network-config",
        "default_build_id": 7482,
        "default_release_id": 169,
        "default_release_name": "Release-9",
        "definition_environment_id": 9,
        "environment_id": 176,
    },
}


def _http_date_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def _parse_project_from_path(path_value: str) -> str:
    if not path_value:
        return "AZGLZ_API_Platform"

    parts = [segment for segment in path_value.split("/") if segment]
    if parts:
        return parts[0]

    return "AZGLZ_API_Platform"


def _extract_variable(variables: list[dict], variable_name: str) -> str:
    for item in variables:
        if not isinstance(item, dict):
            continue
        if str(item.get("Name", "")).strip().lower() == variable_name.lower():
            return str(item.get("Value", "")).strip()
    return ""


def _release_profile(release_def_id: str) -> dict:
    return RELEASE_PROFILES.get(str(release_def_id), RELEASE_PROFILES["5"])


def _extract_build_id_from_description(description: str) -> int:
    match = re.search(r"(\d{4,6})", description or "")
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return 7457
    return 7457


def _extract_branch_from_description(description: str) -> str:
    if not description:
        return "nonprod"

    if "prod" in description.lower() and "nonprod" not in description.lower():
        return "prod"

    return "nonprod"


def _add_validation_issue(missing_fields: list[str], validation_details: list[str], field: str, detail: str) -> None:
    missing_fields.append(field)
    validation_details.append(detail)


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("create_a_new_release function triggered")

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

    missing_fields = []
    validation_details = []

    body = req_body.get("body")
    if not isinstance(body, dict):
        _add_validation_issue(
            missing_fields,
            validation_details,
            "body",
            "'body' is missing or not a valid JSON object",
        )
        body = {}

    queries = req_body.get("queries")
    if not isinstance(queries, dict):
        _add_validation_issue(
            missing_fields,
            validation_details,
            "queries",
            "'queries' is missing or not a valid JSON object",
        )
        queries = {}

    path_value = str(req_body.get("path", "") or "").strip()
    if not path_value:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "path",
            "'path' is missing or empty in the root payload",
        )

    description = str(body.get("Description", "") or "").strip()
    if not description:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "body.Description",
            "'body.Description' is missing or empty",
        )

    if "IsDraft" not in body:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "body.IsDraft",
            "'body.IsDraft' is missing",
        )
        is_draft = False
    else:
        is_draft = body.get("IsDraft")
        if not isinstance(is_draft, bool):
            _add_validation_issue(
                missing_fields,
                validation_details,
                "body.IsDraft (wrong type)",
                f"'body.IsDraft' must be a boolean, got {type(is_draft).__name__}",
            )
            is_draft = bool(is_draft)

    reason = str(body.get("Reason", "") or "").strip()
    if not reason:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "body.Reason",
            "'body.Reason' is missing or empty",
        )

    variables = body.get("Variables")
    if variables is None:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "body.Variables",
            "'body.Variables' is missing",
        )
        variables = []
    elif not isinstance(variables, list):
        _add_validation_issue(
            missing_fields,
            validation_details,
            "body.Variables (wrong type)",
            f"'body.Variables' must be an array, got {type(variables).__name__}",
        )
        variables = []
    elif not variables:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "body.Variables",
            "'body.Variables' is empty",
        )

    account = str(queries.get("account", "") or "").strip()
    if not account:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "queries.account",
            "'queries.account' is missing or empty",
        )

    release_def_id = str(queries.get("releaseDefId", "") or "").strip()
    if not release_def_id:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "queries.releaseDefId",
            "'queries.releaseDefId' is missing or empty",
        )
    elif release_def_id not in RELEASE_PROFILES:
        _add_validation_issue(
            missing_fields,
            validation_details,
            "queries.releaseDefId (unsupported)",
            f"'queries.releaseDefId' value '{release_def_id}' is not supported",
        )

    if isinstance(variables, list):
        for index, item in enumerate(variables):
            if not isinstance(item, dict):
                _add_validation_issue(
                    missing_fields,
                    validation_details,
                    f"body.Variables[{index}]",
                    f"'body.Variables[{index}]' must be an object",
                )
                continue

            var_name = str(item.get("Name", "") or "").strip()
            var_value = str(item.get("Value", "") or "").strip()

            if not var_name:
                _add_validation_issue(
                    missing_fields,
                    validation_details,
                    f"body.Variables[{index}].Name",
                    f"'body.Variables[{index}].Name' is missing or empty",
                )

            if not var_value:
                _add_validation_issue(
                    missing_fields,
                    validation_details,
                    f"body.Variables[{index}].Value",
                    f"'body.Variables[{index}].Value' is missing or empty",
                )

        if release_def_id in RELEASE_PROFILES:
            profile_for_validation = RELEASE_PROFILES[release_def_id]
            required_variable_name = profile_for_validation["variable_name"]
            required_variable_value = _extract_variable(variables, required_variable_name)
            if not required_variable_value:
                _add_validation_issue(
                    missing_fields,
                    validation_details,
                    f"body.Variables.{required_variable_name}",
                    f"Required variable '{required_variable_name}' is missing or empty in 'body.Variables'",
                )

    if missing_fields:
        logging.warning(f"Validation failed. Missing/invalid fields: {missing_fields}")
        return func.HttpResponse(
            body=json.dumps(
                {
                    "status": "FAILED",
                    "error": "There are missing values in input payload, kindly provide the missing payloads.",
                    "missing_fields": missing_fields,
                    "details": validation_details,
                    "hint": "Please provide all required fields and check 'details' for the exact issue in each missing or invalid payload item.",
                },
                indent=2,
            ),
            status_code=400,
            mimetype="application/json",
        )

    project_name = _parse_project_from_path(path_value)
    profile = _release_profile(release_def_id)
    variable_name = profile["variable_name"]
    variable_value = _extract_variable(variables, variable_name)
    if not variable_value:
        variable_value = profile["default_value"]

    build_id = _extract_build_id_from_description(description)
    if build_id == 7457 and not description:
        build_id = profile["default_build_id"]
    branch_name = _extract_branch_from_description(description)
    branch_ref = f"refs/heads/{branch_name}"

    created_on = _iso_now()
    release_id = profile["default_release_id"]
    environment_id = profile["environment_id"]
    release_name = profile["default_release_name"]

    release_url_vsrm = (
        f"https://vsrm.dev.azure.com/{account}/{PROJECT_ID}/_apis/Release/releases/{release_id}"
    )
    release_web_url = (
        f"https://dev.azure.com/{account}/{PROJECT_ID}/_release?releaseId={release_id}&_a=release-summary"
    )
    release_def_url_vsrm = (
        f"https://vsrm.dev.azure.com/{account}/{PROJECT_ID}/_apis/Release/definitions/{release_def_id}"
    )
    release_def_web_url = (
        f"https://dev.azure.com/{account}/{PROJECT_ID}/_release?definitionId={release_def_id}"
    )

    artifact_def_url = (
        f"https://dev.azure.com/{account}/_permalink/_build/index?collectionId={COLLECTION_ID}"
        f"&projectId={PROJECT_ID}&definitionId={profile['build_def_id']}"
    )
    artifact_build_url = (
        f"https://dev.azure.com/{account}/_permalink/_build/index?collectionId={COLLECTION_ID}"
        f"&projectId={PROJECT_ID}&buildId={build_id}"
    )

    headers = {
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
    }

    response = {
        "statusCode": 200,
        "headers": headers,
        "body": {
            "_links": {
                "self": {
                    "href": release_url_vsrm,
                },
                "web": {
                    "href": release_web_url,
                },
            },
            "Artifacts": [
                {
                    "Alias": profile["repo_alias"],
                    "IsPrimary": True,
                    "SourceId": f"{PROJECT_ID}:{profile['build_def_id']}",
                    "Type": "Build",
                    "DefinitionReference": {
                        "artifactSourceDefinitionUrl": {
                            "Id": artifact_def_url,
                            "Name": "",
                        },
                        "branches": {
                            "Id": branch_name,
                            "Name": branch_name,
                        },
                        "definition": {
                            "Id": profile["build_def_id"],
                            "Name": profile["build_def_name"],
                        },
                        "IsMultiDefinitionType": {
                            "Id": "False",
                            "Name": "False",
                        },
                        "project": {
                            "Id": PROJECT_ID,
                            "Name": project_name,
                        },
                        "repository": {
                            "Id": "",
                            "Name": "",
                        },
                        "version": {
                            "Id": str(build_id),
                            "Name": str(build_id),
                        },
                        "artifactSourceVersionUrl": {
                            "Id": artifact_build_url,
                            "Name": "",
                        },
                        "branch": {
                            "Id": branch_ref,
                            "Name": branch_ref,
                        },
                    },
                }
            ],
            "Comment": None,
            "CreatedBy": {
                "DirectoryAlias": None,
                "DisplayName": "Chura Prakash",
                "Id": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "ImageUrl": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
                "Inactive": False,
                "IsAadIdentity": False,
                "IsContainer": False,
                "ProfileUrl": None,
                "UniqueName": "ta25845@stellantis.com",
                "Url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
            },
            "CreatedOn": created_on,
            "DefinitionSnapshotRevision": "1",
            "Description": description,
            "Environments": [
                {
                    "Conditions": [
                        {
                            "Result": True,
                            "ConditionType": "Event",
                            "Name": "ReleaseStarted",
                            "Value": "",
                        }
                    ],
                    "CreatedOn": "0001-01-01T00:00:00",
                    "DefinitionEnvironmentId": profile["definition_environment_id"],
                    "Demands": [],
                    "DeployPhasesSnapshot": [],
                    "DeploySteps": [],
                    "EnvironmentOptions": {
                        "EmailNotificationType": "OnlyOnFailure",
                        "EmailRecipients": "release.environment.owner;release.creator",
                        "EnableAccessToken": False,
                        "PublishDeploymentStatus": True,
                        "SkipArtifactsDownload": False,
                        "TimeoutInMinutes": 0,
                    },
                    "Id": environment_id,
                    "ModifiedOn": "0001-01-01T00:00:00",
                    "Name": "Terraform Apply",
                    "NextScheduledUtcTime": "0001-01-01T00:00:00",
                    "Owner": {
                        "DirectoryAlias": None,
                        "DisplayName": "Chura Prakash (EXTERNAL)",
                        "Id": "9b407520-159d-683b-9bf8-39368b173494",
                        "ImageUrl": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.OWI0MDc1MjAtMTU5ZC03ODNiLTliZjgtMzkzNjhiMTczNDk0",
                        "Inactive": False,
                        "IsAadIdentity": False,
                        "IsContainer": False,
                        "ProfileUrl": None,
                        "UniqueName": "ta25845@inetpsa.com",
                        "Url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/9b407520-159d-683b-9bf8-39368b173494",
                    },
                    "PostApprovalsSnapshot": {
                        "ApprovalOptions": {
                            "AutoTriggeredAndPreviousEnvironmentApprovedCanBeSkipped": False,
                            "EnforceIdentityRevalidation": False,
                            "ReleaseCreatorCanBeApprover": False,
                            "RequiredApproverCount": 0,
                            "TimeoutInMinutes": 0,
                        },
                        "Approvals": [
                            {
                                "Approver": None,
                                "IsAutomated": True,
                                "IsNotificationOn": False,
                                "Rank": 1,
                                "Id": 0,
                            }
                        ],
                    },
                    "PostDeployApprovals": [],
                    "PreApprovalsSnapshot": {
                        "ApprovalOptions": {
                            "AutoTriggeredAndPreviousEnvironmentApprovedCanBeSkipped": False,
                            "EnforceIdentityRevalidation": False,
                            "ReleaseCreatorCanBeApprover": False,
                            "RequiredApproverCount": 0,
                            "TimeoutInMinutes": 0,
                        },
                        "Approvals": [
                            {
                                "Approver": None,
                                "IsAutomated": True,
                                "IsNotificationOn": False,
                                "Rank": 1,
                                "Id": 0,
                            }
                        ],
                    },
                    "PreDeployApprovals": [],
                    "ProcessParameters": {
                        "DataSourceBindings": None,
                        "Inputs": None,
                        "SourceDefinitions": None,
                    },
                    "QueueId": 0,
                    "Rank": 1,
                    "Release": {
                        "_links": {
                            "web": {
                                "href": release_web_url,
                            },
                            "self": {
                                "href": release_url_vsrm,
                            },
                        },
                        "Id": release_id,
                        "Name": release_name,
                        "Url": release_url_vsrm,
                    },
                    "ReleaseCreatedBy": {
                        "DirectoryAlias": None,
                        "DisplayName": "Chura Prakash",
                        "Id": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                        "ImageUrl": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
                        "Inactive": False,
                        "IsAadIdentity": False,
                        "IsContainer": False,
                        "ProfileUrl": None,
                        "UniqueName": "ta25845@stellantis.com",
                        "Url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                    },
                    "ReleaseDefinition": {
                        "_links": {
                            "web": {
                                "href": release_def_web_url,
                            },
                            "self": {
                                "href": release_def_url_vsrm,
                            },
                        },
                        "Id": int(release_def_id),
                        "Name": profile["release_def_name"],
                        "Url": release_def_url_vsrm,
                    },
                    "ReleaseDescription": None,
                    "ReleaseId": release_id,
                    "ScheduledDeploymentTime": "0001-01-01T00:00:00",
                    "Schedules": [],
                    "Status": "NotStarted",
                    "TimeToDeploy": 0,
                    "TriggerReason": "ReleaseStarted",
                    "Variables": {},
                    "WorkflowTasks": [],
                }
            ],
            "Id": release_id,
            "KeepForever": False,
            "LogsContainerUrl": f"https://vsrm.dev.azure.com/{account}/{PROJECT_ID}/_apis/Release/releases/{release_id}/logs",
            "ModifiedBy": {
                "DirectoryAlias": None,
                "DisplayName": "Chura Prakash",
                "Id": "acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
                "ImageUrl": f"https://dev.azure.com/{account}/_apis/GraphProfile/MemberAvatars/aad.YWNkNGE3ZTUtZTc2MC03NGE2LTliZDMtZTVhNjNlZTJiMWYy",
                "Inactive": False,
                "IsAadIdentity": False,
                "IsContainer": False,
                "ProfileUrl": None,
                "UniqueName": "ta25845@stellantis.com",
                "Url": "https://spsprodneu1.vssps.visualstudio.com/A18ca9b51-af9b-4bc0-a64e-c36c38390678/_apis/Identities/acd4a7e5-e760-64a6-9bd3-e5a63ee2b1f2",
            },
            "ModifiedOn": created_on,
            "Name": release_name,
            "PoolName": None,
            "ProjectReference": {
                "Id": PROJECT_ID,
                "Name": None,
            },
            "Properties": {
                "Count": 0,
                "Item": None,
                "Keys": None,
                "Values": None,
            },
            "Reason": reason,
            "ReleaseDefinition": {
                "_links": {
                    "self": {
                        "href": release_def_url_vsrm,
                    },
                    "web": {
                        "href": release_def_web_url,
                    },
                },
                "Id": int(release_def_id),
                "Name": profile["release_def_name"],
                "Url": release_def_url_vsrm,
            },
            "ReleaseNameFormat": "Release-$(rev:r)",
            "Status": "Active",
            "Tags": [],
            "Url": release_url_vsrm,
            "VariableGroups": [],
            "Variables": {
                variable_name: {
                    "IsSecret": False,
                    "Value": variable_value,
                }
            },
            "IsDraft": is_draft,
        },
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=200,
        mimetype="application/json",
    )
