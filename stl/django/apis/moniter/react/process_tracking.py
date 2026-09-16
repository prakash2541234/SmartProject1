import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import requests
from django.conf import settings

from stl.azure_client import get_credentials

logger = logging.getLogger(__name__)

PROCESS_TRIGGER_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="process-trigger",
)


def _setting(name: str, default: str = "") -> str:
    return (getattr(settings, name, default) or "").strip() or default


def get_storage_account_name() -> str:
    return _setting("PROCESS_STATUS_STORAGE_ACCOUNT", "autostorage0001")


def get_table_name() -> str:
    return _setting("PROCESS_STATUS_TABLE_NAME", "ProcessStatus")


def sanitize_table_name(name: str) -> str:
    import re

    value = (name or "").lower()
    value = re.sub(r"[^a-z0-9]", "", value)
    if not value or not value[0].isalpha():
        value = f"t{value}"
    if len(value) < 3:
        value = value.ljust(3, "0")
    return value[:63]


def get_dynamic_table_name(catalog_task_sysid: str) -> str:
    safe_name = sanitize_table_name(catalog_task_sysid)
    return f"logs{safe_name}"


def get_logic_app_trigger_url() -> str:
    url = _setting("LOGIC_APP_TRIGGER_URL")
    if not url:
        raise RuntimeError(
            "LOGIC_APP_TRIGGER_URL is not configured. Set it in Django settings or .env."
        )
    return url


def _storage_base_url() -> str:
    return f"https://{get_storage_account_name()}.table.core.windows.net"


def _table_url(table_name: str) -> str:
    return f"{_storage_base_url()}/{table_name}"


def _table_entity_url(table_name: str, ritm_number: str, catalog_task_sysid: str) -> str:
    partition_key = (ritm_number or "").replace("'", "''")
    row_key = (catalog_task_sysid or "").replace("'", "''")
    return f"{_table_url(table_name)}(PartitionKey='{partition_key}',RowKey='{row_key}')"


def _table_partition_url(table_name: str, ritm_number: str) -> str:
    partition_key = (ritm_number or "").replace("'", "''")
    return f"{_table_url(table_name)}?$filter=PartitionKey%20eq%20'{partition_key}'"


