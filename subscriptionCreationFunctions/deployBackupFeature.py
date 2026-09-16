import json
import logging
import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Dict, List, Optional, Tuple

import azure.functions as func
from azure.core.exceptions import AzureError, HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource.resources import ResourceManagementClient

# App
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Constants
PROVIDERS = [
    "Microsoft.RecoveryServices",
    "Microsoft.DataProtection",
    "Microsoft.Insights",
    "Microsoft.OperationalInsights",
    "Microsoft.Storage",
    "Microsoft.DBforMySQL",
    "Microsoft.DBforPostgreSQL",
    "Microsoft.AlertsManagement",
]

API_VERSIONS = {
    "recovery_vault": "2022-04-01",
    "backup_storage_config": "2022-04-01",
    "backup_vault": "2023-01-01",
    "rsv_policy": "2023-01-01",
    # Use the stable API version that matches known working Blob policy payloads.
    "backup_policy": os.environ.get("BACKUP_POLICY_API_VERSION", "2023-05-01"),
    "diagnostic_settings": "2021-05-01-preview",
    "action_group": "2019-06-01",
    "alert_rule": "2021-08-08",
}

REDUNDANCY_MAP = {
    "locally": "LocallyRedundant",
    "zonally": "ZoneRedundant",
}

# Four backup windows used across all policy tiers
POLICY_TIMES = [
    ("8am", "08:00"),
    ("2pm", "14:00"),
    ("8pm", "20:00"),
    ("2am", "02:00"),
]

# RSV schedule timestamp anchor — day-of-week is irrelevant here because RSV
# policies set daysOfWeek explicitly via the weekdays parameter.
SCHEDULE_ANCHOR_DATE = "2024-01-01"

# Data Protection (Backup Vault) policies use the anchor date as the recurrence
# start, so the day of week in this date directly controls when P1W policies fire.
# 2024-01-05 is a Friday, aligning with WEEKLY_DAY below.
DP_SCHEDULE_ANCHOR_DATE = "2024-01-05"

# Bound the number of concurrent ARM policy creates to avoid throttling while
# still keeping the pipeline busy.
POLICY_MAX_CONCURRENCY = 8

# Shared retention criteria constants. RSV weekly/monthly/yearly schedules use
# Friday, while daily policies do not set a weekday filter.
WEEKLY_DAY = ["Friday"]
FIRST_WEEK = ["First"]
JANUARY = ["January"]

BLOB_DATASOURCE = "Microsoft.Storage/storageAccounts/blobServices"
MYSQL_FLEX_DATASOURCE = "Microsoft.DBforMySQL/flexibleServers"
PGSQL_FLEX_DATASOURCE = "Microsoft.DBforPostgreSQL/flexibleServers"
DATAPROTECTION_WEEKLY_DATASOURCES = {
    MYSQL_FLEX_DATASOURCE,
    PGSQL_FLEX_DATASOURCE,
}

# Log categories forwarded to Log Analytics
RSV_LOG_CATEGORIES = [
    "CoreAzureBackup",
    "AddonAzureBackupJobs",
    "AddonAzureBackupPolicy",
    "AddonAzureBackupStorage",
    "AddonAzureBackupProtectedInstance",
    "AzureBackupOperations",
]
BV_LOG_CATEGORIES = [
    "CoreAzureBackup",
    "AddonAzureBackupJobs",
    "AddonAzureBackupPolicy",
    "AddonAzureBackupProtectedInstance",
]


# Naming helpers


def get_clean_app_id(appid: str) -> str:
    """Strip non-alphanumeric characters and lowercase the app ID."""
    return re.sub(r"[^a-z0-9]", "", appid.lower())


def get_env(environment: str) -> str:
    """Normalise any environment variant to 'prod' or 'np'."""
    mapping = {
        "production": "prod",
        "prod": "prod",
        "non-production": "np",
        "nonproduction": "np",
        "non-prod": "np",
        "nonprod": "np",
        "np": "np",
        "development": "np",
        "dev": "np",
        "testing": "np",
        "test": "np",
        "staging": "np",
        "stage": "np",
        "poc": "np",
    }
    return mapping.get(environment.strip().lower(), "np")


def build_name_suffix(appid: str, environment: str, region: str) -> str:
    return f"{get_clean_app_id(appid)}-{get_env(environment)}-{region}".lower()


# ARM resource ID helpers


def resource_id(
    subscription_id: str, rg: str, provider: str, rtype: str, name: str
) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{rg}/providers/{provider}/{rtype}/{name}"


def child_resource_id(parent_id: str, provider: str, rtype: str, name: str) -> str:
    return f"{parent_id}/providers/{provider}/{rtype}/{name}"


# HTTP helpers


