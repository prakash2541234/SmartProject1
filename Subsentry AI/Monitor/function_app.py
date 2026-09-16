import azure.functions as func

from checkRequestPayload import main as validate_main
from Send_Error_createpayload import main as validate_main
from SubCheck import main as sub_check_main
from SPCheck import main as sp_check_main
from AssignRollCheck import main as assign_role_check_main
from VNetCheck import main as vnet_check_main
from BUCheck import main as bu_check_main
from KVCheck import main as kv_check_main
from Monitor8 import main as monitor_8_main

app = func.FunctionApp()

@app.function_name(name="checkRequestPayload")
@app.route(route="checkRequestPayload", auth_level=func.AuthLevel.FUNCTION)
def check_request_payload(req: func.HttpRequest) -> func.HttpResponse:
    return validate_main(req)


@app.function_name(name="sendErrorCreatePayload")
@app.route(route="sendErrorCreatePayload", auth_level=func.AuthLevel.FUNCTION)
def send_error_create_payload(req: func.HttpRequest) -> func.HttpResponse:
    return validate_main(req)


@app.function_name(name="validateSubscriptionFlow")
@app.route(route="validateSubscriptionFlow", auth_level=func.AuthLevel.FUNCTION)
def validate_subscription_flow(req: func.HttpRequest) -> func.HttpResponse:
    return sub_check_main(req)


@app.function_name(name="validateSPFlow")
@app.route(route="validateSPFlow", auth_level=func.AuthLevel.FUNCTION)
def validate_sp_flow(req: func.HttpRequest) -> func.HttpResponse:
    return sp_check_main(req)


@app.function_name(name="validateAssignRoleFlow")
@app.route(route="validateAssignRoleFlow", auth_level=func.AuthLevel.FUNCTION)
def validate_assign_role_flow(req: func.HttpRequest) -> func.HttpResponse:
    return assign_role_check_main(req)


@app.function_name(name="validateVNetFlow")
@app.route(route="validateVNetFlow", auth_level=func.AuthLevel.FUNCTION)
def validate_vnet_flow(req: func.HttpRequest) -> func.HttpResponse:
    return vnet_check_main(req)


@app.function_name(name="validateBUFlow")
@app.route(route="validateBUFlow", auth_level=func.AuthLevel.FUNCTION)
def validate_bu_flow(req: func.HttpRequest) -> func.HttpResponse:
    return bu_check_main(req)


@app.function_name(name="validateKVFlow")
@app.route(route="validateKVFlow", auth_level=func.AuthLevel.FUNCTION)
def validate_kv_flow(req: func.HttpRequest) -> func.HttpResponse:
    return kv_check_main(req)


@app.function_name(name="monitor_8")
@app.route(route="monitor_8", auth_level=func.AuthLevel.FUNCTION)
def monitor_8(req: func.HttpRequest) -> func.HttpResponse:
    return monitor_8_main(req)