def _table_headers() -> dict[str, str]:
    credential = get_credentials()
    token = credential.get_token("https://storage.azure.com/.default")
    return {
        "Authorization": f"Bearer {token.token}",
        "Accept": "application/json;odata=nometadata",
        "Content-Type": "application/json;odata=nometadata",
        "DataServiceVersion": "3.0",
        "MaxDataServiceVersion": "3.0",
        "x-ms-version": "2020-12-06",
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_final_entity(entity: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(entity, dict):
        return None

    ritm_number = _normalize_text(entity.get("PartitionKey") or entity.get("u_ritm_number"))
    catalog_task_sysid = _normalize_text(
        entity.get("RowKey") or entity.get("u_catalog_task_sysid")
    )
    project_name = _normalize_text(entity.get("name") or entity.get("project_name"))
    status = _normalize_text(entity.get("status")).upper()
    u_state = _normalize_text(entity.get("u_state"))
    u_result = _normalize_text(entity.get("u_result"))
    updated_at = _normalize_text(entity.get("updated_at") or entity.get("Timestamp"))

    if not all([ritm_number, catalog_task_sysid, project_name, status, u_state, u_result, updated_at]):
        return None

    if status not in {"SUCCESS", "FAILED"}:
        return None

    return {
        "ritm_number": ritm_number,
        "catalog_task_sysid": catalog_task_sysid,
        "project_name": project_name,
        "status": status,
        "u_state": u_state,
        "u_result": u_result,
        "updated_at": updated_at,
    }


def _extract_status_record(entity: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(entity, dict):
        return None

    ritm_number = _normalize_text(entity.get("PartitionKey") or entity.get("u_ritm_number"))
    catalog_task_sysid = _normalize_text(
        entity.get("RowKey") or entity.get("u_catalog_task_sysid")
    )
    status = _normalize_text(entity.get("status")).upper()
    project_name = _normalize_text(entity.get("name") or entity.get("project_name"))
    u_state = _normalize_text(entity.get("u_state"))
    u_result = _normalize_text(entity.get("u_result"))
    updated_at = _normalize_text(entity.get("updated_at") or entity.get("Timestamp"))

    if not ritm_number or not catalog_task_sysid:
        return None

    return {
        "ritm_number": ritm_number,
        "catalog_task_sysid": catalog_task_sysid,
        "project_name": project_name,
        "status": status,
        "u_state": u_state,
        "u_result": u_result,
        "updated_at": updated_at,
    }


def _status_priority(status_value: str) -> int:
    normalized = (status_value or "").strip().upper()
    if normalized == "SUCCESS":
        return 3
    if normalized == "FAILED":
        return 2
    if normalized == "PROCESSING":
        return 1
    return 0


def _parse_entity_timestamp(entity: dict[str, Any]) -> datetime:
    raw = _normalize_text(entity.get("updated_at") or entity.get("Timestamp"))
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _fetch_partition_entities(table_name: str, ritm_number: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    next_url = _table_partition_url(table_name, ritm_number)
    pages = 0

    while next_url and pages < 50:
        response = requests.get(
            next_url,
            headers=_table_headers(),
            timeout=20,
        )

        if response.status_code == 404:
            return []

        if not response.ok:
            detail = (response.text or "").strip() or "Unable to query Azure Table Storage."
            raise RuntimeError(
                f"Process status lookup failed with HTTP {response.status_code}: {detail}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Azure Table Storage returned invalid JSON.") from exc

        if isinstance(payload, dict):
            page_items = payload.get("value") or []
            if isinstance(page_items, list):
                items.extend([item for item in page_items if isinstance(item, dict)])
            next_url = payload.get("odata.nextLink") or payload.get("@odata.nextLink") or ""
        elif isinstance(payload, list):
            items.extend([item for item in payload if isinstance(item, dict)])
            next_url = ""
        else:
            next_url = ""

        pages += 1

    return items


def trigger_logic_app_async(payload: dict[str, Any]) -> None:
    PROCESS_TRIGGER_EXECUTOR.submit(_trigger_logic_app, payload)


def _trigger_logic_app(payload: dict[str, Any]) -> None:
    try:
        response = requests.post(get_logic_app_trigger_url(), json=payload, timeout=30)
        if response.ok:
            return

        body = (response.text or "").strip()
        detail = body or "No response body returned."
        raise RuntimeError(
            f"Logic App trigger failed with HTTP {response.status_code}: {detail}"
        )
    except Exception as exc:
        logger.exception("Logic App trigger failed for %s", payload.get("ritm_number"))
        record_dispatch_failure(payload, str(exc))
        raise


def query_process_status(
    ritm_number: str,
    catalog_task_sysid: str = "",
) -> dict[str, Any] | None:
    ritm_number = _normalize_text(ritm_number)
    catalog_task_sysid = _normalize_text(catalog_task_sysid)
    if not ritm_number:
        return None

    table_name = get_dynamic_table_name(catalog_task_sysid) if catalog_task_sysid else get_table_name()

    if catalog_task_sysid:
        response = requests.get(
            _table_entity_url(table_name, ritm_number, catalog_task_sysid),
            headers=_table_headers(),
            timeout=20,
        )

        if response.ok:
            try:
                entity = response.json()
            except ValueError as exc:
                raise RuntimeError("Azure Table Storage returned invalid JSON.") from exc

            normalized = _normalize_final_entity(entity)
            if normalized:
                return normalized

    candidates = []
    for entity in _fetch_partition_entities(table_name, ritm_number):
        extracted = _extract_status_record(entity)
        if extracted:
            candidates.append(extracted)

    if not candidates:
        return None

    terminal_candidates = [item for item in candidates if item["status"] in {"SUCCESS", "FAILED"}]
    if not terminal_candidates:
        return None

    terminal_candidates.sort(
        key=lambda item: (
            _status_priority(item["status"]),
            _parse_entity_timestamp(item),
        ),
        reverse=True,
    )
    return terminal_candidates[0]


def query_process_details(
    ritm_number: str,
    catalog_task_sysid: str,
) -> dict[str, Any] | None:
    ritm_number = _normalize_text(ritm_number)
    catalog_task_sysid = _normalize_text(catalog_task_sysid)
    if not ritm_number or not catalog_task_sysid:
        return None

    table_name = get_dynamic_table_name(catalog_task_sysid)
    rows = _fetch_partition_entities(table_name, ritm_number)
    if not rows:
        return None

    rows.sort(
        key=lambda item: _normalize_text(item.get("TimestampUTC") or item.get("Timestamp")),
        reverse=False,
    )

    return {
        "table_name": table_name,
        "ritm_number": ritm_number,
        "catalog_task_sysid": catalog_task_sysid,
        "rows": rows,
    }


def record_dispatch_failure(
    payload: dict[str, Any],
    error_message: str,
) -> None:
    request_parameters = payload.get("request_parameters") or {}
    storage_parameters = payload.get("storage_parameters") or {}

    ritm_number = _normalize_text(
        payload.get("ritm_number") or request_parameters.get("ritm_number")
    )
    catalog_task_sysid = _normalize_text(
        payload.get("catalog_task_sysid") or request_parameters.get("catalog_task_sysid")
    )
    project_name = _normalize_text(
        payload.get("project_name") or storage_parameters.get("application_id")
    )

    if not ritm_number or not catalog_task_sysid:
        logger.warning("Skipping dispatch failure write because identifiers are missing.")
        return

    entity = {
        "PartitionKey": ritm_number,
        "RowKey": catalog_task_sysid,
        "u_ritm_number": ritm_number,
        "u_catalog_task_sysid": catalog_task_sysid,
        "u_state": "dispatch_failed",
        "u_result": _normalize_text(error_message) or "Logic App dispatch failed.",
        "name": project_name,
        "status": "FAILED",
        "updated_at": _utc_now(),
    }

    response = requests.post(
        f"{_storage_base_url()}/{get_table_name()}",
        headers={
            **_table_headers(),
            "Prefer": "return-no-content",
        },
        json=entity,
        timeout=20,
    )

    if response.status_code not in {200, 201, 204}:
        logger.error(
            "Failed to record dispatch failure in Azure Table Storage: %s %s",
            response.status_code,
            (response.text or "").strip(),
        )
