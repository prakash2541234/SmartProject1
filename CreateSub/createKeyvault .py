import os
import logging
import json
import random
import re
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.keyvault.models import (
    VaultCreateOrUpdateParameters,
    VaultProperties,
    Sku,
)
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.subscription import SubscriptionClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def get_tenant_id(credential, subscription_id):
    """Retrieves the tenant ID for the subscription, falling back to ENV if needed."""
    try:
        sub_client = SubscriptionClient(credential)
        return sub_client.subscriptions.get(subscription_id).tenant_id
    except Exception:
        return os.environ.get("ShiftupTenantId")


def getenv(environment):
    """Convert environment to standardized short form"""
    env_mapping = {
        "production": "prod",
        "prod": "prod",
        "non-production": "np",
        "nonproduction": "np",
        "non-prod": "np",
        "nonprod": "np",
        "np": "np",
        "development": "np",
        "dev": "np",
        "testing": "np",
        "test": "np",
        "staging": "np",
        "stage": "np",
    }
    return env_mapping.get(environment.lower(), "prod")


def get_clean_app_id(appid):
    """This function converts application id to a short form to use in resource names"""
    appid = appid.lower()
    appid = re.sub(r"[^a-z0-9]", "", appid)

    return appid


def ensure_resource_provider_registered(resource_client, provider_namespace):
    """Check if a resource provider is registered and register it if not"""
    try:
        provider = resource_client.providers.get(provider_namespace)

        if provider.registration_state != "Registered":
            logging.info(
                "Resource provider %s is not registered. Registering...",
                provider_namespace,
            )
            resource_client.providers.register(provider_namespace)
            logging.info(
                "Resource provider %s registered successfully.", provider_namespace
            )
        else:
            logging.info(
                "Resource provider %s is already registered.", provider_namespace
            )

        return True
    except Exception as e:
        logging.error(
            "Error checking/registering resource provider %s: %s",
            provider_namespace,
            str(e),
        )
        raise


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Key Vault provisioning API triggered.")

    try:
        # 1. Parse and Validate Request
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON body"}),
                status_code=400,
                mimetype="application/json",
            )

        required_fields = ["subscription_id", "appid", "environment", "region"]
        missing_fields = [field for field in required_fields if not req_body.get(field)]

        if missing_fields:
            return func.HttpResponse(
                json.dumps(
                    {"error": f"Missing required fields: {', '.join(missing_fields)}"}
                ),
                status_code=400,
                mimetype="application/json",
            )

        # 2. Extract Variables
        sub_id = req_body["subscription_id"]
        region = req_body["region"].strip()
        appid = get_clean_app_id(req_body["appid"])
        env = getenv(req_body["environment"])

        random_num = random.randint(100, 999)
        kv_name = f"kv-{appid}-{env}-{random_num}"
        rg_name = f"rg-{appid}-keyvaults"

        # 3. Resolve Identity & Tenant
        # ensure that managed identity has contributor access on the tenant (all subscriptions)
        mi_clientid = os.environ.get("ManagedIdentityClientID")
        if mi_clientid:
            credential = DefaultAzureCredential(managed_identity_client_id=mi_clientid)
        else:
            credential = DefaultAzureCredential()

        tenant_id = get_tenant_id(credential, sub_id)

        if not tenant_id:
            return func.HttpResponse(
                json.dumps({"error": "Unable to resolve Tenant ID"}),
                status_code=400,
                mimetype="application/json",
            )

        # 4. Initialize Clients & Provision
        resource_client = ResourceManagementClient(credential, sub_id)
        kv_client = KeyVaultManagementClient(credential, sub_id)

        # Ensure Microsoft.KeyVault resource provider is registered
        ensure_resource_provider_registered(resource_client, "Microsoft.KeyVault")

        # Ensure Resource Group exists
        resource_client.resource_groups.create_or_update(rg_name, {"location": region})

        # Provision Key Vault
        params = VaultCreateOrUpdateParameters(
            location=region,
            properties=VaultProperties(
                tenant_id=tenant_id,
                sku=Sku(name="standard", family="A"),
                enable_rbac_authorization=True,
                enable_purge_protection=True,
                access_policies=[],
            ),
        )

        poller = kv_client.vaults.begin_create_or_update(rg_name, kv_name, params)
        vault = poller.result()

        # 5. Success Response
        response_payload = {
            "status": "success",
            "message": f"Key Vault {kv_name} provisioned successfully",
            "details": {
                "keyvault_name": kv_name,
                "resource_group": rg_name,
                "region": region,
                "subscription_id": sub_id,
                "tenant_id": tenant_id,
                "vault_uri": vault.properties.vault_uri,
            },
        }

        return func.HttpResponse(
            json.dumps(response_payload, indent=4),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "error",
                    "message": "Failed to provision Key Vault",
                    "details": {"detailed_error": str(e)},
                }
            ),
            status_code=500,
            mimetype="application/json",
        )
