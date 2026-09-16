"""This function is triggered by an HTTP request and returns all 
subscriptions list from data depot with basic details for each sub."""
import logging
import json
import os
import traceback
from unittest import result
import azure.functions as func
from azure.core.exceptions import ServiceRequestError
from azure.cosmos import CosmosClient
from azure.cosmos import exceptions
from azure.cosmos.partition_key import PartitionKey
import json as _json

def main(req: func.HttpRequest) -> func.HttpResponse:
    """This function is triggered by an HTTP request and returns 
    all subscriptions list with basic details for each sub."""

    #check if the request include option to include the decommisioned subsriptions
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

    #check if the request include option to include the decommisioned subsriptions
    nextpagetoken_param = req.params.get('nextPageToken')
    nextpagetoken = None
    if nextpagetoken_param is not None:
        try:
            nextpagetoken = nextpagetoken_param
        except Exception:
            logging.info('Invalid nextPageToken parameter value, defaulting to None')
            nextpagetoken = None

    logging.info('nextPageToken parameter value: %s', nextpagetoken)

    subscriptions_data = {}

    #check if the request is post to get data for specific subscriptions
    if req.method == "POST":
        try:
            #add new logic to check the format of the post body to be list of subscriptions like {"subscriptions": ["1", "2"]}
            req_body = req.get_json()
            if not isinstance(req_body, dict) or "subscriptions" not in req_body:
                raise ValueError("Invalid request body format")

            sub_list = req_body["subscriptions"]
            subscriptions_data = getsubscriptionsdata(subscriptionslist=sub_list, includedecommsub=includedecommsub, continuation_token=nextpagetoken, pageSize=page_size)
        except Exception as e:
            logging.error('Error processing batch subscriptions: %s', str(e))
            return func.HttpResponse(
                body=json.dumps({"error": str(e)}),
                status_code=400,
                mimetype="application/json"
        )
    else:
        logging.info('Processing request for all getsubscriptions.')
        try:
            #call the get subscription data
            subscriptions_data = getsubscriptionsdata(includedecommsub=includedecommsub, continuation_token=nextpagetoken, pageSize=page_size)

        except exceptions.CosmosHttpResponseError as e:
            logging.error('Processing request for all getsubscriptions - CosmosHttpResponseError exception occurred.')
            logging.error(traceback.format_exc())
            return func.HttpResponse(
                body="CosmosHttpResponseError: Unable to connect to Cosmos DB please contact Stellantis Azure Foundation team. " + str(e),
                status_code=500,
                mimetype="application/json"
            )
        except ServiceRequestError as e:
            logging.error('Processing request for all getsubscriptions - ServiceRequestError exception occurred.')
            logging.error(traceback.format_exc())
            return func.HttpResponse(
                body="ServiceRequestError: Unable to connect to Cosmos DB please try again after some time. " + str(e),
                status_code=500,
                mimetype="application/json"
            )
        except ValueError as e:
            logging.error('Processing request for all getsubscriptions - ValueError exception occurred.')
            logging.error(traceback.format_exc())
            return func.HttpResponse(
                body="ValueError: Unable to connect to Cosmos DB please check with Azure Foundation team to resolve this error. " + str(e),
                status_code=500,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error('Processing request for all getsubscriptions - general exception captured.')
            logging.error(traceback.format_exc())
            return func.HttpResponse(
                body="Error: Unable to process your subscription enquiry request at this time please try again after some time. If problem persist please connect with Azure Foundation Team " + str(e),
                status_code=500,
                mimetype="application/json"
            )
    return func.HttpResponse(
        body=str(subscriptions_data),
        status_code=200,
        mimetype="application/json"
    )


def getsubscriptionsdata(subscriptionslist=None, includedecommsub=False, continuation_token=None, pageSize=50) -> dict:
    """
    Fetches subscription data from Cosmos DB, optionally including decommissioned subscriptions 
    and filtering by a list of subscription IDs.
    Returns a dictionary containing the queried subscription details.
    """

    client = CosmosClient(os.environ["COSMOSDB_ENDPOINT"], os.environ["COSMOSDB_KEY"])
    logging.debug('Processing request for all getsubscriptions - Cosmos DB connection established.')

    database = client.get_database_client(os.environ["COSMOSDB_DATABASE"])
    logging.debug('Processing request for all getsubscriptions - Cosmos DB database established.')

    container = database.get_container_client(os.environ["COSMOSDB_CONTAINER"])
    logging.debug('Processing request for all getsubscriptions - Cosmos DB container established.')
    # Build the base query depending on includedecommsub
    if includedecommsub:
        query = (
            "SELECT s.subscription_id as subscriptionId, s.subscription_name as name, "
            "StringToObject(s.subscription_tags) as tags, s.azglz_backup_available AS azglz_backup_available, s.IAM as security, s.vnet_info as network, s.decommission_info "
            "AS decommissionInfo FROM subscriptions as s"
        )
    else:
        query = (
            "SELECT s.subscription_id as subscriptionId, s.subscription_name as name, "
            "StringToObject(s.subscription_tags) as tags, s.azglz_backup_available AS azglz_backup_available, s.IAM as security, s.vnet_info as network FROM subscriptions as s "
            "WHERE s.decommission_info.decommissioned = 'false'"
        )

    # If a subscriptions list is provided, add a filter for those IDs
    if subscriptionslist:
        # Prepare the list for the IN clause
        # Ensure all IDs are strings and properly quoted
        quoted_ids = ', '.join([f"'{str(sub_id)}'" for sub_id in subscriptionslist])
        logging.info('Processing request for batch getsubscriptions - processing specific subscriptions list.' + quoted_ids)
        if "WHERE" in query:
            query += f" AND s.subscription_id IN ({quoted_ids})"
        else:
            query += f" WHERE s.subscription_id IN ({quoted_ids})"

    #query_options = {}

    #covert the incoming continuation token to dict if it is string
    if continuation_token and isinstance(continuation_token, str):
        continuation_token = {
            "token": continuation_token,
            "range": {
                "min": "",
                "max": "FF"
            }
        }


    # query_options = {}
    # if continuation_token:
    #     query_options['continuation_token'] = dict(continuation_token)
    # # Execute the query with pagination support
    items_iterable = container.query_items(query=query, enable_cross_partition_query=True, max_item_count=pageSize)

    # Fetch the first page of results
    items = []
    continuation_token_out = None
    try:
        subscriptions_by_page = items_iterable.by_page(continuation_token=continuation_token)
        subscription_page = next(subscriptions_by_page)
        items = list(subscription_page)  # Convert to list to materialize the iterator

        # Get the continuation token for the next page, if any
        # Extract the continuation token from the page iterator if available
        if hasattr(subscriptions_by_page, 'continuation_token') and subscriptions_by_page.continuation_token:
            # Cosmos continuation token is a JSON string, extract the "token" field if present
            continuation_token_out_json = json.loads(subscriptions_by_page.continuation_token)
            if isinstance(continuation_token_out_json, dict):
                continuation_token_out = continuation_token_out_json.get("token")
            elif isinstance(continuation_token_out_json, list) and continuation_token_out_json:
                continuation_token_out = continuation_token_out_json[0].get("token")
        else:
            continuation_token_out = None
    except Exception as e:
        logging.error(f"Error during Cosmos DB pagination: {e}")
        items = []
        continuation_token_out = None
    logging.debug('Processing request for all getsubscriptions - Cosmos DB query executed.')

    subs_data_response = []
    for subscription in items:
        logging.debug('Processing request for all getsubscriptions - processing subscription items.')
        subs_data_response.append(subscription)

    logging.debug('Processing request for all getsubscriptions - subscription items processed and returning response.')
    if continuation_token_out:
    #     # If continuation_token_out is a JSON string, parse it to a dict before including in the response
    #     try:
    #         next_page_token = json.loads(continuation_token_out)
    #     except Exception:
    #         next_page_token = continuation_token_out  # fallback to original if not valid JSON

        return json.dumps({"nextPageToken": continuation_token_out, "subscriptions": subs_data_response})
    else:
        return json.dumps({"subscriptions": subs_data_response})