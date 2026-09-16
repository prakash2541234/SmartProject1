import json
import logging
import azure.functions as func


REQUIRED_KEYS = [
    "checkbuildstatus_inputs",
    "checkbuildstatus_outputs",
    "Parse_BuildStatusJSON_outputs",
    "CI_Build_status"
]


def validate_checkbuildstatus_outputs(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["checkbuildstatus_outputs must be an object"]

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
        "id",
        "buildNumber",
        "status",
        "queueTime",
        "startTime",
        "url",
        "definition",
        "project",
        "uri",
        "sourceBranch",
        "priority",
        "reason",
        "requestedFor",
        "requestedBy",
        "lastChangedDate",
        "lastChangedBy",
        "parameters",
        "repository"
    ]
    for key in required_body_fields:
        if body.get(key) is None:
            field_errors.append(f"body.{key} is missing")

    body_id = body.get("id")
    if body_id is not None and not isinstance(body_id, int):
        field_errors.append("body.id must be an integer")

    for key in [
        "buildNumber", "status", "queueTime", "startTime", "url", "uri",
        "sourceBranch", "priority", "reason", "lastChangedDate", "parameters"
    ]:
        value = body.get(key)
        if value is not None and not isinstance(value, str):
            field_errors.append(f"body.{key} must be a string")

    definition = body.get("definition")
    if definition is not None:
        if not isinstance(definition, dict):
            field_errors.append("body.definition must be an object")
        else:
            definition_id = definition.get("id")
            definition_name = definition.get("name")
            if definition_id is None:
                field_errors.append("body.definition.id is missing")
            elif not isinstance(definition_id, int):
                field_errors.append("body.definition.id must be an integer")
            if definition_name is None or (isinstance(definition_name, str) and definition_name.strip() == ""):
                field_errors.append("body.definition.name is missing")
            elif not isinstance(definition_name, str):
                field_errors.append("body.definition.name must be a string")

    project = body.get("project")
    if project is not None:
        if not isinstance(project, dict):
            field_errors.append("body.project must be an object")
        else:
            for key in ["id", "name", "url", "state", "revision", "visibility", "lastUpdateTime"]:
                value = project.get(key)
                if value is None:
                    field_errors.append(f"body.project.{key} is missing")

    for identity_key in ["requestedFor", "requestedBy", "lastChangedBy"]:
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

    repository = body.get("repository")
    if repository is not None:
        if not isinstance(repository, dict):
            field_errors.append("body.repository must be an object")
        else:
            for key in ["id", "type", "name", "url"]:
                value = repository.get(key)
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    field_errors.append(f"body.repository.{key} is missing")
                elif not isinstance(value, str):
                    field_errors.append(f"body.repository.{key} must be a string")

    return field_errors


