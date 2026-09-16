import json
import logging
import azure.functions as func


REQUIRED_KEYS = [
    "Create_a_new_release_inputs",
    "Create_a_new_release_outputs"
]


def validate_create_a_new_release_inputs(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["Create_a_new_release_inputs must be an object"]

    # Validate HTTP action metadata
    uri = payload_value.get("uri")
    if uri is None or (isinstance(uri, str) and uri.strip() == ""):
        field_errors.append("uri is missing")
    elif not isinstance(uri, str):
        field_errors.append("uri must be a string")

    method = payload_value.get("method")
    if method is None or (isinstance(method, str) and method.strip() == ""):
        field_errors.append("method is missing")
    elif not isinstance(method, str):
        field_errors.append("method must be a string")

    # Logic App HTTP action stores actual payload inside body
    wrapper_body = payload_value.get("body")

    if wrapper_body is None:
        field_errors.append("body is missing")
        return field_errors

    if not isinstance(wrapper_body, dict):
        field_errors.append("body must be an object")
        return field_errors

    # Actual release request body
    body = wrapper_body.get("body")

    if body is None:
        field_errors.append("body.body is missing")
    elif not isinstance(body, dict):
        field_errors.append("body.body must be an object")
    else:
        description = body.get("Description")

        if description is None:
            field_errors.append("body.Description is missing")
        elif not isinstance(description, str):
            field_errors.append("body.Description must be a string")

        is_draft = body.get("IsDraft")

        if is_draft is None:
            field_errors.append("body.IsDraft is missing")
        elif not isinstance(is_draft, bool):
            field_errors.append("body.IsDraft must be a boolean")

        reason = body.get("Reason")

        if reason is None or (
            isinstance(reason, str) and reason.strip() == ""
        ):
            field_errors.append("body.Reason is missing")
        elif not isinstance(reason, str):
            field_errors.append("body.Reason must be a string")

        variables = body.get("Variables")

        if variables is None:
            field_errors.append("body.Variables is missing")
        elif not isinstance(variables, list):
            field_errors.append("body.Variables must be an array")
        elif len(variables) == 0:
            field_errors.append("body.Variables must contain at least one item")
        else:
            for index, variable in enumerate(variables):

                if not isinstance(variable, dict):
                    field_errors.append(
                        f"body.Variables[{index}] must be an object"
                    )
                    continue

                name = variable.get("Name")

                if name is None or (
                    isinstance(name, str) and name.strip() == ""
                ):
                    field_errors.append(
                        f"body.Variables[{index}].Name is missing"
                    )
                elif not isinstance(name, str):
                    field_errors.append(
                        f"body.Variables[{index}].Name must be a string"
                    )

                value = variable.get("Value")

                if value is None:
                    field_errors.append(
                        f"body.Variables[{index}].Value is missing"
                    )
                elif not isinstance(value, str):
                    field_errors.append(
                        f"body.Variables[{index}].Value must be a string"
                    )

    # queries lives inside wrapper_body
    queries = wrapper_body.get("queries")

    if queries is None:
        field_errors.append("queries is missing")
    elif not isinstance(queries, dict):
        field_errors.append("queries must be an object")
    else:

        account = queries.get("account")

        if account is None or (
            isinstance(account, str) and account.strip() == ""
        ):
            field_errors.append("queries.account is missing")
        elif not isinstance(account, str):
            field_errors.append("queries.account must be a string")

        release_def_id = queries.get("releaseDefId")

        if release_def_id is None or (
            isinstance(release_def_id, str)
            and release_def_id.strip() == ""
        ):
            field_errors.append("queries.releaseDefId is missing")
        elif not isinstance(release_def_id, str):
            field_errors.append("queries.releaseDefId must be a string")

    # path also lives inside wrapper_body
    path = wrapper_body.get("path")

    if path is None or (
        isinstance(path, str) and path.strip() == ""
    ):
        field_errors.append("path is missing")
    elif not isinstance(path, str):
        field_errors.append("path must be a string")

    return field_errors


def validate_create_a_new_release_outputs(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["Create_a_new_release_outputs must be an object"]

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
        "_links", "Artifacts", "CreatedBy", "CreatedOn", "Description", "Environments",
        "Id", "Name", "ReleaseDefinition", "Status", "Url", "Variables", "IsDraft"
    ]
    for key in required_body_fields:
        if body.get(key) is None:
            field_errors.append(f"body.{key} is missing")

    links = body.get("_links")
    if links is not None:
        if not isinstance(links, dict):
            field_errors.append("body._links must be an object")
        else:
            for link_key in ["self", "web"]:
                section = links.get(link_key)
                if section is None:
                    field_errors.append(f"body._links.{link_key} is missing")
                elif not isinstance(section, dict):
                    field_errors.append(f"body._links.{link_key} must be an object")
                else:
                    href = section.get("href")
                    if href is None or (isinstance(href, str) and href.strip() == ""):
                        field_errors.append(f"body._links.{link_key}.href is missing")
                    elif not isinstance(href, str):
                        field_errors.append(f"body._links.{link_key}.href must be a string")

    artifacts = body.get("Artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            field_errors.append("body.Artifacts must be an array")
        elif len(artifacts) == 0:
            field_errors.append("body.Artifacts must contain at least one item")
        else:
            for index, artifact in enumerate(artifacts):
                if not isinstance(artifact, dict):
                    field_errors.append(f"body.Artifacts[{index}] must be an object")
                    continue
                for key in ["Alias", "IsPrimary", "SourceId", "Type", "DefinitionReference"]:
                    if artifact.get(key) is None:
                        field_errors.append(f"body.Artifacts[{index}].{key} is missing")

    created_by = body.get("CreatedBy")
    if created_by is not None:
        if not isinstance(created_by, dict):
            field_errors.append("body.CreatedBy must be an object")
        else:
            unique_name = created_by.get("UniqueName")
            if unique_name is None or (isinstance(unique_name, str) and unique_name.strip() == ""):
                field_errors.append("body.CreatedBy.UniqueName is missing")
            elif not isinstance(unique_name, str):
                field_errors.append("body.CreatedBy.UniqueName must be a string")

    environments = body.get("Environments")
    if environments is not None:
        if not isinstance(environments, list):
            field_errors.append("body.Environments must be an array")
        elif len(environments) == 0:
            field_errors.append("body.Environments must contain at least one item")
        else:
            for index, environment in enumerate(environments):
                if not isinstance(environment, dict):
                    field_errors.append(f"body.Environments[{index}] must be an object")
                    continue
                for key in ["Id", "Name", "Status", "ReleaseDefinition", "Release"]:
                    if environment.get(key) is None:
                        field_errors.append(f"body.Environments[{index}].{key} is missing")

    release_definition = body.get("ReleaseDefinition")
    if release_definition is not None:
        if not isinstance(release_definition, dict):
            field_errors.append("body.ReleaseDefinition must be an object")
        else:
            for key in ["Id", "Name", "Url", "_links"]:
                if release_definition.get(key) is None:
                    field_errors.append(f"body.ReleaseDefinition.{key} is missing")

    variables = body.get("Variables")
    if variables is not None:
        if not isinstance(variables, dict):
            field_errors.append("body.Variables must be an object")
        else:
            networkconfig_filename = variables.get("networkconfig_filename")
            if networkconfig_filename is None:
                field_errors.append("body.Variables.networkconfig_filename is missing")
            elif not isinstance(networkconfig_filename, dict):
                field_errors.append("body.Variables.networkconfig_filename must be an object")
            else:
                if networkconfig_filename.get("Value") is None:
                    field_errors.append("body.Variables.networkconfig_filename.Value is missing")

    body_id = body.get("Id")
    if body_id is not None and not isinstance(body_id, int):
        field_errors.append("body.Id must be an integer")

    for key in ["CreatedOn", "Description", "Name", "Status", "Url"]:
        value = body.get(key)
        if value is not None and not isinstance(value, str):
            field_errors.append(f"body.{key} must be a string")

    is_draft = body.get("IsDraft")
    if is_draft is not None and not isinstance(is_draft, bool):
        field_errors.append("body.IsDraft must be a boolean")

    return field_errors


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("VNet_forth workflow monitoring function triggered")

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

        create_release_input_payload = body.get("Create_a_new_release_inputs")
        if create_release_input_payload is not None:
            create_release_input_errors = validate_create_a_new_release_inputs(create_release_input_payload)
            if create_release_input_errors:
                invalid_fields["Create_a_new_release_inputs"] = create_release_input_errors

        create_release_output_payload = body.get("Create_a_new_release_outputs")
        if create_release_output_payload is not None:
            create_release_output_errors = validate_create_a_new_release_outputs(create_release_output_payload)
            if create_release_output_errors:
                invalid_fields["Create_a_new_release_outputs"] = create_release_output_errors

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
                "message": "VNet_forth.py ran successfully without missing fields"
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
