from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime, timedelta, timezone
import os
import shutil
import subprocess
import time
import uuid
import secrets
import string
import requests
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.authorization.models import RoleAssignmentCreateParameters
from django.core.cache import cache
from django.http import JsonResponse
from apis.moniter.serializers import (
    AssignRoleSerializer,
    CreateVNetSerializer,
    CreateResourceGroupSerializer,
    CreateVMSerializer,
    CreateKeyVaultSerializer,
    CreateServicePrincipalSerializer,
    CreateUserSerializer,
    CreateGroupSerializer,
    CreateBackupSerializer,
    AssignServicePrincipalRoleSerializer,
    AzureNSGSerializer,
    KeyVaultWithPESerializer,
    AssignRole1Serializer,
)
from stl.azure_client import get_credentials
import logging
from azure.identity import DefaultAzureCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from rest_framework.decorators import api_view

from .models import APILog, ManagedServicePrincipal, RequestPayload


ROLE_DEFINITION_IDS = {
    "reader": "acdd72a7-3385-48ef-bd42-f606fba81ae7",
    "contributor": "b24988ac-6180-42a0-ab88-20f7382dd24c",
    "owner": "8e3af657-a8ff-443c-a75c-2fe8c4bcb635",
}
AD_COUNT_CACHE_KEY = "azure_ad_users_count_last_success"
NETWORK_API_VERSION = "2023-09-01"

def provision_nsg_from_payload(data):
    return{
        "mode" : data.get("mode", "create"),
        "message": "NSG processed successfully (dummy response)"
    }

class AzureGraphAPIError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code or "graph_api_error"
        self.status_code = status_code
        self.details = details or {}


def _normalize_scope(scope: str, subscription_id: str) -> str:
    if scope:
        return scope if scope.startswith("/") else f"/{scope}"
    return f"/subscriptions/{subscription_id}"

def _extract_error_message(response):
    try:
        body = response.json()
    except ValueError:
        return response.text

    if isinstance(body, dict):
        if isinstance(body.get("error"), dict):
            details = body["error"].get("details") or []
            if details and isinstance(details, list) and isinstance(details[0], dict):
                return details[0].get("message") or body["error"].get("message") or str(body)
            return body["error"].get("message") or str(body)
        return body.get("message") or str(body)

    return str(body)

def _extract_error_details(response):
    try:
        body = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return {
            "code": "",
            "message": text or "Unknown error response.",
            "inner_error": {},
            "raw": text,
        }
    
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            message = err.get("message") or body.get("message") or str(body)
            return {
                "code": err.get("code") or "",
                "message": message,
                "inner_error": err.get("innerError") if isinstance(err.get("innerError"), dict) else {},
                "raw": body,
            }

        return {
            "code": body.get("code") if isinstance(body.get("code"), str) else "",
            "message": body.get("message") or str(body),
            "inner_error": {},
            "raw": body,
        }

    return {
        "code": "",
        "message": str(body),
        "inner_error": {},
        "raw": body,
    }

def _raise_graph_api_error(response, fallback_message: str = "Microsoft Graph API request failed."):
    details = _extract_error_details(response)
    message = details.get("message") or fallback_message
    raise AzureGraphAPIError(
        code=details.get("code") or "graph_api_error",
        message=message,
        status_code=response.status_code or 400,
        details=details,
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

def _is_graph_sp_app_reference_error(error_code: str = "", message: str = "") -> bool:
    code = (error_code or "").strip().lower()
    text = (message or "").lower()
    return (
        code in {"request_badrequest", "badrequest"}
        and "does not reference a valid application object" in text
    )

def _is_graph_invalid_upn_domain_error(error_code: str = "", message: str = "") -> bool:
    code = (error_code or "").strip().lower()
    text = (message or "").lower()
    return (
        code in {"request_badrequest", "badrequest"}
        and "domain portion of the userprincipalname property is invalid" in text
    )

def _is_graph_member_exists_error(error_code: str = "", message: str = "") -> bool:
    code = (error_code or "").strip().lower()
    text = (message or "").lower()
    return (
        code in {"request_badrequest", "badrequest"}
        and "added object references already exist" in text
    )

def _graph_request_context(details: dict):
    inner = (details or {}).get("inner_error") or {}
    context = {}
    if inner.get("date"):
        context["date"] = inner.get("date")
    if inner.get("request-id"):
        context["request_id"] = inner.get("request-id")
    if inner.get("client-request-id"):
        context["client_request_id"] = inner.get("client-request-id")
    return context

def _extract_upn_domain(user_principal_name: str) -> str:
    upn = (user_principal_name or "").strip()
    if "@" not in upn:
        return ""
    return upn.rsplit("@", 1)[1].strip().lower()

def list_verified_domains():
    headers = _graph_headers()
    url = "https://graph.microsoft.com/v1.0/domains?$select=id,isVerified,isDefault"
    response = requests.get(url, headers=headers, timeout=20)
    if not response.ok:
        _raise_graph_api_error(response, "Failed to fetch verified domains from Microsoft Graph.")

    verified = []
    for item in response.json().get("value", []):
        if bool(item.get("isVerified", False)):
            domain_name = (item.get("id") or "").strip().lower()
            if domain_name:
                verified.append({
                    "domain": domain_name,
                    "is_default": bool(item.get("isDefault", False)),
                })

    verified.sort(key=lambda d: (not d["is_default"], d["domain"]))
    return verified

def _is_dns_resolution_error(message: str) -> bool:
    text = (message or "").lower()
    markers = [
        "failed to resolve",
        "getaddrinfo failed",
        "name or service not known",
        "temporary failure in name resolution",
        "login.microsoftonline.com",
    ]
    return any(marker in text for marker in markers)


def _proxy_settings_hint() -> str:
    proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
    proxy_values = {key: (os.environ.get(key) or "").strip() for key in proxy_keys}
    configured = {key: value for key, value in proxy_values.items() if value}
    if not configured:
        return ""

    if any("127.0.0.1:9" in value or "localhost:9" in value for value in configured.values()):
        return (
            "Your proxy environment variables point to 127.0.0.1:9, which refuses the connection. "
            "Clear or correct HTTP_PROXY / HTTPS_PROXY / ALL_PROXY before calling Azure."
        )

    return (
        "Check HTTP_PROXY / HTTPS_PROXY / ALL_PROXY in your environment. "
        "Azure authentication is attempting to use a proxy and cannot connect."
    )


def _mask_secret(value: str, visible: int = 4) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= visible:
        return "*" * len(raw)
    return f"{raw[:visible]}***{raw[-visible:]}"

def _to_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default

def _management_headers():
    cred = get_credentials()
    token = cred.get_token("https://management.azure.com/.default")
    return {
        "Authorization": f"Bearer {token.token}",
        "Content-Type": "application/json",
    }

def _graph_headers():
    cred = get_credentials()
    token = cred.get_token("https://graph.microsoft.com/.default")
    return {
        "Authorization": f"Bearer {token.token}",
        "Content-Type": "application/json",
    }

def _escape_odata_literal(value: str) -> str:
    return (value or "").replace("'", "''")

def _ensure_tenant_matches(request_tenant_id: str):
    requested = (request_tenant_id or "").strip()
    configured = (settings.AZURE_TENANT_ID or "").strip()
    if requested and configured and requested.lower() != configured.lower():
        raise RuntimeError(
            "tenantId in request does not match backend AZURE_TENANT_ID. "
            "Use the backend tenant or update AZURE_TENANT_ID in Django settings."
        )

def _generate_temporary_password(length: int = 20):
    length = max(12, int(length))
    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*-_+=?"
    all_chars = upper + lower + digits + symbols

    # Ensure complexity requirements are satisfied.
    seed = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    seed.extend(secrets.choice(all_chars) for _ in range(length - len(seed)))
    secrets.SystemRandom().shuffle(seed)
    return "".join(seed)

def _format_key_value_tags(tags: dict | None) -> list[str]:
    normalized = []
    for raw_key, raw_value in (tags or {}).items():
        key = (str(raw_key) or "").strip()
        if not key:
            continue
        value = (str(raw_value) or "").strip()
        normalized.append(f"{key}={value}" if value else key)
    return normalized

def _run_az_command(args, timeout_seconds=60):
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or "Unknown Azure CLI error."
        raise RuntimeError(f"Azure CLI command failed: {' '.join(args)} | {details}")
    return (result.stdout or "").strip()

def _get_provider_registration_state(subscription_id: str, namespace: str) -> str:
    output = _run_az_command(
        [
            "az",
            "provider",
            "show",
            "--namespace",
            namespace,
            "--subscription",
            subscription_id,
            "--query",
            "registrationState",
            "-o",
            "tsv",
        ]
    )
    return output.strip().strip('"')

def _get_provider_registration_state_rest(subscription_id: str, namespace: str) -> str:
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/providers/"
        f"{namespace}?api-version=2021-04-01"
    )
    response = requests.get(url, headers=_management_headers(), timeout=20)
    if not response.ok:
        raise RuntimeError(_extract_error_message(response))

    body = response.json()
    state = body.get("registrationState")
    return (state or "").strip()

def _register_provider_rest(subscription_id: str, namespace: str):
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/providers/"
        f"{namespace}/register?api-version=2021-04-01"
    )
    response = requests.post(url, headers=_management_headers(), timeout=30)
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(_extract_error_message(response))

def ensure_provider_registered(subscription_id: str, namespace: str):
    use_cli = bool(shutil.which("az"))
    method = "azure-cli" if use_cli else "rest-api"
    initial_state = (
        _get_provider_registration_state(subscription_id, namespace)
        if use_cli
        else _get_provider_registration_state_rest(subscription_id, namespace)
    )
    normalized = initial_state.lower()

    if normalized == "registered":
        return {
            "provider": namespace,
            "initial_state": initial_state,
            "action": "none",
            "final_state": initial_state,
            "method": method,
        }

    if use_cli:
        _run_az_command(
            [
                "az",
                "provider",
                "register",
                "--namespace",
                namespace,
                "--subscription",
                subscription_id,
            ],
            timeout_seconds=90,
        )
    else:
        _register_provider_rest(subscription_id, namespace)

    final_state = initial_state
    for _ in range(12):
        time.sleep(5)
        final_state = (
            _get_provider_registration_state(subscription_id, namespace)
            if use_cli
            else _get_provider_registration_state_rest(subscription_id, namespace)
        )
        if final_state.lower() == "registered":
            return {
                "provider": namespace,
                "initial_state": initial_state,
                "action": "register",
                "final_state": final_state,
                "method": method,
            }

    raise RuntimeError(
        f"{namespace} provider registration did not reach 'Registered' state in time."
    )

def ensure_network_provider_registered(subscription_id: str):
    return ensure_provider_registered(subscription_id, "Microsoft.Network")

def _paged_management_get(url: str, headers: dict, max_pages: int = 30):
    items = []
    pages = 0
    next_url = url

    while next_url and pages < max_pages:
        response = requests.get(next_url, headers=headers, timeout=20)
        if not response.ok:
            raise RuntimeError(_extract_error_message(response))

        data = response.json()
        items.extend(data.get("value", []))
        next_url = data.get("nextLink")
        pages += 1

    return items

def list_azure_ad_users(limit: int = 200):
    cred = get_credentials()
    token = cred.get_token("https://graph.microsoft.com/.default")
    access_token = token.token

    page_size = min(limit, 999)
    url = (
        "https://graph.microsoft.com/v1.0/users"
        f"?$select=id,displayName,mail,userPrincipalName,accountEnabled&$top={page_size}"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    users = []
    pages = 0
    while url and len(users) < limit and pages < 20:
        response = requests.get(url, headers=headers, timeout=20)
        if not response.ok:
            _raise_graph_api_error(
                response,
                fallback_message="Failed to list Azure AD users from Microsoft Graph.",
            )

        data = response.json()
        for user in data.get("value", []):
            users.append({
                "id": user.get("id"),
                "display_name": user.get("displayName"),
                "mail": user.get("mail"),
                "user_principal_name": user.get("userPrincipalName"),
                "account_enabled": user.get("accountEnabled"),
            })
            if len(users) >= limit:
                break

        url = data.get("@odata.nextLink")
        pages += 1

    return users

def list_subscriptions():
    headers = _management_headers()
    url = "https://management.azure.com/subscriptions?api-version=2020-01-01"
    response = requests.get(url, headers=headers, timeout=20)
    if not response.ok:
        raise RuntimeError(_extract_error_message(response))

    subscriptions = []
    for item in response.json().get("value", []):
        subscriptions.append({
            "subscription_id": item.get("subscriptionId"),
            "display_name": item.get("displayName"),
            "state": item.get("state"),
            "tenant_id": item.get("tenantId"),
        })

    subscriptions.sort(key=lambda x: (x.get("display_name") or "").lower())
    return subscriptions

def list_resource_groups(subscription_id: str):
    headers = _management_headers()
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups"
        "?api-version=2021-04-01"
    )
    items = _paged_management_get(url, headers=headers)
    groups = []
    for item in items:
        groups.append({
            "name": item.get("name"),
            "id": item.get("id"),
            "location": item.get("location"),
        })

    groups.sort(key=lambda x: (x.get("name") or "").lower())
    return groups

def list_subscription_regions(subscription_id: str):
    headers = _management_headers()
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/locations"
        "?api-version=2022-12-01"
    )
    response = requests.get(url, headers=headers, timeout=20)
    if not response.ok:
        raise RuntimeError(_extract_error_message(response))

    regions = []
    for item in response.json().get("value", []):
        regions.append({
            "name": item.get("name"),
            "display_name": item.get("displayName"),
            "regional_display_name": item.get("regionalDisplayName"),
        })

    regions.sort(key=lambda x: (x.get("display_name") or x.get("name") or "").lower())
    return regions

def _resolve_subscription(subscription_hint: str):
    hint = (subscription_hint or "").strip()
    if not hint:
        raise RuntimeError("subscription is required.")

    subscriptions = list_subscriptions()
    for sub in subscriptions:
        if (sub.get("subscription_id") or "").lower() == hint.lower():
            return sub.get("subscription_id"), sub

    for sub in subscriptions:
        if (sub.get("display_name") or "").lower() == hint.lower():
            return sub.get("subscription_id"), sub

    raise RuntimeError(f"Subscription '{subscription_hint}' was not found for this principal.")

def get_subnets(request):
    try:
        subscription_id = request.GET.get("subscription_id")
        resource_group = request.GET.get("resource_group")
        vnet = request.GET.get("vnet")

        # ✅ Validate inputs
        if not subscription_id or not resource_group or not vnet:
            return JsonResponse(
                {"error": "Missing required parameters"},
                status=400
            )

        # 🔹 MOCK DATA (Replace with Azure SDK later)
        subnets = [
            {"name": "subnet-1", "addressPrefix": "10.0.0.0/24"},
            {"name": "subnet-2", "addressPrefix": "10.0.1.0/24"},
        ]

        return JsonResponse({"subnets": subnets}, status=200)

    except Exception as e:
        return JsonResponse(
            {"error": str(e)},
            status=500
        )

