import azure.functions as func
import logging
import json
import os
from datetime import datetime, timezone, timedelta
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

COSMOS_DB_NAME = os.environ.get("COSMOS_SQL_DATABASE", "azglz")
SUBSCRIPTIONS_CONTAINER = os.environ.get("COSMOS_SQL_CONTAINER_SUBSCRIPTIONS", "subscriptions")
BACKUPCONFIG_CONTAINER = os.environ.get("COSMOS_SQL_CONTAINER_SUBBACKUPCONFIG", "subscription_backupconfig")
BACKUP_METRICS_CONTAINER = os.environ.get("COSMOS_SQL_CONTAINER_BACKUP_METRICS", "backup_metrics")
endpoint = os.environ['COSMOS_SQL_ENDPOINT']


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("backup_monitoring function triggered.")

    try:     

        try:
            mi_client_id = os.environ.get("ManagedIdentityClientID")
            if mi_client_id:
                credential = ManagedIdentityCredential(client_id=mi_client_id)
            else:
                credential = DefaultAzureCredential()
            # validate credential by requesting a token for Cosmos resource
            credential.get_token("https://cosmos.azure.com/.default")
        except Exception as e:
            logging.info("ManagedIdentityCredential not available or failed: %s. Falling back to DefaultAzureCredential.", e)
            credential = DefaultAzureCredential()
    
        client = CosmosClient(url=endpoint, credential=credential)
        database = client.get_database_client(COSMOS_DB_NAME)

        subs_container = database.get_container_client(SUBSCRIPTIONS_CONTAINER)
        config_container = database.get_container_client(BACKUPCONFIG_CONTAINER)
        metrics_container = database.get_container_client(BACKUP_METRICS_CONTAINER)


        # Total subscriptions
        total_subscriptions = list(
            subs_container.query_items(
                "SELECT VALUE COUNT(1) FROM c",
                enable_cross_partition_query=True,
            )
        )[0]

        # Subscriptions with custom backup (azglz_backup_available = 'false')
        subscription_with_custombackup = list(
            subs_container.query_items(
                "SELECT VALUE COUNT(1) FROM c WHERE c.azglz_backup_available = 'false'",
                enable_cross_partition_query=True,
            )
        )[0]

        # All subscription_backupconfig records
        config_items = list(
            config_container.query_items(
                "SELECT c.subscription_id, c.subscription_name, c.resources FROM c",
                enable_cross_partition_query=True,
            )
        )
        total_subscriptions_with_configuration = len(config_items)

        # subscriptions_with_configuration list
        subscriptions_with_configuration = [
            {
                "subscription_id": item.get("subscription_id"),
                "subscription_name": item.get("subscription_name"),
                "resources": item.get("resources", []),
            }
            for item in config_items
        ]

        # subscriptions_without_configuration list:
        # subscriptions where azglz_backup_available != 'false' AND no config record
        config_ids = {item.get("subscription_id") for item in config_items}
        no_custom_subs = list(
            subs_container.query_items(
                "SELECT c.subscription_id, c.subscription_name FROM c WHERE c.azglz_backup_available != 'false'",
                enable_cross_partition_query=True,
            )
        )
        subscriptions_without_configuration = [
            {
                "subscription_id": sub.get("subscription_id"),
                "subscription_name": sub.get("subscription_name"),
            }
            for sub in no_custom_subs
            if sub.get("subscription_id") not in config_ids
        ]
        total_subscriptions_without_configuration = (
            total_subscriptions
            - subscription_with_custombackup
            - total_subscriptions_with_configuration
        )

        now = datetime.now(timezone.utc)

        # Backup job errors from the last 30 days
        thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        error_items = list(
            metrics_container.query_items(
                "SELECT c.subscription_id, c.start_time, c.feature, c.action, "
                "c.job_id, c.error, c.workload_type, c.datasource_id, c.end_time "
                "FROM c WHERE (c.error.message != '' OR c.error.code != '') "
                f"AND c.start_time >= '{thirty_days_ago}'",
                enable_cross_partition_query=True,
            )
        )

        backup_job_errors = []
        for item in error_items:
            start_time = item.get("start_time", "")
            end_time_str = item.get("end_time", "")
            try:
                end_dt = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                expire_at = int(end_dt.timestamp())
            except (ValueError, AttributeError):
                expire_at = 0
            backup_job_errors.append({
                "subscription_id": item.get("subscription_id"),
                "timestamp": start_time,
                "feature": item.get("feature"),
                "action": item.get("action"),
                "action_id": item.get("job_id"),
                "error_message": item.get("error", {}).get("message", ""),
                "resource_type": item.get("workload_type"),
                "datasource_id": item.get("datasource_id"),
                "send_notification": False,
                "date": start_time[:10] if start_time else "",
                "expire_at": expire_at,
            })


        payload = {
            "metric_name": "azglz_backup_stats",
            "date_time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timestamp": int(now.timestamp()),
            "total_subscriptions": total_subscriptions,
            "total_subscriptions_with_custombackup": subscription_with_custombackup,
            "total_subscriptions_with_configuration": total_subscriptions_with_configuration,
            "total_subscriptions_without_configuration": total_subscriptions_without_configuration,
            "subscriptions_with_configuration": subscriptions_with_configuration,
            "subscriptions_without_configuration": subscriptions_without_configuration,
            "total_backup_job_errors_last_30_days": len(backup_job_errors),
            "backup_job_errors": backup_job_errors,

        }

        return func.HttpResponse(
            json.dumps(payload, indent=2),
            mimetype="application/json",
            status_code=200,
        )

    except KeyError:
        logging.error("COSMOS_CONNECTION_STRING environment variable not set.")
        return func.HttpResponse(
            json.dumps({"error": "COSMOS_CONNECTION_STRING is not configured."}),
            mimetype="application/json",
            status_code=500,
        )
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )
 