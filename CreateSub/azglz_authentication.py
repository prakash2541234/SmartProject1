"""This functions implements a wrapper for EntraID authentication API
allowing Azure API management integration and formatting of inputs and 
output aligned to MyCloud Portal requirement."""
import logging
import os
import json
import requests
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="azglz_authentication")
def azglz_authentication(req: func.HttpRequest) -> func.HttpResponse:
    """Main function to authenticate against EntraID API."""
    logging.info('AZGLZ Authentication function is triggered')
    try:
        req_body = req.get_json()
    except ValueError:
        logging.error("Request did not include a valid JSON format which includes username and password")
        return func.HttpResponse(
            "Invalid JSON format. Please provide a valid JSON body with 'username' and 'password'.",
            status_code=400
        )
    else:
        logging.debug('Request body is valid JSON format')

        if 'username' in req_body and 'password' in req_body:
            name = req_body.get('username')
            password = req_body.get('password')
            shiftup_tenant_id = os.environ["AZGLZ_TENANT_ID"]
            scope = os.environ["AZGLZ_AUTH_SCOPE"]

            url = f"https://login.microsoftonline.com/{shiftup_tenant_id}/oauth2/v2.0/token"
            payload = {
                'client_id': name,
                'client_secret': password,
                'grant_type': 'client_credentials',
                'scope': scope
            }
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            logging.debug("Payload for API call: %s", payload)

            response = requests.post(url, data=payload, headers=headers, timeout=30)

            logging.debug("Entra ID toekn API called")
            if response.status_code == 200:
                logging.debug("Entra ID token API call was successful")
                response_json = response.json()
                return func.HttpResponse(
                json.dumps({'token': response_json.get('access_token')}),
                mimetype="application/json",
                status_code=200
                )
            else:
                logging.error("Entra ID token API call failed with status code: %s", response.status_code)
                return func.HttpResponse(f"API call failed to execute. Status code: {response.status_code}, Response: {response.text}", status_code=response.status_code)
        else:
            logging.error("Request did not include a valid JSON format which includes username and password")
            return func.HttpResponse(
                "Invalid JSON format. Please provide a valid JSON body with 'username' and 'password'.",
                status_code=400
            )