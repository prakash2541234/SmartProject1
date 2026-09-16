import azure.functions as func

from checkRequestPayload import main as check_request_payload_main
from Send_Error_createpayload import main as send_error_create_payload_main
from subflowCheck import main as subflow_check_main
from SPCheck import main as sp_check_main
from AssignRollCheck import main as assign_role_check_main
from VNetCheck import main as vnet_check_main
from BUCheck import main as bu_check_main
from KVCheck import main as kv_check_main
from sub12check import main as sub12check_main
from subflowCheckSecound import main as subflow_check_secound_main
from subflowCheckThird import main as subflow_check_third_main
from subflowCheckforth import main as subflow_check_forth_main
from Monitor8 import main as monitor8_main
from VNet_first import main as vnet_first_main
from VNet_second import main as vnet_second_main
from VNet_third import main as vnet_third_main
from VNet_forth import main as vnet_forth_main
from VNet_fifth import main as vnet_fifth_main


app = func.FunctionApp()

@app.function_name(name="checkRequestPayload")
@app.route(route="checkRequestPayload", auth_level=func.AuthLevel.FUNCTION)
def check_request_payload(req: func.HttpRequest) -> func.HttpResponse:
    return check_request_payload_main(req)


@app.function_name(name="sendErrorCreatePayload")
@app.route(route="sendErrorCreatePayload", auth_level=func.AuthLevel.FUNCTION)
def send_error_create_payload(req: func.HttpRequest) -> func.HttpResponse:
    return send_error_create_payload_main(req)


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


@app.function_name(name="validateSubscriptionFlowDetailed")
@app.route(route="validateSubscriptionFlowDetailed", auth_level=func.AuthLevel.FUNCTION)
def validate_subscription_flow_detailed(req: func.HttpRequest) -> func.HttpResponse:
    return subflow_check_main(req)


@app.function_name(name="subflowCheckSecound")
@app.route(route="subflowCheckSecound", auth_level=func.AuthLevel.FUNCTION)
def subflow_check_secound(req: func.HttpRequest) -> func.HttpResponse:
    return subflow_check_secound_main(req)


@app.function_name(name="subflowCheckThird")
@app.route(route="subflowCheckThird", auth_level=func.AuthLevel.FUNCTION)
def subflow_check_third(req: func.HttpRequest) -> func.HttpResponse:
    return subflow_check_third_main(req)


@app.function_name(name="subflowCheckforth")
@app.route(route="subflowCheckforth", auth_level=func.AuthLevel.FUNCTION)
def subflow_check_forth(req: func.HttpRequest) -> func.HttpResponse:
    return subflow_check_forth_main(req)


@app.function_name(name="sub12check")
@app.route(route="sub12check", auth_level=func.AuthLevel.FUNCTION)
def sub12check(req: func.HttpRequest) -> func.HttpResponse:
    return sub12check_main(req)


@app.function_name(name="Monitor_8")
@app.route(route="Monitor_8", auth_level=func.AuthLevel.FUNCTION)
def monitor_8(req: func.HttpRequest) -> func.HttpResponse:
    return monitor8_main(req)


@app.function_name(name="VNet_first")
@app.route(route="VNet_first", auth_level=func.AuthLevel.FUNCTION)
def vnet_first(req: func.HttpRequest) -> func.HttpResponse:
    return vnet_first_main(req)


@app.function_name(name="VNet_second")
@app.route(route="VNet_second", auth_level=func.AuthLevel.FUNCTION)
def vnet_second(req: func.HttpRequest) -> func.HttpResponse:
    return vnet_second_main(req)


@app.function_name(name="VNet_third")
@app.route(route="VNet_third", auth_level=func.AuthLevel.FUNCTION)
def vnet_third(req: func.HttpRequest) -> func.HttpResponse:
    return vnet_third_main(req)


@app.function_name(name="VNet_forth")
@app.route(route="VNet_forth", auth_level=func.AuthLevel.FUNCTION)
def vnet_forth(req: func.HttpRequest) -> func.HttpResponse:
    return vnet_forth_main(req)


@app.function_name(name="VNet_fifth")
@app.route(route="VNet_fifth", auth_level=func.AuthLevel.FUNCTION)
def vnet_fifth(req: func.HttpRequest) -> func.HttpResponse:
    return vnet_fifth_main(req)