"""This function is triggered by an HTTP request and accepts the 
subscription creation payload from the Logic App. It stores the payload
in cosmos db"""
import logging
import json
import os
import re
import random
import datetime
import traceback
import azure.functions as func
from azure.cosmos import CosmosClient
from azure.identity import ManagedIdentityCredential

def main(req: func.HttpRequest) -> func.HttpResponse:
    """this function processes the payload coming through logic app and 
    creates initial subscription request entry"""

    request_payload = req.get_json()
    logging.info('processing create subscription payload request.')
    try:
        # get credentials from environment variables
        credential = ManagedIdentityCredential(client_id=os.environ['ManagedIdentityClientID'])

        cosmos_url = os.environ["COSMOS_SQL_ENDPOINT"]
        database_name = os.environ["COSMOS_SQL_DATABASE"]
        subrequest_container_name = os.environ["COSMOS_SQL_CONTAINER_SUBREQUEST"]

        # Create a Cosmos client
        logging.info('Creating Cosmos DB client with provided credentials.')
        cosmos_client = CosmosClient(
            url=cosmos_url,
            credential=credential
        )
        database = cosmos_client.get_database_client(database_name)
        container = database.get_container_client(subrequest_container_name)

        logging.info('Successfully created Cosmos DB client and obtained container reference.')
        
        account_payload_request = {
            "id": str(request_payload.get("request_parameters", {}).get("catalog_task_sysid")),
            **request_payload
        }
        container.create_item(body=account_payload_request)
        logging.info('Successfully created subscription request in datadepot.')
        return func.HttpResponse(
            body=json.dumps({
            "message": "Successfully accepted the subscription request.",
            "ticket_identifier": account_payload_request.get('id')
            }),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error('Processing accept subscription request - general exception captured.')
        logging.error(traceback.format_exc())
        return func.HttpResponse(
            body=json.dumps({
                "message": "Error: Unable to process your subscription request payload data. If problem persist please connect with Azure Foundation Team.",
                "error_details": str(e)
            }),
            status_code=500,
            mimetype="application/json")