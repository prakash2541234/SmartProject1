import azure.functions as func

from subscription_handler import handle_subscription_request
from procecssCreateSubPayload import main as process_create_sub_payload_main
from createSP import main as createSP
from createKeyvault import main as createKeyvault
from deployBackupFeature import main as deploy_backup_feature_main
from generateVNetPayload import main as generate_vnet_payload_main

app = func.FunctionApp()


@app.function_name(name="acceptSubRequest")
@app.route(route="acceptSubRequest", auth_level=func.AuthLevel.FUNCTION)
def accept_sub_request(req: func.HttpRequest) -> func.HttpResponse:
    return handle_subscription_request(req)


@app.function_name(name="subscriptionRequest")
@app.route(route="subscriptionRequest", auth_level=func.AuthLevel.FUNCTION)
def subscription_request(req: func.HttpRequest) -> func.HttpResponse:
    return handle_subscription_request(req)


@app.function_name(name="processCreateSubPayload")
@app.route(route="processCreateSubPayload", auth_level=func.AuthLevel.FUNCTION)
def process_create_sub_payload(req: func.HttpRequest) -> func.HttpResponse:
    return process_create_sub_payload_main(req) 


@app.function_name(name="createSP")
@app.route(route="createSP", auth_level=func.AuthLevel.FUNCTION)
def create_sp(req: func.HttpRequest) -> func.HttpResponse:
    return createSP(req)


@app.function_name(name="createKeyvault")
@app.route(route="createKeyvault", auth_level=func.AuthLevel.FUNCTION)
def create_keyvault(req: func.HttpRequest) -> func.HttpResponse:
    return createKeyvault(req)


@app.function_name(name="deployBackupFeature")
@app.route(route="deployBackupFeature", auth_level=func.AuthLevel.FUNCTION)
def deploy_backup_feature(req: func.HttpRequest) -> func.HttpResponse:
    return deploy_backup_feature_main(req)


@app.function_name(name="generateVNetPayload")
@app.route(route="generateVNetPayload", auth_level=func.AuthLevel.FUNCTION)
def generate_vnet_payload(req: func.HttpRequest) -> func.HttpResponse:
    return generate_vnet_payload_main(req)

