"""
Azure Functions HTTP trigger to update subscription tags in Cosmos DB 
and apply new tags to the corresponding Azure subscriptions.
"""

import logging
import os
import json
import azure.functions as func
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions
import requests


def main(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP PUT trigger to update the subscription tags in Cosmos DB and Azure."""
    logging.info("updateSubTags function processed a request.")

    # Parse request body
    try:
        req_body = req.get_json()
        subscription_id = req_body['subscriptionId']
        new_tags = req_body.get('updateTags', {})
        tags_to_remove = req_body.get('deleteTags', [])
        if new_tags == {} and tags_to_remove == []:
            raise ValueError("Request must include at least one of 'updateTags' or 'deleteTags'.")
        elif new_tags != {}:
            if not isinstance(new_tags, dict):
                raise ValueError("updateTags must be a JSON object (dictionary) containing tag key-value pairs which needs to be added or updated.")
        elif tags_to_remove != []:
            if not isinstance(tags_to_remove, list):
                raise ValueError("deleteTags must be a list of tags to deleted from subscription")
    except (ValueError, KeyError) as e:
        msg = f"Invalid request body: {e}"
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

    # code to update the tags in the actual Azure subscription
    try:
        # Ensure tags are strings (ARM requires string values)
        if isinstance(new_tags, dict):
            tags_payload = {k: str(v) for k, v in new_tags.items()}
        else:
            # if user provided a JSON string or other form, attempt to use it directly
            tags_payload = new_tags

        token = credential.get_token("https://management.azure.com/.default").token
        arm_url = f"https://management.azure.com/subscriptions/{subscription_id}?api-version=2020-01-01"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        get_resp = requests.get(arm_url, headers=headers)
        current_tags = {}
        if get_resp.status_code == 200:
            current_tags = get_resp.json().get("tags", {})

        # Merge tags (new values overwrite existing keys)
        merged_tags = {**current_tags, **tags_payload}

        #remove tags to be removed from merged_tags
        for tag_key in tags_to_remove:
            merged_tags.pop(tag_key, None)


        # Use the Tags API to set tags at subscription scope.
        tags_endpoint = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Resources/tags/default?api-version=2021-04-01"
        tags_body = {"properties": {"tags": merged_tags}}

        resp = requests.put(tags_endpoint, json=tags_body, headers=headers)

        if resp.status_code not in (200, 201):
            logging.error("Failed to update subscription tags: %s %s", resp.status_code, resp.text)
            return func.HttpResponse(f"Failed to update subscription tags: {resp.status_code} - {resp.text}", status_code=500)
    except Exception as e:
        logging.error("Exception while updating subscription tags: %s", e)
        return func.HttpResponse(f"Exception while updating subscription tags: {e}", status_code=500)
    logging.info(f"Successfully updated tags for subscription ID {subscription_id} in Cosmos DB.")

    # Update tags in Cosmos DB
    try:
        item_response = container.read_item(item=subscription_id, partition_key=subscription_id)
        # remove tagged which starts with hidden tags from merged tag before updating it in cosmosdb 
        # this is to ensure that hidden tags are not returned in any API
        # Create new dictionary excluding hidden tags
        merged_tags_cdb = {k: v for k, v in merged_tags.items() if not k.startswith("hidden-")}

        #assign final merged tags to subscription item
        item_response['subscription_tags'] = json.dumps(merged_tags_cdb)

        #replace existing item with new tags
        container.replace_item(item=subscription_id, body=item_response)
    except cosmos_exceptions.CosmosResourceNotFoundError:
        msg = {
            "status": "error",
            "message": f"Subscription ID {subscription_id} not found in Cosmos DB."
        }
        logging.error(f"Subscription ID {subscription_id} not found in Cosmos DB.")
        return func.HttpResponse(json.dumps(msg), status_code=404, mimetype="application/json")
    except Exception as e:
        msg = {
            "status": "error",
            "message": f"Failed to update tags in Cosmos DB: {e}"
        }
        logging.error(msg["message"])
        return func.HttpResponse(json.dumps(msg), status_code=500, mimetype="application/json")

    response_body = {
        "status": "success",
        "subscription_id": subscription_id,
        "message": f"Successfully updated tags for subscription ID {subscription_id}."
    }
    return func.HttpResponse(json.dumps(response_body), status_code=200, mimetype="application/json")
