"""
Azure Function App to create a Service Principal

- Creates App Registration
- Creates associated Service Principal
- Assigns subscription role (optional)
- Adds SP to standard AAD group
- Stores request + SP details in Cosmos DB
- Optional Logic App callback
"""

"""import logging
import json
import os
import random
import re
import string
import uuid
import asyncio
import aiohttp
import azure.functions as func

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.cosmos import CosmosClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# =====================================================
# CONFIGURATION
# =====================================================
COSMOS_ENDPOINT = os.getenv("COSMOS_SQL_ENDPOINT")
DATABASE_NAME = os.getenv("COSMOS_SQL_DATABASE", "azglz")
INPUT_CONTAINER = os.getenv("COSMOS_SQL_CONTAINER_SPREQUEST", "sp_requests")
OUTPUT_CONTAINER = os.getenv("COSMOS_SQL_CONTAINER_SP", "service_principals")

GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

MI_COSMOS = os.getenv("ManagedIdentityClientID")
MI_GRAPH = os.getenv("ManagedIdentityClientID_AppReg")

AAD_GOLDEN_GROUP = "AAD-GoldenAMIReaderWindows&Ubuntu"

# =====================================================
# HELPERS
# =====================================================
def cosmos_client():
    if MI_COSMOS:
        cred = ManagedIdentityCredential(client_id=MI_COSMOS)
    else:
        cred = DefaultAzureCredential()
    return CosmosClient(COSMOS_ENDPOINT, credential=cred)


def clean_app_id(appid: str) -> str:
    return re.sub(r'[^a-z0-9-]', '', appid.lower())


async def get_token(scope, mi_id=None):
    cred = ManagedIdentityCredential(client_id=mi_id) if mi_id else DefaultAzureCredential()
    token = await asyncio.to_thread(cred.get_token, scope)
    return token.token


# =====================================================
# GRAPH OPERATIONS
# =====================================================
async def create_app_and_sp(token, display_name):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{GRAPH_ENDPOINT}/applications",
            headers=headers,
            json={"displayName": display_name, "signInAudience": "AzureADMyOrg"}
        ) as r:
            app = await r.json()

    app_id = app["appId"]
    app_obj_id = app["id"]

    # Retry SP creation (AAD propagation delay)
    for _ in range(5):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GRAPH_ENDPOINT}/servicePrincipals",
                headers=headers,
                json={"appId": app_id}
            ) as r:
                if r.status in (200, 201):
                    sp = await r.json()
                    return app_id, app_obj_id, sp["id"]
        await asyncio.sleep(2)

    raise RuntimeError("Service Principal creation failed")


async def add_sp_to_group(token, sp_object_id):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{GRAPH_ENDPOINT}/groups?$filter=displayName eq '{AAD_GOLDEN_GROUP}'",
            headers=headers
        ) as r:
            groups = (await r.json()).get("value", [])
            if not groups:
                logging.warning("AAD group not found")
                return

            group_id = groups[0]["id"]

        await session.post(
            f"{GRAPH_ENDPOINT}/groups/{group_id}/members/$ref",
            headers=headers,
            json={"@odata.id": f"{GRAPH_ENDPOINT}/directoryObjects/{sp_object_id}"}
        )


# =====================================================
# ROLE ASSIGNMENT
# =====================================================
async def assign_role(subscription_id, role_name, principal_id):
    token = await get_token("https://management.azure.com/.default", MI_GRAPH)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://management.azure.com/subscriptions/{subscription_id}/providers/"
            f"Microsoft.Authorization/roleDefinitions"
            f"?api-version=2022-04-01&$filter=roleName eq '{role_name}'",
            headers=headers
        ) as r:
            role_def = (await r.json())["value"][0]["id"]

        await session.put(
            f"https://management.azure.com/subscriptions/{subscription_id}/providers/"
            f"Microsoft.Authorization/roleAssignments/{uuid.uuid4()}?api-version=2022-04-01",
            headers=headers,
            json={
                "properties": {
                    "roleDefinitionId": role_def,
                    "principalId": principal_id
                }
            }
        )


# =====================================================
# CORE LOGIC
# =====================================================
async def handle_request(payload):
    sp = payload["sp_parameters"]
    req = payload["request_parameters"]

    display = f"sp-azf-{clean_app_id(sp['application_id'])}-{sp['environment']}-" \
              f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=5))}"

    graph_token = await get_token(GRAPH_SCOPE, MI_GRAPH)

    app_id, app_obj_id, sp_obj_id = await create_app_and_sp(graph_token, display)

    # Cosmos persistence
    client = cosmos_client()
    db = client.get_database_client(DATABASE_NAME)

    db.get_container_client(INPUT_CONTAINER).upsert_item(payload)
    db.get_container_client(OUTPUT_CONTAINER).upsert_item({
        "id": display,
        "appreg_object_id": app_obj_id,
        "service_principal_id": sp_obj_id,
        "display_name": display,
        "catalog_task_sysid": req.get("catalog_task_sysid")
    })

    client.close()

    return display, sp_obj_id


# =====================================================
# HTTP ENTRY POINT
# =====================================================
@app.function_name("CreateServicePrincipal")
@app.route(route="createServicePrincipal", methods=["POST"])
async def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()

        sp_name, sp_id = await handle_request(body)

        sp_params = body.get("sp_parameters", {})
        if sp_params.get("subscription_id") and sp_params.get("subscription_role"):
            await assign_role(
                sp_params["subscription_id"],
                sp_params["subscription_role"],
                sp_id
            )

        token = await get_token(GRAPH_SCOPE, MI_GRAPH)
        await add_sp_to_group(token, sp_id)

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "sp_name": sp_name,
                "sp_id": sp_id
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error("SP creation failed", exc_info=True)
        return func.HttpResponse(
            json.dumps({"status": "error", "message": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import azure.functions as func
import requests
from azure.identity import DefaultAzureCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.authorization.models import RoleAssignmentCreateParameters

app = func.FunctionApp()
logger = logging.getLogger(__name__)

CREDENTIAL = DefaultAzureCredential()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MGMT_BASE = "https://management.azure.com"

ROLE_DEFINITION_IDS = {
    "reader": "acdd72a7-3385-48ef-bd42-f606fba81ae7",
    "contributor": "b24988ac-6180-42a0-ab88-20f7382dd24c",
    "owner": "8e3af657-a8ff-443c-a75c-2fe8c4bcb635",
}


def _json_response(payload: dict, status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def _read_json_body(req: func.HttpRequest):
    try:
        body = req.get_json()
    except ValueError as exc:
        return None, f"Invalid JSON body: {exc}"

    if not isinstance(body, dict):
        return None, "Request body must be a JSON object."

    return body, None


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_text(value):
    return (value or "").strip()


def _escape_odata_literal(value: str) -> str:
    return (value or "").replace("'", "''")


def _get_token(scope: str) -> str:
    return CREDENTIAL.get_token(scope).token


def _mgmt_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token('https://management.azure.com/.default')}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _graph_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token('https://graph.microsoft.com/.default')}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _extract_error_message(response) -> str:
    try:
        body = response.json()
    except Exception:
        return (response.text or "").strip() or "Unknown Azure error."

    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            details = err.get("details") or []
            if details and isinstance(details, list) and isinstance(details[0], dict):
                return details[0].get("message") or err.get("message") or str(body)
            return err.get("message") or str(body)
        return body.get("message") or str(body)

    return str(body)


def _raise_graph_error(response, fallback_message: str):
    raise RuntimeError(f"{fallback_message} {response.status_code}: {_extract_error_message(response)}")


def _is_graph_sp_app_reference_error(error_code: str = "", message: str = "") -> bool:
    code = (error_code or "").strip().lower()
    text = (message or "").lower()
    return (
        code in {"request_badrequest", "badrequest"}
        and "does not reference a valid application object" in text
    )


def _is_graph_permission_error(error_code: str = "", message: str = "") -> bool:
    code = (error_code or "").strip().lower()
    text = (message or "").lower()
    if code in {"authorization_requestdenied", "accessdenied", "insufficientprivileges"}:
        return True
    markers = [
        "insufficient privileges",
        "authorization_requestdenied",
        "does not have permission",
        "permission denied",
    ]
    return any(marker in text for marker in markers)


def _graph_request_details(response) -> dict:
    try:
        body = response.json()
    except Exception:
        return {}

    if not isinstance(body, dict):
        return {}

    err = body.get("error")
    if not isinstance(err, dict):
        return {}

    inner = err.get("innerError")
    if not isinstance(inner, dict):
        inner = {}

    return {
        "code": err.get("code") or "",
        "message": err.get("message") or "",
        "inner_error": inner,
        "raw": body,
    }


def _ensure_tenant_matches(request_tenant_id: str):
    requested = _normalize_text(request_tenant_id)
    configured = _normalize_text(os.getenv("AZURE_TENANT_ID", ""))
    if requested and configured and requested.lower() != configured.lower():
        raise RuntimeError(
            "tenantId in request does not match backend AZURE_TENANT_ID."
        )


def _resolve_subscription(subscription_hint: str):
    hint = _normalize_text(subscription_hint)
    if not hint:
        raise RuntimeError("subscription is required.")

    url = f"{MGMT_BASE}/subscriptions?api-version=2020-01-01"
    response = requests.get(url, headers=_mgmt_headers(), timeout=30)
    if not response.ok:
        raise RuntimeError(_extract_error_message(response))

    subscriptions = response.json().get("value", [])
    for sub in subscriptions:
        sub_id = (sub.get("subscriptionId") or "").strip()
        display_name = (sub.get("displayName") or "").strip()
        if sub_id.lower() == hint.lower() or display_name.lower() == hint.lower():
            return sub_id, {
                "display_name": display_name,
                "state": sub.get("state"),
                "tenant_id": sub.get("tenantId"),
            }

    raise RuntimeError(f"Subscription '{subscription_hint}' was not found for this principal.")


def _normalize_scope(scope_type: str, subscription_id: str, resource_group: str, custom_scope: str) -> str:
    if scope_type == "subscription":
        return f"/subscriptions/{subscription_id}"

    if scope_type == "resource-group":
        if not resource_group:
            raise RuntimeError("resourceGroup is required when scopeType is resource-group.")
        return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"

    if scope_type == "custom":
        if not custom_scope:
            raise RuntimeError("customScope is required when scopeType is custom.")
        return custom_scope if custom_scope.startswith("/") else f"/{custom_scope}"

    raise RuntimeError(f"Unknown scopeType '{scope_type}'.")


def _format_key_value_tags(tags: dict | None) -> list[str]:
    result = []
    for key, value in (tags or {}).items():
        k = _normalize_text(str(key))
        v = _normalize_text(str(value))
        if not k:
            continue
        result.append(f"{k}={v}" if v else k)
    return result


def _lookup_application_by_name(service_principal_name: str):
    escaped_name = _escape_odata_literal(service_principal_name)
    url = (
        f"{GRAPH_BASE}/applications"
        f"?$filter=displayName eq '{escaped_name}'&$select=id,appId,displayName"
    )
    response = requests.get(url, headers=_graph_headers(), timeout=30)
    if not response.ok:
        _raise_graph_error(response, "Failed to lookup application in Microsoft Graph.")

    items = response.json().get("value", [])
    return items[0] if items else None


def _create_application(service_principal_name: str):
    response = requests.post(
        f"{GRAPH_BASE}/applications",
        headers=_graph_headers(),
        json={
            "displayName": service_principal_name,
            "signInAudience": "AzureADMyOrg",
        },
        timeout=30,
    )
    if response.status_code not in (200, 201):
        _raise_graph_error(response, "Failed to create application in Microsoft Graph.")
    return response.json()


def _lookup_service_principal_by_app_id(app_id: str):
    url = (
        f"{GRAPH_BASE}/servicePrincipals"
        f"?$filter=appId eq '{_escape_odata_literal(app_id)}'&$select=id,appId,displayName"
    )
    response = requests.get(url, headers=_graph_headers(), timeout=30)
    if not response.ok:
        _raise_graph_error(response, "Failed to lookup service principal in Microsoft Graph.")
    items = response.json().get("value", [])
    return items[0] if items else None


def _create_service_principal(app_id: str):
    max_attempts = 8
    wait_seconds = 5
    last_response = None

    for attempt in range(1, max_attempts + 1):
        response = requests.post(
            f"{GRAPH_BASE}/servicePrincipals",
            headers=_graph_headers(),
            json={"appId": app_id},
            timeout=30,
        )
        last_response = response
        if response.status_code in (200, 201):
            return response.json(), attempt, (attempt - 1) * wait_seconds

        details = _graph_request_details(response)
        if _is_graph_sp_app_reference_error(details.get("code", ""), details.get("message", "")) and attempt < max_attempts:
            time.sleep(wait_seconds)
            continue

        _raise_graph_error(response, "Failed to create service principal in Microsoft Graph.")

    if last_response is not None:
        _raise_graph_error(last_response, "Failed to create service principal in Microsoft Graph.")

    raise RuntimeError("Failed to create service principal in Microsoft Graph.")


def _wait_for_service_principal_replication(principal_id: str, max_attempts: int = 12, base_sleep: int = 5):
    url = f"{GRAPH_BASE}/servicePrincipals/{principal_id}"

    total_wait = 0
    for attempt in range(1, max_attempts + 1):
        response = requests.get(url, headers=_graph_headers(), timeout=10)
        if response.status_code == 200:
            return True, attempt, total_wait

        sleep_s = base_sleep * attempt
        total_wait += sleep_s
        time.sleep(sleep_s)

    return False, max_attempts, total_wait


def _assign_role_to_principal(principal_id: str, role_key: str, scope: str, subscription_id: str, principal_type: str = "ServicePrincipal"):
    role_key = (role_key or "contributor").strip().lower()
    role_definition_id = ROLE_DEFINITION_IDS.get(role_key)
    if not role_definition_id:
        raise RuntimeError(f"Invalid role '{role_key}'. Use reader, contributor, or owner.")

    credential = CREDENTIAL
    client = AuthorizationManagementClient(credential, subscription_id)
    assignment_name = str(uuid4())

    params = RoleAssignmentCreateParameters(
        principal_id=principal_id,
        role_definition_id=f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/{role_definition_id}",
        principal_type=principal_type,
    )

    result = client.role_assignments.create(
        scope=scope,
        role_assignment_name=assignment_name,
        parameters=params,
    )

    return {
        "assignment_name": assignment_name,
        "scope": scope,
        "role_definition_id": role_definition_id,
        "id": getattr(result, "id", None),
    }


def _retry_role_assignment_if_principal_just_created(
    principal_id: str,
    role_key: str,
    normalized_scope: str,
    subscription_id: str,
):
    max_attempts = 6
    base_sleep = 3
    last_err = None

    for attempt in range(1, max_attempts + 1):
        try:
            return _assign_role_to_principal(
                principal_id=principal_id,
                role_key=role_key,
                scope=normalized_scope,
                subscription_id=subscription_id,
            )
        except RuntimeError as exc:
            text = str(exc).lower()

            retryable_substrings = [
                "does not exist",
                "was not found",
                "could not find",
                "principal was not found",
                "directory object not found",
                "resource not found",
            ]
            if not any(s in text for s in retryable_substrings):
                raise

            deny_markers = [
                "authorizationfailed",
                "insufficient privileges",
                "not authorized",
                "forbidden",
                "deny assignment",
            ]
            if any(s in text for s in deny_markers):
                raise

            sleep_s = base_sleep * attempt
            time.sleep(sleep_s)
            last_err = exc

    raise last_err if last_err else RuntimeError("Role assignment failed after retries.")


def provision_service_principal_from_payload(payload: dict):
    subscription_id, subscription_meta = _resolve_subscription(payload["subscription"])
    service_principal_name = _normalize_text(payload.get("servicePrincipalName"))
    tenant_id = _normalize_text(payload.get("tenantId") or os.getenv("AZURE_TENANT_ID", ""))
    _ensure_tenant_matches(tenant_id)

    role_key = _normalize_text(payload.get("role") or "contributor")
    scope_type = _normalize_text(payload.get("scopeType") or "subscription")
    resource_group = _normalize_text(payload.get("resourceGroup"))
    custom_scope = _normalize_text(payload.get("customScope"))
    credential_type = _normalize_text(payload.get("credentialType") or "client-secret")
    secret_display_name = _normalize_text(payload.get("secretDisplayName") or "sp-client-secret")
    secret_validity_months = int(payload.get("secretValidityMonths", 12))
    create_if_missing = _as_bool(payload.get("createIfMissing", True), True)
    assign_role_now = _as_bool(payload.get("assignRoleNow", True), True)
    dry_run = _as_bool(payload.get("dryRun", True), True)
    tags = payload.get("tags") or {}
    tag_list = _format_key_value_tags(tags)

    normalized_scope = _normalize_scope(
        scope_type=scope_type,
        subscription_id=subscription_id,
        resource_group=resource_group,
        custom_scope=custom_scope,
    )

    plan = {
        "subscription_id": subscription_id,
        "subscription_name": subscription_meta.get("display_name"),
        "service_principal_name": service_principal_name,
        "tenant_id": tenant_id,
        "role": role_key,
        "scope_type": scope_type,
        "scope": normalized_scope,
        "resource_group": resource_group,
        "credential_type": credential_type,
        "secret_display_name": secret_display_name,
        "secret_validity_months": secret_validity_months,
        "create_if_missing": create_if_missing,
        "assign_role_now": assign_role_now,
        "tags": tags,
        "dry_run": dry_run,
    }

    if dry_run:
        return {
            "mode": "dry-run",
            "plan": plan,
            "message": "Service Principal payload validated. Set dryRun=false to apply in Azure.",
        }

    if credential_type == "certificate":
        raise RuntimeError("certificate credential type is not implemented yet. Use client-secret.")

    application = _lookup_application_by_name(service_principal_name)
    application_action = "existing"

    if not application:
        if not create_if_missing:
            raise RuntimeError(
                f"Application '{service_principal_name}' was not found and createIfMissing is false."
            )
        application = _create_application(service_principal_name)
        application_action = "created"

    app_object_id = application.get("id")
    app_id = application.get("appId")
    if not app_object_id or not app_id:
        raise RuntimeError("Microsoft Graph did not return application identifiers.")

    service_principal = _lookup_service_principal_by_app_id(app_id)
    service_principal_action = "existing"
    sp_creation_attempts = 0
    sp_creation_wait_seconds = 0

    if not service_principal:
        service_principal, sp_creation_attempts, sp_creation_wait_seconds = _create_service_principal(app_id)
        service_principal_action = "created"

    principal_id = service_principal.get("id")
    if not principal_id:
        raise RuntimeError("Microsoft Graph did not return service principal object id.")

    if tag_list:
        tag_response = requests.patch(
            f"{GRAPH_BASE}/servicePrincipals/{principal_id}",
            headers=_graph_headers(),
            json={"tags": tag_list},
            timeout=30,
        )
        if tag_response.status_code not in (200, 201, 204):
            _raise_graph_error(tag_response, "Failed to update service principal tags in Microsoft Graph.")

    credential_result = None
    if credential_type == "client-secret":
        secret_expiry = (
            datetime.now(timezone.utc) + timedelta(days=30 * max(secret_validity_months, 1))
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        add_password_response = requests.post(
            f"{GRAPH_BASE}/applications/{app_object_id}/addPassword",
            headers=_graph_headers(),
            json={
                "passwordCredential": {
                    "displayName": secret_display_name,
                    "endDateTime": secret_expiry,
                }
            },
            timeout=30,
        )
        if add_password_response.status_code not in (200, 201):
            _raise_graph_error(add_password_response, "Failed to create client secret in Microsoft Graph.")

        password_body = add_password_response.json()
        credential_result = {
            "type": "client-secret",
            "display_name": secret_display_name,
            "key_id": password_body.get("keyId"),
            "end_date_time": secret_expiry,
            "secret_text": password_body.get("secretText"),
        }

    role_assignment = None
    replication_wait = {"attempts": 0, "waited_seconds": 0}

    if assign_role_now:
        ok, attempts, waited = _wait_for_service_principal_replication(principal_id=principal_id)
        replication_wait = {"attempts": attempts, "waited_seconds": waited}
        if not ok:
            raise RuntimeError(
                f"Service Principal '{principal_id}' not yet replicated in Azure AD. Please retry shortly."
            )

        role_assignment = _retry_role_assignment_if_principal_just_created(
            principal_id=principal_id,
            role_key=role_key,
            normalized_scope=normalized_scope,
            subscription_id=subscription_id,
        )

    return {
        "mode": "applied",
        "plan": plan,
        "application": {
            "id": app_object_id,
            "app_id": app_id,
            "display_name": application.get("displayName") or service_principal_name,
            "action": application_action,
        },
        "service_principal": {
            "id": principal_id,
            "app_id": service_principal.get("appId") or app_id,
            "display_name": service_principal.get("displayName") or service_principal_name,
            "action": service_principal_action,
        },
        "service_principal_creation": {
            "attempts": sp_creation_attempts,
            "wait_seconds": sp_creation_wait_seconds,
        },
        "replication_wait": replication_wait,
        "credential": credential_result,
        "role_assignment": role_assignment,
        "message": "Service Principal configuration applied in Azure.",
    }


@app.route(route="create-service-principal", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def create_service_principal(req: func.HttpRequest) -> func.HttpResponse:
    logger.info("Processing create-service-principal request")

    payload, error = _read_json_body(req)
    if error:
        return _json_response({"status": "error", "message": error}, 400)

    required = ["subscription", "servicePrincipalName"]
    missing = [field for field in required if not _normalize_text(payload.get(field))]
    if missing:
        return _json_response(
            {
                "status": "error",
                "message": "Missing required fields.",
                "missing_fields": missing,
            },
            400,
        )

    try:
        result = provision_service_principal_from_payload(payload)
        status_code = 202 if result.get("mode") == "dry-run" else 201
        if result.get("mode") == "dry-run":
            status_code = 200
        return _json_response(
            {
                "status": "success",
                "received_payload": payload,
                **result,
            },
            status_code,
        )

    except RuntimeError as exc:
        text = str(exc)
        lowered = text.lower()

        if "insufficient privileges" in lowered or "authorizationfailed" in lowered:
            return _json_response(
                {
                    "status": "error",
                    "code": "authorization_failed",
                    "message": text,
                },
                403,
            )

        if "not yet replicated" in lowered:
            return _json_response(
                {
                    "status": "error",
                    "code": "replication_pending",
                    "message": text,
                },
                409,
            )

        return _json_response(
            {
                "status": "error",
                "message": text,
            },
            400,
        )

    except Exception as exc:
        logger.exception("Unexpected error in create-service-principal")
        return _json_response(
            {
                "status": "error",
                "message": str(exc),
            },
            500,
        )