def json_response(payload: Dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, indent=2),
        status_code=status_code,
        mimetype="application/json",
    )


def parse_body(
    req: func.HttpRequest,
) -> Tuple[Optional[Dict], Optional[func.HttpResponse]]:
    try:
        return req.get_json(), None
    except ValueError:
        return None, json_response({"error": "Invalid JSON body"}, 400)


def validate_body(body: Dict) -> Tuple[Optional[Dict], Optional[func.HttpResponse]]:
    required = [
        "subscription_id",
        "appid",
        "environment",
        "region",
        "redundancy",
        "support_email",
    ]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return None, json_response(
            {"error": f"Missing required fields: {', '.join(missing)}"}, 400
        )

    redundancy_key = str(body["redundancy"]).strip().lower()
    if redundancy_key not in REDUNDANCY_MAP:
        return None, json_response(
            {"error": "Invalid redundancy. Use 'locally' or 'zonally'."}, 400
        )

    return {
        "subscription_id": str(body["subscription_id"]).strip(),
        "appid": str(body["appid"]).strip(),
        "environment": str(body["environment"]).strip(),
        "region": str(body["region"]).strip(),
        "redundancy": REDUNDANCY_MAP[redundancy_key],
        "support_email": str(body.get("support_email") or "").strip(),
        # When True, delete unused Data Protection policies before recreating them.
        # Azure rejects deletion with 409 Conflict if the policy has active associations,
        # so we rely on the API to enforce the safety check instead of a separate list call.
        "force_recreate_dp_policies": bool(
            body.get("force_recreate_dp_policies", False)
        ),
    }, None


# ARM operations


def ensure_providers(client: ResourceManagementClient) -> List[str]:
    registered = []
    for ns in PROVIDERS:
        try:
            p = client.providers.get(ns)
            if p.registration_state != "Registered":
                client.providers.register(ns)
            registered.append(ns)
        except HttpResponseError as exc:
            logging.warning("Provider registration failed for %s: %s", ns, exc)
    return registered


def put_resource(
    client: ResourceManagementClient,
    rid: str,
    api_version: str,
    body: Dict,
    timeout: int = 300,
) -> Dict:
    poller = client.resources.begin_create_or_update_by_id(
        rid, api_version, body, polling_interval=10
    )
    result = poller.result(timeout=timeout)
    if result is None:
        raise RuntimeError(f"LRO returned no result for {rid}")
    return result.as_dict()


def put_resource_with_retry(
    client: ResourceManagementClient,
    rid: str,
    api_version: str,
    body: Dict,
    timeout: int = 300,
    retries: int = 5,
    retry_delay: int = 30,
) -> Dict:
    """put_resource but retries on ResourceNotYetSynced.

    The RSV storage config endpoint becomes available only after the vault
    finishes its internal sync — which can take up to ~2 minutes after the
    vault LRO reports completion.
    """
    for attempt in range(1, retries + 1):
        try:
            return put_resource(client, rid, api_version, body, timeout)
        except HttpResponseError as exc:
            if "ResourceNotYetSynced" in str(exc) and attempt < retries:
                logging.warning(
                    "Resource not yet synced for %s — retrying in %ds (attempt %d/%d)",
                    rid,
                    retry_delay,
                    attempt,
                    retries,
                )
                time.sleep(retry_delay)
            else:
                raise
    raise RuntimeError(f"Exhausted retries for {rid}")


def start_put_resource(
    client: ResourceManagementClient,
    rid: str,
    api_version: str,
    body: Dict,
):
    """Fire-and-forget variant — returns a poller for later collection."""
    return client.resources.begin_create_or_update_by_id(
        rid, api_version, body, polling_interval=10
    )


def wait_for_poller(
    rid: str,
    poller: object,
    timeout: int = 180,
) -> Tuple[str, Optional[Dict]]:
    result = poller.result(timeout=timeout)
    return rid, None if result is None else result.as_dict()


def resource_exists_by_id(
    client: ResourceManagementClient,
    rid: str,
    api_version: str,
) -> bool:
    try:
        client.resources.get_by_id(rid, api_version)
        return True
    except HttpResponseError:
        return False


def delete_dataprotection_policy_if_unused(
    client: ResourceManagementClient,
    rid: str,
    api_version: str,
) -> bool:
    """Attempt to delete a Data Protection backup policy.

    Azure returns 409 Conflict when the policy still has active backup instance
    associations, so we rely on the API to enforce that safety check rather than
    making a separate list-instances call.

    Returns:
        True  — policy was deleted successfully.
        False — deletion was refused (policy in use) or failed for another reason.
    """
    try:
        poller = client.resources.begin_delete_by_id(rid, api_version)
        poller.result(timeout=120)
        logging.info("Deleted existing Data Protection policy for recreation: %s", rid)
        return True
    except HttpResponseError as exc:
        logging.warning(
            "Could not delete policy %s (likely has active associations): %s", rid, exc
        )
        return False


