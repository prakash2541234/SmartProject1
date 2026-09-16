import json
import azure.functions as func
import random
import string

# -------------------------------
# Helper Functions
# -------------------------------

def generate_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase, k=length))


def cidr_to_size(cidr):
    return 2 ** (32 - int(cidr.replace("/", "")))


def region_short(region):
    mapping = {
        "northeurope": "dublin",
        "francecentral": "paris"
    }
    return mapping.get(region.lower(), region)


def get_ipam_pool(index):
    return f"10.{index}.0.0/16"


def get_subnet_pool(vnet_index, subnet_index):
    return f"10.{vnet_index}.{subnet_index}.0/24"


def get_next_hop(region):
    mapping = {
        "northeurope": "10.165.239.46",
        "francecentral": "10.165.239.174"
    }
    return mapping.get(region.lower(), "10.0.0.1")


def get_dns_servers(region):
    if region == "northeurope":
        return ["10.165.95.4", "10.165.31.4"]
    else:
        return ["10.165.31.4", "10.165.95.4"]


# -------------------------------
# Main Function
# -------------------------------

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()

        subscription_id = body.get("subscription_id")
        stla = body.get("stla_parameters", {})
        az = body.get("az_parameters", {})

        app_id = stla.get("application_id").lower()
        env = stla.get("environment").lower()
        sensitivity = az.get("sensitivity", "std")

        network_configs = az.get("network_config", [])

        resource_groups = []
        vnets = []
        subnets = []
        route_tables = []

        for vnet_index, net in enumerate(network_configs):
            region = net.get("region").lower()
            region_code = region_short(region)

            rg_suffix = generate_suffix()
            vnet_suffix = generate_suffix()

            rg_name = f"rg-{app_id}-{env}-{sensitivity}-{region_code}-{rg_suffix}"
            vnet_name = f"vnet-{app_id}-{env}-{sensitivity}-{region_code}-{vnet_suffix}"

            resource_groups.append(rg_name)

            # VNET
            vnet_obj = {
                "name": net.get("vnet_name", vnet_name),
                "region": region,
                "vnet_size": cidr_to_size(net.get("vnet")),
                "vnet_rg_name": rg_name,
                "hub_vnet_id": f"/subscriptions/xxxx/resourceGroups/rg-trv-{env}-secu-xp-{region_code}/providers/Microsoft.Network/virtualNetworks/vnet-trv-{env}-secu-xp-{region_code}",
                "hub_vnet_peering_enabled": True,
                "vnet_peering_tohub_name": f"peering-{app_id}-{env}-{sensitivity}-trv-secu-xp-{region_code}",
                "vnet_peering_fromhub_name": f"peering-trv-secu-xp-{region_code}-{app_id}-{env}-{sensitivity}",
                "vnet_dns_servers": get_dns_servers(region),
                "ipam_pool": get_ipam_pool(vnet_index)
            }

            vnets.append(vnet_obj)

            # Route Table
            rt_name = f"rt-default-xp-{region_code}"

            route_tables.append({
                "name": rt_name,
                "vnet_name": vnet_name,
                "rg_name": rg_name,
                "region": region,
                "next_hop_ip": get_next_hop(region)
            })

            # Subnets
            for subnet_index, (snet_name, cidr) in enumerate(net.get("subnets", {}).items()):
                snet_suffix = generate_suffix()

                subnet_obj = {
                    "snet_name": f"snet-{app_id}-{snet_name.lower()}-{env}-{sensitivity}-{snet_suffix}",
                    "vnet_name": vnet_name,
                    "rg_name": rg_name,
                    "region": region,
                    "subnet_size": cidr_to_size(cidr),
                    "ipam_pool": get_subnet_pool(vnet_index, subnet_index + 1),
                    "route_enabled": True,
                    "defaultroutetable": rt_name
                }

                subnets.append(subnet_obj)

        response = {
            "subscription_id": subscription_id,
            "resource_groups": resource_groups,
            "vnets": vnets,
            "subnets": subnets,
            "route_tables": route_tables
        }

        return func.HttpResponse(
            json.dumps(response, indent=2),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        return func.HttpResponse(str(e), status_code=500)