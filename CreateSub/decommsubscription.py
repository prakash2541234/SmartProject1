"""Fucntion app to decommission a subscription in Azure."""
import logging
import os
import json
import requests
import datetime
import azure.functions as func
from azure.identity import DefaultAzureCredential, ClientSecretCredential, ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient
from azure.cosmos import CosmosClient
#import uuid

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="decommsubscription/{subscription_id}")
def decommsubscription(req: func.HttpRequest) -> func.HttpResponse:
    """This function calls the Azure API to decommission a subscription."""
    
    logging.info('Python HTTP trigger function processed a request.')
    subscriptionid = req.route_params.get('subscription_id')
    logging.info("Subscription ID: %s", subscriptionid)

    decommission_reason  = req.params.get('decommission_reason')
    if decommission_reason is None:
        return func.HttpResponse(
            "Please provide valid decommission reason, this may include reference to DigitalMe request ID and decommission requester name.",
            status_code=400
        )

    try:
        key_vault_uri = os.environ["KEY_VAULT_URI"] # Set in app settings
        credential = ManagedIdentityCredential(client_id=os.environ["ManagedIdentityClientID"])
        client = SecretClient(vault_url=key_vault_uri, credential=credential)
        logging.info("Client for Key Vault URI: %s created.", key_vault_uri)
        sp_tenant_id = "d852d5cd-724c-4128-8812-ffa5db3f8507"
        sp_client_id_key = "clientid-sp-sub-decomm"
        sp_client_secret_key = "clientsecret-sp-sub-decomm"

        sp_client_id_secret = client.get_secret(sp_client_id_key)
        sp_client_secret_secret = client.get_secret(sp_client_secret_key)

        logging.info("Client ID: %s and related client secret retrieved.", sp_client_id_secret.value)
        sp_crecentials = ClientSecretCredential(sp_tenant_id, sp_client_id_secret.value, sp_client_secret_secret.value)
        access_token = sp_crecentials.get_token("https://management.azure.com//.default").token
        logging.info("Access token retrieved")

        get_subscription_api_url = f"https://management.azure.com/subscriptions/{subscriptionid}?api-version=2022-12-01"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.get(get_subscription_api_url, headers=headers, timeout=60)

        if response.status_code == 200:
            response_json = json.dumps(response.json(), indent=4)
            logging.info("Get subscription API response: %s", response_json)
            logging.info("Subscription ID %s is valid.", subscriptionid)

            if response.json()["state"] == "Disabled" or response.json()["state"] == "Deleted" or response.json()["state"] == "Warned" or response.json()["state"] == "Expired":
                return func.HttpResponse(
                        f"The current status of subscription {subscriptionid} is {response.json()['state']}. No futher action taken as subscription is not in active state.",
                        status_code=200
                    )
            else:
                # Perform the decommissioning process
                decommission_result, output_message = perform_decommission(subscriptionid, access_token)
                if decommission_result:
                    try:
                        logging.info("Updating decommission info in CosmosDB for subscription %s", subscriptionid)
                        cosmos_url = os.environ["COSMOS_SQL_ENDPOINT"]
                        database_name = os.environ["COSMOS_SQL_DATABASE"]
                        container_name = os.environ["COSMOS_SQL_CONTAINER"]

                        # Cosmos client - using Managed Identity for authentication
                        logging.info("Connecting to CosmosDB using Managed Identity...")
                        cosmos_client = CosmosClient(cosmos_url, credential=credential)
                        database = cosmos_client.get_database_client(database_name)
                        container = database.get_container_client(container_name)


                        decomm_info = {
                            "decommissioned": "true",
                            "decommission_date": datetime.datetime.utcnow().replace(microsecond=0).isoformat(),
                            "decommission_reason": decommission_reason
                        }

                        patch_operations = [{"op": "set", "path": "/decommission_info", "value": decomm_info}]
                        container.patch_item(
                            item=subscriptionid,
                            partition_key=subscriptionid,
                            patch_operations=patch_operations
                        )
                        logging.info("CosmosDB item patched successfully.")
                    except Exception as e:
                        logging.error("Failed to patch CosmosDB item: %s", e)
                        return func.HttpResponse(
                            output_message + f" Although could not update the cosmosdb, Error details: {str(e)}",
                            status_code=200
                        )
                    return func.HttpResponse(
                        output_message,
                        status_code=200
                )
                else:
                    return func.HttpResponse(
                        f"Failed to decommission subscription {subscriptionid}. {output_message}",
                        status_code=500
                    )
        else:
            response_json = json.dumps(response.json(), indent=4)
            logging.error("Get subscription API failed with error: %s", response_json)
            if response.status_code == 404:
                logging.info("Subscription ID %s not found. Inside status code 404 handling", subscriptionid)
                return func.HttpResponse(
                    f"Subscription ID {subscriptionid} not found.",
                    status_code=404
                )
            elif response.status_code == 400:
                logging.error("Bad request for subscription ID %s. Inside status code 400 handling", subscriptionid)
                return func.HttpResponse(
                    response.json(),
                    status_code=response.status_code
                )            
            else:
                output_message = f"Error: {response.status_code}, {response_json}"
                logging.error("Failed to retrieve subscription details: %s", output_message)
                return func.HttpResponse(
                    f"Failed to retrieve subscription details. {output_message}",
                    status_code=500
                )
    except ValueError:
        return func.HttpResponse(
             "Invalid subscription ID format. Please provide a valid Subscription ID.",
             status_code=400
        )
    except KeyError as e:
        return func.HttpResponse(
             f"There was a internal error in decommon subscription, please contact \
             Azure Foundation team with below error. Key error: {str(e)}",
             status_code=500
        )