def submit_policy_request(
    client: ResourceManagementClient,
    executor: ThreadPoolExecutor,
    request: Tuple[str, str, Dict],
    timeout: int,
) -> Future:
    rid, api_version, body = request
    poller = start_put_resource(client, rid, api_version, body)
    return executor.submit(wait_for_poller, rid, poller, timeout)


def fill_active_policy_queue(
    client: ResourceManagementClient,
    executor: ThreadPoolExecutor,
    request_iter,
    active: Dict[Future, str],
    max_workers: int,
    timeout: int,
) -> int:
    failures = 0

    while len(active) < max_workers:
        try:
            request = next(request_iter)
        except StopIteration:
            break

        rid = request[0]
        try:
            active[submit_policy_request(client, executor, request, timeout)] = rid
        except AzureError as exc:
            logging.error("Policy ARM submission error for %s: %s", rid, exc)
            failures += 1
        except TimeoutError as exc:
            logging.error("Policy submission timed out for %s: %s", rid, exc)
            failures += 1

    return failures


def handle_completed_policy_future(
    future: Future,
    active: Dict[Future, str],
) -> Tuple[int, int]:
    rid = active.pop(future)

    try:
        completed_rid, result = future.result()
        if result:
            logging.info("Policy created: %s", completed_rid)
            return 1, 0

        logging.error("Policy create returned no result for %s", completed_rid)
        return 0, 1
    except AzureError as exc:
        logging.error("Policy ARM error for %s: %s", rid, exc)
        return 0, 1
    except TimeoutError as exc:
        logging.error("Policy timed out for %s: %s", rid, exc)
        return 0, 1
    except RuntimeError as exc:
        logging.error("Policy runtime error for %s: %s", rid, exc)
        return 0, 1


def execute_policy_requests(
    client: ResourceManagementClient,
    requests: List[Tuple[str, str, Dict]],
    max_concurrency: int = POLICY_MAX_CONCURRENCY,
    timeout: int = 180,
) -> Tuple[int, int]:
    """Run policy creates with bounded concurrency.

    ARM handles each create asynchronously. This keeps a fixed number of policy
    operations in flight and immediately schedules the next one when one
    completes, without sleeping between batches.
    """
    if not requests:
        return 0, 0

    success, failure = 0, 0
    max_workers = max(1, min(max_concurrency, len(requests)))
    request_iter = iter(requests)
    active: Dict[Future, str] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        failure += fill_active_policy_queue(
            client,
            executor,
            request_iter,
            active,
            max_workers,
            timeout,
        )

        while active:
            completed, _ = wait(active.keys(), return_when=FIRST_COMPLETED)

            for future in completed:
                completed_success, completed_failure = handle_completed_policy_future(
                    future, active
                )
                success += completed_success
                failure += completed_failure

            failure += fill_active_policy_queue(
                client,
                executor,
                request_iter,
                active,
                max_workers,
                timeout,
            )

    return success, failure


# ARM body builders


def build_recovery_vault_body(region: str) -> Dict:
    return {
        "location": region,
        "identity": {"type": "SystemAssigned"},
        "sku": {"name": "Standard"},
        "properties": {
            "securitySettings": {
                "softDeleteSettings": {
                    "softDeleteState": "Enabled",
                    "softDeleteRetentionPeriodInDays": 14,
                }
            },
        },
    }


def build_storage_config_body(redundancy: str) -> Dict:
    """Storage redundancy body for Recovery Services Vault backup storage config."""
    # Storage redundancy cannot be set on the vault PUT — requires a separate
    # child resource call after the vault has finished syncing internally.
    # crossRegionRestoreFlag must be False for ZoneRedundant (safe for LocallyRedundant too).
    return {
        "properties": {
            "storageModelType": redundancy,
            "crossRegionRestoreFlag": False,
        }
    }


def build_backup_vault_body(region: str, redundancy: str) -> Dict:
    """"""

    return {
        "location": region,
        "identity": {"type": "SystemAssigned"},
        "properties": {
            "storageSettings": [{"datastoreType": "VaultStore", "type": redundancy}]
        },
    }


def build_diagnostic_settings_body(
    workspace_id: str,
    log_categories: List[str],
    metric_category: str,
) -> Dict:
    return {
        "properties": {
            "logAnalyticsDestinationType": "Dedicated",
            "workspaceId": workspace_id,
            "logs": [{"category": c, "enabled": True} for c in log_categories],
            "metrics": [
                {
                    "category": metric_category,
                    "enabled": False,
                    "retentionPolicy": {"enabled": False, "days": 0},
                }
            ],
        }
    }


