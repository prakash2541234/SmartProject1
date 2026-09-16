import logging
import json
import uuid
import random
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import azure.functions as func


def get_application_id(app_id: str) -> str:
    app_id = app_id.lower()
    return re.sub(r"[^a-z0-9]", "", app_id)


def get_sensitivity(sensitivity_tag: str) -> str:
    switch = {
        "standard": "std",
        "sensitive": "S3",
        "highly sensitive": "S4",
        "highlysensitive": "S4",
        "highly_sensitive": "S4",
        "highly-sensitive": "S4",
    }

    sensitivity = switch.get((sensitivity_tag or "").strip().lower())
    if sensitivity is None:
        raise ValueError(f"Invalid sensitivity tag '{sensitivity_tag}'")
    return sensitivity


def is_valid_sensitivity_tag(sensitivity_tag: str) -> bool:
    allowed_values = {
        "standard",
        "sensitive",
        "highly sensitive",
        "highlysensitive",
        "highly_sensitive",
        "highly-sensitive",
    }
    return (sensitivity_tag or "").strip().lower() in allowed_values


def normalize_subscription_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9-]", "-", (name or "").strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "unknown-sub"


def get_tag_value(tags: dict, *keys: str) -> str:
    for key in keys:
        value = tags.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def get_first_value(sources: list[dict], keys: list[str]) -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value is not None and str(value).strip() != "":
                return str(value).strip()
    return ""


def parse_devops_uri(uri: str) -> dict:
    if not uri:
        return {
            "organization": "mock-org",
            "project": "mock-project",
            "repository_id": "mock-repo",
            "branch": "",
            "top": "1",
        }

    parsed = urlparse(uri)
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    organization = path_parts[0] if len(path_parts) > 0 else "mock-org"
    project = path_parts[1] if len(path_parts) > 1 else "mock-project"

    repository_id = "mock-repo"
    if "repositories" in path_parts:
        repo_index = path_parts.index("repositories")
        if repo_index + 1 < len(path_parts):
            repository_id = path_parts[repo_index + 1]

    branch = query.get("searchCriteria.itemVersion.version", [""])[0]
    top = query.get("searchCriteria.$top", ["1"])[0]

    return {
        "organization": organization,
        "project": project,
        "repository_id": repository_id,
        "branch": branch,
        "top": top,
    }


