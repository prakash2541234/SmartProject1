""" Azure Function to set backup configuration for a given subscription ID in Cosmos DB. """
import json
import os
import logging
import azure.functions as func
from azure.cosmos import CosmosClient
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
import requests


def main(req: func.HttpRequest) -> func.HttpResponse:
    """ This is a function to set backup configuration for a given subscription ID. """
    logging.info('Python HTTP POST processed.')

    try:
        req_body = req.get_json()
    except ValueError:
        req_body = {}
    subscription_id = req_body.get('subscription_id') or req.params.get('subscription_id')

    if not subscription_id:
        msg = "Missing required json attribute: subscription_id."
        logging.error(msg)
        return func.HttpResponse(msg, status_code=400)

    #read env variable for cosmosdb connection
    try:
        endpoint  = os.environ['COSMOS_SQL_ENDPOINT']
        database_name = os.environ['COSMOS_SQL_DATABASE']
        container_name = os.environ['COSMOS_SQL_CONTAINER_SUBBACKUPCONFIG']
    except KeyError as e:
        msg = f"Missing required environment variable: {e}"
        logging.error(msg)
        return func.HttpResponse(msg, status_code=500)

    # Acquire credential using Managed Identity (preferred)
    # fallback to DefaultAzureCredential for local dev
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

        # Extract backup configuration from request body
        backup_config = req_body
        backup_config['id'] = subscription_id
        # Upsert document (create new or replace existing)
        container.upsert_item(body=backup_config)

        updatesubtags(req_body, credential)

        logging.info("Successfully upserted backup configuration for subscription: %s", subscription_id)
        msg = {
                "status": "success",
                "subscription_id": subscription_id,
                "message": f"Backup configuration saved for subscription: {subscription_id}"
            }
        return func.HttpResponse(json.dumps(msg), status_code=200, mimetype="application/json")

    except Exception as e:
        msg = {
            "status": "error",
            "message": f"Error updating subscription backup configuration: {str(e)}"
        }
        logging.error(msg)
        return func.HttpResponse(json.dumps(msg), status_code=500, mimetype="application/json")

def updatesubtags(backup_config, credential):
    """ Update subscription tags in the subscriptions container based on backup configuration. """
    try:
        subscription_tags_api_url = os.environ.get("SUBSCRIPTION_TAGS_API_URL")
        subscription_id = backup_config['subscription_id']
        # default value of the tags to update
        tags_to_update = {
            "hidden-stla_vm_backup_policy": "",
            "hidden-stla_file_backup_policy": "",
            "hidden-stla_blob_backup_policy": "",
            "hidden-stla_sql_backup_policy": "",
            "hidden-stla_pgsql_backup_policy": "",
            "hidden-stla_mysql_backup_policy": ""
        }

        # loop through the inputs backup config to the API to set new values
        for item in backup_config.get('resources', []):
            tag_key = f"hidden-stla_{item.get('resource')}_backup_policy"
            tag_value = f"STLA-{item.get('resource')}-{item.get('retention')}-{item.get('time')}" if item.get('time') else f"STLA-{item.get('resource')}-{item.get('retention')}"
            tags_to_update[tag_key] = tag_value

        token = credential.get_token("https://management.azure.com/.default").token
        arm_url = f"https://management.azure.com/subscriptions/{subscription_id}?api-version=2020-01-01"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        get_resp = requests.get(arm_url, headers=headers, timeout=60)
        existing_sub_tags = {}
        if get_resp.status_code == 200:
            existing_sub_tags = get_resp.json().get("tags", {})
            # Merge existing tags with new tags, new tags take precedence
            keys_to_remove = []
            for tag_key, new_value in tags_to_update.items():
                current_value = existing_sub_tags.get(tag_key)

                if new_value == "":
                    # If new value is empty and current value exists
                    # (not None/empty string), set to none so the
                    # backup backend logic will clear any existing
                    # backup configurated for service
                    if current_value and current_value != "" and current_value.lower() != "none":
                        tags_to_update[tag_key] = "none"
                    else:
                        # If current value is already None, empty,
                        # or doesn't exist, don't update
                        # (remove from update dict)
                        keys_to_remove.append(tag_key)
                # If new value is not empty, keep it as is
                # (already in tags_to_update)
            
            for key in keys_to_remove:
                tags_to_update.pop(key, None)

        tag_update_api_payload = {
            "subscriptionId": subscription_id,
            "updateTags": tags_to_update
        }

        if not subscription_tags_api_url:
            logging.error("SUBSCRIPTION_TAGS_API_URL environment variable is not set.")
            raise ValueError("SUBSCRIPTION_TAGS_API_URL environment variable is not set. DB updated with backup config but subscription tag update skipped")
        
        response = requests.put(
            url=subscription_tags_api_url,
            json=tag_update_api_payload, timeout=60
        )
    except Exception as e:
        logging.error("Error updating subscription tags in Cosmos DB: %s", str(e))
        raise RuntimeError(f"Error updating subscription tags: {str(e)}") from e

    if response.status_code == 200:
        logging.info("Successfully updated tags for subscription: %s", subscription_id)
    else:
        logging.error("Failed to update tags for subscription: %s. Status Code: %s, Response: %s",
                      subscription_id, response.status_code, response.text)
        raise requests.HTTPError(f"Tag update API call failed with status code {response.status_code}")
    