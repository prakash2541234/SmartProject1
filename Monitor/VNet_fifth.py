import json
import logging
import azure.functions as func


REQUIRED_KEYS = [
    "Get_releaseStatus_inputs",
    "Get_releaseStatus_outputs",
    "ParseReleaseStatus_outputs",
    "release_status"
]


def validate_get_release_status_inputs(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["Get_releaseStatus_inputs must be an object"]

    wrapper_body = payload_value.get("body")

    if wrapper_body is None:
        field_errors.append("body is missing")
        return field_errors

    if not isinstance(wrapper_body, dict):
        field_errors.append("body must be an object")
        return field_errors

    # Actual request payload
    body = wrapper_body.get("body")

    if body is None:
        field_errors.append("body.body is missing")
    elif not isinstance(body, dict):
        field_errors.append("body.body must be an object")
    else:
        method = body.get("Method")

        if method is None or (
            isinstance(method, str) and method.strip() == ""
        ):
            field_errors.append("body.body.Method is missing")
        elif not isinstance(method, str):
            field_errors.append("body.body.Method must be a string")

        uri = body.get("Uri")

        if uri is None or (
            isinstance(uri, str) and uri.strip() == ""
        ):
            field_errors.append("body.body.Uri is missing")
        elif not isinstance(uri, str):
            field_errors.append("body.body.Uri must be a string")

    queries = wrapper_body.get("queries")

    if queries is None:
        field_errors.append("body.queries is missing")
    elif not isinstance(queries, dict):
        field_errors.append("body.queries must be an object")
    else:
        account = queries.get("account")

        if account is None or (
            isinstance(account, str) and account.strip() == ""
        ):
            field_errors.append("body.queries.account is missing")
        elif not isinstance(account, str):
            field_errors.append("body.queries.account must be a string")

    return field_errors


def validate_get_release_status_outputs(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["Get_releaseStatus_outputs must be an object"]

    status_code = payload_value.get("statusCode")
    if status_code is None:
        field_errors.append("statusCode is missing")
    elif not isinstance(status_code, int):
        field_errors.append("statusCode must be an integer")

    body = payload_value.get("body")
    if body is None:
        field_errors.append("body is missing")
        return field_errors
    if not isinstance(body, dict):
        field_errors.append("body must be an object")
        return field_errors

    required_body_fields = [
        "id", "name", "status", "createdOn", "modifiedOn", "modifiedBy", "createdBy", "createdFor",
        "environments", "variables", "artifacts", "releaseDefinition", "reason", "url", "_links"
    ]
    for key in required_body_fields:
        if body.get(key) is None:
            field_errors.append(f"body.{key} is missing")

    body_id = body.get("id")
    if body_id is not None and not isinstance(body_id, int):
        field_errors.append("body.id must be an integer")

    for key in ["name", "status", "createdOn", "modifiedOn", "reason", "url"]:
        value = body.get(key)
        if value is not None and not isinstance(value, str):
            field_errors.append(f"body.{key} must be a string")

    for identity_key in ["modifiedBy", "createdBy", "createdFor"]:
        identity = body.get(identity_key)
        if identity is not None:
            if not isinstance(identity, dict):
                field_errors.append(f"body.{identity_key} must be an object")
            else:
                unique_name = identity.get("uniqueName")
                if unique_name is None or (isinstance(unique_name, str) and unique_name.strip() == ""):
                    field_errors.append(f"body.{identity_key}.uniqueName is missing")
                elif not isinstance(unique_name, str):
                    field_errors.append(f"body.{identity_key}.uniqueName must be a string")

    environments = body.get("environments")
    if environments is not None:
        if not isinstance(environments, list):
            field_errors.append("body.environments must be an array")
        elif len(environments) == 0:
            field_errors.append("body.environments must contain at least one item")
        else:
            for index, environment in enumerate(environments):
                if not isinstance(environment, dict):
                    field_errors.append(f"body.environments[{index}] must be an object")
                    continue
                for key in ["id", "releaseId", "name", "status"]:
                    if environment.get(key) is None:
                        field_errors.append(f"body.environments[{index}].{key} is missing")

    variables = body.get("variables")
    if variables is not None and not isinstance(variables, dict):
        field_errors.append("body.variables must be an object")

    artifacts = body.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            field_errors.append("body.artifacts must be an array")
        elif len(artifacts) == 0:
            field_errors.append("body.artifacts must contain at least one item")
        else:
            for index, artifact in enumerate(artifacts):
                if not isinstance(artifact, dict):
                    field_errors.append(f"body.artifacts[{index}] must be an object")
                    continue
                for key in ["sourceId", "type", "alias", "definitionReference"]:
                    if artifact.get(key) is None:
                        field_errors.append(f"body.artifacts[{index}].{key} is missing")

    release_definition = body.get("releaseDefinition")
    if release_definition is not None:
        if not isinstance(release_definition, dict):
            field_errors.append("body.releaseDefinition must be an object")
        else:
            for key in ["id", "name", "url", "_links"]:
                if release_definition.get(key) is None:
                    field_errors.append(f"body.releaseDefinition.{key} is missing")

    links = body.get("_links")
    if links is not None:
        if not isinstance(links, dict):
            field_errors.append("body._links must be an object")
        else:
            for key in ["self", "web"]:
                section = links.get(key)
                if section is None:
                    field_errors.append(f"body._links.{key} is missing")
                elif not isinstance(section, dict):
                    field_errors.append(f"body._links.{key} must be an object")
                else:
                    href = section.get("href")
                    if href is None or (isinstance(href, str) and href.strip() == ""):
                        field_errors.append(f"body._links.{key}.href is missing")
                    elif not isinstance(href, str):
                        field_errors.append(f"body._links.{key}.href must be a string")

    return field_errors


def validate_parse_release_status_outputs(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["ParseReleaseStatus_outputs must be an object"]

    required_top_fields = [
        "id", "name", "status", "createdOn", "modifiedOn", "modifiedBy", "createdBy", "createdFor",
        "environments", "variables", "variableGroups", "artifacts", "releaseDefinition", "releaseDefinitionRevision",
        "description", "reason", "releaseNameFormat", "keepForever", "definitionSnapshotRevision", "logsContainerUrl",
        "url", "_links", "tags", "triggeringArtifactAlias", "projectReference", "properties"
    ]
    for key in required_top_fields:
        if key not in payload_value:
            field_errors.append(f"{key} is missing")

    if payload_value.get("id") is not None and not isinstance(payload_value.get("id"), int):
        field_errors.append("id must be an integer")

    for key in ["name", "status", "createdOn", "modifiedOn", "description", "reason", "releaseNameFormat", "logsContainerUrl", "url"]:
        value = payload_value.get(key)
        if value is not None and not isinstance(value, str):
            field_errors.append(f"{key} must be a string")

    if payload_value.get("releaseDefinitionRevision") is not None and not isinstance(payload_value.get("releaseDefinitionRevision"), int):
        field_errors.append("releaseDefinitionRevision must be an integer")
    if payload_value.get("definitionSnapshotRevision") is not None and not isinstance(payload_value.get("definitionSnapshotRevision"), int):
        field_errors.append("definitionSnapshotRevision must be an integer")
    if payload_value.get("keepForever") is not None and not isinstance(payload_value.get("keepForever"), bool):
        field_errors.append("keepForever must be a boolean")

    for identity_key in ["modifiedBy", "createdBy", "createdFor"]:
        identity = payload_value.get(identity_key)
        if identity is not None:
            if not isinstance(identity, dict):
                field_errors.append(f"{identity_key} must be an object")
            else:
                for key in ["displayName", "url", "id", "uniqueName", "imageUrl", "descriptor"]:
                    value = identity.get(key)
                    if value is None:
                        field_errors.append(f"{identity_key}.{key} is missing")
                    elif not isinstance(value, str):
                        field_errors.append(f"{identity_key}.{key} must be a string")

                identity_links = identity.get("_links")
                if identity_links is None:
                    field_errors.append(f"{identity_key}._links is missing")
                elif not isinstance(identity_links, dict):
                    field_errors.append(f"{identity_key}._links must be an object")
                else:
                    avatar = identity_links.get("avatar")
                    if avatar is None:
                        field_errors.append(f"{identity_key}._links.avatar is missing")
                    elif not isinstance(avatar, dict):
                        field_errors.append(f"{identity_key}._links.avatar must be an object")
                    else:
                        href = avatar.get("href")
                        if href is None:
                            field_errors.append(f"{identity_key}._links.avatar.href is missing")
                        elif not isinstance(href, str):
                            field_errors.append(f"{identity_key}._links.avatar.href must be a string")

    environments = payload_value.get("environments")
    if environments is not None:
        if not isinstance(environments, list):
            field_errors.append("environments must be an array")
        else:
            for index, environment in enumerate(environments):
                if not isinstance(environment, dict):
                    field_errors.append(f"environments[{index}] must be an object")
                    continue

                required_env_fields = [
                    "id", "releaseId", "name", "status", "variables", "variableGroups", "preDeployApprovals", "postDeployApprovals",
                    "preApprovalsSnapshot", "postApprovalsSnapshot", "deploySteps", "rank", "definitionEnvironmentId", "environmentOptions",
                    "demands", "conditions", "createdOn", "modifiedOn", "workflowTasks", "deployPhasesSnapshot", "owner", "schedules",
                    "release", "releaseDefinition", "releaseCreatedBy", "triggerReason", "processParameters", "preDeploymentGatesSnapshot",
                    "postDeploymentGatesSnapshot"
                ]
                for key in required_env_fields:
                    if key not in environment:
                        field_errors.append(f"environments[{index}].{key} is missing")

                for key in ["id", "releaseId", "rank", "definitionEnvironmentId"]:
                    value = environment.get(key)
                    if value is not None and not isinstance(value, int):
                        field_errors.append(f"environments[{index}].{key} must be an integer")

                for key in ["name", "status", "createdOn", "modifiedOn", "triggerReason"]:
                    value = environment.get(key)
                    if value is not None and not isinstance(value, str):
                        field_errors.append(f"environments[{index}].{key} must be a string")

                for key in ["variableGroups", "postDeployApprovals", "demands", "workflowTasks", "schedules"]:
                    value = environment.get(key)
                    if value is not None and not isinstance(value, list):
                        field_errors.append(f"environments[{index}].{key} must be an array")

                for key in ["variables", "environmentOptions", "preApprovalsSnapshot", "postApprovalsSnapshot", "owner", "release", "releaseDefinition", "releaseCreatedBy", "processParameters", "preDeploymentGatesSnapshot", "postDeploymentGatesSnapshot"]:
                    value = environment.get(key)
                    if value is not None and not isinstance(value, dict):
                        field_errors.append(f"environments[{index}].{key} must be an object")

                pre_deploy_approvals = environment.get("preDeployApprovals")
                if pre_deploy_approvals is not None:
                    if not isinstance(pre_deploy_approvals, list):
                        field_errors.append(f"environments[{index}].preDeployApprovals must be an array")
                    else:
                        for approval_index, approval in enumerate(pre_deploy_approvals):
                            if not isinstance(approval, dict):
                                field_errors.append(f"environments[{index}].preDeployApprovals[{approval_index}] must be an object")
                                continue
                            required_approval_fields = [
                                "id", "revision", "approvalType", "createdOn", "modifiedOn", "status", "comments",
                                "isAutomated", "isNotificationOn", "trialNumber", "attempt", "rank", "release",
                                "releaseDefinition", "releaseEnvironment", "url"
                            ]
                            for key in required_approval_fields:
                                if key not in approval:
                                    field_errors.append(f"environments[{index}].preDeployApprovals[{approval_index}].{key} is missing")

                deploy_steps = environment.get("deploySteps")
                if deploy_steps is not None:
                    if not isinstance(deploy_steps, list):
                        field_errors.append(f"environments[{index}].deploySteps must be an array")
                    else:
                        for step_index, step in enumerate(deploy_steps):
                            if not isinstance(step, dict):
                                field_errors.append(f"environments[{index}].deploySteps[{step_index}] must be an object")
                                continue
                            required_step_fields = [
                                "id", "deploymentId", "attempt", "reason", "status", "operationStatus", "releaseDeployPhases",
                                "requestedBy", "requestedFor", "queuedOn", "lastModifiedBy", "lastModifiedOn", "hasStarted",
                                "tasks", "runPlanId", "issues"
                            ]
                            for key in required_step_fields:
                                if key not in step:
                                    field_errors.append(f"environments[{index}].deploySteps[{step_index}].{key} is missing")

                conditions = environment.get("conditions")
                if conditions is not None:
                    if not isinstance(conditions, list):
                        field_errors.append(f"environments[{index}].conditions must be an array")
                    else:
                        for condition_index, condition in enumerate(conditions):
                            if not isinstance(condition, dict):
                                field_errors.append(f"environments[{index}].conditions[{condition_index}] must be an object")
                                continue
                            for key in ["name", "conditionType", "value", "result"]:
                                if key not in condition:
                                    field_errors.append(f"environments[{index}].conditions[{condition_index}].{key} is missing")

    variables = payload_value.get("variables")
    if variables is not None and not isinstance(variables, dict):
        field_errors.append("variables must be an object")

    variable_groups = payload_value.get("variableGroups")
    if variable_groups is not None and not isinstance(variable_groups, list):
        field_errors.append("variableGroups must be an array")

    artifacts = payload_value.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            field_errors.append("artifacts must be an array")
        else:
            for index, artifact in enumerate(artifacts):
                if not isinstance(artifact, dict):
                    field_errors.append(f"artifacts[{index}] must be an object")
                    continue
                for key in ["sourceId", "type", "alias", "definitionReference", "isPrimary", "isRetained"]:
                    if key not in artifact:
                        field_errors.append(f"artifacts[{index}].{key} is missing")

    release_definition = payload_value.get("releaseDefinition")
    if release_definition is not None:
        if not isinstance(release_definition, dict):
            field_errors.append("releaseDefinition must be an object")
        else:
            for key in ["id", "name", "path", "url", "_links"]:
                if key not in release_definition:
                    field_errors.append(f"releaseDefinition.{key} is missing")

    links = payload_value.get("_links")
    if links is not None:
        if not isinstance(links, dict):
            field_errors.append("_links must be an object")
        else:
            for key in ["self", "web"]:
                section = links.get(key)
                if section is None:
                    field_errors.append(f"_links.{key} is missing")
                elif not isinstance(section, dict):
                    field_errors.append(f"_links.{key} must be an object")
                else:
                    href = section.get("href")
                    if href is None:
                        field_errors.append(f"_links.{key}.href is missing")
                    elif not isinstance(href, str):
                        field_errors.append(f"_links.{key}.href must be a string")

    tags = payload_value.get("tags")
    if tags is not None and not isinstance(tags, list):
        field_errors.append("tags must be an array")

    project_reference = payload_value.get("projectReference")
    if project_reference is not None and not isinstance(project_reference, dict):
        field_errors.append("projectReference must be an object")

    properties = payload_value.get("properties")
    if properties is not None and not isinstance(properties, dict):
        field_errors.append("properties must be an object")

    return field_errors


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("VNet_fifth workflow monitoring function triggered")

    try:
        body = req.get_json()

        if not isinstance(body, dict):
            return func.HttpResponse(
                json.dumps({
                    "status": "FAILED",
                    "message": "Input payload must be a JSON object"
                }, indent=2),
                status_code=400,
                mimetype="application/json"
            )

        missing_fields = []
        invalid_fields = {}

        for key in REQUIRED_KEYS:
            value = body.get(key)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing_fields.append(key)

        release_status = body.get("release_status")
        if release_status is not None:
            release_status_errors = []
            if not isinstance(release_status, str):
                release_status_errors.append("release_status must be a string")
            elif release_status.strip().lower() != "succeeded":
                release_status_errors.append("release_status must be succeeded")

            if release_status_errors:
                invalid_fields["release_status"] = release_status_errors

        get_release_status_inputs_payload = body.get("Get_releaseStatus_inputs")
        if get_release_status_inputs_payload is not None:
            get_release_status_inputs_errors = validate_get_release_status_inputs(get_release_status_inputs_payload)
            if get_release_status_inputs_errors:
                invalid_fields["Get_releaseStatus_inputs"] = get_release_status_inputs_errors

        get_release_status_outputs_payload = body.get("Get_releaseStatus_outputs")
        if get_release_status_outputs_payload is not None:
            get_release_status_outputs_errors = validate_get_release_status_outputs(get_release_status_outputs_payload)
            if get_release_status_outputs_errors:
                invalid_fields["Get_releaseStatus_outputs"] = get_release_status_outputs_errors

        parse_release_status_outputs_payload = body.get("ParseReleaseStatus_outputs")
        if parse_release_status_outputs_payload is not None:
            parse_release_status_outputs_errors = validate_parse_release_status_outputs(parse_release_status_outputs_payload)
            if parse_release_status_outputs_errors:
                invalid_fields["ParseReleaseStatus_outputs"] = parse_release_status_outputs_errors

        if missing_fields or invalid_fields:
            missing_details = {field: "This field is missing" for field in missing_fields}
            return func.HttpResponse(
                json.dumps({
                    "status": "FAILED",
                    "message": "Input validation failed",
                    "missing_fields": missing_details,
                    "invalid_fields": invalid_fields
                }, indent=2),
                status_code=400,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps({
                "status": "SUCCESS",
                "message": "VNet_fifth.py ran successfully without missing fields"
            }, indent=2),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError:
        return func.HttpResponse(
            json.dumps({
                "error": "Invalid JSON payload"
            }),
            status_code=400
        )

    except Exception as error:
        logging.error(str(error))
        return func.HttpResponse(
            json.dumps({
                "error": str(error)
            }),
            status_code=500
        )