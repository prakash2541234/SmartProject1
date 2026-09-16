import json
import logging
import azure.functions as func


REQUIRED_KEYS = [
    "createnetwork-flow-nonprod_output",
    "CI_Build_status",
    "release_status",
    "Call_an_Azure_function_input",
    "Call_an_Azure_function_output",
    "ParseVNetPayload_input",
    "ParseVNetPayload_output"
]


def validate_createnetwork_output(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["createnetwork-flow-nonprod_output must be an object"]

    subscription_id = payload_value.get("subscription_id")
    if subscription_id is None or (isinstance(subscription_id, str) and subscription_id.strip() == ""):
        field_errors.append("subscription_id is missing")
    elif not isinstance(subscription_id, str):
        field_errors.append("subscription_id must be a string")

    stla_parameters = payload_value.get("stla_parameters")
    if stla_parameters is None:
        field_errors.append("stla_parameters is missing")
    elif not isinstance(stla_parameters, dict):
        field_errors.append("stla_parameters must be an object")

    az_parameters = payload_value.get("az_parameters")
    if az_parameters is None:
        field_errors.append("az_parameters is missing")
    elif not isinstance(az_parameters, dict):
        field_errors.append("az_parameters must be an object")

    return field_errors


def validate_call_an_azure_function_input(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["Call_an_Azure_function_input must be an object"]

    subscription_id = payload_value.get("subscription_id")
    if subscription_id is None or (isinstance(subscription_id, str) and subscription_id.strip() == ""):
        field_errors.append("subscription_id is missing")
    elif not isinstance(subscription_id, str):
        field_errors.append("subscription_id must be a string")

    stla_parameters = payload_value.get("stla_parameters")
    if stla_parameters is None:
        field_errors.append("stla_parameters is missing")
    elif not isinstance(stla_parameters, dict):
        field_errors.append("stla_parameters must be an object")
    else:
        required_stla_keys = [
            "application_id",
            "hle_usd",
            "support_email",
            "environment",
            "stla_global_business",
            "stla_global_subfunction",
            "sensitivity",
            "multi_tenant",
            "stla_region",
            "application_source",
            "application_name"
        ]
        for key in required_stla_keys:
            value = stla_parameters.get(key)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                field_errors.append(f"stla_parameters.{key} is missing")

    az_parameters = payload_value.get("az_parameters")
    if az_parameters is None:
        field_errors.append("az_parameters is missing")
    elif not isinstance(az_parameters, dict):
        field_errors.append("az_parameters must be an object")
    else:
        required_az_keys = ["azure_region", "network_domain", "network_model", "network_config", "backup_config", "sp_config"]
        for key in required_az_keys:
            if az_parameters.get(key) is None:
                field_errors.append(f"az_parameters.{key} is missing")

        azure_region = az_parameters.get("azure_region")
        if azure_region is not None and not isinstance(azure_region, str):
            field_errors.append("az_parameters.azure_region must be a string")

        network_domain = az_parameters.get("network_domain")
        if network_domain is not None and not isinstance(network_domain, str):
            field_errors.append("az_parameters.network_domain must be a string")

        network_model = az_parameters.get("network_model")
        if network_model is not None and not isinstance(network_model, str):
            field_errors.append("az_parameters.network_model must be a string")

        network_config = az_parameters.get("network_config")
        if network_config is not None:
            if not isinstance(network_config, list):
                field_errors.append("az_parameters.network_config must be an array")
            elif len(network_config) == 0:
                field_errors.append("az_parameters.network_config must contain at least one item")
            else:
                for index, config in enumerate(network_config):
                    if not isinstance(config, dict):
                        field_errors.append(f"az_parameters.network_config[{index}] must be an object")
                        continue

                    for key in ["vnet_name", "vnet", "region", "network_domain", "subnets"]:
                        if config.get(key) is None:
                            field_errors.append(f"az_parameters.network_config[{index}].{key} is missing")

                    for key in ["vnet_name", "vnet", "region", "network_domain"]:
                        value = config.get(key)
                        if value is not None and not isinstance(value, str):
                            field_errors.append(f"az_parameters.network_config[{index}].{key} must be a string")

                    subnets = config.get("subnets")
                    if subnets is not None:
                        if not isinstance(subnets, dict):
                            field_errors.append(f"az_parameters.network_config[{index}].subnets must be an object")
                        else:
                            for subnet_key in ["fe", "be", "GatewaySubnet"]:
                                subnet_value = subnets.get(subnet_key)
                                if subnet_value is None or (isinstance(subnet_value, str) and subnet_value.strip() == ""):
                                    field_errors.append(f"az_parameters.network_config[{index}].subnets.{subnet_key} is missing")
                                elif not isinstance(subnet_value, str):
                                    field_errors.append(f"az_parameters.network_config[{index}].subnets.{subnet_key} must be a string")

        backup_config = az_parameters.get("backup_config")
        if backup_config is not None:
            if not isinstance(backup_config, dict):
                field_errors.append("az_parameters.backup_config must be an object")
            else:
                for key in ["backup_enabled", "backup_replication_config", "replication_region"]:
                    if backup_config.get(key) is None:
                        field_errors.append(f"az_parameters.backup_config.{key} is missing")

                backup_enabled = backup_config.get("backup_enabled")
                if backup_enabled is not None and not isinstance(backup_enabled, bool):
                    field_errors.append("az_parameters.backup_config.backup_enabled must be a boolean")

                backup_replication_config = backup_config.get("backup_replication_config")
                if backup_replication_config is not None and not isinstance(backup_replication_config, str):
                    field_errors.append("az_parameters.backup_config.backup_replication_config must be a string")

                replication_region = backup_config.get("replication_region")
                if replication_region is not None and not isinstance(replication_region, str):
                    field_errors.append("az_parameters.backup_config.replication_region must be a string")

        sp_config = az_parameters.get("sp_config")
        if sp_config is not None:
            if not isinstance(sp_config, dict):
                field_errors.append("az_parameters.sp_config must be an object")
            else:
                for key in ["sp_requested", "sp_owners"]:
                    if sp_config.get(key) is None:
                        field_errors.append(f"az_parameters.sp_config.{key} is missing")

                sp_requested = sp_config.get("sp_requested")
                if sp_requested is not None and not isinstance(sp_requested, bool):
                    field_errors.append("az_parameters.sp_config.sp_requested must be a boolean")

                sp_owners = sp_config.get("sp_owners")
                if sp_owners is not None:
                    if not isinstance(sp_owners, list):
                        field_errors.append("az_parameters.sp_config.sp_owners must be an array")
                    elif len(sp_owners) == 0:
                        field_errors.append("az_parameters.sp_config.sp_owners must contain at least one item")
                    else:
                        for index, owner in enumerate(sp_owners):
                            if not isinstance(owner, str) or owner.strip() == "":
                                field_errors.append(f"az_parameters.sp_config.sp_owners[{index}] must be a non-empty string")

    return field_errors


def validate_call_an_azure_function_output(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["Call_an_Azure_function_output must be an object"]

    subscription_id = payload_value.get("subscription_id")
    if subscription_id is None or (isinstance(subscription_id, str) and subscription_id.strip() == ""):
        field_errors.append("subscription_id is missing")
    elif not isinstance(subscription_id, str):
        field_errors.append("subscription_id must be a string")

    resource_groups = payload_value.get("resource_groups")
    if resource_groups is None:
        field_errors.append("resource_groups is missing")
    elif not isinstance(resource_groups, list):
        field_errors.append("resource_groups must be an array")
    elif len(resource_groups) == 0:
        field_errors.append("resource_groups must contain at least one item")
    else:
        for index, rg_name in enumerate(resource_groups):
            if not isinstance(rg_name, str) or rg_name.strip() == "":
                field_errors.append(f"resource_groups[{index}] must be a non-empty string")

    vnets = payload_value.get("vnets")
    if vnets is None:
        field_errors.append("vnets is missing")
    elif not isinstance(vnets, list):
        field_errors.append("vnets must be an array")
    elif len(vnets) == 0:
        field_errors.append("vnets must contain at least one item")
    else:
        for index, vnet in enumerate(vnets):
            if not isinstance(vnet, dict):
                field_errors.append(f"vnets[{index}] must be an object")
                continue

            required_vnet_fields = [
                "name",
                "region",
                "vnet_size",
                "vnet_rg_name",
                "hub_vnet_id",
                "hub_vnet_peering_enabled",
                "vnet_peering_tohub_name",
                "vnet_peering_fromhub_name",
                "vnet_dns_servers",
                "ipam_pool"
            ]
            for key in required_vnet_fields:
                if vnet.get(key) is None:
                    field_errors.append(f"vnets[{index}].{key} is missing")

            for key in ["name", "region", "vnet_rg_name", "hub_vnet_id", "vnet_peering_tohub_name", "vnet_peering_fromhub_name", "ipam_pool"]:
                value = vnet.get(key)
                if value is not None and not isinstance(value, str):
                    field_errors.append(f"vnets[{index}].{key} must be a string")

            vnet_size = vnet.get("vnet_size")
            if vnet_size is not None and not isinstance(vnet_size, int):
                field_errors.append(f"vnets[{index}].vnet_size must be an integer")

            hub_vnet_peering_enabled = vnet.get("hub_vnet_peering_enabled")
            if hub_vnet_peering_enabled is not None and not isinstance(hub_vnet_peering_enabled, bool):
                field_errors.append(f"vnets[{index}].hub_vnet_peering_enabled must be a boolean")

            vnet_dns_servers = vnet.get("vnet_dns_servers")
            if vnet_dns_servers is not None:
                if not isinstance(vnet_dns_servers, list):
                    field_errors.append(f"vnets[{index}].vnet_dns_servers must be an array")
                elif len(vnet_dns_servers) == 0:
                    field_errors.append(f"vnets[{index}].vnet_dns_servers must contain at least one item")
                else:
                    for dns_index, dns_server in enumerate(vnet_dns_servers):
                        if not isinstance(dns_server, str) or dns_server.strip() == "":
                            field_errors.append(f"vnets[{index}].vnet_dns_servers[{dns_index}] must be a non-empty string")

    subnets = payload_value.get("subnets")
    if subnets is None:
        field_errors.append("subnets is missing")
    elif not isinstance(subnets, list):
        field_errors.append("subnets must be an array")
    elif len(subnets) == 0:
        field_errors.append("subnets must contain at least one item")
    else:
        for index, subnet in enumerate(subnets):
            if not isinstance(subnet, dict):
                field_errors.append(f"subnets[{index}] must be an object")
                continue

            required_subnet_fields = [
                "snet_name",
                "vnet_name",
                "rg_name",
                "region",
                "subnet_size",
                "ipam_pool",
                "route_enabled",
                "defaultroutetable"
            ]
            for key in required_subnet_fields:
                if subnet.get(key) is None:
                    field_errors.append(f"subnets[{index}].{key} is missing")

            for key in ["snet_name", "vnet_name", "rg_name", "region", "ipam_pool", "defaultroutetable"]:
                value = subnet.get(key)
                if value is not None and not isinstance(value, str):
                    field_errors.append(f"subnets[{index}].{key} must be a string")

            subnet_size = subnet.get("subnet_size")
            if subnet_size is not None and not isinstance(subnet_size, int):
                field_errors.append(f"subnets[{index}].subnet_size must be an integer")

            route_enabled = subnet.get("route_enabled")
            if route_enabled is not None and not isinstance(route_enabled, bool):
                field_errors.append(f"subnets[{index}].route_enabled must be a boolean")

    route_tables = payload_value.get("route_tables")
    if route_tables is None:
        field_errors.append("route_tables is missing")
    elif not isinstance(route_tables, list):
        field_errors.append("route_tables must be an array")
    elif len(route_tables) == 0:
        field_errors.append("route_tables must contain at least one item")
    else:
        for index, route_table in enumerate(route_tables):
            if not isinstance(route_table, dict):
                field_errors.append(f"route_tables[{index}] must be an object")
                continue

            required_route_table_fields = ["name", "vnet_name", "rg_name", "region", "next_hop_ip"]
            for key in required_route_table_fields:
                value = route_table.get(key)
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    field_errors.append(f"route_tables[{index}].{key} is missing")
                elif not isinstance(value, str):
                    field_errors.append(f"route_tables[{index}].{key} must be a string")

    return field_errors


def validate_parse_vnet_payload_output(payload_value):
    field_errors = []

    if not isinstance(payload_value, dict):
        return ["ParseVNetPayload_output must be an object"]

    subscription_id = payload_value.get("subscription_id")
    if subscription_id is None or (isinstance(subscription_id, str) and subscription_id.strip() == ""):
        field_errors.append("subscription_id is missing")
    elif not isinstance(subscription_id, str):
        field_errors.append("subscription_id must be a string")

    resource_groups = payload_value.get("resource_groups")
    if resource_groups is None:
        field_errors.append("resource_groups is missing")
    elif not isinstance(resource_groups, list):
        field_errors.append("resource_groups must be an array")
    else:
        for index, resource_group in enumerate(resource_groups):
            if not isinstance(resource_group, str) or resource_group.strip() == "":
                field_errors.append(f"resource_groups[{index}] must be a non-empty string")

    vnets = payload_value.get("vnets")
    if vnets is None:
        field_errors.append("vnets is missing")
    elif not isinstance(vnets, list):
        field_errors.append("vnets must be an array")
    else:
        for index, vnet in enumerate(vnets):
            if not isinstance(vnet, dict):
                field_errors.append(f"vnets[{index}] must be an object")
                continue

            required_vnet_fields = [
                "name",
                "region",
                "vnet_size",
                "vnet_rg_name",
                "hub_vnet_id",
                "hub_vnet_peering_enabled",
                "vnet_peering_tohub_name",
                "vnet_peering_fromhub_name",
                "vnet_dns_servers",
                "ipam_pool"
            ]
            for key in required_vnet_fields:
                if vnet.get(key) is None:
                    field_errors.append(f"vnets[{index}].{key} is missing")

            for key in ["name", "region", "vnet_rg_name", "hub_vnet_id", "vnet_peering_tohub_name", "vnet_peering_fromhub_name", "ipam_pool"]:
                value = vnet.get(key)
                if value is not None and not isinstance(value, str):
                    field_errors.append(f"vnets[{index}].{key} must be a string")

            vnet_size = vnet.get("vnet_size")
            if vnet_size is not None and not isinstance(vnet_size, int):
                field_errors.append(f"vnets[{index}].vnet_size must be an integer")

            hub_vnet_peering_enabled = vnet.get("hub_vnet_peering_enabled")
            if hub_vnet_peering_enabled is not None and not isinstance(hub_vnet_peering_enabled, bool):
                field_errors.append(f"vnets[{index}].hub_vnet_peering_enabled must be a boolean")

            vnet_dns_servers = vnet.get("vnet_dns_servers")
            if vnet_dns_servers is not None:
                if not isinstance(vnet_dns_servers, list):
                    field_errors.append(f"vnets[{index}].vnet_dns_servers must be an array")
                else:
                    for dns_index, dns_server in enumerate(vnet_dns_servers):
                        if not isinstance(dns_server, str) or dns_server.strip() == "":
                            field_errors.append(f"vnets[{index}].vnet_dns_servers[{dns_index}] must be a non-empty string")

    subnets = payload_value.get("subnets")
    if subnets is None:
        field_errors.append("subnets is missing")
    elif not isinstance(subnets, list):
        field_errors.append("subnets must be an array")
    else:
        for index, subnet in enumerate(subnets):
            if not isinstance(subnet, dict):
                field_errors.append(f"subnets[{index}] must be an object")
                continue

            required_subnet_fields = ["snet_name", "vnet_name", "rg_name", "region", "subnet_size"]
            for key in required_subnet_fields:
                if subnet.get(key) is None:
                    field_errors.append(f"subnets[{index}].{key} is missing")

            for key in ["snet_name", "vnet_name", "rg_name", "region"]:
                value = subnet.get(key)
                if value is not None and not isinstance(value, str):
                    field_errors.append(f"subnets[{index}].{key} must be a string")

            subnet_size = subnet.get("subnet_size")
            if subnet_size is not None and not isinstance(subnet_size, int):
                field_errors.append(f"subnets[{index}].subnet_size must be an integer")

    route_tables = payload_value.get("route_tables")
    if route_tables is None:
        field_errors.append("route_tables is missing")
    elif not isinstance(route_tables, list):
        field_errors.append("route_tables must be an array")
    else:
        for index, route_table in enumerate(route_tables):
            if not isinstance(route_table, dict):
                field_errors.append(f"route_tables[{index}] must be an object")
                continue

            required_route_table_fields = ["name", "vnet_name", "rg_name", "region", "next_hop_ip"]
            for key in required_route_table_fields:
                value = route_table.get(key)
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    field_errors.append(f"route_tables[{index}].{key} is missing")
                elif not isinstance(value, str):
                    field_errors.append(f"route_tables[{index}].{key} must be a string")

    return field_errors


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Strict workflow monitoring function triggered")

    try:
        body = req.get_json()

        if not isinstance(body, dict):
            return func.HttpResponse(
                json.dumps({
                    "status": "FAILED",
                    "message": "Input payload must be a JSON object"
                }, indent=2),
                status_code=400,
                mimetype="application/json"
            )

        missing_fields = []
        invalid_fields = {}
        for key in REQUIRED_KEYS:
            value = body.get(key)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing_fields.append(key)

        ci_build_status = body.get("CI_Build_status")
        if ci_build_status is not None:
            ci_build_errors = []
            if not isinstance(ci_build_status, str):
                ci_build_errors.append("CI_Build_status must be a string")
            elif ci_build_status.strip().lower() != "inprogress":
                ci_build_errors.append("CI_Build_status must be inprogress")
            if ci_build_errors:
                invalid_fields["CI_Build_status"] = ci_build_errors

        release_status = body.get("release_status")
        if release_status is not None:
            release_status_errors = []
            if not isinstance(release_status, str):
                release_status_errors.append("release_status must be a string")
            elif release_status.strip().lower() != "inprogress":
                release_status_errors.append("release_status must be inprogress")
            if release_status_errors:
                invalid_fields["release_status"] = release_status_errors

        createnetwork_payload = body.get("createnetwork-flow-nonprod_output")
        if createnetwork_payload is not None:
            createnetwork_errors = validate_createnetwork_output(createnetwork_payload)
            if createnetwork_errors:
                invalid_fields["createnetwork-flow-nonprod_output"] = createnetwork_errors

        call_an_azure_function_input_payload = body.get("Call_an_Azure_function_input")
        if call_an_azure_function_input_payload is not None:
            call_an_azure_function_input_errors = validate_call_an_azure_function_input(call_an_azure_function_input_payload)
            if call_an_azure_function_input_errors:
                invalid_fields["Call_an_Azure_function_input"] = call_an_azure_function_input_errors

        call_an_azure_function_output_payload = body.get("Call_an_Azure_function_output")
        if call_an_azure_function_output_payload is not None:
            call_an_azure_function_output_errors = validate_call_an_azure_function_output(call_an_azure_function_output_payload)
            if call_an_azure_function_output_errors:
                invalid_fields["Call_an_Azure_function_output"] = call_an_azure_function_output_errors

        parse_vnet_payload_output_payload = body.get("ParseVNetPayload_output")
        if parse_vnet_payload_output_payload is not None:
            parse_vnet_payload_output_errors = validate_parse_vnet_payload_output(parse_vnet_payload_output_payload)
            if parse_vnet_payload_output_errors:
                invalid_fields["ParseVNetPayload_output"] = parse_vnet_payload_output_errors

        if missing_fields or invalid_fields:
            missing_details = {field: "This field is missing" for field in missing_fields}
            return func.HttpResponse(
                json.dumps({
                    "status": "FAILED",
                    "message": "Input validation failed",
                    "missing_fields": missing_details,
                    "invalid_fields": invalid_fields
                }, indent=2),
                status_code=400,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps({
                "status": "SUCCESS",
                "message": "VNet_first.py ran successfully without missing fields"
            }, indent=2),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError:
        return func.HttpResponse(
            json.dumps({
                "error": "Invalid JSON payload"
            }),
            status_code=400
        )

    except Exception as e:
        logging.error(str(e))
        return func.HttpResponse(
            json.dumps({
                "error": str(e)
            }),
            status_code=500
        )