def build_subscription_name_from_tags(subscription_tags: dict) -> str:
    app_id = get_tag_value(subscription_tags, "stla_application_id", "application_id")
    environment = get_tag_value(subscription_tags, "stla_environment", "environment")
    sensitivity_tag = get_tag_value(subscription_tags, "stla_sensitivity", "sensitivity")

    missing = []
    if not app_id:
        missing.append("stla_application_id")
    if not environment:
        missing.append("stla_environment")
    if not sensitivity_tag:
        missing.append("stla_sensitivity")
    if missing:
        raise ValueError(f"Missing required subscription_tags fields: {missing}")

    return (
        f"sub-{get_application_id(app_id)}-"
        f"{environment.lower()}-{get_sensitivity(sensitivity_tag)}-{random.randint(100, 999)}"
    )


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Mock DevOps Function triggered.')

    try:
        # Read request body
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    # ── Resolve body and sources ─────────────────────────────────────────────
    connector_body = req_body.get("body", {}) if isinstance(req_body, dict) else {}
    if not isinstance(connector_body, dict):
        connector_body = {}

    payload_source = connector_body if (
        "subscription_name" in connector_body
        or "subscription_mgmtgroup" in connector_body
        or "subscription_tags" in connector_body
    ) else req_body

    all_sources = [payload_source, req_body, connector_body]

    # ── Upfront validation ───────────────────────────────────────────────────
    missing_fields = []
    validation_details = []

    # body object
    if not isinstance(req_body.get("body"), dict):
        missing_fields.append("body")
        validation_details.append("'body' is missing or not a valid JSON object — it should contain 'Method' and 'Uri'")

    # body.Method
    method_val = str(connector_body.get("Method", "") or "").strip()
    if not method_val:
        missing_fields.append("body.Method")
        validation_details.append("'body.Method' is missing or empty — expected HTTP method string (e.g. 'POST')")

    # body.Uri
    uri_val = str(connector_body.get("Uri", "") or "").strip()
    if not uri_val:
        missing_fields.append("body.Uri")
        validation_details.append("'body.Uri' is missing or empty — expected the Azure DevOps API URI to commit to")

    # subscription_name
    subscription_name_input = get_first_value(
        all_sources,
        ["subscription_name", "SubscriptionName", "subscriptionName"],
    )
    if not subscription_name_input:
        missing_fields.append("subscription_name")
        validation_details.append("'subscription_name' is missing or empty â€” expected the subscription name to commit")

    # subscription_tags (resolve from all sources)
    subscription_tags = payload_source.get("subscription_tags")
    if not subscription_tags and isinstance(req_body, dict):
        subscription_tags = req_body.get("subscription_tags")
    if not subscription_tags and isinstance(connector_body, dict):
        subscription_tags = connector_body.get("subscription_tags")

    if subscription_tags is None:
        missing_fields.append("subscription_tags")
        validation_details.append("'subscription_tags' is missing — expected a JSON object with 'stla_application_id', 'stla_environment', and 'stla_sensitivity'")
        subscription_tags = {}
    elif not isinstance(subscription_tags, dict):
        missing_fields.append("subscription_tags (wrong type)")
        validation_details.append(f"'subscription_tags' must be a JSON object, got {type(subscription_tags).__name__}")
        subscription_tags = {}
    else:
        required_tag_fields = {
            "stla_application_id": "Application ID used to build the subscription name (e.g. 'myapp')",
            "stla_environment":    "Target environment used as the branch (e.g. 'nonprod', 'prod')",
            "stla_sensitivity":    "Data sensitivity level (e.g. 'standard', 'sensitive', 'highly sensitive')",
        }
        for tag_field, description in required_tag_fields.items():
            val = subscription_tags.get(tag_field)
            if not val or not str(val).strip():
                missing_fields.append(f"subscription_tags.{tag_field}")
                validation_details.append(f"'subscription_tags.{tag_field}' is missing or empty — expected: {description}")

        sensitivity_value = str(subscription_tags.get("stla_sensitivity", "") or "").strip()
        if sensitivity_value and not is_valid_sensitivity_tag(sensitivity_value):
            missing_fields.append("subscription_tags.stla_sensitivity (invalid)")
            validation_details.append(
                f"'subscription_tags.stla_sensitivity' has invalid value '{sensitivity_value}' â€” expected one of: "
                "standard, sensitive, highly sensitive"
            )

    # subscription_mgmtgroup
    mgmt_group_val = get_first_value(all_sources, ["subscription_mgmtgroup", "subscription_mgmt_group", "management_group"])
    if not mgmt_group_val:
        missing_fields.append("subscription_mgmtgroup")
        validation_details.append("'subscription_mgmtgroup' is missing or empty — expected the management group name the subscription belongs to")

    # repository_name
    repo_name_val = get_first_value(all_sources, ["repository_name", "repo_name", "repositoryName"])
    if not repo_name_val:
        missing_fields.append("repository_name")
        validation_details.append("'repository_name' is missing or empty — expected the Azure DevOps repository name (e.g. 'azglz_pipeline_createsub')")

    # ── Return clear error if anything is missing ────────────────────────────
    if missing_fields:
        logging.warning(f"Validation failed. Missing/invalid fields: {missing_fields}")
        return func.HttpResponse(
            body=json.dumps(
                {
                    "status": "FAILED",
                    "error": "Request failed due to missing or invalid input payload fields.",
                    "missing_fields": missing_fields,
                    "details": validation_details,
                    "hint": (
                        "Please provide all required fields. "
                        "Check 'missing_fields' for the list of missing inputs "
                        "and 'details' for what each field should contain."
                    ),
                },
                indent=2
            ),
            status_code=400,
            mimetype="application/json",
        )

    # ── All fields validated — extract values ────────────────────────────────
    try:
        subscription_name_generated = ""

        connector_http_method = method_val
        uri_in = uri_val
        repository_name = repo_name_val

        devops_uri_info = parse_devops_uri(uri_in)

        sub_name = normalize_subscription_name(subscription_name_input)

        mgmt_group = mgmt_group_val

    except ValueError as ve:
        return func.HttpResponse(
            body=json.dumps(
                {
                    "status": "FAILED",
                    "error": "Request failed due to missing or invalid input payload fields.",
                    "missing_fields": [str(ve)],
                    "details": [str(ve)],
                    "hint": "Check the 'details' field for what went wrong during value processing.",
                },
                indent=2
            ),
            status_code=400,
            mimetype="application/json",
        )

    # Generate fake commit ID (no dashes → like real API)
    commit_id = uuid.uuid4().hex

    # Current UTC time
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    account = ""
    queries = req_body.get("queries", {}) if isinstance(req_body, dict) else {}
    if isinstance(queries, dict):
        account = str(queries.get("account", "") or "").strip()

    if not account:
        account = devops_uri_info["organization"] or "mock-org"

    mock_headers = {
        "Cache-Control": "no-store, no-cache",
        "Pragma": "no-cache",
        "Content-Type": "application/json; charset=utf-8; api-version=7.1",
        "Date": datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "X-TFS-ProcessId": str(uuid.uuid4()),
        "ActivityId": str(uuid.uuid4()),
    }

    response = {
        "statusCode": 200,
        "headers": mock_headers,
        "body": {
            "count": 1,
            "value": [
                {
                    "commitId": commit_id,
                    "author": {
                        "name": "SYSTEM USER",
                        "email": "system@mock.dev",
                        "date": now,
                    },
                    "committer": {
                        "name": "SYSTEM USER",
                        "email": "system@mock.dev",
                        "date": now,
                    },
                    "comment": f"commiting subscription {sub_name} json.",
                    "changeCounts": {
                        "Add": 1,
                        "Edit": 0,
                        "Delete": 0,
                    },
                    "url": (
                        f"https://dev.azure.com/{account}/{devops_uri_info['project']}"
                        f"/_apis/git/repositories/{devops_uri_info['repository_id']}/commits/{commit_id}"
                    ),
                    "remoteUrl": (
                        f"https://dev.azure.com/{account}/{devops_uri_info['project']}"
                        f"/_git/{repository_name or devops_uri_info['repository_id']}/commit/{commit_id}"
                    ),
                    "inputs": {
                        "request_method": req_body.get("method", "") if isinstance(req_body, dict) else "",
                        "connector_http_method": connector_http_method,
                        "connector_uri": uri_in,
                        "subscription_name": subscription_name_input,
                        "subscription_name_generated": subscription_name_generated,
                        "subscription_name_resolved": sub_name,
                        "subscription_mgmtgroup": mgmt_group,
                        "subscription_tags": subscription_tags,
                        "branch": devops_uri_info["branch"],
                        "top": devops_uri_info["top"],
                    },
                }
            ]
        },
    }

    return func.HttpResponse(
        body=json.dumps(response),
        status_code=200,
        mimetype="application/json"
    )
