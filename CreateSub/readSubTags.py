""" HTTP trigger to read subscription tags from Cosmos DB."""
import os
import json
import logging

import azure.functions as func
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.cosmos import CosmosClient


def main(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger to read subscription tags from Cosmos DB.
    Mandatory route parameter: subscriptionId
    If provided, returns tags for that subscription only. Otherwise returns tags for all subscriptions (may be large).
    """
    logging.info("GET subtags function processed a request.")

    # subscriptionId must be provided in the URL route (mandatory)
    subscription_id = req.route_params.get('subscriptionId')

    if not subscription_id:
        msg = "Missing required URL parameter: subscriptionId. Use /api/subtags/{subscriptionId}"
        logging.error(msg)
        return func.HttpResponse(msg, status_code=400)

    # Validate environment
    try:
        endpoint = os.environ['COSMOS_SQL_ENDPOINT']
        database_name = os.environ['COSMOS_SQL_DATABASE']
        container_name = os.environ['COSMOS_SQL_CONTAINER']
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

    # Build query
    if subscription_id:
        query = (
            "SELECT s.subscription_id, s.subscription_tags AS tags "
            f"FROM subscriptions AS s WHERE s.subscription_id = '{subscription_id}'"
        )
    else:
        query = "SELECT s.subscription_id, s.subscription_tags AS tags FROM subscriptions AS s"

    results = {}
    try:
        iterator = container.query_items(
            query=query,
            enable_cross_partition_query=True
        )

        for item in iterator:
            results = {
                "subscriptionId": item.get('subscription_id'),
                "tags": json.loads(item.get('tags', {}))
            }
    except Exception as e:
        logging.error("Error querying Cosmos DB: %s", e)
        return func.HttpResponse(f"Error querying Cosmos DB: {e}", status_code=500)

    return func.HttpResponse(body=json.dumps(results), status_code=200, mimetype="application/json")
