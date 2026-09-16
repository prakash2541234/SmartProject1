"""
This function is triggered to process VNet payload.
The inputs is original API payload sent by digital me 
output is the actaul payload required for VNet creation
"""
import logging
import re
import traceback
import ipaddress
import random
import string
import json
import os
import azure.functions as func

# Hub VNet constants for peering with spoke VNets
HUB_VNETS = {
    "xp_francecentral": "/subscriptions/4e09edb6-a2bf-4ee5-bf7c-64ec8e2de99e/resourceGroups/rg-trv-prod-secu-xp-paris/providers/Microsoft.Network/virtualNetworks/vnet-trv-prod-secu-xp-paris",
    "xf_francecentral": "/subscriptions/4e09edb6-a2bf-4ee5-bf7c-64ec8e2de99e/resourceGroups/rg-trv-prod-secu-xf-paris/providers/Microsoft.Network/virtualNetworks/vnet-trv-prod-secu-xf-paris",
    "xp_northeurope": "/subscriptions/4e09edb6-a2bf-4ee5-bf7c-64ec8e2de99e/resourceGroups/rg-trv-prod-secu-xp-dublin/providers/Microsoft.Network/virtualNetworks/vnet-trv-prod-secu-xp-dublin",
    "xf_northeurope": "/subscriptions/4e09edb6-a2bf-4ee5-bf7c-64ec8e2de99e/resourceGroups/rg-trv-prod-secu-xf-dublin/providers/Microsoft.Network/virtualNetworks/vnet-trv-prod-secu-xf-dublin",
    "xf_eastus": "/subscriptions/4e09edb6-a2bf-4ee5-bf7c-64ec8e2de99e/resourceGroups/rg-trv-prod-secu-xf-eastus/providers/Microsoft.Network/virtualNetworks/vnet-trv-prod-secu-xf-eastus",
    "xp_brazilsouth": "/subscriptions/4e09edb6-a2bf-4ee5-bf7c-64ec8e2de99e/resourceGroups/rg-trv-prod-secu-xp-saopaulo/providers/Microsoft.Network/virtualNetworks/vnet-trv-prod-secu-xp-saopaulo",
    "xp_centralindia": "/subscriptions/4e09edb6-a2bf-4ee5-bf7c-64ec8e2de99e/resourceGroups/rg-trv-prod-secu-xp-pune/providers/Microsoft.Network/virtualNetworks/vnet-trv-prod-secu-xp-pune"
}

