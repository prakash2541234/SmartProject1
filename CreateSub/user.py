import os
import json
import logging
import requests
from wsgiref import headers
import azure.functions as func
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from msgraph import GraphServiceClient
from azure.cosmos import CosmosClient

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function to get user access details processed a request.')
    user_id = req.route_params.get('userId')

    if not user_id:
        return func.HttpResponse(
            "Please pass a valid user ID in the request URL.",
            status_code=400
        )
    else:
        try:
            
            logging.info("The inputs userid is %s. Fetching access details for this user.", user_id)

            # Acquire token using DefaultAzureCredential
            # credential = DefaultAzureCredential()
            credential = ManagedIdentityCredential(client_id=os.environ["ManagedIdentityClientID"])
            token = credential.get_token("https://graph.microsoft.com/.default")
            access_token = token.token

            # try to find the user by searching in the userPrincipalName to extract the full userprincipalName
            response = callGraphAPI(f"https://graph.microsoft.com/v1.0/users?$filter=startswith(userPrincipalName, '{user_id}')", access_token)
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
            response = callGraphAPI(f"https://graph.microsoft.com/v1.0/users/{user_pricipalname}", access_token)
            if response.status_code != 200:
                return func.HttpResponse(
                    f"Failed to retrieve user details. Status code: {response.status_code}, Response: {response.text}",
                    status_code=response.status_code
                )
            else:
                user_details = response.json()
                logging.info("User details retrieved successfully: %s", user_details)

                # Get only groups where securityEnabled is true
                groupsurl = f"https://graph.microsoft.com/v1.0/users/{user_pricipalname}/memberOf?$filter=(securityEnabled eq true)&$count=true"
                # Call the function to get user groups
                groups = getusergroups(groupsurl, access_token)

                return func.HttpResponse(
                    body=json.dumps({"user_id": user_pricipalname, "principal_id": user_details["id"], "group_assignment": groups}),
                    status_code=200,
                    mimetype="application/json"
            )
        except Exception as e:
            logging.error("An error occurred: %s", str(e))
            return func.HttpResponse(
                f"An error occurred while processing the request to get user details for {user_id}: {str(e)}",
                status_code=500
            )

def getusergroups(graphapiurl, access_token):
    """Function to get user groups from Microsoft Graph API."""
    logging.info(f"Fetching user groups from Graph API: {graphapiurl}")
    if 'groups' not in locals():
        groups = []
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "ConsistencyLevel": "eventual"  # Required for $count
    }
    response = requests.get(graphapiurl, headers=headers)
    if response.status_code == 200:
        user_details = response.json()
        if "@odata.nextLink" in user_details:
            logging.info("Pagination detected, fetching next page of results.")
            next_page_url = user_details["@odata.nextLink"]
            groups = getusergroups(next_page_url, access_token)  # Recursive call to fetch next page
        for membership in user_details['value']:
            if membership['@odata.type'] == '#microsoft.graph.group':
                group_id = membership['id']
                group_display_name = membership['displayName']
                group_mail = membership.get('mail', 'N/A')
                group_type = "group"
                logging.info(f"User is a member of group: ID={group_id}, Name={group_display_name}, Mail={group_mail}")
                groupdetails = {
                    "principal_id": group_id,
                    "principal_type": group_type,
                    "principal_name": group_display_name
                }
                # Collect group IDs in a list
                groups.append(groupdetails)
        return groups
    else:   
        logging.error(f"Failed to fetch user groups. Status code: {response.status_code}, Response: {response.text}")
        return []

def callGraphAPI(url, access_token):
    """Function to call Microsoft Graph API."""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "ConsistencyLevel": "eventual"  # Required for $count
    }
    response = requests.get(url, headers=headers)

    return response