def _resolve_region(subscription_id: str, region_hint: str):
    raw_hint = (region_hint or "").strip()
    if not raw_hint:
        raise RuntimeError("region is required.")

    hints_to_try = [raw_hint]
    if raw_hint.startswith("(") and ")" in raw_hint:
        stripped = raw_hint.split(")", 1)[1].strip()
        if stripped and stripped.lower() != raw_hint.lower():
            hints_to_try.append(stripped)

    if any(h.lower() == "other" for h in hints_to_try):
        raise RuntimeError("Region cannot be 'Other'. Select or type a specific Azure region.")

    regions = list_subscription_regions(subscription_id)
    for hint in hints_to_try:
        for region in regions:
            candidates = {
                (region.get("name") or "").lower(),
                (region.get("display_name") or "").lower(),
                (region.get("regional_display_name") or "").lower(),
            }
            if hint.lower() in candidates:
                return region.get("name") or hint, region

    for hint in hints_to_try:
        compact_hint = hint.lower().replace(" ", "").replace("-", "")
        for region in regions:
            compact_name = (region.get("name") or "").lower().replace(" ", "").replace("-", "")
            compact_display = (region.get("display_name") or "").lower().replace(" ", "").replace("-", "")
            compact_regional = (region.get("regional_display_name") or "").lower().replace(" ", "").replace("-", "")
            if compact_hint in {compact_name, compact_display, compact_regional}:
                return region.get("name") or hint, region

    return hints_to_try[-1], None

def _ensure_resource_group(
    subscription_id: str,
    resource_group: str,
    location: str,
    tags: dict | None = None,
    ):
    normalized_tags = tags or {}
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups/"
        f"{resource_group}?api-version=2021-04-01"
    )
    headers = _management_headers()

    # Prefer existing group to avoid requiring create permission when not needed.
    get_response = requests.get(url, headers=headers, timeout=20)
    if get_response.status_code == 200:
        body = get_response.json()
        if normalized_tags:
            patch_payload = {"tags": normalized_tags}
            patch_response = requests.patch(url, headers=headers, json=patch_payload, timeout=30)
            if patch_response.status_code not in (200, 201, 204):
                raise RuntimeError(_extract_error_message(patch_response))
            if patch_response.status_code in (200, 201):
                body = patch_response.json()
        return {
            "id": body.get("id"),
            "name": body.get("name") or resource_group,
            "location": body.get("location") or location,
        }

    if get_response.status_code not in (403, 404):
        raise RuntimeError(_extract_error_message(get_response))

    payload = {"location": location}
    if normalized_tags:
        payload["tags"] = normalized_tags
    put_response = requests.put(url, headers=headers, json=payload, timeout=30)
    if put_response.status_code in (200, 201):
        body = put_response.json()
        return {
            "id": body.get("id"),
            "name": body.get("name") or resource_group,
            "location": body.get("location") or location,
        }
    raise RuntimeError(_extract_error_message(put_response))

def _ensure_route_table(
    subscription_id: str,
    resource_group: str,
    location: str,
    route_table_name: str,
    routes: list,
):
    route_defs = []
    for route in routes:
        route_props = {
            "addressPrefix": route["destination"],
            "nextHopType": route["nextHop"],
        }
        if route.get("nextHop") == "VirtualAppliance" and route.get("nextHopIp"):
            route_props["nextHopIpAddress"] = route["nextHopIp"]

        route_defs.append(
            {
                "name": route["routeName"],
                "properties": route_props,
            }
        )

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/routeTables/{route_table_name}?api-version=2023-09-01"
    )
    payload = {
        "location": location,
        "properties": {
            "disableBgpRoutePropagation": False,
            "routes": route_defs,
        },
    }
    response = requests.put(url, headers=_management_headers(), json=payload, timeout=45)
    if response.status_code in (200, 201):
        body = response.json()
        return {
            "id": body.get("id"),
            "name": body.get("name") or route_table_name,
            "routes_count": len(route_defs),
        }
    raise RuntimeError(_extract_error_message(response))

def _create_or_update_vnet(
    subscription_id: str,
    resource_group: str,
    location: str,
    vnet_name: str,
    address_space: str,
    subnets: list,
    route_table_id: str = "",
    tags: dict | None = None,
):
    subnet_defs = []
    for subnet in subnets:
        subnet_props = {"addressPrefix": subnet["addressPrefix"]}
        if route_table_id:
            subnet_props["routeTable"] = {"id": route_table_id}

        subnet_defs.append(
            {
                "name": subnet["subnetName"],
                "properties": subnet_props,
            }
        )

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/virtualNetworks/{vnet_name}?api-version=2023-09-01"
    )
    payload = {
        "location": location,
        **({"tags": tags} if tags else {}),
        "properties": {
            "addressSpace": {"addressPrefixes": [address_space]},
            "subnets": subnet_defs,
        },
    }
    response = requests.put(url, headers=_management_headers(), json=payload, timeout=60)
    if response.status_code in (200, 201):
        body = response.json()
        created_subnets = [item.get("name") for item in body.get("properties", {}).get("subnets", [])]
        return {
            "id": body.get("id"),
            "name": body.get("name") or vnet_name,
            "location": body.get("location") or location,
            "subnets": created_subnets,
            "provisioning_state": body.get("properties", {}).get("provisioningState"),
        }
    raise RuntimeError(_extract_error_message(response))

def _ensure_vnet_and_subnet(
    subscription_id: str,
    resource_group: str,
    location: str,
    vnet_name: str,
    subnet_name: str,
):
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/virtualNetworks/{vnet_name}?api-version=2023-09-01"
    )
    headers = _management_headers()
    get_response = requests.get(url, headers=headers, timeout=30)

    if get_response.status_code == 200:
        body = get_response.json()
        for item in body.get("properties", {}).get("subnets", []):
            if (item.get("name") or "").strip().lower() == subnet_name.strip().lower():
                return {
                    "vnet_id": body.get("id"),
                    "vnet_name": body.get("name") or vnet_name,
                    "subnet_id": item.get("id"),
                    "subnet_name": item.get("name") or subnet_name,
                    "created": False,
                }

        raise RuntimeError(
            f"Subnet '{subnet_name}' was not found in virtual network '{vnet_name}'. "
            "Create the subnet first or use an existing subnet."
        )

    if get_response.status_code not in (403, 404):
        raise RuntimeError(_extract_error_message(get_response))

    payload = {
        "location": location,
        "properties": {
            "addressSpace": {
                "addressPrefixes": ["10.0.0.0/16"],
            },
            "subnets": [
                {
                    "name": subnet_name,
                    "properties": {
                        "addressPrefix": "10.0.0.0/24",
                    },
                }
            ],
        },
    }
    put_response = requests.put(url, headers=headers, json=payload, timeout=90)
    if put_response.status_code in (200, 201):
        body = put_response.json()
        subnet = (body.get("properties", {}).get("subnets") or [{}])[0]
        return {
            "vnet_id": body.get("id"),
            "vnet_name": body.get("name") or vnet_name,
            "subnet_id": subnet.get("id"),
            "subnet_name": subnet.get("name") or subnet_name,
            "created": True,
        }

    raise RuntimeError(_extract_error_message(put_response))

def _ensure_public_ip(
    subscription_id: str,
    resource_group: str,
    location: str,
    public_ip_name: str,
    public_ip_sku: str,
):
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/publicIPAddresses/{public_ip_name}?api-version=2023-09-01"
    )
    allocation = "Static" if public_ip_sku == "Standard" else "Dynamic"
    payload = {
        "location": location,
        "sku": {
            "name": public_ip_sku,
        },
        "properties": {
            "publicIPAllocationMethod": allocation,
            "publicIPAddressVersion": "IPv4",
        },
    }
    response = requests.put(url, headers=_management_headers(), json=payload, timeout=75)
    if response.status_code in (200, 201):
        body = response.json()
        return {
            "id": body.get("id"),
            "name": body.get("name") or public_ip_name,
            "ip_address": body.get("properties", {}).get("ipAddress"),
            "allocation_method": allocation,
            "sku": public_ip_sku,
            "provisioning_state": body.get("properties", {}).get("provisioningState"),
        }

    raise RuntimeError(_extract_error_message(response))

@api_view(["GET"])
def list_subnets(request):
    subscription_id = request.GET.get("subscription_id")
    resource_group = request.GET.get("resource_group")
    vnet_name = request.GET.get("vnet")

    if not subscription_id or not resource_group or not vnet_name:
        return Response(
            {"error": "subscription_id, resource_group and vnet are required"},
            status=400,
        )

    # Azure GET VNET API
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/virtualNetworks/{vnet_name}"
        f"?api-version=2023-09-01"
    )

    response = requests.get(url, headers=_management_headers(), timeout=30)

    if response.status_code != 200:
        return Response(
            {"error": response.text},
            status=response.status_code
        )

    data = response.json()

    subnets = [
        {
            "name": s.get("name"),
            "id": s.get("id"),
            "addressPrefix": s.get("properties", {}).get("addressPrefix")
        }
        for s in data.get("properties", {}).get("subnets", [])
    ]

    return Response({"status": "success", "subnets": subnets}, status=200)

def _ensure_network_interface(
    subscription_id: str,
    resource_group: str,
    location: str,
    nic_name: str,
    subnet_id: str,
    public_ip_id: str = "",
):
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/networkInterfaces/{nic_name}?api-version=2023-09-01"
    )
    ip_config = {
        "name": "ipconfig1",
        "properties": {
            "subnet": {"id": subnet_id},
            "privateIPAllocationMethod": "Dynamic",
        },
    }
    if public_ip_id:
        ip_config["properties"]["publicIPAddress"] = {"id": public_ip_id}

    payload = {
        "location": location,
        "properties": {
            "ipConfigurations": [ip_config],
        },
    }
    response = requests.put(url, headers=_management_headers(), json=payload, timeout=90)
    if response.status_code in (200, 201):
        body = response.json()
        return {
            "id": body.get("id"),
            "name": body.get("name") or nic_name,
            "private_ip": (
                ((body.get("properties", {}).get("ipConfigurations") or [{}])[0].get("properties") or {}).get(
                    "privateIPAddress"
                )
            ),
            "provisioning_state": body.get("properties", {}).get("provisioningState"),
        }

    raise RuntimeError(_extract_error_message(response))

def _create_or_update_virtual_machine(
    subscription_id: str,
    resource_group: str,
    location: str,
    plan: dict,
    payload: dict,
    network_interface_id: str,
):
    vm_name = plan["vm_name"]
    admin = payload["admin"]
    image = payload["image"]
    storage = payload["storage"]
    tags = payload.get("tags") or {}
    auth_type = admin["authenticationType"]
    admin_username = admin["username"]

    os_profile = {
        "computerName": vm_name,
        "adminUsername": admin_username,
    }
    if auth_type == "password":
        os_profile["adminPassword"] = admin["password"]

    if plan["os_type"] == "Linux":
        linux_configuration = {"disablePasswordAuthentication": auth_type == "ssh"}
        if auth_type == "ssh":
            linux_configuration["ssh"] = {
                "publicKeys": [
                    {
                        "path": f"/home/{admin_username}/.ssh/authorized_keys",
                        "keyData": admin["sshPublicKey"],
                    }
                ]
            }
        os_profile["linuxConfiguration"] = linux_configuration
    else:
        os_profile["windowsConfiguration"] = {
            "enableAutomaticUpdates": True,
        }

    request_body = {
        "location": location,
        "tags": tags,
        "properties": {
            "hardwareProfile": {
                "vmSize": plan["vm_size"],
            },
            "storageProfile": {
                "imageReference": {
                    "publisher": image["publisher"],
                    "offer": image["offer"],
                    "sku": image["sku"],
                    "version": image.get("version") or "latest",
                },
                "osDisk": {
                    "name": plan["os_disk_name"],
                    "createOption": "FromImage",
                    "diskSizeGB": int(storage["osDiskSizeGb"]),
                    "managedDisk": {
                        "storageAccountType": storage["osDiskType"],
                    },
                },
            },
            "osProfile": os_profile,
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": network_interface_id,
                        "properties": {
                            "primary": True,
                        },
                    }
                ],
            },
        },
    }

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Compute/virtualMachines/{vm_name}?api-version=2024-03-01"
    )
    response = requests.put(url, headers=_management_headers(), json=request_body, timeout=180)
    if response.status_code in (200, 201, 202):
        body = response.json() if (response.text or "").strip() else {}
        vm_props = body.get("properties", {})
        status_items = vm_props.get("instanceView", {}).get("statuses", []) or []
        power_state = ""
        for item in status_items:
            code = item.get("code") or ""
            if code.startswith("PowerState/"):
                power_state = code
                break

        return {
            "id": body.get("id"),
            "name": body.get("name") or vm_name,
            "location": body.get("location") or location,
            "vm_id": vm_props.get("vmId"),
            "provisioning_state": vm_props.get("provisioningState"),
            "power_state": power_state,
        }

    raise RuntimeError(_extract_error_message(response))

def build_vnet_plan(payload: dict):
    subscription_id, subscription_meta = _resolve_subscription(payload["subscription"])
    region_name, region_meta = _resolve_region(subscription_id, payload["region"])

    route_table = payload.get("routeTable") or {}
    route_table_name = route_table.get("routeTableName") or payload.get("routeTableName") or ""
    routes = route_table.get("routes") or []
    custom_routing_enabled = payload.get("enableCustomRouting") == "Yes"
    tags = payload.get("tags") or {}

    plan = {
        "subscription_id": subscription_id,
        "subscription_name": subscription_meta.get("display_name"),
        "resource_group": payload["resourceGroup"],
        "region": region_name,
        "region_display_name": (region_meta or {}).get("display_name"),
        "vnet_name": payload["vnetName"],
        "address_space": payload["addressSpace"],
        "subnets": payload["subnets"],
        "enable_custom_routing": custom_routing_enabled,
        "route_table_name": route_table_name if custom_routing_enabled else "",
        "routes": routes if custom_routing_enabled else [],
        "dry_run": bool(payload.get("dryRun", True)),
        "tags": tags,
    }
    return plan

def build_vm_plan(payload: dict):
    subscription_id, subscription_meta = _resolve_subscription(payload["subscription"])
    region_name, region_meta = _resolve_region(subscription_id, payload["region"])

    vm_name = payload["vmName"]
    network = payload["network"]
    storage = payload["storage"]
    admin = payload["admin"]
    image = payload["image"]
    dry_run = bool(payload.get("dryRun", True))

    plan = {
        "subscription_id": subscription_id,
        "subscription_name": subscription_meta.get("display_name"),
        "resource_group": payload["resourceGroup"],
        "region": region_name,
        "region_display_name": (region_meta or {}).get("display_name"),
        "vm_name": vm_name,
        "vm_size": payload["vmSize"],
        "os_type": payload["osType"],
        "image": {
            "publisher": image["publisher"],
            "offer": image["offer"],
            "sku": image["sku"],
            "version": image.get("version") or "latest",
        },
        "admin": {
            "username": admin["username"],
            "authentication_type": admin["authenticationType"],
            "uses_password": admin["authenticationType"] == "password",
            "uses_ssh": admin["authenticationType"] == "ssh",
        },
        "network": {
            "virtual_network_name": network["virtualNetworkName"],
            "subnet_name": network["subnetName"],
            "enable_public_ip": bool(network.get("enablePublicIp", True)),
            "public_ip_sku": network.get("publicIpSku", "Standard"),
            "network_interface_name": f"{vm_name}-nic",
            "public_ip_name": f"{vm_name}-pip",
        },
        "storage": {
            "os_disk_type": storage["osDiskType"],
            "os_disk_size_gb": int(storage["osDiskSizeGb"]),
        },
        "os_disk_name": f"{vm_name}-osdisk",
        "tags": payload.get("tags") or {},
        "dry_run": dry_run,
    }
    return plan

