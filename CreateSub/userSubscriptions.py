"""Azure Function to get user access details based on group memberships from Microsoft Graph and Cosmos DB."""
import os
import json
import logging
import requests
import azure.functions as func
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.cosmos import CosmosClient
from msgraph import GraphServiceClient


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function to get user access details processed a request.')
    user_id = req.route_params.get('userId')

    if not user_id:
        return func.HttpResponse(
            "Please pass a valid user ID in the request URL.",
            status_code=400
        )
    else:
        logging.info("The inputs userid is %s. Fetching access details for this user.", user_id)

        # Parse simpleRequest parameter
        simple_request_param = req.params.get('simpleRequest')
        simple_request = False
        if simple_request_param is not None:
            try:
                if simple_request_param.lower() in ['true', '1', 'yes']:
                    simple_request = True
            except Exception:
                logging.info('Invalid simpleRequest parameter value, defaulting to False')
                simple_request = False

        #check if the request includes includedecommsub parameter to include decommissioned subscriptions
        includedecommsub_param = req.params.get('includedecommsub')
        includedecommsub = False
        if includedecommsub_param is not None:
            try:
                if includedecommsub_param.lower() in ['true', '1', 'yes']:
                    includedecommsub = True
            except Exception:
                logging.info('Invalid includedecommsub parameter value, defaulting to False')
                includedecommsub = False

        logging.info('includedecommsub parameter value: %s', includedecommsub)

        #check if the request includes pageSize parameter to set the number of records per page
        page_size_param = req.params.get('pageSize')
        page_size = 50
        if page_size_param is not None:
            try:
                page_size = int(page_size_param)
                if page_size <= 0:
                    raise ValueError("pageSize must be a positive integer")
            except Exception:
                logging.info('Invalid pageSize parameter value, defaulting to 50')
                page_size = 50

        logging.info('pageSize parameter value: %s', page_size)

        #check if the request include next page token
        nextpagetoken_param = req.params.get('nextPageToken')
        logging.info('nextPageToken parameter value: %s', nextpagetoken_param)

        #check if the request include the subscription_id parameter
        subscription_id_param = req.params.get('subscription_id')
        logging.info('subscription_id parameter value: %s', subscription_id_param)

        # Acquire token using DefaultAzureCredential
        # Acquire token using ManagedIdentityCredential if available, 
        # otherwise DefaultAzureCredential
        mi_client_id = os.environ.get("ManagedIdentityClientID")
        if mi_client_id:
            logging.info("Using ManagedIdentityCredential with client ID: %s", mi_client_id)
            credential = ManagedIdentityCredential(client_id=mi_client_id)
        else:
            logging.info("ManagedIdentityClientID not found, using DefaultAzureCredential")
            credential = DefaultAzureCredential()

        token = credential.get_token("https://graph.microsoft.com/.default")
        access_token = token.token

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "ConsistencyLevel": "eventual"  # Required for $count
        }
        response = requests.get(f"https://graph.microsoft.com/v1.0/users?$filter=startswith(userPrincipalName, '{user_id}')", headers=headers, timeout=30)

        if response.status_code == 200:
            users = response.json().get('value', [])
            if users:
                user_pricipalname = users[0]['userPrincipalName']  # Update user_id to the full ID
                logging.info("User found with ID: %s", user_pricipalname)
            else:
                logging.error("No user found with the provided identifier: %s", user_id)
                return func.HttpResponse(
                    f"No user found with the provided identifier: {user_id}",
                    status_code=404
                )
        else:
            logging.error("Failed to search for user. Status code: %s, Response: %s", response.status_code, response.text)
            return func.HttpResponse(
                f"Failed to search for user. Status code: {response.status_code}, Response: {response.text}",
                status_code=response.status_code
            )

        # Prepare Graph API request
        # Get only groups where securityEnabled is true
        url = f"https://graph.microsoft.com/v1.0/users/{user_pricipalname}/memberOf?$filter=(securityEnabled eq true)&$count=true"

        # Call the function to get user groups
        group_ids = getusergroups(url, access_token)
        logging.info("User %s is a member of %d groups.", user_pricipalname, len(group_ids))
        # After the loop, return the group_ids as JSON response
        subscriptionlist, continuation_token_out = getuseraccessdetails_usinggroups(group_ids, credential, includedecommsub=includedecommsub, continuation_token=nextpagetoken_param, pageSize=page_size, subscription_id=subscription_id_param)

        useraccessdetils = []
        for subscription in subscriptionlist:
            logging.info("Processing subscription: %s with access level: %s", subscription['subscription_id'], subscription['AccessLevel'])
            sub_id = subscription['subscription_id']
            sub_name = subscription['subscription_name']
            access_level = subscription['AccessLevel']
            azglz_backup_available = subscription.get('azglz_backup_available', "false")
            # Find if this subscription_id already exists in the list
            existing = next((item for item in useraccessdetils if item['subscriptionId'] == sub_id), None)
            if existing:
                if existing['access_level'] == 'User' and access_level == 'Admin':
                    existing['access_level'] = 'Admin'
            else:
                if simple_request:
                    useraccessdetils.append({
                        "subscriptionId": sub_id,
                        "name": sub_name,
                        "access_level": access_level
                    })
                else:
                    useraccessdetils.append({
                        "subscriptionId": sub_id,
                        "name": sub_name,
                        "tags": subscription.get('tags', {}),
                        "azglz_backup_available": azglz_backup_available,
                        "security": subscription.get('security', []),
                        "network": subscription.get('network', []),
                        "access_level": access_level
                    })
        logging.info("Total unique accessible subscriptions found: %d", len(useraccessdetils))

        if continuation_token_out:
            responseBody  = json.dumps({"user_id": user_pricipalname, "nextPageToken": continuation_token_out, "subscriptions": useraccessdetils})
        else:
            responseBody  = json.dumps({"user_id": user_pricipalname, "subscriptions": useraccessdetils})

        return func.HttpResponse(
            body=responseBody,
            status_code=200,
            mimetype="application/json"
        )


