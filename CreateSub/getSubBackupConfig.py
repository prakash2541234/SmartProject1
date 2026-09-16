import json
import azure.functions as func
import logging
import os
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions
import requests

def main(req: func.HttpRequest) -> func.HttpResponse:
    """ This is a function to get backup configuration for a given subscription ID. """
    logging.info('Python HTTP GET processed.')

    subscription_id = req.route_params.get('subscriptionid')
    if not subscription_id:
        msg = "Missing required URL parameter: subscriptionId. Use /api/subtags/{subscriptionId}"
        logging.error(msg)
        return func.HttpResponse(msg, status_code=400)
    
    # Validate environment
    try:
        endpoint = os.environ['COSMOS_SQL_ENDPOINT']
        database_name = os.environ['COSMOS_SQL_DATABASE']
        container_name = os.environ['COSMOS_SQL_CONTAINER_SUBBACKUPCONFIG']
    except KeyError as e:
        msg = f"Missing required environment variable: {e}"
        logging.error(msg)
        return func.HttpResponse(msg, status_code=500)

    # Acquire credential using Managed Identity (preferred) with fallback to DefaultAzureCredential for local dev
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

    try:
        client = CosmosClient(url=endpoint, credential=credential)
        database = client.get_database_client(database_name)
        container = database.get_container_client(container_name)
    except Exception as e:
        logging.error("Failed to connect to Cosmos DB: %s", e)
        return func.HttpResponse(f"Failed to connect to Cosmos DB: {e}", status_code=500)

    #build query to get subscription backup config
        # Build query
    if subscription_id:
        query = (
            "SELECT s.subscription_id, s.subscription_name, s.stla_backup_enabled, s.last_update_user, s.last_update_timestamp, s.resources "
            f"FROM subscription_backupconfig AS s WHERE s.subscription_id = '{subscription_id}'"
        )
    else:
        query = "SELECT * AS tags FROM subscription_backupconfig AS s"

    try:
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        if not items:
            msg = f"No backup configuration found for subscription ID: {subscription_id}"
            logging.warning(msg)
            reponse = {
                "subscription_id": subscription_id,
                "stla_backup_enabled": False,
                "resources": []
            }

            return func.HttpResponse(json.dumps(reponse), mimetype="application/json", status_code=200)
        result = items[0]
        return func.HttpResponse(
            body=json.dumps(result),
            mimetype="application/json",
            status_code=200
        )
    except cosmos_exceptions.CosmosHttpResponseError as e:
        logging.error("Cosmos DB query failed: %s", e)
        return func.HttpResponse(f"Cosmos DB query failed: {e}", status_code=500)