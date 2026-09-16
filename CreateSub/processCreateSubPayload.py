"""This function is triggered by an HTTP request and returns
details of single subscriptions passed as url parameter."""
import logging
import json
import re
import random
import datetime
import traceback
import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    """this function processes the payload coming through logic app and 
    create various payloads for subscription creation and local cutomizations."""

    request_payload = req.get_json()
    logging.info('processing create subscription payload request.')
    try:
        subrequest_params = request_payload.get('stla_parameters', {})
        az_parameters = request_payload.get('az_parameters', {})

        appId = subrequest_params.get('application_id', '')
        environment = subrequest_params.get('environment', '')
        sensitivity_tag = subrequest_params.get('sensitivity', 'standard')
        subscriptionname = f"sub-{get_application_id(appId)}-{environment}-{get_senstivity(sensitivity_tag)}-{random.randint(100, 999)}"
        network_model = az_parameters.get('network_model', 'standalone')

        #as digital allowed app team to select different environment names we are normalizing all lower env to nonprod
        #poc and prod will not be changed, this new variable is used to decide the right management group
        if environment in ("dev", "test", "stage", "non prod", "non-prod", "development", "testing", "staging"):
            m_group_environment = "nonprod"
        else:
            m_group_environment = environment

        subscriptionPayload = {
            "subscription_name": subscriptionname,
            "subscription_mgmtgroup": get_sub_mgmtgroup(sensitivity_tag, m_group_environment, network_model),
            "subscription_tags" :
                {
                    "stla_application_id":appId,
                    "stla_hle_usd":subrequest_params.get('hle_usd', 0),
                    "stla_support_email": subrequest_params.get('support_email', ''),
                    "stla_environment":environment,
                    "stla_global_business": subrequest_params.get('stla_global_business', ''),
                    "stla_global_subfunction": subrequest_params.get('stla_global_subfunction', ''),
                    "stla_sensitivity": sensitivity_tag,
                    "stla_multi_tenant": subrequest_params.get('multi_tenant', 'false'),
                    "stla_purchase_date":datetime.date.today().strftime("%d/%m/%Y"),
                    "stla_region": az_parameters.get('azure_region', subrequest_params.get('stla_region', 'n/a')),
                    "stla_network_domain": az_parameters.get('network_domain', 'n/a'),
                    "stla_model_deployment": network_model,
                    "stla_application_source":subrequest_params.get('application_source', 'unknown'),
                    "stla_application_name": subrequest_params.get('application_name', 'unknown'),
                },
        }

        return json.dumps(subscriptionPayload)

    except Exception as e:
        logging.error('Processing request for all getsubscription - general exception captured.')
        logging.error(traceback.format_exc())
        return func.HttpResponse(
            body="Error: Unable to process your subscription request payload data. If problem persist please connect with Azure Foundation Team. Error Details - " + str(e),
            status_code=500,
            mimetype="application/json"
        )
def get_application_id(appid):
    """This function converts application id to a short form to use in subscription name"""
    appid = appid.lower()
    appid = re.sub(r'[^a-z0-9]', '', appid)

    return appid

def get_senstivity(sensitivity_tag):
    """This function converts sensitivity tag to a short form to use in subscription name"""
    switch={
       'standard': "std",
       'sensitive': "S3",
       'highly sensitive': "S4",
       'highlysensitive': "S4",
       'highly_sensitive': "S4",
       'highly-sensitive': "S4",
       }
    sensitivity = switch.get(sensitivity_tag)
    if sensitivity is None:
        logging.error("Invalid sensitivity tag: %s", sensitivity_tag)
        raise ValueError(f"Invalid sensitivity tag '{sensitivity_tag}' specified")
    return sensitivity
def get_sub_mgmtgroup(sensitivity_tag, environment, network_model):
    """This function returns the subscription management group based on the sensitivity tag"""
    mg_lz_corp_highly_sensitive_prod_id    = "mg-lz-corp-highlysensitive-prod"
    mg_lz_corp_highly_sensitive_nonprod_id = "mg-lz-corp-highlysensitive-nonprod"
    mg_lz_corp_highly_sensitive_poc_id     = "mg-lz-corp-highlysensitive-poc"
    mg_lz_corp_sensitive_prod_id          = "mg-lz-corp-sensitive-prod"
    mg_lz_corp_sensitive_nonprod_id        = "mg-lz-corp-sensitive-nonprod"
    mg_lz_corp_sensitive_poc_id            = "mg-lz-corp-sensitive-poc"
    mg_lz_corp_standard_prod_id           = "mg-lz-corp-standard-prod"
    mg_lz_corp_standard_nonprod_id         = "mg-lz-corp-standard-nonprod"
    mg_lz_corp_standard_poc_id             = "mg-lz-corp-standard-poc"

    mg_lz_standalone_highly_sensitive_prod_id = "mg-lz-standalone-highlysensitive-prod"
    mg_lz_standalone_highly_sensitive_nonprod_id = "mg-lz-standalone-highlysensitive-nonprod"
    mg_lz_standalone_highly_sensitive_poc_id = "mg-lz-standalone-highlysensitive-poc"
    mg_lz_standalone_sensitive_prod_id    = "mg-lz-standalone-sensitive-prod"
    mg_lz_standalone_sensitive_nonprod_id = "mg-lz-standalone-sensitive-nonprod"
    mg_lz_standalone_sensitive_poc_id     = "mg-lz-standalone-sensitive-poc"
    mg_lz_standalone_standard_prod_id     = "mg-lz-standalone-standard-prod"
    mg_lz_standalone_standard_nonprod_id   = "mg-lz-standalone-standard-nonprod"
    mg_lz_standalone_standard_poc_id       = "mg-lz-standalone-standard-poc"



    if environment == "prod":
        if sensitivity_tag == "standard":
            return mg_lz_corp_standard_prod_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_standard_prod_id
        elif sensitivity_tag == "sensitive":
            return mg_lz_corp_sensitive_prod_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_sensitive_prod_id
        elif (sensitivity_tag in ("highly sensitive", "highlysensitive", "highly_sensitive", "highly-sensitive")):
            return mg_lz_corp_highly_sensitive_prod_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_highly_sensitive_prod_id
    if environment == "nonprod":  
        if sensitivity_tag == "standard":
            return mg_lz_corp_standard_nonprod_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_standard_nonprod_id
        elif sensitivity_tag == "sensitive":
            return mg_lz_corp_sensitive_nonprod_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_sensitive_nonprod_id
        elif (sensitivity_tag in ("highly sensitive", "highlysensitive", "highly_sensitive", "highly-sensitive")):
            return mg_lz_corp_highly_sensitive_nonprod_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_highly_sensitive_nonprod_id
    if environment == "poc":
        if sensitivity_tag == "standard":
            return mg_lz_corp_standard_poc_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_standard_poc_id
        elif sensitivity_tag == "sensitive":
            return mg_lz_corp_sensitive_poc_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_sensitive_poc_id
        elif (sensitivity_tag in ("highly sensitive", "highlysensitive", "highly_sensitive", "highly-sensitive")):
            return mg_lz_corp_highly_sensitive_poc_id if (network_model in ("onprem_extension", "onprem", "on-prem")) else mg_lz_standalone_highly_sensitive_poc_id
    else:
        logging.error("Invalid environment: %s", environment)
        raise ValueError(f"Invalid environment - '{environment}' specified")