def provision_vm_from_payload(payload: dict):
    plan = build_vm_plan(payload)
    if plan["dry_run"]:
        return {
            "mode": "dry-run",
            "plan": plan,
            "message": "VM payload validated. Set dryRun=false to apply in Azure.",
        }

    network_provider_status = ensure_network_provider_registered(plan["subscription_id"])
    compute_provider_status = ensure_provider_registered(plan["subscription_id"], "Microsoft.Compute")

    resource_group_result = _ensure_resource_group(
        subscription_id=plan["subscription_id"],
        resource_group=plan["resource_group"],
        location=plan["region"],
    )

    subnet_result = _ensure_vnet_and_subnet(
        subscription_id=plan["subscription_id"],
        resource_group=plan["resource_group"],
        location=plan["region"],
        vnet_name=plan["network"]["virtual_network_name"],
        subnet_name=plan["network"]["subnet_name"],
    )

    public_ip_result = None
    if plan["network"]["enable_public_ip"]:
        public_ip_result = _ensure_public_ip(
            subscription_id=plan["subscription_id"],
            resource_group=plan["resource_group"],
            location=plan["region"],
            public_ip_name=plan["network"]["public_ip_name"],
            public_ip_sku=plan["network"]["public_ip_sku"],
        )

    network_interface_result = _ensure_network_interface(
        subscription_id=plan["subscription_id"],
        resource_group=plan["resource_group"],
        location=plan["region"],
        nic_name=plan["network"]["network_interface_name"],
        subnet_id=subnet_result["subnet_id"],
        public_ip_id=(public_ip_result or {}).get("id", ""),
    )

    vm_result = _create_or_update_virtual_machine(
        subscription_id=plan["subscription_id"],
        resource_group=plan["resource_group"],
        location=plan["region"],
        plan=plan,
        payload=payload,
        network_interface_id=network_interface_result["id"],
    )

    return {
        "mode": "applied",
        "plan": plan,
        "provider_status": {
            "network": network_provider_status,
            "compute": compute_provider_status,
        },
        "resource_group": resource_group_result,
        "network": subnet_result,
        "public_ip": public_ip_result,
        "network_interface": network_interface_result,
        "virtual_machine": vm_result,
        "message": "Virtual machine configuration applied in Azure.",
    }

def provision_vnet_from_payload(payload: dict):
    plan = build_vnet_plan(payload)
    if plan["dry_run"]:
        return {
            "mode": "dry-run",
            "plan": plan,
            "message": "Payload validated. Set dryRun=false to apply in Azure.",
        }

    provider_status = ensure_network_provider_registered(plan["subscription_id"])

    resource_group_result = _ensure_resource_group(
        subscription_id=plan["subscription_id"],
        resource_group=plan["resource_group"],
        location=plan["region"],
    )

    route_table_result = None
    if plan["enable_custom_routing"] and plan["route_table_name"]:
        route_table_result = _ensure_route_table(
        subscription_id=plan["subscription_id"],
        resource_group=plan["resource_group"],
        location=plan["region"],
        route_table_name=plan["route_table_name"],
        routes=plan["routes"],
    )

    vnet_result = _create_or_update_vnet(
        subscription_id=plan["subscription_id"],
        resource_group=plan["resource_group"],
        location=plan["region"],
        vnet_name=plan["vnet_name"],
        address_space=plan["address_space"],
        subnets=plan["subnets"],
        route_table_id=(route_table_result or {}).get("id", ""),
        tags=plan.get("tags"),
    )

    return {
        "mode": "applied",
        "plan": plan,
        "provider_status": provider_status,
        "resource_group": resource_group_result,
        "route_table": route_table_result,
        "virtual_network": vnet_result,
        "message": "VNet configuration applied in Azure.",
    }

def provision_resource_group_from_payload(payload: dict):
    subscription_id, subscription_meta = _resolve_subscription(payload["subscription"])
    region_name, region_meta = _resolve_region(subscription_id, payload["region"])
    resource_group_name = payload["resourceGroup"]
    dry_run = bool(payload.get("dryRun", False))
    tags = payload.get("tags") or {}

    plan = {
        "subscription_id": subscription_id,
        "subscription_name": subscription_meta.get("display_name"),
        "resource_group": resource_group_name,
        "region": region_name,
        "region_display_name": (region_meta or {}).get("display_name"),
        "tags": tags,
        "dry_run": dry_run,
    }

    if dry_run:
        return {
            "mode": "dry-run",
            "plan": plan,
            "message": "Resource group payload validated. Set dryRun=false to apply in Azure.",
        }

    result = _ensure_resource_group(
        subscription_id=subscription_id,
        resource_group=resource_group_name,
        location=region_name,
        tags=tags,
    )
    return {
        "mode": "applied",
        "plan": plan,
        "resource_group": result,
        "message": "Resource group ensured in Azure.",
    }

def provision_key_vault_from_payload(payload: dict):
    subscription_id, subscription_meta = _resolve_subscription(payload["subscription"])
    region_name, region_meta = _resolve_region(subscription_id, payload["region"])
    tenant_id = (payload.get("tenantId") or settings.AZURE_TENANT_ID or "").strip()

    if not tenant_id:
        raise RuntimeError("tenantId is required. Configure AZURE_TENANT_ID or provide tenantId in payload.")

    sku_name = str(payload.get("skuName", "standard")).lower()
    dry_run = bool(payload.get("dryRun", True))
    tags = payload.get("tags") or {}
    plan = {
        "subscription_id": subscription_id,
        "subscription_name": subscription_meta.get("display_name"),
        "resource_group": payload["resourceGroup"],
        "region": region_name,
        "region_display_name": (region_meta or {}).get("display_name"),
        "key_vault_name": payload["keyVaultName"],
        "tenant_id": tenant_id,
        "sku_name": sku_name,
        "enable_rbac_authorization": bool(payload.get("enableRbacAuthorization", True)),
        "public_network_access": payload.get("publicNetworkAccess", "Enabled"),
        "soft_delete_retention_days": int(payload.get("softDeleteRetentionInDays", 90)),
        "enable_purge_protection": bool(payload.get("enablePurgeProtection", False)),
        "enabled_for_deployment": bool(payload.get("enabledForDeployment", False)),
        "enabled_for_disk_encryption": bool(payload.get("enabledForDiskEncryption", False)),
        "enabled_for_template_deployment": bool(payload.get("enabledForTemplateDeployment", False)),
        "tags": tags,
        "dry_run": dry_run,
    }

    if dry_run:
        return {
            "mode": "dry-run",
            "plan": plan,
            "message": "Key Vault payload validated. Set dryRun=false to apply in Azure.",
        }

    provider_status = ensure_provider_registered(subscription_id, "Microsoft.KeyVault")
    resource_group_result = _ensure_resource_group(
        subscription_id=subscription_id,
        resource_group=plan["resource_group"],
        location=region_name,
    )

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{plan['resource_group']}"
        f"/providers/Microsoft.KeyVault/vaults/{plan['key_vault_name']}?api-version=2023-07-01"
    )
    payload_body = {
        "location": region_name,
        "properties": {
            "tenantId": tenant_id,
            "sku": {
                "family": "A",
                "name": sku_name,
            },
            "accessPolicies": [],
            "enableRbacAuthorization": plan["enable_rbac_authorization"],
            "publicNetworkAccess": plan["public_network_access"],
            "softDeleteRetentionInDays": plan["soft_delete_retention_days"],
            "enablePurgeProtection": plan["enable_purge_protection"],
            "enabledForDeployment": plan["enabled_for_deployment"],
            "enabledForDiskEncryption": plan["enabled_for_disk_encryption"],
            "enabledForTemplateDeployment": plan["enabled_for_template_deployment"],
        },
        "tags": tags,
    }
    response = requests.put(url, headers=_management_headers(), json=payload_body, timeout=75)
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(_extract_error_message(response))

    body = response.json()
    key_vault_result = {
        "id": body.get("id"),
        "name": body.get("name") or plan["key_vault_name"],
        "location": body.get("location") or region_name,
        "vault_uri": body.get("properties", {}).get("vaultUri"),
        "provisioning_state": body.get("properties", {}).get("provisioningState"),
    }
    return {
        "mode": "applied",
        "plan": plan,
        "provider_status": provider_status,
        "resource_group": resource_group_result,
        "key_vault": key_vault_result,
        "message": "Key Vault configuration applied in Azure.",
    }

def provision_backup_from_payload(payload: dict):
    subscription_id, subscription_meta = _resolve_subscription(payload["subscription"])
    region_name, region_meta = _resolve_region(subscription_id, payload["region"])
    resource_group_name = payload["resourceGroup"]
    backup_vault_name = payload["backupVaultName"]
    public_network_access = payload.get("publicNetworkAccess", "Enabled")
    tags = payload.get("tags") or {}
    dry_run = bool(payload.get("dryRun", True))

    plan = {
        "subscription_id": subscription_id,
        "subscription_name": subscription_meta.get("display_name"),
        "resource_group": resource_group_name,
        "region": region_name,
        "region_display_name": (region_meta or {}).get("display_name"),
        "backup_vault_name": backup_vault_name,
        "public_network_access": public_network_access,
        "tags": tags,
        "dry_run": dry_run,
    }

    if dry_run:
        return {
            "mode": "dry-run",
            "plan": plan,
            "message": "Backup payload validated. Set dryRun=false to apply in Azure.",
        }

    provider_status = ensure_provider_registered(subscription_id, "Microsoft.RecoveryServices")
    resource_group_result = _ensure_resource_group(
        subscription_id=subscription_id,
        resource_group=resource_group_name,
        location=region_name,
    )

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
        f"/providers/Microsoft.RecoveryServices/vaults/{backup_vault_name}?api-version=2023-02-01"
    )
    payload_body = {
        "location": region_name,
        "sku": {
            "name": "RS0",
            "tier": "Standard",
        },
        "properties": {
            "publicNetworkAccess": public_network_access,
        },
        "tags": tags,
    }
    response = requests.put(url, headers=_management_headers(), json=payload_body, timeout=75)
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(_extract_error_message(response))

    body = response.json()
    backup_vault_result = {
        "id": body.get("id"),
        "name": body.get("name") or backup_vault_name,
        "location": body.get("location") or region_name,
        "public_network_access": body.get("properties", {}).get("publicNetworkAccess") or public_network_access,
        "provisioning_state": body.get("properties", {}).get("provisioningState"),
    }
    return {
        "mode": "applied",
        "plan": plan,
        "provider_status": provider_status,
        "resource_group": resource_group_result,
        "backup_vault": backup_vault_result,
        "message": "Backup vault configuration applied in Azure.",
    }

def wait_for_service_principal_replication(principal_id: str, headers: dict, max_attempts: int = 12, base_sleep: int = 5) -> tuple[bool, int, int]:
    """
    Poll Microsoft Graph until the service principal becomes readable.
    Returns: (ok, attempts, waited_seconds)
    """
    import time
    import requests

    total_wait = 0
    url = f"https://graph.microsoft.com/v1.0/servicePrincipals/{principal_id}"

    for attempt in range(1, max_attempts + 1):
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return True, attempt, total_wait

        sleep_s = base_sleep * attempt  # 5, 10, 15, ...
        total_wait += sleep_s
        # Optional: replace print with your logger
        print(f"[Azure][SP-Replication] SP {principal_id} not visible yet (attempt {attempt}/{max_attempts}). Waiting {sleep_s}s...")
        time.sleep(sleep_s)

    return False, max_attempts, total_wait

def _retry_role_assignment_if_principal_just_created(
    principal_id: str,
    role_key: str,
    normalized_scope: str,
    subscription_id: str
):
    """
    Retry role assignment when ARM says the principal doesn't exist yet.
    This catches only 'not found/does not exist' flavors; ABAC/authorization errors are raised immediately.
    """
    import time

    max_attempts = 6
    base_sleep = 3
    last_err = None

    for attempt in range(1, max_attempts + 1):
        try:
            return assign_role_to_principal(
                principal_id=principal_id,
                role_key=role_key,
                scope=normalized_scope,
                subscription_id_override=subscription_id,
                principal_type="ServicePrincipal",
            )
        except RuntimeError as exc:
            text = (str(exc) or "").lower()

            # Retry only when the principal is not found/does not exist (ARM still catching up)
            retryable_substrings = [
                "does not exist",
                "was not found",
                "could not find",
                "principal was not found",
                "directory object not found",
                "resource not found",
            ]
            is_retryable = any(s in text for s in retryable_substrings)

            # Do NOT retry on ABAC/authorization/deny
            deny_markers = [
                "abac condition",
                "requestdisallowedbypolicy",
                "authorizationfailed",
                "insufficient privileges",
                "not authorized",
                "forbidden",
                "deny assignment",
            ]
            is_deny = any(s in text for s in deny_markers)

            if not is_retryable or is_deny:
                # surface the original error
                raise

            sleep_s = base_sleep * attempt  # 3, 6, 9, ...
            print(f"[Azure][RBAC-Retry] Principal {principal_id} not visible to ARM yet (attempt {attempt}/{max_attempts}). Waiting {sleep_s}s…")
            time.sleep(sleep_s)
            last_err = exc

    # give up with the last error
    raise last_err if last_err else RuntimeError("Role assignment failed after retries.")

