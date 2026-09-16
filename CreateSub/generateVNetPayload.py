import json
import logging
import random
import string
import ipaddress
from typing import Dict, List
import azure.functions as func

def generate_random_suffix(length: int = 3) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def calculate_ip_count(netmask: int) -> int:
    return 2 ** (32 - netmask)

def generate_ip_pool(base_ip: str, netmask: int, count: int) -> List[str]:
    network = ipaddress.ip_network(f"{base_ip}/{netmask}", strict=False)
    return [str(ip) for ip in network.hosts()][:count]

def build_vnet_name(app_id: str, environment: str, sensitivity: str, city: str, suffix: str) -> str:
    return f"vnet-{app_id}-{environment}-{sensitivity}-{city}-{suffix}"

def build_subnet_name(app_id: str, subnet_key: str, environment: str, sensitivity: str, suffix: str) -> str:
    return f"snet-{app_id}-{subnet_key}-{environment}-{sensitivity}-{suffix}"

def build_route_table_name(domain: str, city: str) -> str:
    return f"rt-default-{domain}-{city}"

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        request_payload = req.get_json()

        subscription_id = request_payload.get("subscription_id", "")
        stla_parameters = request_payload.get("stla_parameters", {})
        az_parameters = request_payload.get("az_parameters", {})

        app_id = stla_parameters.get("application_id", "").lower()
        environment = stla_parameters.get("environment", "prod").lower()
        region = az_parameters.get("azure_region", "").lower()
        network_domain = az_parameters.get("network_domain", "default").lower()
        sensitivity = az_parameters.get("sensitivity", "standard").lower()
        network_config = az_parameters.get("network_config", [])

        resource_groups = []
        vnets = []
        subnets = []
        route_tables = []

        for vnet in network_config:
            vnet_netmask = int(vnet.get("vnet", "/24").lstrip("/"))
            vnet_ip_count = calculate_ip_count(vnet_netmask)
            vnet_region = vnet.get("region", region).lower()
            vnet_suffix = generate_random_suffix()

            vnet_name = build_vnet_name(app_id, environment, sensitivity, vnet_region, vnet_suffix)
            vnet_rg_name = f"rg-{app_id}-{environment}-{sensitivity}-{vnet_region}-{generate_random_suffix()}"

            resource_groups.append(vnet_rg_name)

            vnets.append({
                "name": vnet_name,
                "region": vnet_region,
                "vnet_size": vnet_ip_count,
                "vnet_rg_name": vnet_rg_name,
                "ip_pool": generate_ip_pool("10.0.0.0", vnet_netmask, vnet_ip_count)
            })

            for subnet_key, subnet_mask in vnet.get("subnets", {}).items():
                subnet_netmask = int(subnet_mask.lstrip("/"))
                subnet_ip_count = calculate_ip_count(subnet_netmask)
                subnet_suffix = generate_random_suffix()

                subnet_name = build_subnet_name(app_id, subnet_key, environment, sensitivity, subnet_suffix)

                subnets.append({
                    "snet_name": subnet_name,
                    "vnet_name": vnet_name,
                    "rg_name": vnet_rg_name,
                    "region": vnet_region,
                    "subnet_size": subnet_ip_count,
                    "ip_pool": generate_ip_pool("10.0.0.0", subnet_netmask, subnet_ip_count)
                })

            route_table_name = build_route_table_name(network_domain, vnet_region)
            route_tables.append({
                "name": route_table_name,
                "vnet_name": vnet_name,
                "rg_name": vnet_rg_name,
                "region": vnet_region,
                "next_hop_ip": "10.0.0.1"
            })

        response_payload = {
            "subscription_id": subscription_id,
            "resource_groups": resource_groups,
            "vnets": vnets,
            "subnets": subnets,
            "route_tables": route_tables
        }

        return func.HttpResponse(
            json.dumps(response_payload, indent=2),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error("Error processing VNet payload: %s", str(e))
        return func.HttpResponse(
            json.dumps({"error": "Internal Server Error", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )