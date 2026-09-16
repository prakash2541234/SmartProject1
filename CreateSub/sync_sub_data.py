import datetime
import logging
import os
import json
import requests

import azure.functions as func
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.resource import ResourceManagementClient
from azure.cosmos import CosmosClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.keyvault.secrets import SecretClient
import redis
from redis_entraid.cred_provider import *


def get_all_management_groups(token):
    """
    Gets all management groups and their subscriptions in one call.
    Returns a tuple of:
    - dict mapping subscription_id to immediate parent management_group_name
    - dict mapping subscription_id to list of ALL ancestor management groups
    """
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Get ALL entities at once - no search parameter
        url = "https://management.azure.com/providers/Microsoft.Management/getEntities?api-version=2020-05-01"

        response = requests.post(url, headers=headers, json={}, timeout=60)

        if response.status_code == 200:
            data = response.json()
            entities = data.get("value", [])

            # Build mappings
            subscription_to_mg = {}  # subscription_id -> immediate parent
            subscription_ancestors = {}  # subscription_id -> [all ancestors]

            for entity in entities:
                if entity.get("type") == "/subscriptions":
                    sub_id = entity.get("name")
                    props = entity.get("properties", {})

                    # Get immediate parent
                    parent = props.get("parent", {})
                    if parent and "id" in parent and sub_id:
                        parent_id = parent["id"]
                        parent_name = parent_id.split("/")[-1]
                        subscription_to_mg[sub_id] = parent_name

                    # Get all ancestors from parentNameChain
                    parent_chain = props.get("parentNameChain", [])
                    if parent_chain and sub_id:
                        # parentNameChain includes all ancestors from root to immediate parent
                        # Skip the tenant root (first item) if it's a GUID
                        ancestors = []
                        for ancestor in parent_chain:
                            if (
                                ancestor
                                and not ancestor.replace("-", "")
                                .replace(" ", "")
                                .lower()
                                == "tenantrootgroup"
                            ):
                                # Skip if it looks like a tenant ID (GUID format)
                                if len(ancestor) != 36 or ancestor.count("-") != 4:
                                    ancestors.append(ancestor)
                        subscription_ancestors[sub_id] = ancestors

            logging.info(
                "Loaded management groups for %s subscriptions", len(subscription_to_mg)
            )
            return subscription_to_mg, subscription_ancestors
        else:
            logging.error(
                "getEntities API returned status %s: %s",
                response.status_code,
                response.text,
            )
    except Exception as e:
        logging.error("getEntities API failed: %s", str(e))

    return {}, {}


def main(mytimer: func.TimerRequest) -> None:
    """
    Azure Function that runs every hour to update subscription data in CosmosDB SQL API.
    """
    utc_timestamp = datetime.datetime.utcnow().replace(microsecond=0).isoformat()
    principalname_cache_reads = 0
    principalname_cache_misses = 0

    if mytimer.past_due:
        logging.info("The timer is past due!")

    logging.info("Python timer trigger function started at %s", utc_timestamp)

    try:
        # when in local use default credential and managed identity in function app
        if not os.environ.get("ManagedIdentityClientID"):
            credential = DefaultAzureCredential()
        else:
            credential = ManagedIdentityCredential(
                client_id=os.environ["ManagedIdentityClientID"]
            )

        # Check for dry run mode
        dryrun = os.environ.get("DRY_RUN", "false").lower() == "true"
        if dryrun:
            logging.info(
                "DRYRUN mode enabled: No data will be written to CosmosDB SQL."
            )

        # Get token once for reuse
        token = credential.get_token("https://management.azure.com/.default").token

        # Cosmos DB SQL connection info - Using Managed Identity (NO KEYS!)
        cosmos_url = os.environ["COSMOS_SQL_ENDPOINT"]
        database_name = os.environ["COSMOS_SQL_DATABASE"]
        container_name = os.environ["COSMOS_SQL_CONTAINER"]

        # Cosmos client - using Managed Identity for authentication
        logging.info("Connecting to CosmosDB using Managed Identity...")
        cosmos_client = CosmosClient(cosmos_url, credential=credential)
        database = cosmos_client.get_database_client(database_name)
        container = database.get_container_client(container_name)

        # Get ALL management groups mapping ONCE
        logging.info("Loading management group mappings...")
        subscription_to_mg, subscription_ancestors = get_all_management_groups(token)

        # Get subscription data
        subscription_client = SubscriptionClient(credential)
        all_subscriptions = list(subscription_client.subscriptions.list())

        # Get management groups to scan from environment variable
        mgmt_groups_to_scan = os.environ.get("MANAGEMENT_GROUPS", "").strip()
        if mgmt_groups_to_scan:
            # Parse comma-separated management groups
            target_mg_list = [mg.strip() for mg in mgmt_groups_to_scan.split(",")]
            logging.info(
                "Filtering subscriptions by management groups: %s", target_mg_list
            )

            # Filter subscriptions - check if ANY ancestor is in our target list
            subscriptions = []
            for sub in all_subscriptions:
                # Get all ancestors for this subscription
                ancestors = subscription_ancestors.get(sub.subscription_id, [])

                # Check if any ancestor matches our target management groups
                if any(ancestor in target_mg_list for ancestor in ancestors):
                    subscriptions.append(sub)
                    logging.debug(
                        "Including subscription %s (ancestors: %s)",
                        sub.display_name,
                        ancestors,
                    )

            logging.info(
                "Filtered to %d subscriptions from %d total",
                len(subscriptions),
                len(all_subscriptions),
            )
        else:
            logging.info(
                "No MANAGEMENT_GROUPS filter specified, scanning all accessible subscriptions"
            )
            subscriptions = all_subscriptions
        # Process each subscription
        total_subscriptions = len(subscriptions)
        logging.info("Processing %d subscriptions...", total_subscriptions)

        # Initialize Redis connection only once per function app instance
        # if not hasattr(syncSubData, "redis_client"):
        # credential_provider = create_from_default_azure_credential(("https://redis.azure.com/.default",),)
        # credential_provider = create_from_managed_identity(identity_type=ManagedIdentityType.USER_ASSIGNED, resource="https://redis.azure.com/.default", id_type=ManagedIdentityIdType.CLIENT_ID, id_value=os.environ["ManagedIdentityClientID"])
        redis_host = os.environ.get("REDIS_HOST")
        # redis_port = int(os.environ.get("REDIS_PORT", 6380))
        # redis_ssl = os.environ.get("REDIS_SSL", "true").lower() == "true"
        # Use SSL for Azure Redis
        # redis_token = credential.get_token("https://redis.azure.com/.default")
        # redis_access_token = redis_token.token
        # logging.info("redis access token acquired %s", redis_access_token)
        key_vault_uri = os.environ["KEY_VAULT_URI"]  # Set in app settings
        kvclient = SecretClient(vault_url=key_vault_uri, credential=credential)
        rediscache_accesskey = kvclient.get_secret("azglz-rediscache-accesskey")

        main.redis_client = redis.Redis(
            host=redis_host,
            port=6380,
            password=rediscache_accesskey.value,
            ssl=True,
            decode_responses=True,
        )

        for index, sub in enumerate(subscriptions):
            # Skip all subscriptions except the one we want to process
            # if sub.subscription_id != "64b90b3a-dc40-407b-8729-7d7d61666a6e":
            #     continue

            logging.info(
                "Processing subscription %d/%d: %s",
                index + 1,
                total_subscriptions,
                sub.display_name,
            )
            # Get full subscription object
            sub_full = subscription_client.subscriptions.get(sub.subscription_id)
            resource_client = ResourceManagementClient(credential, sub.subscription_id)
            # Get tags using ResourceManagementClient
            try:
                tag_obj = resource_client.tags.get_at_scope(sub_full.id)
                tags_dict = (
                    tag_obj.properties.tags
                    if hasattr(tag_obj, "properties")
                    and hasattr(tag_obj.properties, "tags")
                    and tag_obj.properties.tags
                    else {}
                )
                # Remove tags that start with "hidden-" prefix
                tags_dict = {
                    k: v
                    for k, v in tags_dict.items()
                    if not k.lower().startswith("hidden-")
                }
            except Exception as e:
                logging.warning(
                    "Could not fetch tags for subscription %s: %s",
                    sub.subscription_id,
                    e,
                )
                tags_dict = {}
            tags = [{"Key": k, "Value": v} for k, v in tags_dict.items()]

            # Get additional subscription details
            # resource_groups = list(resource_client.resource_groups.list())

            # Get VNets and subnets
            network_client = NetworkManagementClient(credential, sub.subscription_id)
            vnet_info = []
            subnet_info = []
            for vnet in network_client.virtual_networks.list_all():
                vnet_info.append(
                    {
                        "vnet_name": vnet.name,
                        "vnet_cidr": vnet.address_space.address_prefixes[0]
                        if vnet.address_space.address_prefixes
                        else None,
                        "vnet_rg": vnet.id.split("/resourceGroups/")[1].split("/")[0],
                        "vnet_location": vnet.location,
                    }
                )
                for subnet in vnet.subnets:
                    subnet_info.append(
                        {
                            "subnet_name": subnet.name,
                            "subnet_cidr": subnet.address_prefix,
                            "subnet_vnet": vnet.name,
                        }
                    )

            # Get IAM role assignments for the subscription
            try:
                auth_client = AuthorizationManagementClient(
                    credential, sub.subscription_id
                )
                scope = f"/subscriptions/{sub.subscription_id}"
                # Get role assignments at subscription scope only using list_for_scope
                role_assignments = list(
                    auth_client.role_assignments.list_for_scope(
                        scope=scope, filter="atScope()"
                    )
                )
                # Defensive: some role definitions may not have id
                role_defs = {}
                for rd in auth_client.role_definitions.list(scope):
                    rd_id = getattr(rd, "id", None)
                    if rd_id:
                        role_defs[rd_id.lower()] = rd
                IAM = []

                # Get token for Graph API
                graph_token = credential.get_token(
                    "https://graph.microsoft.com/.default"
                ).token

                for ra in role_assignments:
                    role_def_id = getattr(ra, "role_definition_id", None)
                    role_def_id_lc = (
                        role_def_id.lower() if isinstance(role_def_id, str) else ""
                    )
                    role_def = role_defs.get(role_def_id_lc)
                    role_name = getattr(role_def, "role_name", "") if role_def else ""
                    principal_id = getattr(ra, "principal_id", "")
                    principal_type = getattr(ra, "principal_type", "")
                    principal_name = ""
                    # Query principal name for all principal types
                    try:
                        # Use a cache to avoid repeated Graph API calls for the same principal_id
                        # Use Azure Cache for Redis instead of local in-memory cache
                        redis_client = main.redis_client
                        # logging.info("Checking cache for principal_id %s", principal_id)
                        redis_cache_key = f"principal_name:{principal_id}"
                        principal_name = redis_client.get(redis_cache_key)
                        if principal_name:
                            logging.info(
                                "Using Redis cached principal_name for principal_id %s: %s",
                                principal_id,
                                principal_name,
                            )
                            principalname_cache_reads += 1
                        else:
                            logging.info(
                                "No Redis cache found for principal_id %s, querying Graph API",
                                principal_id,
                            )
                            principalname_cache_misses += 1
                            principal_name = getprincipalname(
                                principal_id, principal_type, graph_token
                            )
                            redis_client.set(
                                redis_cache_key, principal_name
                            )  # Cache with no expiry
                    except BaseException as e:
                        logging.error(
                            "There was a cache operation error for principal_id %s: %s",
                            principal_id,
                            str(e),
                        )

                    IAM.append(
                        {
                            "role_assignment": getattr(ra, "id", ""),
                            "role_definition": role_name,
                            "principal_id": principal_id,
                            "principal_type": principal_type,
                            "principal_name": principal_name,
                        }
                    )
            except Exception as e:
                logging.warning(
                    "Could not fetch IAM for subscription %s: %s",
                    sub.subscription_id,
                    e,
                )
                IAM = []

            # Get parent management group from cached mapping
            parent_mngt_group = subscription_to_mg.get(sub.subscription_id, "")

            # define default Decomm Info block
            decomm_info = {
                "decommissioned": "false",
                "decommission_date": "",
                "decommission_reason": "",
            }

            if "mg-decommission" in parent_mngt_group:
                decomm_info["decommissioned"] = "true"
                decomm_info["decommission_date"] = (
                    utc_timestamp  # Use current timestamp for decommission date, to capture the job run time. ideally this will be updated as part of decomm sub API
                )
                decomm_info["decommission_reason"] = (
                    "This Subscription is marked as cancelled. Please contact Cloud Adoption team or Azure Foundation team for further assistance."
                )

            # Check if subscription is in backup unavailable list
            backup_unavailable_subids = os.getenv("BACKUP_UNAVAILABLE_SUBIDs", "")
            backup_unavailable_subids_list = [
                sub_id.strip()
                for sub_id in backup_unavailable_subids.split(",")
                if sub_id.strip()
            ]
            if sub.subscription_id in backup_unavailable_subids_list:
                azglz_backup_available = "false"
            else:
                azglz_backup_available = "true"

            # Document structure for Cosmos DB SQL API
            doc = {
                "id": sub.subscription_id,
                "subscription_id": sub.subscription_id,
                "subscription_name": sub.display_name,
                "subscription_tags": json.dumps(tags_dict),
                "support_email": tags_dict.get("stla_support_email", ""),
                "env": tags_dict.get("stla_environment", ""),
                "last_checked": utc_timestamp,  # Always update this
                "parent_mngt_group": parent_mngt_group,
                "azglz_backup_available": azglz_backup_available,
                "tags": tags,
                "vnet_info": vnet_info,
                "subnet_info": subnet_info,
                "decommission_info": decomm_info,
                "IAM": IAM,
            }

            if dryrun:
                logging.info(
                    "[DRYRUN] Would update document for subscription %s: %s",
                    sub.subscription_id,
                    doc,
                )
            else:
                # Try to patch existing document first
                try:
                    # Fields to exclude from updates,
                    # the logic is if there is no change in decommission_info then add it to exclude_fields
                    logging.info(
                        "Trying to patch existing document for subscription %s",
                        sub.subscription_id,
                    )
                    exclude_fields = [
                        "id",
                        "subscription_id",
                        "env",
                        "last_updated",
                        "pipeline_managed",
                        "joined_method",
                        "joined_timestamp",
                        "alternate_contacts",
                        "tags" #this is added to start decommisioning this field as we used subscription_tags as main field and we want to avoid confusion between these two fields
                    ]

                    existing_doc = container.read_item(
                        item=sub.subscription_id, partition_key=sub.subscription_id
                    )

                    if (
                        existing_doc["decommission_info"]["decommissioned"]
                        == doc["decommission_info"]["decommissioned"]
                    ):
                        logging.info(
                            "Decommission info has not changed for subscription %s, excluding decommission_info from patch",
                            sub.subscription_id,
                        )
                        exclude_fields = [
                            "id",
                            "subscription_id",
                            "env",
                            "decommission_info",
                            "last_updated",
                            "pipeline_managed",
                            "joined_method",
                            "joined_timestamp",
                            "alternate_contacts",
                            "tags" #this is added to start decommisioning this field as we used subscription_tags as main field and we want to avoid confusion between these two fields
                        ]

                    # Build patch operations
                    patch_operations = []
                    for key, value in doc.items():
                        if key not in exclude_fields:
                            patch_operations.append(
                                {"op": "set", "path": f"/{key}", "value": value}
                            )

                    # Patch existing document
                    container.patch_item(
                        item=sub.subscription_id,
                        partition_key=sub.subscription_id,
                        patch_operations=patch_operations,
                    )
                    logging.info(
                        "Patched existing document for subscription %s",
                        sub.subscription_id,
                    )
                except Exception as e:
                    logging.info(
                        "Error in Patching for subscription %s: %s",
                        sub.subscription_id,
                        str(e),
                    )
                    if "Not Found" in str(e) or "404" in str(e) or "NotFound" in str(e):
                        # Document doesn't exist, create it
                        logging.info(
                            "Document not found, creating new document for subscription %s",
                            sub.subscription_id,
                        )
                        container.create_item(body=doc)
                        logging.info(
                            "Created new document for subscription %s",
                            sub.subscription_id,
                        )
                    else:
                        # Some other error
                        raise e

        logging.info("Successfully updated all subscription data in Cosmos DB SQL API.")
        logging.info(
            "Principal name cache reads: %d, cache misses: %d",
            principalname_cache_reads,
            principalname_cache_misses,
        )
    except Exception as e:
        logging.error("Error updating subscription data: %s", str(e))
        raise

    logging.info("Python timer trigger function completed at %s", utc_timestamp)