def build_action_group_body(support_email: str) -> Dict:
    return {
        "location": "global",
        "properties": {
            "groupShortName": "backupag",
            "enabled": True,
            "emailReceivers": [
                {"name": "SupportEmailAddress", "emailAddress": support_email}
            ],
        },
    }


def build_alert_rule_body(action_group_id: str, scopes: List[str]) -> Dict:
    return {
        "location": "global",
        "properties": {
            "scopes": scopes,
            "enabled": True,
            "description": "Routes Azure Backup alerts to the designated action group.",
            "conditions": [
                {
                    "field": "severity",
                    "operator": "Equals",
                    "values": ["Sev0", "Sev1", "Sev2"],
                }
            ],
            "actions": [
                {
                    "actionType": "AddActionGroups",
                    "actionGroupIds": [action_group_id],
                }
            ],
        },
    }


# Policy body builders


def schedule_time(hhmm: str) -> str:
    return f"{SCHEDULE_ANCHOR_DATE}T{hhmm}:00Z"


def build_rsv_policy_body(
    management_type: str,
    object_type: str,
    hhmm: str,
    daily_count: int,
    weekly_count: Optional[int] = None,
    monthly_count: Optional[int] = None,
    yearly_count: Optional[int] = None,
    weekdays: Optional[List[str]] = None,
    instant_restore_days: Optional[int] = None,
) -> Dict:
    run_time = schedule_time(hhmm)

    retention: Dict = {
        "retentionPolicyType": "LongTermRetentionPolicy",
        "dailySchedule": {
            "retentionTimes": [run_time],
            "retentionDuration": {"count": daily_count, "durationType": "Days"},
        },
    }
    if weekly_count and weekdays:
        retention["weeklySchedule"] = {
            "daysOfTheWeek": weekdays,
            "retentionTimes": [run_time],
            "retentionDuration": {"count": weekly_count, "durationType": "Weeks"},
        }
    if monthly_count and weekdays:
        retention["monthlySchedule"] = {
            "retentionScheduleFormatType": "Weekly",
            "retentionScheduleWeekly": {
                "daysOfTheWeek": weekdays,
                "weeksOfTheMonth": FIRST_WEEK,
            },
            "retentionTimes": [run_time],
            "retentionDuration": {"count": monthly_count, "durationType": "Months"},
        }
    if yearly_count and weekdays:
        retention["yearlySchedule"] = {
            "retentionScheduleFormatType": "Weekly",
            "monthsOfYear": JANUARY,
            "retentionScheduleWeekly": {
                "daysOfTheWeek": weekdays,
                "weeksOfTheMonth": FIRST_WEEK,
            },
            "retentionTimes": [run_time],
            "retentionDuration": {"count": yearly_count, "durationType": "Years"},
        }

    body: Dict = {
        "properties": {
            "objectType": object_type,
            "backupManagementType": management_type,
            "schedulePolicy": {
                "schedulePolicyType": "SimpleSchedulePolicy",
                "scheduleRunFrequency": "Daily",
                "scheduleRunTimes": [run_time],
            },
            "retentionPolicy": retention,
            "timeZone": "UTC",
        }
    }

    if management_type == "AzureStorage":
        body["properties"]["workLoadType"] = "AzureFileShare"

    if instant_restore_days is not None:
        body["properties"]["instantRpRetentionRangeInDays"] = instant_restore_days

    return body