def provision_service_principal_from_payload(payload: dict):
    subscription_id, subscription_meta = _resolve_subscription(payload["subscription"])
    service_principal_name = (payload.get("servicePrincipalName") or "").strip()
    tenant_id = (payload.get("tenantId") or settings.AZURE_TENANT_ID or "").strip()
    _ensure_tenant_matches(tenant_id)
    role_key = payload.get("role", "contributor")
    scope_type = payload.get("scopeType", "subscription")
    resource_group = (payload.get("resourceGroup") or "").strip()
    custom_scope = (payload.get("customScope") or "").strip()
    credential_type = payload.get("credentialType", "client-secret")
    secret_display_name = (payload.get("secretDisplayName") or "sp-client-secret").strip()
    secret_validity_months = int(payload.get("secretValidityMonths", 12))
    create_if_missing = bool(payload.get("createIfMissing", True))
    assign_role_now = bool(payload.get("assignRoleNow", True))
    dry_run = bool(payload.get("dryRun", True))
    tags = payload.get("tags") or {}
    tag_list = _format_key_value_tags(tags)

    if scope_type == "subscription":
        normalized_scope = f"/subscriptions/{subscription_id}"
    elif scope_type == "resource-group":
        if not resource_group:
            raise RuntimeError("resourceGroup is required when scopeType is resource-group.")
        normalized_scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    else:
        if not custom_scope:
            raise RuntimeError("customScope is required when scopeType is custom.")
        normalized_scope = custom_scope if custom_scope.startswith("/") else f"/{custom_scope}"

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
    
    graph_headers = _graph_headers()
    escaped_name = _escape_odata_literal(service_principal_name)
    app_lookup_url = (
        "https://graph.microsoft.com/v1.0/applications"
        f"?$filter=displayName eq '{escaped_name}'&$select=id,appId,displayName"
    )

    app_lookup_response = requests.get(app_lookup_url, headers=graph_headers, timeout=30)
    if not app_lookup_response.ok:
        _raise_graph_api_error(app_lookup_response, "Failed to lookup application in Microsoft Graph.")
    app_items = app_lookup_response.json().get("value", [])
    application = app_items[0] if app_items else None
    application_action = "existing"
    if not application:
        if not create_if_missing:
            raise RuntimeError(
                f"Application '{service_principal_name}' was not found and createIfMissing is false."
            )
        create_app_response = requests.post(
            "https://graph.microsoft.com/v1.0/applications",
            headers=graph_headers,
            json={
                "displayName": service_principal_name,
                "signInAudience": "AzureADMyOrg",
            },
            timeout=30,
        )
        if create_app_response.status_code not in (200, 201):
            _raise_graph_api_error(create_app_response, "Failed to create application in Microsoft Graph.")
        application = create_app_response.json()
        application_action = "created"
    app_object_id = application.get("id")
    app_id = application.get("appId")
    if not app_object_id or not app_id:
        raise RuntimeError("Microsoft Graph did not return application identifiers.")
    sp_lookup_url = (
        "https://graph.microsoft.com/v1.0/servicePrincipals"
        f"?$filter=appId eq '{_escape_odata_literal(app_id)}'&$select=id,appId,displayName"
    )
    sp_lookup_response = requests.get(sp_lookup_url, headers=graph_headers, timeout=30)
    if not sp_lookup_response.ok:
        _raise_graph_api_error(sp_lookup_response, "Failed to lookup service principal in Microsoft Graph.")
    sp_items = sp_lookup_response.json().get("value", [])
    service_principal = sp_items[0] if sp_items else None
    service_principal_action = "existing"
    sp_creation_attempts = 0
    sp_creation_wait_seconds = 0
    if not service_principal:
        max_attempts = 8
        wait_seconds = 5
        last_response = None
        for attempt in range(1, max_attempts + 1):
            sp_creation_attempts = attempt
            create_sp_response = requests.post(
                "https://graph.microsoft.com/v1.0/servicePrincipals",
                headers=graph_headers,
                json={"appId": app_id},
                timeout=30,
            )
            last_response = create_sp_response
            if create_sp_response.status_code in (200, 201):
                service_principal = create_sp_response.json()
                service_principal_action = "created"
                sp_creation_wait_seconds = (attempt - 1) * wait_seconds
                break
            details = _extract_error_details(create_sp_response)
            is_replication_issue = _is_graph_sp_app_reference_error(
                details.get("code"),
                details.get("message"),
            )
            if is_replication_issue and attempt < max_attempts:
                time.sleep(wait_seconds)
                continue
            _raise_graph_api_error(
                create_sp_response,
                "Failed to create service principal in Microsoft Graph.",
            )
        if not service_principal and last_response is not None:
            _raise_graph_api_error(
                last_response,
                "Failed to create service principal in Microsoft Graph.",
            )
    principal_id = service_principal.get("id")
    if not principal_id:
        raise RuntimeError("Microsoft Graph did not return service principal object id.")
    _register_managed_principal(
        principal_id,
        service_principal.get("displayName") or service_principal_name,
    )
    if tag_list:
        tag_response = requests.patch(
            f"https://graph.microsoft.com/v1.0/servicePrincipals/{principal_id}",
            headers=graph_headers,
            json={"tags": tag_list},
            timeout=30,
        )
        if tag_response.status_code not in (200, 201, 204):
            _raise_graph_api_error(tag_response, "Failed to update service principal tags in Microsoft Graph.")

    credential_result = None
    if credential_type == "client-secret":
        secret_expiry = (
            datetime.now(timezone.utc) + timedelta(days=30 * max(secret_validity_months, 1))
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        add_password_response = requests.post(
            f"https://graph.microsoft.com/v1.0/applications/{app_object_id}/addPassword",
            headers=graph_headers,
            json={
                "passwordCredential": {
                    "displayName": secret_display_name,
                    "endDateTime": secret_expiry,
                }
            },
            timeout=30,
        )
        if add_password_response.status_code not in (200, 201):
            _raise_graph_api_error(add_password_response, "Failed to create client secret in Microsoft Graph.")

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
        # 1) Wait until the SP is visible in Graph (global replication)
        ok, attempts, waited = wait_for_service_principal_replication(
            principal_id=principal_id,
            headers=graph_headers,
        )
        replication_wait = {"attempts": attempts, "waited_seconds": waited}
        if not ok:
            raise RuntimeError(
                f"Service Principal '{principal_id}' not yet replicated in Azure AD. Please retry shortly."
            )

        # 2) Retry the ARM role assignment ONLY when ARM still doesn't see the principal yetM
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
        "replication_wait": replication_wait,   # <— NEW: for observability
        "credential": credential_result,
        "role_assignment": role_assignment,
        "message": "Service Principal configuration applied in Azure.",
    }

import uuid

def provision_user_from_payload(payload: dict, request_id=None):
    # ✅ Ensure request_id always exists
    request_id = request_id or str(uuid.uuid4())

    display_name = (payload.get("displayName") or "").strip()
    user_principal_name = (payload.get("userPrincipalName") or "").strip()
    mail_nickname = (payload.get("mailNickname") or "").strip()
    requested_password = payload.get("password") or ""
    force_change = bool(payload.get("forceChangePasswordNextSignIn", True))
    account_enabled = bool(payload.get("accountEnabled", True))
    tenant_id = (payload.get("tenantId") or settings.AZURE_TENANT_ID or "")
    dry_run = bool(payload.get("dryRun", True))
    upn_domain = _extract_upn_domain(user_principal_name)

    _ensure_tenant_matches(tenant_id)

    if not upn_domain:
        raise RuntimeError("userPrincipalName must include a valid domain.")

    submitted_payload = {
        "displayName": display_name,
        "userPrincipalName": user_principal_name,
        "mailNickname": mail_nickname,
        "forceChangePasswordNextSignIn": force_change,
        "accountEnabled": account_enabled,
        "tenantId": tenant_id,
    }

    plan = {
        "display_name": display_name,
        "user_principal_name": user_principal_name,
        "upn_domain": upn_domain,
        "mail_nickname": mail_nickname,
        "force_change_password_next_sign_in": force_change,
        "account_enabled": account_enabled,
        "tenant_id": tenant_id,
        "dry_run": dry_run,
    }

    # 🔹 DRY RUN
    if dry_run:
        return {
            "mode": "dry-run",
            "request_id": request_id,   # ✅ attach UUID
            "plan": plan,
            "payload": submitted_payload,
            "subscription_id": settings.AZURE_SUBSCRIPTION_ID,
            "user_name": display_name,
            "user_principal_id": user_principal_name,
            "message": "User payload validated.",
        }

    headers = _graph_headers()

    # 🔍 Check existing user
    escaped_upn = _escape_odata_literal(user_principal_name)
    lookup_url = (
        "https://graph.microsoft.com/v1.0/users"
        f"?$filter=userPrincipalName eq '{escaped_upn}'"
    )

    lookup_response = requests.get(lookup_url, headers=headers, timeout=30)

    if not lookup_response.ok:
        _raise_graph_api_error(lookup_response, "User lookup failed.")

    existing = (lookup_response.json().get("value") or [])

    if existing:
        user = existing[0]

        # ✅ LOG
        create_log(request_id, "success", "User already exists")

        return {
            "mode": "applied",
            "request_id": request_id,
            "plan": plan,
            "payload": submitted_payload,
            "subscription_id": settings.AZURE_SUBSCRIPTION_ID,
            "user": {
                "id": user.get("id"),
                "display_name": user.get("displayName"),
                "user_principal_name": user.get("userPrincipalName"),
                "mail_nickname": user.get("mailNickname"),
                "action": "existing",
            },
            "user_name": user.get("displayName") or display_name,
            "user_principal_id": user.get("id"),
            "message": "User already exists in Azure AD.",
        }

    # 🔐 PASSWORD HANDLING
    auto_generated_password = not bool(str(requested_password).strip())
    password_value = (
        requested_password if not auto_generated_password
        else _generate_temporary_password()
    )

    create_payload = {
        "accountEnabled": account_enabled,
        "displayName": display_name,
        "mailNickname": mail_nickname,
        "userPrincipalName": user_principal_name,
        "passwordProfile": {
            "forceChangePasswordNextSignIn": force_change,
            "password": password_value,
        },
    }

    create_response = requests.post(
        "https://graph.microsoft.com/v1.0/users",
        headers=headers,
        json=create_payload,
        timeout=30,
    )

    if create_response.status_code not in (200, 201):
        _raise_graph_api_error(create_response, "User creation failed.")

    created = create_response.json()

    # ✅ STORE LOG WITH UUID
    create_log(
        request_id,
        "success",
        "User created successfully",
        generated_password=password_value if auto_generated_password else None,
    )

    result = {
        "mode": "applied",
        "request_id": request_id,   # ✅ IMPORTANT
        "plan": plan,
        "payload": submitted_payload,
        "subscription_id": settings.AZURE_SUBSCRIPTION_ID,
        "user": {
            "id": created.get("id"),
            "display_name": created.get("displayName") or display_name,
            "user_principal_name": created.get("userPrincipalName") or user_principal_name,
            "mail_nickname": created.get("mailNickname") or mail_nickname,
            "action": "created",
        },
        "user_name": created.get("displayName") or display_name,
        "user_principal_id": created.get("id"),
        "message": "User created in Azure AD.",
    }

    # 🔐 Return password only if generated
    if auto_generated_password:
        result["generated_password"] = password_value

    return result


def _add_members_to_group(group_id: str, member_user_ids: list[str], headers: dict):
    if not (group_id or "").strip():
        raise RuntimeError("Cannot add members: group id is missing.")

    unique_ids = []
    seen = set()
    for raw in member_user_ids or []:
        member_id = (raw or "").strip()
        if not member_id:
            continue
        lowered = member_id.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_ids.append(member_id)

    if not unique_ids:
        return {
            "requested": 0,
            "added_count": 0,
            "already_member_count": 0,
            "failed_count": 0,
            "added_ids": [],
            "already_member_ids": [],
            "failed": [],
        }

    added_ids = []
    already_member_ids = []
    failed = []
    unique_ids = []  # Initialize with actual values

    for member_id in unique_ids:
        url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/$ref"
        payload = {
            "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{member_id}",
        }
        headers = {}  # Define headers appropriately
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code in (200, 201, 204):
            added_ids.append(member_id)
            continue

        details = _extract_error_details(response)
        if _is_graph_member_exists_error(details.get("code"), details.get("message")):
            already_member_ids.append(member_id)
            continue

        failed.append(
            {
                "member_id": member_id,
                "code": details.get("code") or "graph_api_error",
                "message": details.get("message") or _extract_error_message(response),
            }
        )

    return {
        "requested": len(unique_ids),
        "added_count": len(added_ids),
        "already_member_count": len(already_member_ids),
        "failed_count": len(failed),
        "added_ids": added_ids,
        "already_member_ids": already_member_ids,
        "failed": failed,
    }

def provision_group_from_payload(payload: dict):
    display_name = (payload.get("displayName") or "").strip()
    mail_nickname = (payload.get("mailNickname") or "").strip()
    description = (payload.get("description") or "").strip()
    mail_enabled = bool(payload.get("mailEnabled", False))
    security_enabled = bool(payload.get("securityEnabled", True))
    group_types = payload.get("groupTypes") or []
    member_user_ids = payload.get("memberUserIds") or []
    tenant_id = (payload.get("tenantId") or settings.AZURE_TENANT_ID or "").strip()
    dry_run = bool(payload.get("dryRun", True))
    tags = payload.get("tags") or {}
    tag_list = _format_key_value_tags(tags)

    _ensure_tenant_matches(tenant_id)

    plan = {
        "display_name": display_name,
        "mail_nickname": mail_nickname,
        "description": description,
        "mail_enabled": mail_enabled,
        "security_enabled": security_enabled,
        "group_types": group_types,
        "member_user_ids": member_user_ids,
        "requested_member_count": len(member_user_ids),
        "tenant_id": tenant_id,
        "tags": tags,
        "dry_run": dry_run,
    }

    if dry_run:
        return {
            "mode": "dry-run",
            "plan": plan,
            "message": "Group payload validated. Set dryRun=false to create group in Azure AD.",
        }

    headers = _graph_headers()
    escaped_display = _escape_odata_literal(display_name)
    lookup_by_display_url = (
        "https://graph.microsoft.com/v1.0/groups"
        f"?$filter=displayName eq '{escaped_display}'&$select=id,displayName,mailNickname,mailEnabled,securityEnabled"
    )
    lookup_response = requests.get(lookup_by_display_url, headers=headers, timeout=30)
    if not lookup_response.ok:
        _raise_graph_api_error(lookup_response, "Failed to lookup Azure AD groups in Microsoft Graph.")

    existing = lookup_response.json().get("value") or []
    if not existing:
        escaped_nickname = _escape_odata_literal(mail_nickname)
        lookup_by_nickname_url = (
            "https://graph.microsoft.com/v1.0/groups"
            f"?$filter=mailNickname eq '{escaped_nickname}'&$select=id,displayName,mailNickname,mailEnabled,securityEnabled"
        )
        lookup_nickname_response = requests.get(lookup_by_nickname_url, headers=headers, timeout=30)
        if not lookup_nickname_response.ok:
            _raise_graph_api_error(
                lookup_nickname_response,
                "Failed to lookup Azure AD groups by mailNickname in Microsoft Graph.",
            )
        existing = lookup_nickname_response.json().get("value") or []

    if existing:
        group = existing[0]
        if tag_list:
            patch_response = requests.patch(
                f"https://graph.microsoft.com/v1.0/groups/{group.get('id')}",
                headers=headers,
                json={"tags": tag_list},
                timeout=30,
            )
            if patch_response.status_code not in (200, 201, 204):
                _raise_graph_api_error(patch_response, "Failed to update group tags in Microsoft Graph.")
        membership_result = _add_members_to_group(group.get("id"), member_user_ids, headers)
        return {
            "mode": "applied",
            "plan": plan,
            "group": {
                "id": group.get("id"),
                "display_name": group.get("displayName"),
                "mail_nickname": group.get("mailNickname"),
                "mail_enabled": group.get("mailEnabled"),
                "security_enabled": group.get("securityEnabled"),
                "action": "existing",
            },
            "members": membership_result,
            "message": (
                "Group already exists in Azure AD. "
                f"Members added: {membership_result['added_count']}, already member: {membership_result['already_member_count']}, failed: {membership_result['failed_count']}."
            ),
        }

    create_payload = {
        "displayName": display_name,
        "mailNickname": mail_nickname,
        "mailEnabled": mail_enabled,
        "securityEnabled": security_enabled,
        "groupTypes": group_types,
    }
    if description:
        create_payload["description"] = description
    if tag_list:
        create_payload["tags"] = tag_list

    create_response = requests.post(
        "https://graph.microsoft.com/v1.0/groups",
        headers=headers,
        json=create_payload,
        timeout=30,
    )
    if create_response.status_code not in (200, 201):
        _raise_graph_api_error(create_response, "Failed to create Azure AD group in Microsoft Graph.")

    created = create_response.json()
    membership_result = _add_members_to_group(created.get("id"), member_user_ids, headers)
    return {
        "mode": "applied",
        "plan": plan,
        "group": {
            "id": created.get("id"),
            "display_name": created.get("displayName") or display_name,
            "mail_nickname": created.get("mailNickname") or mail_nickname,
            "mail_enabled": created.get("mailEnabled"),
            "security_enabled": created.get("securityEnabled"),
            "action": "created",
        },
        "members": membership_result,
        "message": (
            "Group created in Azure AD. "
            f"Members added: {membership_result['added_count']}, already member: {membership_result['already_member_count']}, failed: {membership_result['failed_count']}."
        ),
    }