def getprincipalname(principal_id, principal_type, graph_token):
    """
    Helper function to get principal name from Microsoft Graph API.
    """
    try:
        if principal_type == "User":
            graph_url = f"https://graph.microsoft.com/v1.0/users/{principal_id}"
        elif principal_type == "Group":
            graph_url = f"https://graph.microsoft.com/v1.0/groups/{principal_id}"
        elif principal_type == "ServicePrincipal":
            graph_url = (
                f"https://graph.microsoft.com/v1.0/servicePrincipals/{principal_id}"
            )
        elif principal_type == "ForeignGroup":
            graph_url = f"https://graph.microsoft.com/v1.0/groups/{principal_id}"
        elif principal_type == "Device":
            graph_url = f"https://graph.microsoft.com/v1.0/devices/{principal_id}"
        else:
            return ""

        graph_headers = {
            "Authorization": f"Bearer {graph_token}",
            "Content-Type": "application/json",
        }
        graph_resp = requests.get(graph_url, headers=graph_headers, timeout=10)
        if graph_resp.status_code == 200:
            graph_data = graph_resp.json()
            # Try to get displayName or userPrincipalName
            principal_name = (
                graph_data.get("displayName")
                or graph_data.get("userPrincipalName")
                or graph_data.get("appDisplayName")
                or graph_data.get("deviceId")
                or ""
            )
            return principal_name
        else:
            logging.debug(
                "Graph API returned %s for principal_id %s",
                graph_resp.status_code,
                principal_id,
            )
    except BaseException as e:
        logging.error(
            "Could not fetch principal name for principal_id %s: %s",
            principal_id,
            str(e),
        )
    return ""
