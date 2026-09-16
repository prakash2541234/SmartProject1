import azure.functions as func
import logging
import os
from datetime import datetime, timezone
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from azure.cosmos import CosmosClient, exceptions

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logger.info("Function app is starting up...")


def main(mytimer: func.TimerRequest) -> None:
    logger.info("Python timer trigger function processed a request.")

    if mytimer.past_due:
        logger.info("The timer is past due!")

    try:
        # ------------------------------------------------------------------
        # 1. AUTHENTICATION
        # ------------------------------------------------------------------
        # For Azure: Use ManagedIdentityCredential with the user-assigned identity
        # For Local: Use DefaultAzureCredential (falls back to Azure CLI)
        # ------------------------------------------------------------------

        managed_identity_client_id = os.environ.get("ManagedIdentityClientID")
        lookback_window = os.environ.get(
            "LOOKBACK_WINDOW", "24h"
        )  # Default to last 24 hours if not set

        try:
            # Check if running in Azure (has managed identity configured)
            if managed_identity_client_id:
                # Running in Azure - use Managed Identity
                credential = ManagedIdentityCredential(
                    client_id=managed_identity_client_id
                )
            else:
                # Running locally - use DefaultAzureCredential
                credential = DefaultAzureCredential()
        except Exception as auth_error:
            logger.error("Authentication failed: %s", str(auth_error))
            raise

        # ------------------------------------------------------------------
        # 2. RUN RESOURCE GRAPH QUERY (KQL)
        # ------------------------------------------------------------------
        #
        # This is a PLACEHOLDER query.
        # Replace it later with your real backup job KQL.
        #
        # IMPORTANT:
        # Resource Graph requires a subscription list.
        #
        # ------------------------------------------------------------------

        try:
            resource_graph_client = ResourceGraphClient(credential)
        except Exception as client_error:
            logger.error(
                "Failed to create Resource Graph client: %s", str(client_error)
            )
            raise

        query = f"""
        recoveryservicesresources
            | where (
                    type in~
                    ('Microsoft.RecoveryServices/vaults/replicationJobs','Microsoft.RecoveryServices/vaults/backupJobs','Microsoft.DataProtection/backupVaults/backupJobs')
                    )
            | extend isNonProtectedItemJob = case(
                type =~ "Microsoft.RecoveryServices/vaults/backupJobs", '0',
                type =~ "Microsoft.DataProtection/backupVaults/backupJobs", '0',
                type =~ "Microsoft.RecoveryServices/vaults/replicationJobs", '1', '--')
            | extend workloadType = tostring(case (
                isnotnull(properties.workloadType), properties.workloadType,
                properties.backupManagementType == 'AzureIaasVM', 'VM',
                properties.dataSourceType has "/fileServices/shares", "AzureFileShare",
                properties.dataSourceType has "/storageAccounts/blobServices", "AzureBlob",
                properties.dataSourceType == 'Microsoft.DBforPostgreSQL/flexibleServers', 'PostgreSQL','--'))
            | extend vaultIdLowerCase = tolower(case(
                type =~ "Microsoft.RecoveryServices/vaults/backupJobs",split(id, '/backupJobs')[0],
                type =~ "Microsoft.DataProtection/backupVaults/backupJobs", split(id, '/backupJobs')[0],
                type =~ "Microsoft.RecoveryServices/vaults/replicationJobs", split(id, '/replicationJobs')[0], '--'))
            | extend datasourceType = case(
                type =~ "Microsoft.RecoveryServices/vaults/backupJobs", strcat(properties.backupManagementType,'/',workloadType),
                type =~ "Microsoft.DataProtection/backupVaults/backupJobs", properties.dataSourceType,
                type =~ "Microsoft.RecoveryServices/vaults/replicationJobs", properties.providerSpecificDetails.instanceType, '--')
            | extend datasourceId = case(
                type =~ "Microsoft.RecoveryServices/vaults/backupJobs", properties.dataSourceId,
                type =~ "Microsoft.DataProtection/backupVaults/backupJobs", properties.dataSourceId,
                type =~ "Microsoft.RecoveryServices/vaults/replicationJobs", properties.providerSpecificDetails.dataSourceId, '--')
            | extend datasourceSubscription = split(split(datasourceId, '/subscriptions/')[1],'/')[0]
            | extend datasourceResourceGroup = split(split(tolower(datasourceId), '/resourcegroups/')[1],'/')[0]
            | extend datasourceLocation = case(
                type =~ "Microsoft.RecoveryServices/vaults/backupJobs", properties.dataSourceLocation,
                type =~ "Microsoft.DataProtection/backupVaults/backupJobs", properties.dataSourceLocation,
                type =~ "Microsoft.RecoveryServices/vaults/replicationJobs", properties.providerSpecificDetails.dataSourceLocation, '--')
            | extend datasourceName = case(
                type =~ "Microsoft.RecoveryServices/vaults/backupJobs", properties.entityFriendlyName,
                type =~ "Microsoft.DataProtection/backupVaults/backupJobs", properties.backupInstanceFriendlyName,
                type =~ "Microsoft.RecoveryServices/vaults/replicationJobs", properties.entityFriendlyName, '--')
            | join kind=inner (
                resources
                | extend vaultIdLowerCase = tolower(id)
                | extend vaultLocation = location
                | project vaultIdLowerCase, vaultLocation
            ) on vaultIdLowerCase
                    | extend Status = tostring(properties.status)
                    | extend StartTime = todatetime(properties.startTime)
                    | extend Duration = totimespan(properties.duration)
                    | extend EndTime = todatetime(properties.startTime)
                    | extend feature  = properties.operationCategory
                    | extend action  = properties.operation
                    | extend dataSourceId = properties.dataSourceId
                    | where StartTime >= ago({lookback_window})
                    | extend ErrorDetails = properties.errorDetails[0]
                    | extend ErrorCode = coalesce(tostring(ErrorDetails.errorCode), tostring(ErrorDetails.code))
                    | extend ErrorMessage = coalesce(tostring(ErrorDetails.errorString), tostring(ErrorDetails.message))
                    | extend Recommendation = coalesce(strcat_array(ErrorDetails.recommendations, "; "), strcat_array(ErrorDetails.recommendedAction, "; "))
                    | extend JobId = coalesce(tostring(properties.activityId), tostring(properties.activityID))
                    | sort by StartTime desc
                    | project JobId, subscriptionId, datasourceName, feature, action, Status, StartTime, Duration, EndTime, dataSourceId, datasourceType, workloadType, datasourceLocation, ErrorCode, ErrorMessage, Recommendation
        """

        query_request = QueryRequest(query=query)

        # Fetch all pages from Resource Graph
        rows = []
        skip_token = None
        page_count = 0

        try:
            while True:
                page_count += 1

                # Add skip_token for pagination if available
                if skip_token:
                    query_request.options = {"$skipToken": skip_token}

                query_response = resource_graph_client.resources(query_request)

                # Add current page data to results
                rows.extend(query_response.data)

                logger.info(
                    "Page %d: Retrieved %d rows (Total so far: %d)",
                    page_count,
                    len(query_response.data),
                    len(rows),
                )

                # Check if there are more pages
                skip_token = query_response.skip_token
                if not skip_token:
                    break

            logger.info(
                "Retrieved %d total rows from Resource Graph across %d page(s).",
                len(rows),
                page_count,
            )
        except Exception as query_error:
            logger.error("Failed to execute Resource Graph query: %s", str(query_error))
            return

        # ------------------------------------------------------------------
        # 3. COSMOS DB CLIENT SETUP (SQL / CORE API)
        # ------------------------------------------------------------------
        #
        # This code assumes:
        #   - Cosmos DB SQL (Core) API
        #   - RBAC enabled on Cosmos DB
        #
        # If RBAC is enabled:
        #   - Assign "Cosmos DB Built-in Data Contributor"
        #     to the Managed Identity.
        #
        # ------------------------------------------------------------------

        cosmos_account_url = os.environ.get("COSMOS_SQL_ENDPOINT")
        cosmos_database_name = os.environ.get("COSMOS_SQL_DATABASE")
        cosmos_container_name = os.environ.get("COSMOS_SQL_CONTAINER_BKP_STATS")

        # Validate environment variables
        if not all([cosmos_account_url, cosmos_database_name, cosmos_container_name]):
            error_msg = (
                "Missing required Cosmos DB configuration in environment variables"
            )
            logger.error(error_msg)
            return

        try:
            cosmos_client = CosmosClient(url=cosmos_account_url, credential=credential)

            database = cosmos_client.get_database_client(cosmos_database_name)
            container = database.get_container_client(cosmos_container_name)
        except Exception as cosmos_setup_error:
            logger.error(
                "Failed to setup Cosmos DB client: %s", str(cosmos_setup_error)
            )
            return

        # ------------------------------------------------------------------
        # 4. TRANSFORM + UPSERT DATA INTO COSMOS DB
        # ------------------------------------------------------------------
        #
        # Each Resource Graph row becomes ONE Cosmos document.
        # Partition key = /subscriptionId
        #
        # We generate:
        #   - id      -> unique per job
        #   - ingestedAt -> current UTC time
        #
        # ------------------------------------------------------------------

        ingested_at = datetime.now(timezone.utc).isoformat()

        documents_written = 0
        failed_documents = 0
        skipped_missing_jobid = 0

        for row in rows:
            # ------------------------------------------------------------------
            # This is a MOCK transformation.
            # Replace field mappings once real KQL is added.
            # ------------------------------------------------------------------

            try:
                job_id = row.get("JobId")
                if not job_id:
                    skipped_missing_jobid += 1
                    logger.warning("Skipping row because JobId is missing: %s", str(row))
                    continue

                document = {
                    # Cosmos DB requires an "id" field
                    "id": job_id,
                    "job_id": job_id,
                    "subscription_id": row.get("subscriptionId", "unknown"),
                    "datasource_name": row.get("datasourceName", "unknown"),
                    "datasource_type": row.get("datasourceType", "unknown"),
                    "datasource_location": row.get("datasourceLocation", "unknown"),
                    "workload_type": row.get("workloadType", "unknown"),
                    "datasource_id": row.get("dataSourceId", "unknown"),
                    "feature": row.get("feature", "unknown"),
                    "action": row.get("action", "unknown"),
                    "status": row.get("Status", "unknown"),
                    "start_time": row.get("StartTime"),
                    "duration": row.get("Duration"),
                    "end_time": row.get("EndTime"),
                    "error": {
                        "code": row.get("ErrorCode", "None"),
                        "message": row.get("ErrorMessage", "None"),
                        "recommendation": row.get("Recommendation", "None"),
                    },
                    "ingested_at": ingested_at,
                }

                # Upsert = insert if new, replace if exists
                container.upsert_item(body=document)
                documents_written += 1

            except exceptions.CosmosHttpResponseError as cosmos_error:
                failed_documents += 1
                logger.error(
                    "Cosmos DB error - Failed to write document for JobId %s: %s - %s",
                    row.get("JobId", "unknown"),
                    cosmos_error.status_code,
                    str(cosmos_error),
                )
            except KeyError as key_error:
                failed_documents += 1
                logger.error(
                    "Data transformation error - Missing key in row data: %s",
                    str(key_error),
                )
            except Exception as doc_error:
                failed_documents += 1
                logger.error(
                    "Unexpected error processing document for JobId %s: %s",
                    row.get("JobId", "unknown"),
                    str(doc_error),
                )

        # ------------------------------------------------------------------
        # 5. SUCCESS RESPONSE
        # ------------------------------------------------------------------

        logger.info(
            "Successfully written %d documents to Cosmos DB.", documents_written
        )
        if skipped_missing_jobid > 0:
            logger.warning("Skipped %d rows because JobId was missing.", skipped_missing_jobid)
        if failed_documents > 0:
            logger.warning(
                "Failed to write %d documents to Cosmos DB.", failed_documents
            )

        logger.info(
            "Data Collection Summary | rows_found=%d, rows_written=%d, failed_documents=%d",
            len(rows),
            documents_written,
            failed_documents,
        )
        return

    except Exception as e:
        # Catch any unexpected errors at the top level
        error_message = f"Unexpected error in datacollector function: {str(e)}"
        logger.exception(error_message)
        return