def build_dataprotection_policy_body(
    datasource_type: str,
    schedule_interval: str,
    default_duration: str,
    retention_rules: Optional[List[Dict]] = None,
    backup_type: str = "Incremental",
    tier_tagging_criteria: Optional[List[Dict]] = None,
) -> Dict:
    retention_rules = retention_rules or []
    tier_tagging_criteria = tier_tagging_criteria or []
    trigger_time = schedule_interval.split("/")[1]

    interval_token = schedule_interval.split("/")[-1]
    frequency_map = {
        "PT24H": ("Daily", 1, "P1D"),
        "P1D": ("Daily", 1, "P1D"),
        "P7D": ("Weekly", 1, "P7D"),
        "P1W": ("Weekly", 1, "P1W"),
    }
    frequency_tuple = frequency_map.get(interval_token)
    normalized_interval = schedule_interval

    if frequency_tuple:
        schedule_frequency, schedule_interval_value, normalized_token = frequency_tuple
        if normalized_token != interval_token:
            normalized_interval = schedule_interval.replace(
                interval_token, normalized_token
            )
    else:
        schedule_frequency, schedule_interval_value = None, None

    # Default tagging criteria: no criteria field, matches all backups
    tagging_criteria = [
        {
            "isDefault": True,
            "tagInfo": {"tagName": "Default"},
            "taggingPriority": 99,
        }
    ]

    if datasource_type == BLOB_DATASOURCE:
        tagging_criteria[0]["criteria"] = [
            {
                "objectType": "ScheduleBasedBackupCriteria",
                "scheduleTimes": [trigger_time],
            }
        ]

    tagging_criteria.extend(tier_tagging_criteria)

    backup_rule = {
        "name": "BackupWeekly",
        "objectType": "AzureBackupRule",
        "backupParameters": {
            "objectType": "AzureBackupParams",
            "backupType": backup_type,
        },
        "trigger": {
            "objectType": "ScheduleBasedTriggerContext",
            "schedule": {
                "repeatingTimeIntervals": [normalized_interval],
                "timeZone": "UTC",
            },
            "taggingCriteria": tagging_criteria,
        },
        "dataStore": {
            "dataStoreType": "VaultStore",
            "objectType": "DataStoreInfoBase",
        },
    }

    if schedule_frequency and schedule_interval_value:
        backup_rule["trigger"]["schedule"].update(
            {"frequency": schedule_frequency, "interval": schedule_interval_value}
        )

    # Keep Blob policies vaulted-only so the portal shows a single vaulted backup section.
    default_rules = []
    # Vaulted backups: use default_duration in VaultStore
    default_rules.append(
        {
            "name": "Default",
            "objectType": "AzureRetentionRule",
            "isDefault": True,
            "lifecycles": [
                {
                    "deleteAfter": {
                        "objectType": "AbsoluteDeleteOption",
                        "duration": default_duration,
                    },
                    "sourceDataStore": {
                        "dataStoreType": "VaultStore",
                        "objectType": "DataStoreInfoBase",
                    },
                    "targetDataStoreCopySettings": [],
                }
            ],
        }
    )

    named_rules = []
    for rule in retention_rules:
        named_rule = {
            "name": rule["name"],
            "objectType": "AzureRetentionRule",
            "isDefault": False,
            "lifecycles": [
                {
                    "deleteAfter": {
                        "objectType": "AbsoluteDeleteOption",
                        "duration": rule["duration"],
                    },
                    "sourceDataStore": {
                        "dataStoreType": "VaultStore",
                        "objectType": "DataStoreInfoBase",
                    },
                    "targetDataStoreCopySettings": [],
                }
            ],
        }
        criteria_fields = {
            k: v
            for k, v in {
                "objectType": "ScheduleBasedBackupCriteria",
                "daysOfTheWeek": rule.get("days_of_week"),
                "weeksOfTheMonth": rule.get("weeks_of_month"),
                "monthsOfYear": rule.get("months_of_year"),
            }.items()
            if v is not None
        }
        if len(criteria_fields) > 1:
            named_rule["criteria"] = [criteria_fields]
        named_rules.append(named_rule)

    return {
        "properties": {
            "datasourceTypes": [datasource_type],
            "objectType": "BackupPolicy",
            "policyRules": [backup_rule] + default_rules + named_rules,
        }
    }


# Policy helpers


def _rsv_vm(
    hhmm: str,
    daily_only: bool = False,
    monthly_retention: bool = False,
    yearly_retention: bool = False,
) -> Dict:
    return build_rsv_policy_body(
        "AzureIaasVM",
        "AzureIaasVMProtectionPolicy",
        hhmm,
        daily_count=15,
        weekly_count=None if daily_only else 5,
        monthly_count=12 if monthly_retention else None,
        yearly_count=4 if yearly_retention else None,
        weekdays=None if daily_only else WEEKLY_DAY,
        instant_restore_days=5,
    )


def _rsv_file(
    hhmm: str,
    daily_only: bool = False,
    monthly_retention: bool = False,
    yearly_retention: bool = False,
) -> Dict:
    return build_rsv_policy_body(
        "AzureStorage",
        "AzureFileShareProtectionPolicy",
        hhmm,
        daily_count=15,
        weekly_count=None if daily_only else 5,
        monthly_count=12 if monthly_retention else None,
        yearly_count=4 if yearly_retention else None,
        weekdays=None if daily_only else WEEKLY_DAY,
    )


def get_dataprotection_interval_token(datasource_type: str) -> str:
    if datasource_type in DATAPROTECTION_WEEKLY_DATASOURCES:
        return "P1W"
    return "P1D"


# Policy creation — all LROs launched in parallel then collected