def getusergroups(graphapiurl, access_token):
    """Fetch user group memberships from Microsoft Graph API."""

    logging.info("Fetching user groups from Graph API: %s", graphapiurl)
    if 'group_ids' not in locals():
        group_ids = []
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "ConsistencyLevel": "eventual"  # Required for $count
    }
    response = requests.get(graphapiurl, headers=headers, timeout=30)
    if response.status_code == 200:
        user_details = response.json()
        if "@odata.nextLink" in user_details:
            logging.info("Pagination detected, fetching next page of results.")
            next_page_url = user_details["@odata.nextLink"]
            group_ids = getusergroups(next_page_url, access_token)  # Recursive call to fetch next page
        for membership in user_details['value']:
            if membership['@odata.type'] == '#microsoft.graph.group':
                group_id = membership['id']
                group_display_name = membership['displayName']
                group_mail = membership.get('mail', 'N/A')
                logging.info("User is a member of group: ID=%s, Name=%s, Mail=%s", group_id, group_display_name, group_mail)
                # Collect group IDs in a list
                group_ids.append(group_id)
        return group_ids
    else:   
        logging.error("Failed to fetch user groups. Status code: %s, Response: %s", response.status_code, response.text)
        return []

def getuseraccessdetails_usinggroups(groups, credentials, includedecommsub=False, continuation_token=None, pageSize=100, subscription_id=None):
    """Fetch user access details from Cosmos DB based on group memberships."""

    logging.info("Fetching access details for groups: %s", groups)
    try:
        database_name = os.environ["COSMOS_SQL_DATABASE"]
        container_name = os.environ["COSMOS_SQL_CONTAINER"]

        #select s.subscription_id, IIF(iamdetails.role_definition = "Owner" , 'Admin', IIF(iamdetails.role_definition = "Contributor", "Admin", "User")) AS AccessLevel from subscriptions as s JOIN iamdetails in s.IAM WHERE iamdetails.principal_id = '5e5212f8-50e1-40e8-98e4-fd860523ce8e'

        cosmos_client = CosmosClient(url=os.environ["COSMOS_SQL_ENDPOINT"], credential=credentials)
        logging.info("Connected to Cosmos DB successfully with endpoint: %s, database: %s, container: %s", os.environ["COSMOS_SQL_ENDPOINT"], database_name, container_name)

        database = cosmos_client.get_database_client(database_name)
        container = database.get_container_client(container_name)

        group_ids_str = ','.join([f"'{group}'" for group in groups])

        if includedecommsub:
            if subscription_id:
                query = f"SELECT DISTINCT s.subscription_id, s.subscription_name, StringToObject(s.subscription_tags) as tags, s.azglz_backup_available AS azglz_backup_available, s.IAM as security, s.vnet_info as network, IIF(iamdetails.role_definition = 'Owner' , 'Admin', IIF(iamdetails.role_definition = 'Contributor', 'Admin', 'User')) AS AccessLevel FROM subscriptions AS s JOIN iamdetails IN s.IAM WHERE iamdetails.principal_id IN ({group_ids_str}) AND s.subscription_id = '{subscription_id}' ORDER BY s.subscription_id"
            else:
                query = f"SELECT DISTINCT s.subscription_id, s.subscription_name, StringToObject(s.subscription_tags) as tags, s.azglz_backup_available AS azglz_backup_available, s.IAM as security, s.vnet_info as network, IIF(iamdetails.role_definition = 'Owner' , 'Admin', IIF(iamdetails.role_definition = 'Contributor', 'Admin', 'User')) AS AccessLevel FROM subscriptions AS s JOIN iamdetails IN s.IAM WHERE iamdetails.principal_id IN ({group_ids_str}) ORDER BY s.subscription_id"
        else:
            if subscription_id:
                query = f"SELECT DISTINCT s.subscription_id, s.subscription_name, StringToObject(s.subscription_tags) as tags, s.azglz_backup_available AS azglz_backup_available, s.IAM as security, s.vnet_info as network, IIF(iamdetails.role_definition = 'Owner' , 'Admin', IIF(iamdetails.role_definition = 'Contributor', 'Admin', 'User')) AS AccessLevel FROM subscriptions AS s JOIN iamdetails IN s.IAM WHERE iamdetails.principal_id IN ({group_ids_str}) AND (NOT IS_DEFINED(s.decommission_info) OR s.decommission_info.decommissioned = 'false') AND s.subscription_id = '{subscription_id}' ORDER BY s.subscription_id"
            else:
                query = f"SELECT DISTINCT s.subscription_id, s.subscription_name, StringToObject(s.subscription_tags) as tags, s.azglz_backup_available AS azglz_backup_available, s.IAM as security, s.vnet_info as network, IIF(iamdetails.role_definition = 'Owner' , 'Admin', IIF(iamdetails.role_definition = 'Contributor', 'Admin', 'User')) AS AccessLevel FROM subscriptions AS s JOIN iamdetails IN s.IAM WHERE iamdetails.principal_id IN ({group_ids_str}) AND (NOT IS_DEFINED(s.decommission_info) OR s.decommission_info.decommissioned = 'false')  ORDER BY s.subscription_id"

        #covert the incoming continuation token to dict if it is string
        # if continuation_token and isinstance(continuation_token, str):
        #     continuation_token = {
        #         "token": continuation_token,
        #         # "range": {
        #         #     "min": "",
        #         #     "max": "FF"
        #         # }
        #     }
        # Fetch the first page of results
        items = []
        continuation_token_out = None
        logging.info("Executing cosmosdb query")

        # items_iterable = container.query_items(query=query, enable_cross_partition_query=True, max_item_count=pageSize)
        items_iterable = container.query_items(query=query, enable_cross_partition_query=True)

        # try:
        #     subscriptions_by_page = items_iterable.by_page(continuation_token=continuation_token)
        #     subscription_page = next(subscriptions_by_page)
        #     items = list(subscription_page)  # Convert to list to materialize the iterator

        #     # Get the continuation token for the next page, if any
        #     # Extract the continuation token from the page iterator if available
        #     if hasattr(subscriptions_by_page, 'continuation_to```ken') and subscriptions_by_page.continuation_token:
        #         # Cosmos continuation token is a JSON string, extract the "token" field if present
        #         # continuation_token_out_json = json.loads(subscriptions_by_page.continuation_token)
        #         # if isinstance(continuation_token_out_json, dict):
        #         #     continuation_token_out = continuation_token_out_json.get("token")
        #         # elif isinstance(continuation_token_out_json, list) and continuation_token_out_json:
        #         #     continuation_token_out = continuation_token_out_json[0].get("token")
        #         continuation_token_out = subscriptions_by_page.continuation_token
        #     else:
        #         continuation_token_out = None
        # except Exception as e:
        #     logging.error(f"Error during Cosmos DB pagination: {e}")
        #     items = []
        #     continuation_token_out = None

        subscriptions = []
        for item in items_iterable:
            subscriptions.append(item)
        logging.info("Access details fetched successfully from Cosmos DB, with %d results.", len(subscriptions))
        return subscriptions, continuation_token_out
    except Exception as e:
        logging.error("Error fetching access details from Cosmos DB: %s", str(e))
        return []
