import json
import logging
import azure.functions as func

REQUIRED_KEYS = [
    "base64-vnetpayload_input",
    "QueryLastCommitVNetRepo_input",
    "QueryLastCommitVNetRepo_output",
    "ParseCommitOutput_output",
    "CommitVNetPayloadFile_output",
    "NetworkCIBuild_output"
]


def validate_query_last_commit_vnet_repo_input(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["QueryLastCommitVNetRepo_input must be an object"]

    uri = (
        payload_value.get("uri") or
        payload_value.get("Uri") or
        payload_value.get("relative_uri")
    )

    if uri is None:
        field_errors.append("uri is missing")
    elif not isinstance(uri, str):
        field_errors.append("uri must be a string")

    body_section = payload_value.get("body")
    queries = body_section.get("queries") if isinstance(body_section, dict) else None
    if queries is None or not isinstance(queries, dict):
        field_errors.append("queries is missing or invalid")
    else:
        account = queries.get("account")
        if account is None or (isinstance(account, str) and account.strip() == ""):
            field_errors.append("queries.account is missing")
        elif not isinstance(account, str):
            field_errors.append("queries.account must be a string")

    return field_errors


def validate_query_last_commit_vnet_repo_output(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["QueryLastCommitVNetRepo_output must be an object"]

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
        "count",
        "organization_name",
        "method",
        "relative_uri",
        "repository_name",
        "branch",
        "project",
        "top",
        "value"
    ]
    for key in required_body_fields:
        if body.get(key) is None:
            field_errors.append(f"body.{key} is missing")

    count = body.get("count")
    if count is not None and not isinstance(count, int):
        field_errors.append("body.count must be an integer")

    for key in ["organization_name", "method", "relative_uri", "repository_name", "branch", "project", "top"]:
        value = body.get(key)
        if value is not None and not isinstance(value, str):
            field_errors.append(f"body.{key} must be a string")

    commits = body.get("value")
    if commits is not None:
        if not isinstance(commits, list):
            field_errors.append("body.value must be an array")
        elif len(commits) == 0:
            field_errors.append("body.value must contain at least one commit")
        else:
            for index, commit in enumerate(commits):
                if not isinstance(commit, dict):
                    field_errors.append(f"body.value[{index}] must be an object")
                    continue

                required_commit_fields = ["commitId", "author", "committer", "comment", "changeCounts", "url", "remoteUrl"]
                for key in required_commit_fields:
                    if commit.get(key) is None:
                        field_errors.append(f"body.value[{index}].{key} is missing")

                for key in ["commitId", "comment", "url", "remoteUrl"]:
                    value = commit.get(key)
                    if value is not None and not isinstance(value, str):
                        field_errors.append(f"body.value[{index}].{key} must be a string")

                author = commit.get("author")
                if author is not None:
                    if not isinstance(author, dict):
                        field_errors.append(f"body.value[{index}].author must be an object")
                    else:
                        for key in ["name", "email", "date"]:
                            value = author.get(key)
                            if value is None or (isinstance(value, str) and value.strip() == ""):
                                field_errors.append(f"body.value[{index}].author.{key} is missing")
                            elif not isinstance(value, str):
                                field_errors.append(f"body.value[{index}].author.{key} must be a string")

                committer = commit.get("committer")
                if committer is not None:
                    if not isinstance(committer, dict):
                        field_errors.append(f"body.value[{index}].committer must be an object")
                    else:
                        for key in ["name", "email", "date"]:
                            value = committer.get(key)
                            if value is None or (isinstance(value, str) and value.strip() == ""):
                                field_errors.append(f"body.value[{index}].committer.{key} is missing")
                            elif not isinstance(value, str):
                                field_errors.append(f"body.value[{index}].committer.{key} must be a string")

                change_counts = commit.get("changeCounts")
                if change_counts is not None:
                    if not isinstance(change_counts, dict):
                        field_errors.append(f"body.value[{index}].changeCounts must be an object")
                    else:
                        for key in ["Add", "Edit", "Delete"]:
                            value = change_counts.get(key)
                            if value is None:
                                field_errors.append(f"body.value[{index}].changeCounts.{key} is missing")
                            elif not isinstance(value, int):
                                field_errors.append(f"body.value[{index}].changeCounts.{key} must be an integer")

    return field_errors


def validate_parse_commit_output(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["ParseCommitOutput_output must be an object"]

    body_section = payload_value.get("body")
    if not isinstance(body_section, dict):
        field_errors.append("body must be an object")
    else:
        count = body_section.get("count")
        value = body_section.get("value")

        if count is None:
            field_errors.append("Count is missing")

    commits = body_section.get("value")
    if commits is None:
        field_errors.append("value is missing")
        return field_errors
    if not isinstance(commits, list):
        field_errors.append("value must be an array")
        return field_errors

    for index, commit in enumerate(commits):
        if not isinstance(commit, dict):
            field_errors.append(f"value[{index}] must be an object")
            continue

        required_commit_fields = ["commitId", "author", "committer", "comment", "changeCounts", "url", "remoteUrl"]
        for key in required_commit_fields:
            if commit.get(key) is None:
                field_errors.append(f"value[{index}].{key} is missing")

        for key in ["commitId", "comment", "url", "remoteUrl"]:
            value = commit.get(key)
            if value is not None and not isinstance(value, str):
                field_errors.append(f"value[{index}].{key} must be a string")

        author = commit.get("author")
        if author is not None:
            if not isinstance(author, dict):
                field_errors.append(f"value[{index}].author must be an object")
            else:
                for key in ["name", "email", "date"]:
                    value = author.get(key)
                    if value is None:
                        field_errors.append(f"value[{index}].author.{key} is missing")
                    elif not isinstance(value, str):
                        field_errors.append(f"value[{index}].author.{key} must be a string")

        committer = commit.get("committer")
        if committer is not None:
            if not isinstance(committer, dict):
                field_errors.append(f"value[{index}].committer must be an object")
            else:
                for key in ["name", "email", "date"]:
                    value = committer.get(key)
                    if value is None:
                        field_errors.append(f"value[{index}].committer.{key} is missing")
                    elif not isinstance(value, str):
                        field_errors.append(f"value[{index}].committer.{key} must be a string")

        change_counts = commit.get("changeCounts")
        if change_counts is not None:
            if not isinstance(change_counts, dict):
                field_errors.append(f"value[{index}].changeCounts must be an object")
            else:
                for key in ["Add", "Edit", "Delete"]:
                    value = change_counts.get(key)
                    if value is None:
                        field_errors.append(f"value[{index}].changeCounts.{key} is missing")
                    elif not isinstance(value, int):
                        field_errors.append(f"value[{index}].changeCounts.{key} must be an integer")

    return field_errors


def validate_commit_vnet_payload_file_output(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["CommitVNetPayloadFile_output must be an object"]

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
        "commits",
        "refUpdates",
        "repository",
        "pushedBy",
        "pushId",
        "date",
        "url",
        "_links",
        "input_subscription_id"
    ]
    for key in required_body_fields:
        if body.get(key) is None:
            field_errors.append(f"body.{key} is missing")

    commits = body.get("commits")
    if commits is not None:
        if not isinstance(commits, list):
            field_errors.append("body.commits must be an array")
        elif len(commits) == 0:
            field_errors.append("body.commits must contain at least one item")
        else:
            for index, commit in enumerate(commits):
                if not isinstance(commit, dict):
                    field_errors.append(f"body.commits[{index}] must be an object")
                    continue
                for key in ["commitId", "author", "committer", "comment", "url"]:
                    if commit.get(key) is None:
                        field_errors.append(f"body.commits[{index}].{key} is missing")

    ref_updates = body.get("refUpdates")
    if ref_updates is not None:
        if not isinstance(ref_updates, list):
            field_errors.append("body.refUpdates must be an array")
        elif len(ref_updates) == 0:
            field_errors.append("body.refUpdates must contain at least one item")
        else:
            for index, ref_update in enumerate(ref_updates):
                if not isinstance(ref_update, dict):
                    field_errors.append(f"body.refUpdates[{index}] must be an object")
                    continue
                for key in ["repositoryId", "name", "newObjectId"]:
                    value = ref_update.get(key)
                    if value is None or (isinstance(value, str) and value.strip() == ""):
                        field_errors.append(f"body.refUpdates[{index}].{key} is missing")

    repository = body.get("repository")
    if repository is not None:
        if not isinstance(repository, dict):
            field_errors.append("body.repository must be an object")
        else:
            for key in ["id", "name", "url", "project", "remoteUrl", "sshUrl", "webUrl"]:
                if repository.get(key) is None:
                    field_errors.append(f"body.repository.{key} is missing")

            project = repository.get("project")
            if project is not None:
                if not isinstance(project, dict):
                    field_errors.append("body.repository.project must be an object")
                else:
                    for key in ["id", "name", "url", "state", "revision", "visibility", "lastUpdateTime"]:
                        if project.get(key) is None:
                            field_errors.append(f"body.repository.project.{key} is missing")

    pushed_by = body.get("pushedBy")
    if pushed_by is not None:
        if not isinstance(pushed_by, dict):
            field_errors.append("body.pushedBy must be an object")
        else:
            for key in ["displayName", "id", "uniqueName"]:
                value = pushed_by.get(key)
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    field_errors.append(f"body.pushedBy.{key} is missing")

    push_id = body.get("pushId")
    if push_id is not None and not isinstance(push_id, int):
        field_errors.append("body.pushId must be an integer")

    for key in ["date", "url", "input_subscription_id"]:
        value = body.get(key)
        if value is not None and not isinstance(value, str):
            field_errors.append(f"body.{key} must be a string")

    links = body.get("_links")
    if links is not None and not isinstance(links, dict):
        field_errors.append("body._links must be an object")

    return field_errors


def validate_network_ci_build_output(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["NetworkCIBuild_output must be an object"]

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
        "sourceBranch",
        "status",
        "priority",
        "queueTime",
        "startTime",
        "finishTime",
        "reason",
        "requestedFor",
        "parameters",
        "definition",
        "_links",
        "input_netconfig_filename"
    ]
    for key in required_body_fields:
        if body.get(key) is None:
            field_errors.append(f"body.{key} is missing")

    body_id = body.get("id")
    if body_id is not None and not isinstance(body_id, int):
        field_errors.append("body.id must be an integer")

    for key in [
        "buildNumber",
        "sourceBranch",
        "status",
        "priority",
        "queueTime",
        "startTime",
        "finishTime",
        "reason",
        "parameters",
        "input_netconfig_filename"
    ]:
        value = body.get(key)
        if value is not None and not isinstance(value, str):
            field_errors.append(f"body.{key} must be a string")

    requested_for = body.get("requestedFor")
    if requested_for is not None:
        if not isinstance(requested_for, dict):
            field_errors.append("body.requestedFor must be an object")
        else:
            unique_name = requested_for.get("uniqueName")
            if unique_name is None or (isinstance(unique_name, str) and unique_name.strip() == ""):
                field_errors.append("body.requestedFor.uniqueName is missing")
            elif not isinstance(unique_name, str):
                field_errors.append("body.requestedFor.uniqueName must be a string")

    definition = body.get("definition")
    if definition is not None:
        if not isinstance(definition, dict):
            field_errors.append("body.definition must be an object")
        else:
            definition_id = definition.get("id")
            if definition_id is None:
                field_errors.append("body.definition.id is missing")
            elif not isinstance(definition_id, int):
                field_errors.append("body.definition.id must be an integer")

            definition_name = definition.get("name")
            if definition_name is None or (isinstance(definition_name, str) and definition_name.strip() == ""):
                field_errors.append("body.definition.name is missing")
            elif not isinstance(definition_name, str):
                field_errors.append("body.definition.name must be a string")

    links = body.get("_links")
    if links is not None:
        if not isinstance(links, dict):
            field_errors.append("body._links must be an object")
        else:
            web = links.get("web")
            if web is None:
                field_errors.append("body._links.web is missing")
            elif not isinstance(web, dict):
                field_errors.append("body._links.web must be an object")
            else:
                href = web.get("href")
                if href is None or (isinstance(href, str) and href.strip() == ""):
                    field_errors.append("body._links.web.href is missing")
                elif not isinstance(href, str):
                    field_errors.append("body._links.web.href must be a string")

    return field_errors


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("VNet second workflow monitoring function triggered")

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

        query_last_commit_vnet_repo_input_payload = body.get("QueryLastCommitVNetRepo_input")
        if query_last_commit_vnet_repo_input_payload is not None:
            query_last_commit_vnet_repo_input_errors = validate_query_last_commit_vnet_repo_input(query_last_commit_vnet_repo_input_payload)
            if query_last_commit_vnet_repo_input_errors:
                invalid_fields["QueryLastCommitVNetRepo_input"] = query_last_commit_vnet_repo_input_errors

        query_last_commit_vnet_repo_output_payload = body.get("QueryLastCommitVNetRepo_output")
        if query_last_commit_vnet_repo_output_payload is not None:
            query_last_commit_vnet_repo_output_errors = validate_query_last_commit_vnet_repo_output(query_last_commit_vnet_repo_output_payload)
            if query_last_commit_vnet_repo_output_errors:
                invalid_fields["QueryLastCommitVNetRepo_output"] = query_last_commit_vnet_repo_output_errors

        parse_commit_output_payload = body.get("ParseCommitOutput_output")
        if parse_commit_output_payload is not None:
            parse_commit_output_errors = validate_parse_commit_output(parse_commit_output_payload)
            if parse_commit_output_errors:
                invalid_fields["ParseCommitOutput_output"] = parse_commit_output_errors

        commit_vnet_payload_file_output_payload = body.get("CommitVNetPayloadFile_output")
        if commit_vnet_payload_file_output_payload is not None:
            commit_vnet_payload_file_output_errors = validate_commit_vnet_payload_file_output(commit_vnet_payload_file_output_payload)
            if commit_vnet_payload_file_output_errors:
                invalid_fields["CommitVNetPayloadFile_output"] = commit_vnet_payload_file_output_errors

        network_ci_build_output_payload = body.get("NetworkCIBuild_output")
        if network_ci_build_output_payload is not None:
            network_ci_build_output_errors = validate_network_ci_build_output(network_ci_build_output_payload)
            if network_ci_build_output_errors:
                invalid_fields["NetworkCIBuild_output"] = network_ci_build_output_errors

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
                "message": "VNet_second.py ran successfully without missing fields"
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