def create_backup_policies(
    client: ResourceManagementClient,
    subscription_id: str,
    rg_name: str,
    rsv_name: str,
    bv_name: str,
    force_recreate_dp_policies: bool = False,
) -> Tuple[int, int]:
    rsv_base = (
        f"/subscriptions/{subscription_id}/resourceGroups/{rg_name}"
        f"/providers/Microsoft.RecoveryServices/vaults/{rsv_name}/backupPolicies"
    )
    bv_base = (
        f"/subscriptions/{subscription_id}/resourceGroups/{rg_name}"
        f"/providers/Microsoft.DataProtection/backupVaults/{bv_name}/backupPolicies"
    )

    policy_requests: List[Tuple[str, str, Dict]] = []

    for label, hhmm in POLICY_TIMES:
        interval_prefix = f"R/{DP_SCHEDULE_ANCHOR_DATE}T{hhmm}:00Z"

        # --- RSV: VM policies ---
        rsv_vm_policies = {
            f"stla-vm-daily-{label}": _rsv_vm(hhmm, daily_only=True),
            f"stla-vm-weekly-{label}": _rsv_vm(hhmm),
            f"stla-vm-monthly-{label}": _rsv_vm(hhmm, monthly_retention=True),
            f"stla-vm-yearly-{label}": _rsv_vm(
                hhmm,
                monthly_retention=True,
                yearly_retention=True,
            ),
        }

        # --- RSV: File share policies ---
        rsv_file_policies = {
            f"stla-file-daily-{label}": _rsv_file(hhmm, daily_only=True),
            f"stla-file-weekly-{label}": _rsv_file(hhmm),
            f"stla-file-monthly-{label}": _rsv_file(hhmm, monthly_retention=True),
            f"stla-file-yearly-{label}": _rsv_file(
                hhmm,
                monthly_retention=True,
                yearly_retention=True,
            ),
        }

        for name, body in {**rsv_vm_policies, **rsv_file_policies}.items():
            rid = f"{rsv_base}/{name}"
            policy_requests.append((rid, API_VERSIONS["rsv_policy"], body))

        # --- Backup Vault: Blob (P1D daily, tagging criteria routing) ---
        blob_tier_configs = [
            (
                "weekly",
                [
                    {
                        "name": "Weekly",
                        "duration": "P5W",
                    }
                ],
                [
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Weekly"},
                        "taggingPriority": 20,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfWeek"],
                            }
                        ],
                    }
                ],
            ),
            (
                "monthly",
                [
                    {
                        "name": "Weekly",
                        "duration": "P5W",
                    },
                    {
                        "name": "Monthly",
                        "duration": "P12M",
                    },
                ],
                [
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Weekly"},
                        "taggingPriority": 20,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfWeek"],
                            }
                        ],
                    },
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Monthly"},
                        "taggingPriority": 15,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfMonth"],
                            }
                        ],
                    },
                ],
            ),
            (
                "yearly",
                [
                    {
                        "name": "Weekly",
                        "duration": "P5W",
                    },
                    {
                        "name": "Monthly",
                        "duration": "P12M",
                    },
                    {
                        "name": "Yearly",
                        "duration": "P4Y",
                    },
                ],
                [
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Weekly"},
                        "taggingPriority": 20,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfWeek"],
                            }
                        ],
                    },
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Monthly"},
                        "taggingPriority": 15,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfMonth"],
                            }
                        ],
                    },
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Yearly"},
                        "taggingPriority": 10,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfYear"],
                            }
                        ],
                    },
                ],
            ),
        ]

        blob_interval = f"{interval_prefix}/P1D"
        for tier, blob_retention_rules, blob_tier_tagging_criteria in blob_tier_configs:
            rid = f"{bv_base}/stla-blob-{tier}-{label}"
            if resource_exists_by_id(client, rid, API_VERSIONS["backup_policy"]):
                if force_recreate_dp_policies:
                    if not delete_dataprotection_policy_if_unused(
                        client, rid, API_VERSIONS["backup_policy"]
                    ):
                        continue  # in use or deletion failed — leave as-is
                    # deleted — fall through to create below
                else:
                    logging.info(
                        "Skipping existing backup policy (create-only mode): %s", rid
                    )
                    continue
            body = build_dataprotection_policy_body(
                BLOB_DATASOURCE,
                blob_interval,
                "P15D",
                blob_retention_rules,
                "Discrete",
                blob_tier_tagging_criteria,
            )
            payload_str = json.dumps(body, indent=2)
            logging.info("Backup policy payload for %s: %s", rid, payload_str)
            logging.info("Queued backup policy create for %s", rid)
            policy_requests.append((rid, API_VERSIONS["backup_policy"], body))

        # --- Backup Vault: MySQL, PostgreSQL (P1W weekly, tagging criteria) ---
        bv_specs = [
            ("stla-mysql", MYSQL_FLEX_DATASOURCE, "P7D", "Full"),
            ("stla-pgsql", PGSQL_FLEX_DATASOURCE, "P15D", "Full"),
        ]
        tier_configs = [
            (
                "weekly",
                [
                    {
                        "name": "Weekly",
                        "duration": "P5W",
                    }
                ],
                [
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Weekly"},
                        "taggingPriority": 20,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfWeek"],
                            }
                        ],
                    }
                ],
            ),
            (
                "monthly",
                [
                    {
                        "name": "Weekly",
                        "duration": "P5W",
                    },
                    {
                        "name": "Monthly",
                        "duration": "P12M",
                    },
                ],
                [
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Weekly"},
                        "taggingPriority": 20,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfWeek"],
                            }
                        ],
                    },
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Monthly"},
                        "taggingPriority": 15,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfMonth"],
                            }
                        ],
                    },
                ],
            ),
            (
                "yearly",
                [
                    {
                        "name": "Weekly",
                        "duration": "P5W",
                    },
                    {
                        "name": "Monthly",
                        "duration": "P12M",
                    },
                    {
                        "name": "Yearly",
                        "duration": "P4Y",
                    },
                ],
                [
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Weekly"},
                        "taggingPriority": 20,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfWeek"],
                            }
                        ],
                    },
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Monthly"},
                        "taggingPriority": 15,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfMonth"],
                            }
                        ],
                    },
                    {
                        "isDefault": False,
                        "tagInfo": {"tagName": "Yearly"},
                        "taggingPriority": 10,
                        "criteria": [
                            {
                                "objectType": "ScheduleBasedBackupCriteria",
                                "absoluteCriteria": ["FirstOfYear"],
                            }
                        ],
                    },
                ],
            ),
        ]

        for prefix, datasource, default_dur, btype in bv_specs:
            for (
                tier,
                mysql_pgsql_retention_rules,
                tier_tagging_criteria,
            ) in tier_configs:
                interval_token = get_dataprotection_interval_token(datasource)
                effective_interval = f"{interval_prefix}/{interval_token}"
                rid = f"{bv_base}/{prefix}-{tier}-{label}"

                if resource_exists_by_id(client, rid, API_VERSIONS["backup_policy"]):
                    if force_recreate_dp_policies:
                        if not delete_dataprotection_policy_if_unused(
                            client, rid, API_VERSIONS["backup_policy"]
                        ):
                            continue  # in use or deletion failed — leave as-is
                        # deleted — fall through to create below
                    else:
                        logging.info(
                            "Skipping existing backup policy (create-only mode): %s",
                            rid,
                        )
                        continue

                body = build_dataprotection_policy_body(
                    datasource,
                    effective_interval,
                    default_dur,
                    mysql_pgsql_retention_rules,
                    btype,
                    tier_tagging_criteria,
                )
                payload_str = json.dumps(body, indent=2)
                logging.info("Backup policy payload for %s: %s", rid, payload_str)
                logging.info(
                    "Queued backup policy create for %s",
                    rid,
                )
                policy_requests.append((rid, API_VERSIONS["backup_policy"], body))

    logging.info(
        "Submitting %d backup policy creates with max concurrency %d using backup policy API version %s",
        len(policy_requests),
        POLICY_MAX_CONCURRENCY,
        API_VERSIONS["backup_policy"],
    )
    return execute_policy_requests(client, policy_requests)