def assign_role_to_principal(
    principal_id: str,
    role_key: str,
    scope: str = "",
    subscription_id_override: str = "",
    principal_type: str = "ServicePrincipal",  # ✅ DEFAULT FIXED HERE
):
    """
    Assigns an Azure RBAC role to a principal (Service Principal by default).
    This is the corrected implementation with proper default principalType.
    """

    # 1) Resolve subscription
    subscription_id = (subscription_id_override or settings.AZURE_SUBSCRIPTION_ID or "").strip()
    if not subscription_id:
        raise RuntimeError("AZURE_SUBSCRIPTION_ID is not configured.")

    # 2) Validate & resolve role
    normalized_role = role_key.lower().strip()
    if normalized_role not in ROLE_DEFINITION_IDS:
        raise RuntimeError(f"Unsupported role '{role_key}'. Use reader, contributor, or owner.")

    # 3) Normalize scope
    normalized_scope = _normalize_scope(scope, subscription_id)

    # 4) Build roleDefinitionId
    role_definition_id = (
        f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/"
        f"{ROLE_DEFINITION_IDS[normalized_role]}"
    )

    # 5) Role assignment GUID
    assignment_id = str(uuid.uuid4())

    # 6) Azure auth token
    cred = get_credentials()
    token = cred.get_token("https://management.azure.com/.default")

    headers = {
        "Authorization": f"Bearer {token.token}",
        "Content-Type": "application/json",
    }

    # 7) ARM PUT endpoint
    url = (
        f"https://management.azure.com{normalized_scope}/providers/"
        f"Microsoft.Authorization/roleAssignments/{assignment_id}"
        f"?api-version=2022-04-01"
    )

    # 8) RBAC body (principalType now correct)
    payload = {
        "properties": {
            "principalId": principal_id,
            "roleDefinitionId": role_definition_id,
            "principalType": principal_type,  # <-- ALWAYS 'ServicePrincipal'
        }
    }

    # 9) Execute RBAC request
    response = requests.put(url, headers=headers, json=payload, timeout=30)

    # 10) Success
    if response.status_code in (200, 201):
        body = response.json()
        return {
            "assignment_id": assignment_id,
            "scope": normalized_scope,
            "role": normalized_role,
            "principal_id": principal_id,
            "azure_response_id": body.get("id"),
        }

    # 11) Already exists
    if response.status_code == 409:
        return {
            "assignment_id": assignment_id,
            "scope": normalized_scope,
            "role": normalized_role,
            "principal_id": principal_id,
            "status": "already_exists",
            "message": _extract_error_message(response),
        }

    # 12) Other errors
    raise RuntimeError(_extract_error_message(response))

