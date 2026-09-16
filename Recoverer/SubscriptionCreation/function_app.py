import azure.functions as func

from subscription_handler import handle_subscription_request
from procecssCreateSubPayload import main as process_create_sub_payload_main
from createSP import main as createSP
from createKeyvault import main as createKeyvault
from deployBackupFeature import main as deploy_backup_feature_main
from generateVNetPayload import main as generate_vnet_payload_main
from commitAzureDevOps import main as commit_azure_devops_main
from checkin_newsubjson import main as checkin_newsubjson_main
from QueueNewBuildforSubPipeline import main as queue_new_build_main
from checkbuildstatus import main as check_build_status_main
from create_a_new_release import main as create_a_new_release_main
from Get_ReleaseStatus import main as get_release_status_main
from QueryLastCommitVNetRepo import main as query_last_commit_vnet_repo_main
from CommitVNetPayloadFile import main as commit_vnet_payload_file_main
from NetworkCIBuild import main as network_ci_build_main
from Get_releaseStatus_network import main as get_release_status_network_main

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


@app.function_name(name="commitAzureDevOps")
@app.route(route="commitAzureDevOps", auth_level=func.AuthLevel.FUNCTION)
def commit_azure_devops(req: func.HttpRequest) -> func.HttpResponse:
    return commit_azure_devops_main(req)


@app.function_name(name="checkinNewSubJson")
@app.route(route="checkinNewSubJson", auth_level=func.AuthLevel.FUNCTION)
def checkin_new_sub_json(req: func.HttpRequest) -> func.HttpResponse:
    return checkin_newsubjson_main(req)


@app.function_name(name="QueueNewBuildforSubPipeline")
@app.route(route="QueueNewBuildforSubPipeline", auth_level=func.AuthLevel.FUNCTION)
def queue_new_build_for_sub_pipeline(req: func.HttpRequest) -> func.HttpResponse:
    return queue_new_build_main(req)


@app.function_name(name="checkbuildstatus")
@app.route(route="checkbuildstatus", auth_level=func.AuthLevel.FUNCTION)
def check_build_status(req: func.HttpRequest) -> func.HttpResponse:
    return check_build_status_main(req)


@app.function_name(name="create_a_new_release")
@app.route(route="create_a_new_release", auth_level=func.AuthLevel.FUNCTION)
def create_a_new_release(req: func.HttpRequest) -> func.HttpResponse:
    return create_a_new_release_main(req)


@app.function_name(name="Get_ReleaseStatus")
@app.route(route="Get_ReleaseStatus", auth_level=func.AuthLevel.FUNCTION)
def get_release_status(req: func.HttpRequest) -> func.HttpResponse:
    return get_release_status_main(req)


@app.function_name(name="QueryLastCommitVNetRepo")
@app.route(route="QueryLastCommitVNetRepo", auth_level=func.AuthLevel.FUNCTION)
def query_last_commit_vnet_repo(req: func.HttpRequest) -> func.HttpResponse:
    return query_last_commit_vnet_repo_main(req)


@app.function_name(name="CommitVNetPayloadFile")
@app.route(route="CommitVNetPayloadFile", auth_level=func.AuthLevel.FUNCTION)
def commit_vnet_payload_file(req: func.HttpRequest) -> func.HttpResponse:
    return commit_vnet_payload_file_main(req)


@app.function_name(name="NetworkCIBuild")
@app.route(route="NetworkCIBuild", auth_level=func.AuthLevel.FUNCTION)
def network_ci_build(req: func.HttpRequest) -> func.HttpResponse:
    return network_ci_build_main(req)


@app.function_name(name="Get_releaseStatus_network")
@app.route(route="Get_releaseStatus_network", auth_level=func.AuthLevel.FUNCTION)
def get_release_status_network(req: func.HttpRequest) -> func.HttpResponse:
    return get_release_status_network_main(req)