# Main function
def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Main entry point for the Azure Function. Validates input, ensures required
    resource providers are registered, creates the resource group, Recovery Services Vault,
    Backup Vault, diagnostic settings, action group, alert processing rule, and backup policies.

    payload accepted
    {
        "subscription_id": "a4766423-b97a-4b03-8f4b-901225f28ca6",
        "appid": "mgmt/azure",
        "environment": "poc",
        "region": "northeurope",
        "redundancy": "zonally",
        "support_email": "backup-alerts@example.com"
    }

    """
    logging.info("Backup solution provisioning triggered.")

    body, err = parse_body(req)
    if err:
        return err

    data, err = validate_body(body)
    if err:
        return err

    subscription_id = data["subscription_id"]
    appid = data["appid"]
    environment = data["environment"]
    region = data["region"]
    redundancy = data["redundancy"]
    support_email = data["support_email"]
    force_recreate_dp_policies = data["force_recreate_dp_policies"]

    workspace_id = os.environ.get("LOG_ANALYTICS_WORKSPACE_ID", "").strip() or None
    if not workspace_id:
        return json_response(
            {
                "status": "error",
                "message": "LOG_ANALYTICS_WORKSPACE_ID environment variable is required.",
                "details": {
                    "hint": "Please set up a Log Analytics workspace and provide its ID via the LOG_ANALYTICS_WORKSPACE_ID environment variable.",
                },
            },
            400,
        )

    # Resource names
    suffix = build_name_suffix(appid, environment, region)
    clean_appid = get_clean_app_id(appid)
    env_short = get_env(environment)
    rg_name = f"rg-{clean_appid}-{env_short}-backupservices-{region}"
    rsv_name = f"rsv-{suffix}"
    bv_name = f"bv-{suffix}"
    ag_name = f"ag-{clean_appid}-{env_short}-backup"
    alert_rule_name = f"apr-{clean_appid}-{env_short}-backup"

    # ensure that managed identity has contributor access on the tenant (all subscriptions)
    mi_clientid = os.environ.get("ManagedIdentityClientID")
    if mi_clientid:
        credential = DefaultAzureCredential(managed_identity_client_id=mi_clientid)
    else:
        credential = DefaultAzureCredential()

    client = ResourceManagementClient(credential, subscription_id)

    try:
        # 1. Register providers and create resource group
        registered = ensure_providers(client)
        client.resource_groups.create_or_update(rg_name, {"location": region})

        # 2. Create Recovery Services Vault
        rsv_id = resource_id(
            subscription_id, rg_name, "Microsoft.RecoveryServices", "vaults", rsv_name
        )
        rsv = put_resource(
            client,
            rsv_id,
            API_VERSIONS["recovery_vault"],
            build_recovery_vault_body(region),
        )

        # 3. Set RSV storage redundancy via child resource
        #    Must be done after vault creation. Azure needs time to sync internally
        #    before this endpoint becomes writable — hence the retry logic.
        storage_cfg_id = f"{rsv_id}/backupstorageconfig/vaultstorageconfig"
        put_resource_with_retry(
            client,
            storage_cfg_id,
            API_VERSIONS["backup_storage_config"],
            build_storage_config_body(redundancy),
        )

        # 4. Create Backup Vault
        bv_id = resource_id(
            subscription_id,
            rg_name,
            "Microsoft.DataProtection",
            "backupVaults",
            bv_name,
        )
        bv = put_resource(
            client,
            bv_id,
            API_VERSIONS["backup_vault"],
            build_backup_vault_body(region, redundancy),
        )

        # 5. Configure diagnostic settings for both vaults
        rsv_diag_id = child_resource_id(
            rsv_id, "Microsoft.Insights", "diagnosticSettings", f"logs-{rsv_name}"
        )
        bv_diag_id = child_resource_id(
            bv_id, "Microsoft.Insights", "diagnosticSettings", f"logs-{bv_name}"
        )
        put_resource(
            client,
            rsv_diag_id,
            API_VERSIONS["diagnostic_settings"],
            build_diagnostic_settings_body(
                workspace_id, RSV_LOG_CATEGORIES, "AllMetrics"
            ),
        )
        put_resource(
            client,
            bv_diag_id,
            API_VERSIONS["diagnostic_settings"],
            build_diagnostic_settings_body(workspace_id, BV_LOG_CATEGORIES, "Health"),
        )

        # 6. Create all backup policies (launched in parallel)
        policy_success, policy_failures = create_backup_policies(
            client,
            subscription_id,
            rg_name,
            rsv_name,
            bv_name,
            force_recreate_dp_policies=force_recreate_dp_policies,
        )

        # 7. Create action group and alert processing rule
        ag_id = resource_id(
            subscription_id, rg_name, "Microsoft.Insights", "actionGroups", ag_name
        )
        alert_rule_id = resource_id(
            subscription_id,
            rg_name,
            "Microsoft.AlertsManagement",
            "actionRules",
            alert_rule_name,
        )
        put_resource(
            client,
            ag_id,
            API_VERSIONS["action_group"],
            build_action_group_body(support_email),
        )
        put_resource(
            client,
            alert_rule_id,
            API_VERSIONS["alert_rule"],
            build_alert_rule_body(ag_id, [rsv_id, bv_id]),
        )

        response_payload = {
            "status": "success" if policy_failures == 0 else "error",
            "message": (
                "Backup infrastructure provisioned successfully."
                if policy_failures == 0
                else "Backup infrastructure provisioned with policy creation failures."
            ),
            "details": {
                "resources": {
                    "resource_group": rg_name,
                    "recovery_services_vault": rsv.get("id"),
                    "backup_vault": bv.get("id"),
                },
                "providers": registered,
                "policy_count": policy_success,
                "policy_failures": policy_failures,
            },
        }

        return json_response(response_payload, 200 if policy_failures == 0 else 500)

    except HttpResponseError as exc:
        logging.error("Azure API error: %s", exc)
        return json_response(
            {
                "status": "error",
                "message": "Error during backup infrastructure provisioning: {}".format(
                    str(exc)
                ),
            },
            500,
        )
    except Exception as exc:
        logging.error("Unhandled error: %s", exc)
        return json_response(
            {
                "status": "error",
                "message": "Unhandled error during backup infrastructure provisioning: {}".format(
                    str(exc)
                ),
            },
            500,
        )