def perform_decommission(subscription_id, access_token) -> tuple:
    """Perform the decommissioning of the subscription."""
    decomm_management_group_id = os.environ["DECOMM_MANAGEMENT_GROUP_ID"] # Set in app settings
    decomission_result = False
    # Placeholder for the actual decommissioning logic
    # This could involve API calls, database updates, etc.
    logging.info("Decommissioning subscription: %s", subscription_id)

    mgmt_group_move_api_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{decomm_management_group_id}/subscriptions/{subscription_id}?api-version=2020-05-01" # Example API endpoint
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    mg_move_response = requests.put(mgmt_group_move_api_url, headers=headers, timeout=60)

    if mg_move_response.status_code == 200:
        response_message = json.dumps(mg_move_response.json(), indent=4)
        logging.info("Move from management successful")
        logging.info("Move from management successful API response : %s", response_message)
    
        cancel_subscription_api_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Subscription/cancel?api-version=2021-10-01&IgnoreResourceCheck=true" # Example API endpoint
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        cs_response = requests.post(cancel_subscription_api_url, headers=headers, timeout=60)

        if cs_response.status_code == 200:
            response_message = json.dumps(cs_response.json(), indent=4)
            logging.info("Cancel subscription successful")
            logging.info("Cancel subscription successful API response : %s", response_message)
            decomission_result = True
            output_message = f"Subscription {subscription_id} has been successfully decommissioned."
        elif cs_response.status_code == 400:
            response_json = json.dumps(cs_response.json(), indent=4)
            output_message = f"Cancellation of Subscription with ID: {subscription_id} unsuccessful. Error: {cs_response.status_code}, {response_json}"
            logging.error("Cancel subscription failed with error: %s", response_message)
        else:
            response_json = json.dumps(cs_response.json(), indent=4)
            output_message = f"Error: {cs_response.status_code}, {response_json}"
            logging.error("Cancel subscription failed with error: %s", response_message)
    else:
        response_json = json.dumps(mg_move_response.json(), indent=4)
        output_message = f"Moving subscription to decommision Managment group failed, Error: {mg_move_response.status_code}, {response_json}"

    # Simulate a successful decommissioning process
    return decomission_result, output_message