def validate_checkbuildstatus_inputs(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["checkbuildstatus_inputs must be an object"]

    body = payload_value.get("body")
    if isinstance(body, dict):
        inner_body = body.get("body", {})
        request_method = inner_body.get(
            "Method",
            body.get("Method", payload_value.get("Method"))
        )
        request_uri = inner_body.get(
            "Uri",
            body.get("Uri", payload_value.get("Uri"))
        )
        request_queries = (
            payload_value.get("queries")
            or body.get("queries")
        )

        if (
            "_links" in body
            or "definition" in body
            or "queue" in body
            or "sourceVersion" in body
        ):
            # Build response payload shape; it is not a request wrapper.
            return []

        if request_method is None or (isinstance(request_method, str) and request_method.strip() == ""):
            field_errors.append("body.Method is missing")
        elif not isinstance(request_method, str):
            field_errors.append("body.Method must be a string")

        if request_uri is None or (isinstance(request_uri, str) and request_uri.strip() == ""):
            field_errors.append("body.Uri is missing")
        elif not isinstance(request_uri, str):
            field_errors.append("body.Uri must be a string")

        queries = request_queries
        if queries is None:
            field_errors.append("queries is missing")
        elif not isinstance(queries, dict):
            field_errors.append("queries must be an object")
        else:
            account = queries.get("account")
            if account is None or (isinstance(account, str) and account.strip() == ""):
                field_errors.append("queries.account is missing")
            elif not isinstance(account, str):
                field_errors.append("queries.account must be a string")
    else:
        method = payload_value.get("Method")
        uri = payload_value.get("Uri")
        queries = payload_value.get("queries")

        if method is None or (isinstance(method, str) and method.strip() == ""):
            field_errors.append("Method is missing")
        elif not isinstance(method, str):
            field_errors.append("Method must be a string")

        if uri is None or (isinstance(uri, str) and uri.strip() == ""):
            field_errors.append("Uri is missing")
        elif not isinstance(uri, str):
            field_errors.append("Uri must be a string")

        if queries is None:
            field_errors.append("queries is missing")
        elif not isinstance(queries, dict):
            field_errors.append("queries must be an object")
        else:
            account = queries.get("account")
            if account is None or (isinstance(account, str) and account.strip() == ""):
                field_errors.append("queries.account is missing")
            elif not isinstance(account, str):
                field_errors.append("queries.account must be a string")

    return field_errors


def validate_parse_build_status_json_outputs(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["Parse_BuildStatusJSON_outputs must be an object"]

    required_top_level_fields = [
        "_links", "properties", "tags", "validationResults", "plans", "triggerInfo", "id",
        "buildNumber", "status", "queueTime", "startTime", "url",
        "definition", "project", "uri", "sourceBranch", "sourceVersion", "queue", "priority",
        "reason", "requestedFor", "requestedBy", "lastChangedDate", "lastChangedBy", "parameters",
        "orchestrationPlan", "logs", "repository", "retainedByRelease", "triggeredByBuild",
        "appendCommitMessageToRunName"
    ]
    for key in required_top_level_fields:
        if key not in payload_value:
            field_errors.append(f"{key} is missing")

    links = payload_value.get("_links")
    if links is not None:
        if not isinstance(links, dict):
            field_errors.append("_links must be an object")
        else:
            for key in ["self", "web", "sourceVersionDisplayUri", "timeline", "badge"]:
                section = links.get(key)
                if section is None:
                    field_errors.append(f"_links.{key} is missing")
                elif not isinstance(section, dict):
                    field_errors.append(f"_links.{key} must be an object")
                else:
                    href = section.get("href")
                    if href is None or (isinstance(href, str) and href.strip() == ""):
                        field_errors.append(f"_links.{key}.href is missing")
                    elif not isinstance(href, str):
                        field_errors.append(f"_links.{key}.href must be a string")

    for key in ["properties", "triggerInfo"]:
        value = payload_value.get(key)
        if value is not None and not isinstance(value, dict):
            field_errors.append(f"{key} must be an object")

    for key in ["tags", "validationResults"]:
        value = payload_value.get(key)
        if value is not None and not isinstance(value, list):
            field_errors.append(f"{key} must be an array")

    plans = payload_value.get("plans")
    if plans is not None:
        if not isinstance(plans, list):
            field_errors.append("plans must be an array")
        else:
            for index, plan in enumerate(plans):
                if not isinstance(plan, dict):
                    field_errors.append(f"plans[{index}] must be an object")
                    continue
                plan_id = plan.get("planId")
                if plan_id is None or (isinstance(plan_id, str) and plan_id.strip() == ""):
                    field_errors.append(f"plans[{index}].planId is missing")
                elif not isinstance(plan_id, str):
                    field_errors.append(f"plans[{index}].planId must be a string")

    int_fields = ["id"]
    for key in int_fields:
        value = payload_value.get(key)
        if value is not None and not isinstance(value, int):
            field_errors.append(f"{key} must be an integer")

    str_fields = [
        "buildNumber", "status", "queueTime", "startTime", "url", "uri",
        "sourceBranch", "sourceVersion", "priority", "reason", "lastChangedDate", "parameters"
    ]
    for key in str_fields:
        value = payload_value.get(key)
        if value is not None and not isinstance(value, str):
            field_errors.append(f"{key} must be a string")

    definition = payload_value.get("definition")
    if definition is not None:
        if not isinstance(definition, dict):
            field_errors.append("definition must be an object")
        else:
            if definition.get("drafts") is not None and not isinstance(definition.get("drafts"), list):
                field_errors.append("definition.drafts must be an array")

            if definition.get("id") is None:
                field_errors.append("definition.id is missing")
            elif not isinstance(definition.get("id"), int):
                field_errors.append("definition.id must be an integer")

            if definition.get("revision") is None:
                field_errors.append("definition.revision is missing")
            elif not isinstance(definition.get("revision"), int):
                field_errors.append("definition.revision must be an integer")

            for key in ["name", "url", "uri", "path", "type", "queueStatus"]:
                value = definition.get(key)
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    field_errors.append(f"definition.{key} is missing")
                elif not isinstance(value, str):
                    field_errors.append(f"definition.{key} must be a string")

            definition_project = definition.get("project")
            if definition_project is None:
                field_errors.append("definition.project is missing")
            elif not isinstance(definition_project, dict):
                field_errors.append("definition.project must be an object")
            else:
                for key in ["id", "name", "url", "state", "revision", "visibility", "lastUpdateTime"]:
                    value = definition_project.get(key)
                    if value is None:
                        field_errors.append(f"definition.project.{key} is missing")
                    elif key == "revision" and not isinstance(value, int):
                        field_errors.append("definition.project.revision must be an integer")
                    elif key != "revision" and not isinstance(value, str):
                        field_errors.append(f"definition.project.{key} must be a string")

    project = payload_value.get("project")
    if project is not None:
        if not isinstance(project, dict):
            field_errors.append("project must be an object")
        else:
            for key in ["id", "name", "url", "state", "revision", "visibility", "lastUpdateTime"]:
                value = project.get(key)
                if value is None:
                    field_errors.append(f"project.{key} is missing")
                elif key == "revision" and not isinstance(value, int):
                    field_errors.append("project.revision must be an integer")
                elif key != "revision" and not isinstance(value, str):
                    field_errors.append(f"project.{key} must be a string")

    queue = payload_value.get("queue")
    if queue is not None:
        if not isinstance(queue, dict):
            field_errors.append("queue must be an object")
        else:
            if queue.get("id") is None:
                field_errors.append("queue.id is missing")
            elif not isinstance(queue.get("id"), int):
                field_errors.append("queue.id must be an integer")
            if queue.get("name") is None:
                field_errors.append("queue.name is missing")
            elif not isinstance(queue.get("name"), str):
                field_errors.append("queue.name must be a string")

            pool = queue.get("pool")
            if pool is None:
                field_errors.append("queue.pool is missing")
            elif not isinstance(pool, dict):
                field_errors.append("queue.pool must be an object")
            else:
                if pool.get("id") is None:
                    field_errors.append("queue.pool.id is missing")
                elif not isinstance(pool.get("id"), int):
                    field_errors.append("queue.pool.id must be an integer")
                if pool.get("name") is None:
                    field_errors.append("queue.pool.name is missing")
                elif not isinstance(pool.get("name"), str):
                    field_errors.append("queue.pool.name must be a string")
                if pool.get("isHosted") is None:
                    field_errors.append("queue.pool.isHosted is missing")
                elif not isinstance(pool.get("isHosted"), bool):
                    field_errors.append("queue.pool.isHosted must be a boolean")

    for identity_key in ["requestedFor", "requestedBy", "lastChangedBy"]:
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

    orchestration_plan = payload_value.get("orchestrationPlan")
    if orchestration_plan is not None:
        if not isinstance(orchestration_plan, dict):
            field_errors.append("orchestrationPlan must be an object")
        else:
            plan_id = orchestration_plan.get("planId")
            if plan_id is None:
                field_errors.append("orchestrationPlan.planId is missing")
            elif not isinstance(plan_id, str):
                field_errors.append("orchestrationPlan.planId must be a string")

    logs = payload_value.get("logs")
    if logs is not None:
        if not isinstance(logs, dict):
            field_errors.append("logs must be an object")
        else:
            if logs.get("id") is None:
                field_errors.append("logs.id is missing")
            elif not isinstance(logs.get("id"), int):
                field_errors.append("logs.id must be an integer")
            for key in ["type", "url"]:
                value = logs.get(key)
                if value is None:
                    field_errors.append(f"logs.{key} is missing")
                elif not isinstance(value, str):
                    field_errors.append(f"logs.{key} must be a string")

    repository = payload_value.get("repository")
    if repository is not None:
        if not isinstance(repository, dict):
            field_errors.append("repository must be an object")
        else:
            for key in ["id", "type", "name", "url"]:
                value = repository.get(key)
                if value is None:
                    field_errors.append(f"repository.{key} is missing")
                elif not isinstance(value, str):
                    field_errors.append(f"repository.{key} must be a string")

            checkout_submodules = repository.get("checkoutSubmodules")
            if checkout_submodules is None:
                field_errors.append("repository.checkoutSubmodules is missing")
            elif not isinstance(checkout_submodules, bool):
                field_errors.append("repository.checkoutSubmodules must be a boolean")

    retained_by_release = payload_value.get("retainedByRelease")
    if retained_by_release is not None and not isinstance(retained_by_release, bool):
        field_errors.append("retainedByRelease must be a boolean")

    append_commit_message = payload_value.get("appendCommitMessageToRunName")
    if append_commit_message is not None and not isinstance(append_commit_message, bool):
        field_errors.append("appendCommitMessageToRunName must be a boolean")

    return field_errors


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("VNet_third workflow monitoring function triggered")

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

        ci_build_status = body.get("CI_Build_status")
        if ci_build_status is not None:
            ci_build_status_errors = []
            if not isinstance(ci_build_status, str):
                ci_build_status_errors.append("CI_Build_status must be a string")
            elif ci_build_status.strip().lower() != "completed":
                ci_build_status_errors.append("CI_Build_status must be completed")

            if ci_build_status_errors:
                invalid_fields["CI_Build_status"] = ci_build_status_errors

        checkbuildstatus_inputs_payload = body.get("checkbuildstatus_inputs")
        if checkbuildstatus_inputs_payload is not None:
            checkbuildstatus_inputs_errors = validate_checkbuildstatus_inputs(checkbuildstatus_inputs_payload)
            if checkbuildstatus_inputs_errors:
                invalid_fields["checkbuildstatus_inputs"] = checkbuildstatus_inputs_errors

        checkbuildstatus_outputs_payload = body.get("checkbuildstatus_outputs")
        if checkbuildstatus_outputs_payload is not None:
            checkbuildstatus_outputs_errors = validate_checkbuildstatus_outputs(checkbuildstatus_outputs_payload)
            if checkbuildstatus_outputs_errors:
                invalid_fields["checkbuildstatus_outputs"] = checkbuildstatus_outputs_errors

        parse_build_status_json_outputs_payload = body.get("Parse_BuildStatusJSON_outputs")
        if parse_build_status_json_outputs_payload is not None:
            parse_build_status_json_outputs_errors = validate_parse_build_status_json_outputs(parse_build_status_json_outputs_payload)
            if parse_build_status_json_outputs_errors:
                invalid_fields["Parse_BuildStatusJSON_outputs"] = parse_build_status_json_outputs_errors

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
                "message": "VNet_third.py ran successfully without missing fields"
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