class AzureStorageAccountsAPIView(APIView):
    """Example: List Azure Storage Accounts in your subscription"""
    
    def get(self, request):
        """List all storage accounts using Azure SDK"""
        try:
            from stl.azure_client import get_storage_management_client
            
            # Get the storage management client
            client = get_storage_management_client()
            
            # List all storage accounts in the subscription
            # Note: This command requires you to set Azure credentials in environment
            accounts = client.storage_accounts.list()
            
            # Convert to list for serialization
            account_list = []
            for account in accounts:
                account_list.append({
                    'name': account.name,
                    'resource_group': account.id.split('/')[4],  # Extract from resource ID
                    'location': account.location,
                    'kind': account.kind,
                    'sku': account.sku.name if account.sku else None,
                })
            
            return Response({
                'status': 'success',
                'message': f'Found {len(account_list)} storage accounts',
                'accounts': account_list,
                'timestamp': datetime.now().isoformat()
            })
        
        except RuntimeError as e:
            # Azure credentials not set
            return Response({
                'status': 'error',
                'message': str(e),
                'info': 'Set Azure environment variables: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_SUBSCRIPTION_ID'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except ImportError as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Azure API error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AzureSubscriptionsAPIView(APIView):
    """List subscriptions available to the configured Azure principal."""

    def get(self, request):
        timestamp = datetime.now().isoformat()
        try:
            subscriptions = list_subscriptions()
            return Response({
                "status": "success",
                "count": len(subscriptions),
                "subscriptions": subscriptions,
                "default_subscription_id": settings.AZURE_SUBSCRIPTION_ID,
                "timestamp": timestamp,
            })
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response({
                "status": "error",
                "code": code,
                "message": message,
                "timestamp": timestamp,
            }, status=http_code)
        except ClientAuthenticationError as exc:
            return Response({
                "status": "error",
                "code": "azure_auth_error",
                "message": str(exc),
                "hint": _proxy_settings_hint() or (
                    "Verify AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET, "
                    "and make sure the Azure service principal can authenticate."
                ),
                "timestamp": timestamp,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except requests.RequestException as exc:
            return Response({
                "status": "error",
                "code": "azure_network_error",
                "message": str(exc),
                "hint": _proxy_settings_hint() or "Check your network connectivity to management.azure.com.",
                "timestamp": timestamp,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({
                "status": "error",
                "message": str(exc),
                "timestamp": timestamp,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AzureDebugConfigAPIView(APIView):
    """Return a masked snapshot of the Azure config loaded by Django."""

    def get(self, request):
        return Response(
            {
                "status": "success",
                "settings_source": "django.conf.settings",
                "azure": {
                    "subscription_id_present": bool((settings.AZURE_SUBSCRIPTION_ID or "").strip()),
                    "tenant_id_present": bool((settings.AZURE_TENANT_ID or "").strip()),
                    "client_id_present": bool((settings.AZURE_CLIENT_ID or "").strip()),
                    "client_secret_present": bool((settings.AZURE_CLIENT_SECRET or "").strip()),
                    "subscription_id": _mask_secret(settings.AZURE_SUBSCRIPTION_ID, visible=6),
                    "tenant_id": _mask_secret(settings.AZURE_TENANT_ID, visible=6),
                    "client_id": _mask_secret(settings.AZURE_CLIENT_ID, visible=6),
                    "client_secret": _mask_secret(settings.AZURE_CLIENT_SECRET, visible=3),
                },
                "env_proxy": {
                    "http_proxy": bool((os.environ.get("HTTP_PROXY") or "").strip()),
                    "https_proxy": bool((os.environ.get("HTTPS_PROXY") or "").strip()),
                    "all_proxy": bool((os.environ.get("ALL_PROXY") or "").strip()),
                },
            }
        )

class AzureResourceGroupsAPIView(APIView):
    """List resource groups for a subscription."""

    def get(self, request):
        timestamp = datetime.now().isoformat()
        subscription_id = (request.query_params.get("subscription_id") or settings.AZURE_SUBSCRIPTION_ID or "").strip()
        if not subscription_id:
            return Response({
                "status": "error",
                "message": "subscription_id is required.",
                "timestamp": timestamp,
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            groups = list_resource_groups(subscription_id)
            return Response({
                "status": "success",
                "subscription_id": subscription_id,
                "count": len(groups),
                "resource_groups": groups,
                "timestamp": timestamp,
            })
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response({
                "status": "error",
                "code": code,
                "message": message,
                "timestamp": timestamp,
            }, status=http_code)
        except ClientAuthenticationError as exc:
            return Response({
                "status": "error",
                "code": "azure_auth_error",
                "message": str(exc),
                "hint": _proxy_settings_hint() or (
                    "Verify AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET, "
                    "and make sure the Azure service principal can authenticate."
                ),
                "timestamp": timestamp,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except requests.RequestException as exc:
            return Response({
                "status": "error",
                "code": "azure_network_error",
                "message": str(exc),
                "hint": _proxy_settings_hint() or "Check your network connectivity to management.azure.com.",
                "timestamp": timestamp,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({
                "status": "error",
                "message": str(exc),
                "timestamp": timestamp,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AzureRegionsAPIView(APIView):
    """List available Azure regions for a subscription."""

    def get(self, request):
        timestamp = datetime.now().isoformat()
        subscription_id = (request.query_params.get("subscription_id") or settings.AZURE_SUBSCRIPTION_ID or "").strip()
        if not subscription_id:
            return Response({
                "status": "error",
                "message": "subscription_id is required.",
                "timestamp": timestamp,
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            regions = list_subscription_regions(subscription_id)
            return Response({
                "status": "success",
                "subscription_id": subscription_id,
                "count": len(regions),
                "regions": regions,
                "timestamp": timestamp,
            })
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response({
                "status": "error",
                "code": code,
                "message": message,
                "timestamp": timestamp,
            }, status=http_code)
        except ClientAuthenticationError as exc:
            return Response({
                "status": "error",
                "code": "azure_auth_error",
                "message": str(exc),
                "hint": _proxy_settings_hint() or (
                    "Verify AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET, "
                    "and make sure the Azure service principal can authenticate."
                ),
                "timestamp": timestamp,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except requests.RequestException as exc:
            return Response({
                "status": "error",
                "code": "azure_network_error",
                "message": str(exc),
                "hint": _proxy_settings_hint() or "Check your network connectivity to management.azure.com.",
                "timestamp": timestamp,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({
                "status": "error",
                "message": str(exc),
                "timestamp": timestamp,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AzureCreateVNetAPIView(APIView):
    """Create or validate VNet configuration in Azure."""

    def post(self, request):
        timestamp = datetime.now().isoformat()
        serializer = CreateVNetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = provision_vnet_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        "timestamp": timestamp,
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    "timestamp": timestamp,
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": code,
                    "message": message,
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AzureCreateVMAPIView(APIView):
    """Create or validate VM configuration in Azure."""

    def post(self, request):
        timestamp = datetime.now().isoformat()
        serializer = CreateVMSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = provision_vm_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        "timestamp": timestamp,
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    "timestamp": timestamp,
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": code,
                    "message": message,
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AzureCreateResourceGroupAPIView(APIView):
    """Create or validate Resource Group configuration in Azure."""

    def post(self, request):
        timestamp = datetime.now().isoformat()
        logging.info(f"Incoming request data at {timestamp}: {request.data}")
        serializer = CreateResourceGroupSerializer(data=request.data)
        if not serializer.is_valid():
            logging.error(f"Validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = provision_resource_group_from_payload(serializer.validated_data)
            logging.info(f"Resource group creation result: {result}")
            return Response(result, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logging.error(f"Error during resource group creation: {str(exc)}")
            return Response({
                "error": "Failed to create resource group.",
                "message": str(exc),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AzureCreateKeyVaultAPIView(APIView):
    """Create or validate Key Vault configuration in Azure."""

    def post(self, request):
        timestamp = datetime.now().isoformat()
        serializer = CreateKeyVaultSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for Key Vault request.",
                    "errors": serializer.errors,
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_key_vault_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        "timestamp": timestamp,
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    "timestamp": timestamp,
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": code,
                    "message": message,
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AzureCreateBackupAPIView(APIView):
    """Create or validate Backup vault configuration in Azure."""

    def post(self, request):
        timestamp = datetime.now().isoformat()
        serializer = CreateBackupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for Backup request.",
                    "errors": serializer.errors,
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_backup_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        "timestamp": timestamp,
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    "timestamp": timestamp,
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": code,
                    "message": message,
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AzureCreateServicePrincipalAPIView(APIView):
    """Create or validate Service Principal configuration in Azure."""

    def post(self, request):
        timestamp = datetime.now().isoformat()
        serializer = CreateServicePrincipalSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for Service Principal request.",
                    "errors": serializer.errors,
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_service_principal_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        "timestamp": timestamp,
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    "timestamp": timestamp,
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except AzureGraphAPIError as exc:
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response(
                    {
                        "status": "error",
                        "code": "graph_permission_denied",
                        "message": (
                            "Cannot create Service Principal because Microsoft Graph permissions "
                            "are missing for this backend app."
                        ),
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "request_context": _graph_request_context(exc.details),
                        "troubleshooting": [
                            "Add Application.ReadWrite.All in App Registration API permissions.",
                            "Grant Admin Consent for the tenant.",
                            "Ensure the app has permission to create service principals in directory.",
                        ],
                        "timestamp": timestamp,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if exc.code == "invalid_upn_domain" or _is_graph_invalid_upn_domain_error(exc.code, str(exc)):
                verified_domains = (exc.details or {}).get("verified_domains") or []
                if not verified_domains:
                    try:
                        verified_domains = [item["domain"] for item in list_verified_domains()]
                    except Exception:
                        verified_domains = []

                provided_domain = (exc.details or {}).get("provided_domain", "")
                return Response(
                    {
                        "status": "error",
                        "code": "invalid_upn_domain",
                        "message": (
                            "The domain part of userPrincipalName is invalid for this tenant. "
                            "Use one of the verified domains."
                        ),
                        "provided_domain": provided_domain,
                        "verified_domains": verified_domains,
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "request_context": _graph_request_context(exc.details),
                        "troubleshooting": [
                            "Use UPN like user@<verified-domain> from the list.",
                            "If your custom domain is missing, verify it in Microsoft Entra ID > Custom domain names.",
                            "Keep tenantId empty unless you intentionally use a different configured tenant.",
                        ],
                        "timestamp": timestamp,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": "graph_api_error",
                    "message": str(exc),
                    "azure_error_code": exc.code,
                    "request_context": _graph_request_context(exc.details),
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": code,
                    "message": message,
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AzureVerifiedDomainsAPIView(APIView):
    """List verified domains available in Microsoft Entra tenant."""

    def get(self, request):
        timestamp = datetime.now().isoformat()
        try:
            domains = list_verified_domains()
            return Response(
                {
                    "status": "success",
                    "count": len(domains),
                    "domains": domains,
                    "timestamp": timestamp,
                },
                status=status.HTTP_200_OK,
            )
        except AzureGraphAPIError as exc:
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response(
                    {
                        "status": "error",
                        "code": "graph_permission_denied",
                        "message": "Cannot list verified domains due to Microsoft Graph permission restrictions.",
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "troubleshooting": [
                            "Grant Directory.Read.All or Domain.Read.All application permission.",
                            "Grant admin consent for the tenant.",
                        ],
                        "request_context": _graph_request_context(exc.details),
                        "timestamp": timestamp,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": "graph_api_error",
                    "message": str(exc),
                    "azure_error_code": exc.code,
                    "request_context": _graph_request_context(exc.details),
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": code,
                    "message": message,
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AzureCreateUserAPIView(APIView):
    """Create or validate Azure AD user configuration."""

    def post(self, request):
        # ✅ Generate or use existing UUID
        request_id = request.data.get("request_id") or str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        serializer = CreateUserSerializer(data=request.data)

        # ❌ Validation Error
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "request_id": request_id,
                    "message": "Validation failed for user request.",
                    "errors": serializer.errors,
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ✅ STEP 1: Save INPUT payload (before processing)
        save_input_payload(
            request_id=request_id,
            process_name="User Creation",
            payload=request.data
        )

        try:
            # ✅ STEP 2: Call service layer
            result = provision_user_from_payload(
                serializer.validated_data,
                request_id=request_id
            )

            # ✅ Dry Run Response
            if result.get("mode") == "dry-run":
                
                # ✅ Save output payload
                save_output_payload(
                    request_id=request_id,
                    payload=result,
                    status="accepted"
                )

                return Response(
                    {
                        "status": "accepted",
                        "request_id": request_id,
                        "timestamp": timestamp,
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            # ✅ STEP 3: Save SUCCESS output payload
            save_output_payload(
                request_id=request_id,
                payload=result,
                status="success"
            )

            # ✅ Success Response
            return Response(
                {
                    "status": "success",
                    "request_id": request_id,
                    "timestamp": timestamp,
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except AzureGraphAPIError as exc:
            # 🔐 Permission Error
            if _is_graph_permission_error(exc.code, str(exc)):

                save_output_payload(
                    request_id=request_id,
                    payload={},
                    status="failed",
                    error_message=str(exc)
                )

                return Response(
                    {
                        "status": "error",
                        "request_id": request_id,
                        "code": "graph_permission_denied",
                        "message": "Cannot create user because Microsoft Graph permissions are missing.",
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "troubleshooting": [
                            "Add User.ReadWrite.All and Directory.ReadWrite.All application permissions.",
                            "Grant admin consent for the tenant.",
                        ],
                        "request_context": _graph_request_context(exc.details),
                        "timestamp": timestamp,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # 🔴 General Graph Error
            save_output_payload(
                request_id=request_id,
                payload={},
                status="failed",
                error_message=str(exc)
            )

            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST

            return Response(
                {
                    "status": "error",
                    "request_id": request_id,
                    "code": "graph_api_error",
                    "message": str(exc),
                    "azure_error_code": exc.code,
                    "request_context": _graph_request_context(exc.details),
                    "timestamp": timestamp,
                },
                status=http_code,
            )

        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = (
                status.HTTP_503_SERVICE_UNAVAILABLE
                if code == "network_dns_error"
                else status.HTTP_400_BAD_REQUEST
            )

            save_output_payload(
                request_id=request_id,
                payload={},
                status="failed",
                error_message=message
            )

            return Response(
                {
                    "status": "error",
                    "request_id": request_id,
                    "code": code,
                    "message": message,
                    "timestamp": timestamp,
                },
                status=http_code,
            )

        except Exception as exc:
            # 🔥 Catch-all error

            save_output_payload(
                request_id=request_id,
                payload={},
                status="failed",
                error_message=str(exc)
            )

            return Response(
                {
                    "status": "error",
                    "request_id": request_id,
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
class AzureCreateGroupAPIView(APIView):
    """Create or validate Azure AD group configuration."""

    def post(self, request):
        timestamp = datetime.now().isoformat()
        serializer = CreateGroupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for group request.",
                    "errors": serializer.errors,
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_group_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        "timestamp": timestamp,
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            return Response(
                {
                    "status": "success",
                    "timestamp": timestamp,
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except AzureGraphAPIError as exc:
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response(
                    {
                        "status": "error",
                        "code": "graph_permission_denied",
                        "message": "Cannot create group because Microsoft Graph permissions are missing.",
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "troubleshooting": [
                            "Add Group.ReadWrite.All and Directory.ReadWrite.All application permissions.",
                            "Grant admin consent for the tenant.",
                        ],
                        "request_context": _graph_request_context(exc.details),
                        "timestamp": timestamp,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": "graph_api_error",
                    "message": str(exc),
                    "azure_error_code": exc.code,
                    "request_context": _graph_request_context(exc.details),
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": code,
                    "message": message,
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AzureADUsersListAPIView(APIView):
    """List Azure AD users for role assignment dropdowns."""

    def get(self, request):
        timestamp = datetime.now().isoformat()
        limit = min(_to_positive_int(request.query_params.get("limit"), 200), 500)

        try:
            users = list_azure_ad_users(limit=limit)
            return Response({
                "status": "success",
                "count": len(users),
                "users": users,
                "message": "No Azure AD users found in this tenant." if len(users) == 0 else "",
                "timestamp": timestamp,
            })
        except AzureGraphAPIError as exc:
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response({
                    "status": "error",
                    "code": "graph_permission_denied",
                    "message": (
                        "Cannot list Azure AD users because Microsoft Graph permissions are missing "
                        "for this app. This is a permission issue, not an empty-tenant issue."
                    ),
                    "azure_error_code": exc.code,
                    "azure_error_message": str(exc),
                    "request_context": _graph_request_context(exc.details),
                    "troubleshooting": [
                        "In the Azure App Registration used by backend, add Application permission User.Read.All or Directory.Read.All.",
                        "Grant Admin Consent for the tenant after adding permissions.",
                        "Retry after consent is granted.",
                    ],
                    "timestamp": timestamp,
                }, status=status.HTTP_403_FORBIDDEN)
            
            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response({
                "status": "error",
                "code": "graph_api_error",
                "message": str(exc),
                "azure_error_code": exc.code,
                "request_context": _graph_request_context(exc.details),
                "timestamp": timestamp,
            }, status=http_code)
        except RuntimeError as exc:
            message = str(exc)
            if _is_dns_resolution_error(message):
                return Response({
                    "status": "error",
                    "code": "network_dns_error",
                    "message": (
                        "Cannot reach Microsoft login service (login.microsoftonline.com) "
                        "from this machine."
                    ),
                    "details": message,
                    "timestamp": timestamp,
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            return Response({
                "status": "error",
                "message": message,
                "timestamp": timestamp,
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({
                "status": "error",
                "message": str(exc),
                "timestamp": timestamp,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AzureADUsersCountAPIView(APIView):
    """Example: Get Azure AD users count using Microsoft Graph"""

    def get(self, request):
        timestamp = datetime.now().isoformat()
        try:
            # Acquire token for Microsoft Graph using client credentials
            cred = get_credentials()
            token = cred.get_token("https://graph.microsoft.com/.default")
            access_token = token.token

            headers = {
                'Authorization': f'Bearer {access_token}',
                'ConsistencyLevel': 'eventual'
            }

            # Try the $count endpoint first
            graph_count_url = 'https://graph.microsoft.com/v1.0/users/$count'
            resp = requests.get(graph_count_url, headers=headers, timeout=20)
            if resp.status_code == 200:
                try:
                    count = int(resp.text)
                except Exception:
                    count = None
                cache.set(
                    AD_COUNT_CACHE_KEY,
                    {"count": count, "timestamp": timestamp},
                    timeout=3600,
                )
                return Response({
                    'status': 'success',
                    'count': count,
                    'raw': resp.text,
                    'timestamp': timestamp,
                })

            # Fallback to $count via query
            graph_query_url = 'https://graph.microsoft.com/v1.0/users?$count=true&$top=1'
            resp2 = requests.get(graph_query_url, headers=headers, timeout=20)
            if resp2.ok:
                j = resp2.json()
                count = j.get('@odata.count')
                cache.set(
                    AD_COUNT_CACHE_KEY,
                    {"count": count, "timestamp": timestamp},
                    timeout=3600,
                )
                return Response({
                    'status': 'success',
                    'count': count,
                    'data_sample': j.get('value', [])[:1],
                    'timestamp': timestamp,
                })

            _raise_graph_api_error(
                resp2,
                fallback_message="Failed to fetch Azure AD users count from Microsoft Graph.",
            )

        except AzureGraphAPIError as exc:
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response({
                    "status": "error",
                    "code": "graph_permission_denied",
                    "message": (
                        "Cannot read Azure AD users count because Microsoft Graph permissions are missing "
                        "for this app. This is a permission issue, not a 'no users' issue."
                    ),
                    "azure_error_code": exc.code,
                    "azure_error_message": str(exc),
                    "request_context": _graph_request_context(exc.details),
                    "troubleshooting": [
                        "Add Application permission User.Read.All or Directory.Read.All in Azure App Registration.",
                        "Grant Admin Consent for the tenant.",
                        "Retry the users count request.",
                    ],
                    "timestamp": timestamp,
                }, status=status.HTTP_403_FORBIDDEN)

            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response({
                "status": "error",
                "code": "graph_api_error",
                "message": str(exc),
                "azure_error_code": exc.code,
                "request_context": _graph_request_context(exc.details),
                "timestamp": timestamp,
            }, status=http_code)
        except RuntimeError as e:
            return Response({
                'status': 'error',
                'message': str(e),
                'info': 'Ensure app has Microsoft Graph application permissions (User.Read.All) and consent.',
                'timestamp': timestamp,
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            message = str(e)
            if _is_dns_resolution_error(message):
                cached = cache.get(AD_COUNT_CACHE_KEY)
                if cached and cached.get("count") is not None:
                    return Response({
                        "status": "degraded",
                        "count": cached["count"],
                        "message": (
                            "Live Azure AD check failed due to DNS/network issue. "
                            "Showing last successful count."
                        ),
                        "cached_at": cached.get("timestamp"),
                        "timestamp": timestamp,
                        "troubleshooting": [
                            "Check internet/VPN connection on the Django host.",
                            "Verify DNS/proxy settings allow login.microsoftonline.com.",
                            "Retry after network is stable.",
                        ],
                    }, status=status.HTTP_200_OK)

                return Response({
                    "status": "error",
                    "code": "network_dns_error",
                    "message": (
                        "Cannot reach Microsoft login service (login.microsoftonline.com) "
                        "from this machine."
                    ),
                    "details": message,
                    "timestamp": timestamp,
                    "troubleshooting": [
                        "Check internet/VPN connection on the Django host.",
                        "Verify DNS/proxy settings allow login.microsoftonline.com.",
                        "If your company uses a proxy, set HTTPS proxy for Python process.",
                    ],
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            return Response({
                'status': 'error',
                'message': message,
                'timestamp': timestamp,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AzureAssignRoleAPIView(APIView):
    """Assign an Azure RBAC role to a principal using ARM roleAssignments API."""

    def post(self, request):
        # Pass expected PrincipalType to serializer context
        expected_principal_type = request.data.get("principal_type", "ServicePrincipal")
        serializer = AssignRoleSerializer(data=request.data, context={"expected_principal_type": expected_principal_type})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        principal_id = data.get("principal_id")
        if not principal_id:
            return Response({
                "status": "error",
                "message": "principal_id is required for Azure role assignment.",
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = assign_role_to_principal(
                principal_id=principal_id,
                role_key=data["role"],
                scope=data.get("scope", ""),
            )
        except RuntimeError as exc:
            return Response({
                "status": "error",
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({
                "status": "error",
                "message": f"Unexpected Azure role assignment failure: {exc}",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "status": "success",
            "message": "Role assignment completed.",
            "assignment": result,
        }, status=status.HTTP_201_CREATED) 

# --- ADD THIS CLASS to apis/moniter/azure/views.py ---

class AzureLookupServicePrincipalByIdAPIView(APIView):
    """
    Lookup a Service Principal by its object ID using Microsoft Graph.
    POST body:
      { "principal_id": "<GUID>" }
    """

    def post(self, request):
        timestamp = datetime.now().isoformat()
        principal_id = (request.data.get("principal_id") or "").strip()

        if not principal_id:
            return Response(
                {
                    "status": "error",
                    "message": "principal_id is required.",
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            headers = _graph_headers()
            url = f"https://graph.microsoft.com/v1.0/servicePrincipals/{principal_id}"
            resp = requests.get(url, headers=headers, timeout=20)

            if resp.status_code == 404:
                return Response(
                    {
                        "status": "not_found",
                        "principal_id": principal_id,
                        "message": "Service Principal not found in this tenant.",
                        "timestamp": timestamp,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not resp.ok:
                _raise_graph_api_error(resp, "Failed to lookup Service Principal by object ID.")

            body = resp.json()
            result = {
                "id": body.get("id"),
                "appId": body.get("appId"),
                "displayName": body.get("displayName"),
                "servicePrincipalType": body.get("servicePrincipalType"),
                "appOwnerOrganizationId": body.get("appOwnerOrganizationId"),
                "signInAudience": body.get("signInAudience"),
                "accountEnabled": body.get("accountEnabled"),
                "tags": body.get("tags"),
            }
            return Response(
                {
                    "status": "success",
                    "principal": result,
                    "timestamp": timestamp,
                },
                status=status.HTTP_200_OK,
            )

        except AzureGraphAPIError as exc:
            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": exc.code,
                    "message": str(exc),
                    "request_context": _graph_request_context(exc.details),
                    "timestamp": timestamp,
                },
                status=http_code,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AzureAssignServicePrincipalRoleAPIView(APIView):
    """
    Assign an RBAC role to a Service Principal using ARM.
    Uses AssignServicePrincipalRoleSerializer for strict validation.
    """

    def post(self, request):
        # 1) Validate incoming payload
        serializer = AssignServicePrincipalRoleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data

        principal_id = data["principal_id"]
        role_key = data["role"]
        scope_type = data["scope_type"]
        subscription = data["subscription"]

        # -------------------------
        # 2) Build SCOPE
        # -------------------------
        if scope_type == "subscription":
            scope = f"/subscriptions/{subscription}"

        elif scope_type == "resourceGroup":
            rg = data.get("resource_group")
            if not rg:
                return Response(
                    {"status": "error", "message": "resource_group is required for resourceGroup scope"},
                    status=400,
                )
            scope = f"/subscriptions/{subscription}/resourceGroups/{rg}"

        elif scope_type == "vnet":
            rg = data.get("resource_group")
            vnet = data.get("vnet")
            if not (rg and vnet):
                return Response(
                    {"status": "error", "message": "resource_group and vnet are required for vnet scope"},
                    status=400,
                )
            scope = (
                f"/subscriptions/{subscription}/resourceGroups/{rg}"
                f"/providers/Microsoft.Network/virtualNetworks/{vnet}"
            )

        elif scope_type == "keyvault":
            rg = data.get("resource_group")
            kv = data.get("keyvault")
            if not (rg and kv):
                return Response(
                    {"status": "error", "message": "resource_group and keyvault are required for keyvault scope"},
                    status=400,
                )
            scope = (
                f"/subscriptions/{subscription}/resourceGroups/{rg}"
                f"/providers/Microsoft.KeyVault/vaults/{kv}"
            )

        elif scope_type == "custom":
            scope = data.get("scope")
            if not scope:
                return Response(
                    {"status": "error", "message": "scope is required for custom scope type"},
                    status=400,
                )

        else:
            return Response(
                {"status": "error", "message": f"Unknown scope_type '{scope_type}'"},
                status=400,
            )

        # -------------------------
        # 3) Assign the role (call your ARM function)
        # -------------------------
        try:
            result = assign_role_to_principal(
                principal_id=principal_id,
                role_key=role_key,
                scope=scope
            )

            return Response(
                {
                    "status": "success",
                    "message": "Role assigned successfully.",
                    "scope": scope,
                    "role": role_key,
                    "assignment": result,
                },
                status=status.HTTP_201_CREATED,
            )

        except RuntimeError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": f"Unexpected Azure RBAC error: {str(exc)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

@api_view(['GET'])
def list_vnets(request):
    try:
        # Mock data for VNETs; replace with actual Azure API call
        vnets = [
            {"id": "1", "name": "vnet-1", "ipAddress": "10.0.0.1"},
            {"id": "2", "name": "vnet-2", "ipAddress": "10.0.1.1"},
        ]
        return Response({"vnets": vnets})
    except Exception as e:
        return Response({"error": str(e)}, status=500)

class AzureVNetListAPIView(APIView):
    """
    List VNets for a subscription (optionally filter by resource group).
    GET /api/moniter/azure/vnets/?subscription_id=<id>&resource_group=<rg-name>

    Response:
    {
      "status": "success",
      "subscription_id": "...",
      "resource_group": "rg-optional",
      "count": 2,
      "vnets": [
        {
          "id": ".../virtualNetworks/vnet-01",
          "name": "vnet-01",
          "location": "centralindia",
          "addressSpace": { "addressPrefixes": ["10.1.0.0/16"] },
          "subnets": [
            { "id": ".../subnets/default", "name": "default", "addressPrefix": "10.1.0.0/24" }
          ]
        }
      ],
      "timestamp": "..."
    }
    """

    def get(self, request):
        timestamp = datetime.now().isoformat()

        subscription_id = (request.query_params.get("subscription_id")
                           or settings.AZURE_SUBSCRIPTION_ID or "").strip()
        if not subscription_id:
            return Response({
                "status": "error",
                "message": "subscription_id is required.",
                "timestamp": timestamp,
            }, status=status.HTTP_400_BAD_REQUEST)

        resource_group = (request.query_params.get("resource_group") or "").strip()

        try:
            headers = _management_headers()

            def _map_vnet(item: dict) -> dict:
                props = item.get("properties") or {}
                aspace = props.get("addressSpace") or {}
                subnets = []
                for sn in props.get("subnets") or []:
                    sprops = sn.get("properties") or {}
                    subnets.append({
                        "id": sn.get("id"),
                        "name": sn.get("name"),
                        "addressPrefix": sprops.get("addressPrefix"),
                    })
                return {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "location": item.get("location"),
                    "addressSpace": aspace,  # {"addressPrefixes": [...]}
                    "subnets": subnets,
                }

            if resource_group:
                # List VNets inside a specific RG
                url = (f"https://management.azure.com/subscriptions/{subscription_id}"
                       f"/resourceGroups/{resource_group}"
                       f"/providers/Microsoft.Network/virtualNetworks?api-version=2023-09-01")
                resp = requests.get(url, headers=headers, timeout=20)
                if not resp.ok:
                    raise RuntimeError(_extract_error_message(resp))
                items = (resp.json().get("value") or [])
            else:
                # List all VNets in the subscription (paged)
                url = (f"https://management.azure.com/subscriptions/{subscription_id}"
                       f"/providers/Microsoft.Network/virtualNetworks?api-version=2023-09-01")
                items = _paged_management_get(url, headers, max_pages=50)

            vnets = [_map_vnet(v) for v in items]
            vnets.sort(key=lambda v: (v.get("name") or "").lower())

            return Response({
                "status": "success",
                "subscription_id": subscription_id,
                "resource_group": resource_group or "",
                "count": len(vnets),
                "vnets": vnets,
                "timestamp": timestamp,
            }, status=status.HTTP_200_OK)

        except RuntimeError as exc:
            message = str(exc)
            code = "network_dns_error" if _is_dns_resolution_error(message) else "azure_runtime_error"
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE if code == "network_dns_error" else status.HTTP_400_BAD_REQUEST
            return Response({
                "status": "error",
                "code": code,
                "message": message,
                "timestamp": timestamp,
            }, status=http_code)

        except Exception as exc:
            return Response({
                "status": "error",
                "message": str(exc),
                "timestamp": timestamp,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AzureNSGAPIView(APIView):
    """Create or validate Azure NSG configuration."""

    def post(self, request):
        timestamp = datetime.now().isoformat()

        serializer = AzureNSGSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Invalid NSG input",
                    "errors": serializer.errors,
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_nsg_from_payload(serializer.validated_data)

            response_data = {
                "timestamp": timestamp,
                **result
            }

            # Handle dry-run mode
            if result.get("mode") == "dry-run":
                response_data["status"] = "accepted"
                return Response(response_data, status=status.HTTP_202_ACCEPTED)

            # Success case
            response_data["status"] = "success"
            return Response(response_data, status=status.HTTP_201_CREATED)

        except AzureGraphAPIError as exc:
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response(
                    {
                        "status": "error",
                        "code": "graph_permission_denied",
                        "message": "Missing Microsoft Graph permissions.",
                        "timestamp": timestamp,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            return Response(
                {
                    "status": "error",
                    "code": "azure_error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "code": "internal_error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

@api_view(["POST"])
def create_keyvault_with_pe(request):
    try:
        print("🔥 Incoming request:", request.data)

        serializer = KeyVaultWithPESerializer(data=request.data)

        if not serializer.is_valid():
            print("❌ VALIDATION ERRORS:", serializer.errors)
            return Response({
                "status": "error",
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=400)

        data = serializer.validated_data
        kv = data["keyVault"]
        pe = data["privateEndpoint"]
        dry_run = data.get("dryRun", True)

        print("✅ Validated data:", data)
        print("🔧 Dry run mode:", dry_run)

        if dry_run:
            print("⚠️ Dry run mode enabled. No resources will be created.")
            return Response({
                "status": "accepted",
                "message": "Payload validated. Set dryRun=false to create resources.",
                "keyVault": kv,
                "privateEndpoint": pe
            })

        subscription_id = kv["subscription"]
        resource_group = kv["resourceGroup"]
        location = kv["region"]
        kv_name = kv["keyVaultName"]
        tenant_id = kv.get("tenantId")
        print("🔑 Creating Key Vault with name:", kv_name)
        print("📍 Location:", location, "Resource Group:", resource_group)
        credential = DefaultAzureCredential()
        kv_client = KeyVaultManagementClient(credential, subscription_id)
        kv_params = {
            "location": location,
            "properties": {
                "sku": {"family": "A", "name": kv.get("skuName", "standard")},
                "tenantId": tenant_id,
                "accessPolicies": []
            }
        }
        kv_client.vaults.begin_create_or_update(
            resource_group_name=resource_group,
            vault_name=kv_name,
            parameters=kv_params
        ).result()
        print("✅ Key Vault created successfully.")
        return Response({
            "status": "success",
            "message": "Key Vault created successfully."
        })
    except Exception as e:
        print("❌ Exception occurred:", str(e))
        return Response({
            "status": "error",
            "message": f"Failed to create Key Vault: {str(e)}"
        }, status=500)

@api_view(["GET"])
def list_resources(request):
    subscription_id = request.GET.get("subscription_id") or request.GET.get("subscriptionId")
    resource_group = request.GET.get("resource_group") or request.GET.get("resourceGroup")
    if not subscription_id or not resource_group:
        return Response({"error": "subscription_id and resource_group required"}, status=400)
    try:
        credential = get_credentials()
        client = ResourceManagementClient(credential, subscription_id)
        resources = client.resources.list_by_resource_group(resource_group)
        output = [
            {
                "id": r.id,
                "name": r.name,
                "type": r.type,
                "location": r.location,
            }
            for r in resources
        ]
        return Response({"resources": output})
    except ClientAuthenticationError as exc:
        return Response(
            {
                "error": "Azure credential issue",
                "details": str(exc),
                "hint": "Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET (or run `az login`) so DefaultAzureCredential can authenticate.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(["DELETE"])
def delete_resource_group(request):
    subscription_id = request.GET.get("subscriptionId") or request.GET.get("subscription_id")
    resource_group = request.GET.get("resourceGroup") or request.GET.get("resource_group")

    if not subscription_id or not resource_group:
        return Response({"error": "subscriptionId and resourceGroup required"}, status=400)

    try:
        credential = get_credentials()
        client = ResourceManagementClient(credential, subscription_id)

        delete_async = client.resource_groups.begin_delete(resource_group)
        delete_async.result()

        return Response({"status": "success", "message": "Resource group deleted"})
    
    except ClientAuthenticationError as exc:
        return Response(
            {
                "error": "Azure credential issue",
                "details": str(exc),
                "hint": "Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET (or run `az login`) so DefaultAzureCredential can authenticate.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=500)

class AssignRole1APIView(APIView):

    def post(self, request):
        print("REQUEST DATA:", request.data)

        serializer = AssignRole1Serializer(data=request.data)

        if not serializer.is_valid():
            print("VALIDATION ERRORS:", serializer.errors)
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data

        try:
            # ✅ Extract scope
            scope = data["scope"]
            parts = scope.strip("/").split("/")

            if len(parts) < 2 or parts[0] != "subscriptions":
                return Response(
                    {"message": "Invalid scope format"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            subscription_id = parts[1]

            # ✅ Get role_definition_id directly from frontend
            role_id = data["role_definition_id"]
            if not role_id:
                return Response(
                    {"message": "Invalid role"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Build full role definition ID safely
            if role_id.startswith("/"):
                full_role_definition_id = role_id
            else:
                full_role_definition_id = (
                    f"/subscriptions/{subscription_id}"
                    f"/providers/Microsoft.Authorization/roleDefinitions/{role_id}"
                )

            # ✅ Get Azure credential + client
            credential = get_credentials()
            client = AuthorizationManagementClient(credential, subscription_id)

            # ✅ Generate unique assignment ID
            assignment_name = str(uuid.uuid4())

            print("Assigning role with:")
            print("Principal ID:", data["principal_id"])
            print("Scope:", scope)
            print("Role Definition ID:", full_role_definition_id)

            # ✅ Create role assignment
            parameters = RoleAssignmentCreateParameters(
                role_definition_id=full_role_definition_id,
                principal_id=data["principal_id"],
            )

            result = client.role_assignments.create(
                scope=scope,
                role_assignment_name=assignment_name,
                parameters=parameters,
            )

            print("ASSIGNMENT RESULT:", result)

            return Response({
                "status": "success",
                "message": "Role assigned successfully",
                "assignment_id": assignment_name
            })

        except Exception as e:
            print("ERROR:", str(e))
            return Response(
                {"message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
from azure.identity import ClientSecretCredential
# ------------------- GLOBAL CONFIG -------------------
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from azure.mgmt.authorization import AuthorizationManagementClient

# ------------------- GLOBAL CONFIG -------------------

GRAPH_URL = "https://graph.microsoft.com/v1.0/directoryObjects/"

# ✅ CACHE (VERY IMPORTANT)
principal_cache = {}

# ------------------- GRAPH TOKEN -------------------

def get_graph_token():
    try:
        credential = get_credentials()
        token = credential.get_token("https://graph.microsoft.com/.default")
        return token.token
    except Exception as e:
        print("Graph Token Error:", str(e))
        return None

# ------------------- GET PRINCIPAL NAME (WITH CACHE) -------------------

def get_principal_name(principal_id, token):
    # 🔥 1. Check cache first
    if principal_id in principal_cache:
        return principal_cache[principal_id]

    if not token:
        raise RuntimeError(
            f"Microsoft Graph token is unavailable while resolving principal '{principal_id}'."
        )

    url = f"{GRAPH_URL}{principal_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        res = requests.get(url, headers=headers, timeout=20)
        if res.status_code != 200:
            raise RuntimeError(
                f"Microsoft Graph lookup failed for principal '{principal_id}' "
                f"with status {res.status_code}: {res.text}"
            )

        data = res.json()
        name = (
            data.get("displayName")
            or data.get("userPrincipalName")
            or data.get("appId")
            or "Unknown principal"
        )

        # 🔥 2. Store in cache
        principal_cache[principal_id] = name
        return name

    except requests.RequestException as exc:
        raise RuntimeError(
            f"Microsoft Graph lookup request failed for principal '{principal_id}': {exc}"
        ) from exc
    except ValueError as exc:
        raise RuntimeError(
            f"Microsoft Graph returned invalid JSON while resolving principal '{principal_id}'."
        ) from exc

# ------------------- PROCESS EACH ROLE -------------------

def process_role(a, client, scope, graph_token):
    try:
        role_def_id = a.role_definition_id.split("/")[-1]

        role_def = client.role_definitions.get(scope, role_def_id)

        principal_lookup_error = None
        try:
            principal_name = get_principal_name(
                a.principal_id,
                graph_token
            )
        except RuntimeError as exc:
            principal_name = "Unknown principal"
            principal_lookup_error = str(exc)

        result = {
            "assignment_id": a.name,
            "principal_id": a.principal_id,
            "principal_name": principal_name,
            "role_name": role_def.role_name,
            "scope": a.scope
        }
        if principal_lookup_error:
            result["principal_lookup_error"] = principal_lookup_error

        return result

    except Exception as inner_error:
        print("Role Processing Error:", str(inner_error))
        return None

# ------------------- VIEW ROLES API -------------------

class AzureViewRolesAPIView(APIView):

    def get(self, request):
        try:
            scope = request.GET.get("scope")

            if not scope:
                return Response(
                    {"message": "Scope is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 🔹 Extract subscription ID
            parts = scope.strip("/").split("/")
            if len(parts) < 2:
                return Response(
                    {"message": "Invalid scope format"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            subscription_id = parts[1]

            # ✅ Azure Client
            client = AuthorizationManagementClient(
                get_credentials(),
                subscription_id
            )

            # 🔹 Get Graph token ONCE
            graph_token = get_graph_token()

            # 🔹 Convert to list (important for parallel)
            assignments = list(
                client.role_assignments.list_for_scope(scope)
            )

            roles = []

            # 🚀 PARALLEL EXECUTION (MAIN IMPROVEMENT)
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(
                        process_role,
                        a,
                        client,
                        scope,
                        graph_token
                    )
                    for a in assignments
                ]

                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        roles.append(result)

            return Response({
                "status": "success",
                "count": len(roles),
                "roles": roles
            })

        except Exception as e:
            print("API Error:", str(e))
            return Response(
                {"message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
                        
class AzureDeleteRoleAPIView(APIView):

    def delete(self, request):
        try:
            assignment_name = request.data.get("assignment_name")
            scope = request.data.get("scope")

            if not assignment_name or not scope:
                return Response(
                    {"message": "assignment_name and scope required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            parts = scope.strip("/").split("/")
            subscription_id = parts[1]

            credential = get_credentials()
            client = AuthorizationManagementClient(credential, subscription_id)

            client.role_assignments.delete(
                scope=scope,
                role_assignment_name=assignment_name
            )

            return Response({
                "status": "success",
                "message": "Role deleted successfully"
            })

        except Exception as e:
            return Response(
                {"message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
from rest_framework.response import Response
from rest_framework import status
from azure.mgmt.resource import ResourceManagementClient
from azure.core.exceptions import ClientAuthenticationError

def _extract_network_interface_and_ipconfig(ip_config_id: str):
    normalized = (ip_config_id or "").strip("/")
    segments = [segment for segment in normalized.split("/") if segment]
    lower_segments = [segment.lower() for segment in segments]

    try:
        nic_index = lower_segments.index("networkinterfaces")
        nic_name = segments[nic_index + 1]
    except (ValueError, IndexError):
        raise RuntimeError("IP configuration does not reference a network interface.")

    try:
        ipconfig_index = lower_segments.index("ipconfigurations")
        ipconfig_name = segments[ipconfig_index + 1]
    except (ValueError, IndexError):
        raise RuntimeError("IP configuration path is malformed.")

    return nic_name, ipconfig_name


@api_view(["POST"])
def detach_public_ip(request):
    subscription_id = (
        request.data.get("subscription_id") or request.data.get("subscriptionId")
    )
    resource_group = (
        request.data.get("resource_group") or request.data.get("resourceGroup")
    )
    resource_id = (
        request.data.get("resource_id") or request.data.get("resourceId")
    )

    if not subscription_id or not resource_group or not resource_id:
        return Response(
            {"error": "subscription_id, resource_group and resource_id are required"},
            status=400,
        )

    try:
        credential = get_credentials()
        resource_client = ResourceManagementClient(credential, subscription_id)
        public_ip = resource_client.resources.get_by_id(
            resource_id,
            api_version=NETWORK_API_VERSION,
        )

        properties = getattr(public_ip, "properties", {}) or {}
        ip_config = properties.get("ipConfiguration") or {}
        ip_configuration_id = ip_config.get("id")

        if not ip_configuration_id:
            return Response(
                {
                    "status": "success",
                    "message": "Public IP is already detached from any resource.",
                },
                status=200,
            )

        nic_name, ip_config_name = _extract_network_interface_and_ipconfig(
            ip_configuration_id
        )

        network_client = NetworkManagementClient(credential, subscription_id)
        nic = network_client.network_interfaces.get(resource_group, nic_name)

        matched_config = next(
            (
                config
                for config in (nic.ip_configurations or [])
                if config.name == ip_config_name
            ),
            None,
        )

        if not matched_config:
            return Response(
                {"error": "Referenced IP configuration was not found on the NIC."},
                status=400,
            )

        if not getattr(matched_config, "public_ip_address", None):
            return Response(
                {
                    "status": "success",
                    "message": "Public IP was already detached from the NIC.",
                },
                status=200,
            )

        matched_config.public_ip_address = None
        network_client.network_interfaces.begin_create_or_update(
            resource_group, nic_name, nic
        ).result()

        return Response(
            {
                "status": "success",
                "message": "Public IP detached from the NIC.",
            }
        )

    except ClientAuthenticationError as exc:
        return Response(
            {
                "error": "Azure credential issue",
                "details": str(exc),
                "hint": "Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET (or run `az login`) so DefaultAzureCredential can authenticate.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    except HttpResponseError as exc:
        response = getattr(exc, "response", None)
        message = _extract_error_message(response) if response else str(exc)
        return Response({"error": message}, status=exc.status_code or 500)

    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["DELETE"])
def delete_resource(request):
    subscription_id = request.GET.get("subscriptionId") or request.GET.get("subscription_id")
    resource_group = request.GET.get("resourceGroup") or request.GET.get("resource_group")
    resource_id = request.GET.get("resourceId") or request.GET.get("resource_id")

    # 🔴 Validate inputs
    if not subscription_id or not resource_group or not resource_id:
        return Response(
            {"error": "subscriptionId, resourceGroup and resourceId are required"},
            status=400
        )

    try:
        credential = get_credentials()
        client = ResourceManagementClient(credential, subscription_id)

        # 🔹 Split resource ID
        parts = resource_id.split("/")

        # Example structure:
        # /subscriptions/{sub}/resourceGroups/{rg}/providers/{provider}/{type}/{name}

        provider_namespace = parts[6]
        resource_type = parts[7]
        resource_name = parts[8]

        # 🔹 Handle nested resources (important)
        if len(parts) > 9:
            resource_type = "/".join(parts[7:-1])
            resource_name = parts[-1]

        # 🔹 Delete resource
        delete_async = client.resources.begin_delete(
            resource_group_name=resource_group,
            resource_provider_namespace=provider_namespace,
            parent_resource_path="",
            resource_type=resource_type,
            resource_name=resource_name,
            api_version="2021-04-01"  # You can adjust if needed
        )

        delete_async.result()

        return Response({
            "status": "success",
            "message": f"Resource '{resource_name}' deleted successfully"
        })

    except ClientAuthenticationError as exc:
        return Response(
            {
                "error": "Azure credential issue",
                "details": str(exc),
                "hint": "Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET or run `az login`.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    except Exception as e:
        return Response({"error": str(e)}, status=500)

import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 🔥 USE EXISTING credential (DO NOT recreate)
# credential = ClientSecretCredential(...)  <-- already defined above

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ------------------- GENERIC GRAPH REQUEST -------------------

def graph_request(method, endpoint, token, data=None):
    try:
        url = f"{GRAPH_BASE}{endpoint}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        response = requests.request(
            method,
            url,
            headers=headers,
            json=data
        )

        # ❌ Error handling
        if response.status_code not in [200, 201, 204]:
            return None, response.text

        # ✅ No content (DELETE case)
        if response.status_code == 204:
            return {}, None

        return response.json(), None

    except Exception as e:
        return None, str(e)


# ------------------- CONFIG (TEMP - MOVE TO DB LATER) -------------------

def _get_managed_principal_ids():
    return set(
        ManagedServicePrincipal.objects.values_list(
            "service_principal_id", flat=True
        )
    )

def _register_managed_principal(sp_id, display_name=None):
    if not sp_id:
        return

    ManagedServicePrincipal.objects.update_or_create(
        service_principal_id=sp_id,
        defaults={"display_name": display_name or ""},
    )

def _unregister_managed_principal(sp_id):
    if not sp_id:
        return

    ManagedServicePrincipal.objects.filter(
        service_principal_id=sp_id
    ).delete()


in_use_principals = [
    "sp-id-in-use-1",
    "sp-id-in-use-2",
]


# ------------------- GET ALL SERVICE PRINCIPALS -------------------

def get_service_principals(request):
    try:
        token = get_graph_token()

        if not token:
            return JsonResponse({"error": "Failed to get Graph token"}, status=500)

        data, error = graph_request(
            "GET",
            "/servicePrincipals",
            token
        )

        if error:
            return JsonResponse({"error": error}, status=500)

        sp_list = data.get("value", [])

        managed_ids = _get_managed_principal_ids()
        formatted = []

        for sp in sp_list:
            sp_id = sp.get("id")

            formatted.append({
                "id": sp_id,
                "appId": sp.get("appId"),
                "displayName": sp.get("displayName"),
                "tenantId": sp.get("appOwnerOrganizationId"),

                # 🔐 Ownership + usage flags
                "isManaged": sp_id in managed_ids,
                "isInUse": sp_id in in_use_principals,
            })

        return JsonResponse(formatted, safe=False)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ------------------- GET IN-USE PRINCIPALS -------------------

def get_in_use_service_principals(request):
    return JsonResponse(in_use_principals, safe=False)


# ------------------- DELETE SERVICE PRINCIPAL -------------------

def create_log(request_id, status, message, generated_password=None):
    APILog.objects.create(
        request_id=request_id,
        status=status,
        message=message,
        generated_password=generated_password,
    )

def get_logs_by_request(request, request_id):
    logs = (
        APILog.objects.filter(request_id=request_id)
        .order_by("created_at")
        .values("status", "message", "created_at")
    )

    process_name = (
        RequestPayload.objects.filter(request_id=request_id)
        .values_list("process_name", flat=True)
        .first()
        or ""
    )

    payload = []
    for row in logs:
        payload.append(
            {
                "status": row["status"],
                "message": row["message"],
                "timestamp": row["created_at"].isoformat(),
                "step_name": process_name,
            }
        )

    return JsonResponse(payload, safe=False)

@csrf_exempt
def delete_service_principal(request, sp_id):
    request_id = str(uuid.uuid4())  # 🔥 Generate UUID

    # 🔹 Log start
    create_log(request_id, "info", f"Delete request started for SP: {sp_id}")

    if request.method != "DELETE":
        create_log(request_id, "failed", "Invalid request method")
        return JsonResponse({
            "error": "Invalid request method",
            "request_id": request_id
        }, status=405)

    try:
        # 🔄 Auto-register unmanaged principals so the delete flow can proceed
        if not ManagedServicePrincipal.objects.filter(
            service_principal_id=sp_id
        ).exists():
            create_log(request_id, "info", "Auto-registering unmanaged SP before delete")
            _register_managed_principal(sp_id)

        # ❌ Block if currently used
        if sp_id in in_use_principals:
            create_log(request_id, "failed", "SP is currently in use")
            return JsonResponse({
                "error": "This service principal is used by our APIs",
                "request_id": request_id
            }, status=400)

        # 🔐 Get token
        token = get_graph_token()

        if not token:
            create_log(request_id, "failed", "Failed to get Graph token")
            return JsonResponse({
                "error": "Failed to get Graph token",
                "request_id": request_id
            }, status=500)

        # 🔗 Call Graph API
        _, error = graph_request(
            "DELETE",
            f"/servicePrincipals/{sp_id}",
            token
        )

        if error:
            create_log(request_id, "failed", f"Graph API error: {error}")
            return JsonResponse({
                "error": "Failed to delete service principal",
                "details": error,
                "request_id": request_id
            }, status=500)

        # ✅ Success log
        create_log(request_id, "success", "Service Principal deleted successfully")
        _unregister_managed_principal(sp_id)

        return JsonResponse({
            "message": "Service Principal deleted successfully",
            "request_id": request_id
        })

    except Exception as e:
        create_log(request_id, "failed", str(e))

        return JsonResponse({
            "error": str(e),
            "request_id": request_id
        }, status=500)

def save_input_payload(request_id, process_name, payload):
    try:
        obj, created = RequestPayload.objects.update_or_create(
            request_id=request_id,
            defaults={
                "process_name": process_name,
                "input_payload": payload,
                "status": "pending"
            }
        )

        print(f"Input Saved | {request_id}")
        return obj
    except Exception as e:
        print(f"Error saving input payload: {str(e)}")
        return None

import json
def save_output_payload(request_id, payload, status="success", error_message=None):
    try:
        obj, created = RequestPayload.objects.update_or_create(
            request_id=request_id,
            defaults={
                "output_payload": json.loads(json.dumps(payload)),
                "status": status,
                "error_message": error_message
            }
        )
        print(f"Output Saved | {request_id} | {status}")
        return obj
    except Exception as e:
        print(f"Error saving output payload: {str(e)}")
        return None

def update_status(request_id, status, error_message=None):
    try:
        RequestPayload.objects.filter(request_id=request_id).update(
            status=status,
            error_message=error_message
        )
        print(f"Status Updated | {request_id} | {status}")
    except Exception as e:
        print("Error updating status:", str(e))


def get_payload(request_id):
    try:
        obj = RequestPayload.objects.get(request_id=request_id)

        return {
            "request_id": obj.request_id,
            "process_name": obj.process_name,
            "input_payload": obj.input_payload,
            "output_payload": obj.output_payload,
            "status": obj.status,
            "error_message": obj.error_message
        }

    except RequestPayload.DoesNotExist:
        return None
    
from django.http import JsonResponse

def get_payload_by_request(request, request_id):
    data = get_payload(request_id)

    if not data:
        return JsonResponse(
            {"error": "Payload not found"},
            status=404
        )

    return JsonResponse({
        "request_id": data["request_id"],
        "process_name": data["process_name"],

        # 🔹 Input payload (shown immediately)
        "input_payload": data["input_payload"],

        # 🔹 Output payload (only if available)
        "output_payload": data["output_payload"],

        # 🔹 Status control
        "status": data["status"],
        "error_message": data["error_message"]
    })

# -------------------- IMPORTS --------------------
import uuid

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# 👉 Make sure these are already implemented in your project

# -------------------- SERVICE FUNCTION --------------------
def delete_user_from_azure(user_id):
    """
    Delete the Azure AD user via Microsoft Graph.
    This helper is only concerned with executing the delete call and returning a simple payload.
    """

    normalized_user_id = (user_id or "").strip()
    if not normalized_user_id:
        raise RuntimeError("user_id is required to delete an Azure AD user.")

    token = get_graph_token()
    if not token:
        raise RuntimeError("Failed to acquire Microsoft Graph token for deleting user.")

    endpoint = f"/users/{normalized_user_id}"
    _, error = graph_request("DELETE", endpoint, token)
    if error:
        raise RuntimeError(f"Microsoft Graph delete user failed: {error}")

    return {"message": f"User {normalized_user_id} deleted successfully"}


# -------------------- API VIEW --------------------
@method_decorator(csrf_exempt, name='dispatch')
class DeleteUserAPIView(APIView):
    permission_classes = [AllowAny]

    def delete(self, request, user_id):
        request_id = str(uuid.uuid4())

        try:
            # ✅ STEP 1: Save INPUT payload
            save_input_payload(
                request_id=request_id,
                process_name="Delete User",
                payload={"user_id": user_id}
            )

            create_log(request_id, "info", f"Delete request started for user {user_id}")

            # ✅ STEP 2: Perform delete
            result = delete_user_from_azure(user_id)

            # ✅ STEP 3: Save OUTPUT payload
            save_output_payload(
                request_id=request_id,
                payload=result,
                status="success"
            )

            create_log(request_id, "success", f"User {user_id} deleted successfully")

            # ✅ STEP 4: Return response (for Dashboard)
            return Response({
                "status": "success",
                "request_id": request_id,
                **result
            })

        except Exception as e:
            # ❌ Save failure payload
            save_output_payload(
                request_id=request_id,
                payload={},
                status="failed",
                error_message=str(e)
            )

            create_log(request_id, "failed", str(e))

            return Response({
                "status": "error",
                "request_id": request_id,
                "message": str(e)
            }, status=500)