# Load IPAM pools once at module level (executes on cold start)
def load_ipam_pools(file_path='azglz_avnm_ipampool_mapping.json'):
    """Load IPAM pools from JSON file"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, file_path) 
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning("IPAM pools file not found at %s, using empty dict", file_path)
        return {}
    except json.JSONDecodeError:
        logging.error("Invalid JSON in IPAM pools file %s", file_path)
        return {}

IPAM_POOLS = load_ipam_pools()

vnet_dns = {
  "xp_northeurope"   : ["10.165.95.4", "10.165.31.4"],
  "xp_francecentral"    : ["10.165.31.4", "10.165.95.4"],
  "xf_northeurope"   : ["10.50.95.4", "10.50.31.4"],
  "xf_francecentral"    : ["10.50.31.4", "10.50.95.4"],
  "xf_eastus"   : ["10.219.31.4", "10.50.95.4"],
  "xp_brazilsouth" : ["10.45.135.4", "10.165.31.4"],
  "xp_centralindia"     : ["10.45.131.4", "10.165.31.4"]
}

route_next_hop_ips = {
  "xp_paris"    : "10.165.239.174",
  "xf_paris"    : "10.50.239.174",
  "xp_dublin"   : "10.165.239.46",
  "xf_dublin"   : "10.50.239.46",
  "xf_eastus"   : "10.219.239.174",
  "xp_saopaulo" : "10.165.238.46",
  "xp_pune"     : "10.165.238.174"
}

def get_clean_app_id(appid):
    """This function converts application id to a short form to use in subscription name"""
    appid = appid.lower()
    appid = re.sub(r'[^a-z0-9]', '', appid)

    return appid
def getenv(environment):
    """Convert environment to standardized short form"""
    env_mapping = {
        'production': 'prod',
        'prod': 'prod',
        'non-production': 'np',
        'nonproduction': 'np',
        'non-prod': 'np',
        'nonprod': 'np',
        'np': 'np',
        'development': 'np',
        'dev': 'np',
        'testing': 'np',
        'test': 'np',
        'staging': 'np',
        'stage': 'np',
        'poc': 'np'
    }
    return env_mapping.get(environment.lower(), 'prod')

def getvnetcity(region):
    """This function maps azure region to city for VNET hub selection"""
    region_city_map = {
        "francecentral": "paris",
        "northeurope": "dublin",
        "eastus": "eastus", #due to naming of other foundation resources in east us, keeping it same
        "brazilsouth": "saopaulo",
        "centralindia": "pune"
    }
    return region_city_map.get(region.lower(), "")

def getsensitivyabbrv(sensitivity):
    """This function retrieves sensitive information required for VNet processing"""
    sensitivity_map = {
        "standard": "std",
        "std": "std",
        "sensitive": "s3",
        "s3": "s3",
        "highlysensitive": "s4",

    }
    return sensitivity_map.get(sensitivity.lower(), "std")

def main(req: func.HttpRequest) -> func.HttpResponse:
    """this function processes the payload coming through logic app and 
    create various payloads for VNet creation."""
    logging.info('processing VNet payload request.')
    try:
        request_payload = req.get_json()
        sub_id = request_payload.get('subscription_id', '')
        subrequest_params = request_payload.get('stla_parameters', {})
        az_parameters = request_payload.get('az_parameters', {})

        #default region to be used for VNET
        app_id = subrequest_params.get('application_id', '')
        app_id_clean = get_clean_app_id(app_id)
        app_environment = getenv(subrequest_params.get('environment', 'prod')).lower()

        default_vnet_region = az_parameters.get('azure_region', '').lower()
        default_network_domain = az_parameters.get('network_domain', '')
        if not default_network_domain:
            default_network_domain = az_parameters.get('network_routing', '')
        default_network_domain = default_network_domain.lower()
        app_network_model = az_parameters.get('network_model', 'standalone').lower()
        app_sensitivity = getsensitivyabbrv(az_parameters.get('sensitivity', 'standard')).lower()

        vnet_config = az_parameters.get('network_config', [])
        rg_random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))

        rgs = []
        vnets = []
        subnets = []
        route_tables = []

        for vnet in vnet_config:
            vnet_netmask = vnet.get('vnet', '')
            # Remove preceding / if present and ensure it's an integer
            if isinstance(vnet_netmask, str):
                vnet_netmask = vnet_netmask.lstrip('/')
            vnet_netmask = int(vnet_netmask) if vnet_netmask else 0
            # Calculate IP count from netmask (e.g., /24 -> 256 addresses)
            vnet_ip_count = 2 ** (32 - vnet_netmask)
            vnet_region = vnet.get('region', default_vnet_region).lower()
            vnet_network_domain = vnet.get('network_domain', default_network_domain).lower()
            vnet_random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
            vnet_city = getvnetcity(vnet_region)
            vnet_name = f"vnet-{app_id_clean}-{app_environment}-{app_sensitivity}-{vnet_city}-{vnet_random_suffix}"
            vnet_rg_name = f"rg-{app_id_clean}-{app_environment}-{app_sensitivity}-{vnet_city}-{rg_random_suffix}"
            vnet_dns_servers = vnet_dns.get(f"{vnet_network_domain}_{vnet_region}", [])
            route_table_name = f"rt-default-{vnet_network_domain}-{vnet_city}"

            vnets.append({
                "name": vnet_name,
                "region": vnet_region,
                "vnet_size": vnet_ip_count,
                "vnet_rg_name": vnet_rg_name,
                "hub_vnet_id": HUB_VNETS.get(f"{vnet_network_domain}_{vnet_region}", "") if app_network_model == "on-prem" else "",
                "hub_vnet_peering_enabled": True if app_network_model == "on-prem" else False,
                "vnet_peering_tohub_name": f"peering-{app_id_clean}-{app_environment}-{app_sensitivity}-trv-secu-{vnet_network_domain}-{vnet_city}" if app_network_model == "on-prem" else "",
                "vnet_peering_fromhub_name": f"peering-trv-secu-{vnet_network_domain}-{vnet_city}-{app_id_clean}-{app_environment}-{app_sensitivity}" if app_network_model == "on-prem" else "",
                "vnet_dns_servers": vnet_dns_servers if app_network_model == "on-prem" else [],
                "ipam_pool": IPAM_POOLS.get(f"{vnet_network_domain}_{vnet_region}_{app_network_model}_{app_environment}", "")
            })

            if vnet_rg_name not in rgs:
                rgs.append(vnet_rg_name)

            subnet_config = vnet.get('subnets', [])
            for subnet in subnet_config:
                subnet_name_key = subnet
                subnet_netmask = subnet_config[subnet]
                # Remove preceding / if present
                if isinstance(subnet_netmask, str):
                    subnet_netmask = subnet_netmask.lstrip('/')
                subnet_netmask = int(subnet_netmask) if subnet_netmask else 0
                # Calculate IP count from netmask
                subnet_ip_count = 2 ** (32 - subnet_netmask)
                snet_random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))

                if subnet_name_key.lower() in ["azurefirewallsubnet", "azurebastionsubnet", "gatewaysubnet"]:
                    subnet_name = subnet_name_key
                else:
                    subnet_name = f"snet-{app_id_clean}-{subnet_name_key.lower()}-{app_environment}-{app_sensitivity}-{snet_random_suffix}"
                
                subnets.append({
                    "snet_name": subnet_name,
                    "vnet_name": vnet_name,
                    "rg_name": vnet_rg_name,
                    "region": vnet_region,
                    "subnet_size": subnet_ip_count,
                    "ipam_pool": IPAM_POOLS.get(f"{vnet_network_domain}_{vnet_region}_{app_network_model}_{app_environment}", ""),
                    "route_enabled": True if app_network_model == "on-prem" else False,
                    "defaultroutetable": route_table_name if app_network_model == "on-prem" else ""
                })

            if route_table_name not in [rt["rt_name"] for rt in route_tables]:
                route_tables.append({
                    "name": route_table_name,
                    "vnet_name": vnet_name,
                    "rg_name": vnet_rg_name,
                    "region": vnet_region,
                    "next_hop_ip": route_next_hop_ips.get(f"{vnet_network_domain}_{vnet_city}", "")
                })


        vnet_payload = {
            "subscription_id": sub_id,
            "resource_groups": rgs,
            "vnets": vnets,
            "subnets": subnets,
            "route_tables": route_tables if app_network_model == "on-prem" else []
        }

        return json.dumps(vnet_payload)
    except Exception as e:
        logging.error('Processing request for VNet payload - general exception captured.')
        logging.error(traceback.format_exc())
        return func.HttpResponse(
            body="Error: Unable to process your VNet request payload data. If problem persist please connect with Azure Foundation Team. Error Details - " + str(e),
            status_code=500,
            mimetype="application/json"
        )
        