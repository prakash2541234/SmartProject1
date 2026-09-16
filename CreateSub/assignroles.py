"""
This Azure Function assigns RBAC roles to specified principals (users or groups) at the subscription level.
It uses the Azure SDK for Python to interact with Azure Resource Manager and Microsoft Graph API.
Along with role assignment, it also add the principal to a local Entra ID group if the assigned role is 'manager' or 'standard'.
"""

import json
import logging
import os
import uuid
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.core.exceptions import HttpResponseError
from msgraph import GraphServiceClient
from msgraph.generated.groups.groups_request_builder import GroupsRequestBuilder
from msgraph.generated.users.users_request_builder import UsersRequestBuilder
from msgraph.generated.models.reference_create import ReferenceCreate

# Initialize Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


class RoleAssignmentManager:
    """Manages Azure RBAC role assignments using Azure SDK."""

    # Azure built-in role definitions
    BUILTIN_ROLES = {
        "Owner": "8e3af657-a8ff-443c-a75c-2fe8c4bcb635",
        "Contributor": "b24988ac-6180-42a0-ab88-20f7382dd24c",
        "Reader": "acdd72a7-3385-48ef-bd42-f606fba81ae7",
        "User Access Administrator": "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9",
        "Storage Blob Data Contributor": "ba92f5b4-2d11-453d-a403-e96b0029c9fe",
    }

    # Custom role name mappings
    ROLE_MAPPINGS = {"manager": "Owner", "standard": "Contributor", "view": "Reader"}

    def __init__(self, subscription_id):
        """Initialize the manager with Azure credentials."""
        mi_client_id_rbac = os.environ.get("ManagedIdentityClientID")
        mi_client_id_graph = os.environ.get("ManagedIdentityClientID_AppReg")

        # RBAC: Use ManagedIdentityClientID
        self.credential_rbac = (
            DefaultAzureCredential(managed_identity_client_id=mi_client_id_rbac)
            if mi_client_id_rbac
            else DefaultAzureCredential()
        )

        # Graph: Use ManagedIdentityClientID_AppReg
        self.credential_graph = (
            DefaultAzureCredential(managed_identity_client_id=mi_client_id_graph)
            if mi_client_id_graph
            else DefaultAzureCredential()
        )

        self.subscription_id = subscription_id
        self.auth_client = AuthorizationManagementClient(
            credential=self.credential_rbac, subscription_id=subscription_id
        )
        self.graph_client = GraphServiceClient(credentials=self.credential_graph)

    async def find_principal(self, principal_name):
        """
        Find an Azure AD principal (group or user) by name.
        Returns (principal_id, principal_type) or (None, None) if not found.
        """
        # Search for group
        group_id = await self._search_group(principal_name)
        if group_id:
            return group_id, "Group"

        # Search for user
        user_id = await self._search_user(principal_name)
        if user_id:
            return user_id, "User"

        logging.error("Could not find principal '%s' in Azure AD", principal_name)
        return None, None

    async def _search_group(self, name):
        """Search for group by display name."""
        try:
            config = GroupsRequestBuilder.GroupsRequestBuilderGetRequestConfiguration(
                query_parameters=GroupsRequestBuilder.GroupsRequestBuilderGetQueryParameters(
                    filter=f"displayName eq '{name}'", select=["id", "displayName"]
                )
            )
            groups = await self.graph_client.groups.get(request_configuration=config)
            if groups and groups.value:
                logging.info("Found group '%s' - ID: %s", name, groups.value[0].id)
                return groups.value[0].id
        except Exception as e:
            logging.warning("Error searching for group '%s': %s", name, e)
        return None

    async def _search_user(self, name):
        """Search for user by UPN or display name."""
        try:
            # Try UPN lookup first
            try:
                user = await self.graph_client.users.by_user_id(name).get()
                if user:
                    logging.info("Found user by UPN '%s' - ID: %s", name, user.id)
                    return user.id
            except:
                pass

            # Search by display name
            config = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
                query_parameters=UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
                    filter=f"displayName eq '{name}'", select=["id", "displayName"]
                )
            )
            users = await self.graph_client.users.get(request_configuration=config)
            if users and users.value:
                logging.info("Found user '%s' - ID: %s", name, users.value[0].id)
                return users.value[0].id
        except Exception as e:
            logging.warning("Error searching for user '%s': %s", name, e)
        return None

    def get_role_definition_id(self, role_name):
        """Get the full role definition ID for a built-in role or custom role."""
        role_id = self.BUILTIN_ROLES.get(role_name)
        if role_id:
            return f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/{role_id}"

        # If not found in built-in roles, search for custom role at subscription level
        try:
            roles = self.auth_client.role_definitions.list(
                scope=f"/subscriptions/{self.subscription_id}",
                filter=f"roleName eq '{role_name}'",
            )
            for role in roles:
                if role.role_name.lower() == role_name.lower():
                    logging.info("Found custom role '%s' - ID: %s", role_name, role.id)
                    return role.id
        except Exception as e:
            logging.warning("Error searching for custom role '%s': %s", role_name, e)

        logging.error("Unknown role: %s", role_name)
        return None

    def check_existing_assignment(self, principal_id, role_definition_id):
        """Check if a role assignment already exists."""
        try:
            assignments = self.auth_client.role_assignments.list_for_scope(
                scope=f"/subscriptions/{self.subscription_id}",
                filter=f"principalId eq '{principal_id}'",
            )
            return any(a.role_definition_id == role_definition_id for a in assignments)
        except Exception as e:
            logging.warning("Error checking existing assignments: %s", e)
            return False

    def assign_role(self, principal_id, principal_type, role_name):
        """Assign a role to a principal at subscription level."""
        try:
            role_definition_id = self.get_role_definition_id(role_name)
            if not role_definition_id:
                return False

            if self.check_existing_assignment(principal_id, role_definition_id):
                logging.info("Role '%s' already assigned (skipping)", role_name)
                return True

            self.auth_client.role_assignments.create(
                scope=f"/subscriptions/{self.subscription_id}",
                role_assignment_name=str(uuid.uuid4()),
                parameters={
                    "role_definition_id": role_definition_id,
                    "principal_id": principal_id,
                    "principal_type": principal_type,
                },
            )
            logging.info("Successfully assigned role '%s'", role_name)
            return True

        except HttpResponseError as e:
            if "RoleAssignmentExists" in str(e):
                logging.info("Role '%s' already assigned", role_name)
                return True
            logging.error("Error assigning role '%s': %s", role_name, e.message)
            return False
        except Exception as e:
            logging.error("Error assigning role '%s': %s", role_name, e)
            return False


async def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Function to assign RBAC roles to principals in a subscription.

    Expected JSON body:
    {
        "subscription_id": "xyz",
        "subscription_access": {
            "manager": "Group or User Name",
            "standard": "Group or User Name",
            "view": "Group or User Name"
        },
        "request_parameters": {
            "requester": {
                "first_name": "John",
                "last_name": "Doe"
            },
            "catalog_task_sysid": "691d888f93f27250d2e6fc3d6cba108a",
            "ritm_number": "RITM0123456"
        }
    }
    """
    logging.info("Processing role assignment request")

    try:
        # Parse request body
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON in request body"}),
                status_code=400,
                mimetype="application/json",
            )

        # Extract configuration values
        subscription_id = req_body.get("subscription_id")
        subscription_access = req_body.get("subscription_access", {})
        request_params = req_body.get("request_parameters", {})

        if not subscription_id:
            return func.HttpResponse(
                json.dumps(
                    {
                        "status": "error",
                        "message": "'subscription_id' is required",
                        "details": {},
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        logging.info("Subscription ID: %s", subscription_id)
        requester = request_params.get("requester", {})
        logging.info(
            "Requester: %s %s",
            requester.get("first_name", ""),
            requester.get("last_name", ""),
        )
        logging.info("RITM Number: %s", request_params.get("ritm_number", "N/A"))

        # Initialize the role assignment manager
        logging.info("Initializing Azure SDK clients...")
        manager = RoleAssignmentManager(subscription_id)

        # Process each role assignment
        logging.info("Processing role assignments...")

        success_count = 0
        failure_count = 0
        skipped_count = 0
        results = []

        for role_key, principal_name in subscription_access.items():
            if not principal_name or principal_name.strip() == "":
                logging.info("Skipping '%s' - no principal name provided", role_key)
                skipped_count += 1
                results.append(
                    {
                        "role": role_key,
                        "principal": principal_name,
                        "status": "skipped",
                        "message": "No principal name provided",
                    }
                )
                continue

            logging.info(
                "Processing role '%s' for principal '%s'", role_key, principal_name
            )

            # Find the principal in Azure AD
            principal_id, principal_type = await manager.find_principal(principal_name)

            if not principal_id:
                failure_count += 1
                results.append(
                    {
                        "role": role_key,
                        "principal": principal_name,
                        "status": "failed",
                        "message": f"Could not find principal in Azure AD",
                    }
                )
                continue

            # Map custom role to built-in role
            azure_role_name = RoleAssignmentManager.ROLE_MAPPINGS.get(
                role_key, role_key
            )
            logging.info("Assigning Azure Role: %s", azure_role_name)

            # Assign the role
            if manager.assign_role(principal_id, principal_type, azure_role_name):
                # Additional logic: Add principal to local Entra ID group if manager or standard
                local_group_add_status = None
                if role_key in ("manager", "standard"):
                    bastionaccess_local_group_id = os.environ.get(
                        "BastionAccessLocalGroupId"
                    )
                    if bastionaccess_local_group_id:
                        try:
                            odata_id = (
                                "https://graph.microsoft.com/v1.0/"
                                f"directoryObjects/{principal_id}"
                            )

                            ref_body = ReferenceCreate()
                            ref_body.odata_id = odata_id
                            await manager.graph_client.groups.by_group_id(
                                bastionaccess_local_group_id
                            ).members.ref.post(body=ref_body)
                            local_group_add_status = (
                                "added to bastion access local group"
                            )
                            logging.info(
                                "Added principal %s (%s) to local Entra ID group %s",
                                principal_name,
                                principal_id,
                                bastionaccess_local_group_id,
                            )
                        except Exception as e:
                            local_group_add_status = (
                                f"failed_to_add_to_bastion_access_local_group: {e}"
                            )
                            logging.error(
                                "Failed to add principal %s (%s) to bastion access local Entra ID group %s: %s",
                                principal_name,
                                principal_id,
                                bastionaccess_local_group_id,
                                e,
                            )
                    else:
                        local_group_add_status = "local_group_id_not_set"
                        logging.warning(
                            "BastionAccessLocalGroupId environment variable not set."
                        )

                result_entry = {
                    "role": role_key,
                    "principal": principal_name,
                    "principal_id": principal_id,
                    "principal_type": principal_type,
                    "azure_role": azure_role_name,
                    "status": "success",
                    "message": f"Role '{azure_role_name}' assigned successfully",
                }
                if local_group_add_status is not None:
                    result_entry["bastion_access_local_group_addition"] = (
                        local_group_add_status
                    )
                success_count += 1
                results.append(result_entry)
            else:
                failure_count += 1
                results.append(
                    {
                        "role": role_key,
                        "principal": principal_name,
                        "principal_id": principal_id,
                        "principal_type": principal_type,
                        "azure_role": azure_role_name,
                        "status": "failed",
                        "message": f"Failed to assign role '{azure_role_name}'",
                    }
                )
        response_body = {
            "status": "success",
            "message": f"Role assignment process completed for {subscription_id} with {success_count} successes, {failure_count} failures, and {skipped_count} skipped.",
            "details": {"results": results},
        }

        logging.info(
            "Summary - Successful: %s, Failed: %s, Skipped: %s",
            success_count,
            failure_count,
            skipped_count,
        )

        # Return appropriate status code
        # status_code = 200 if failure_count == 0 else 207  # 207 = Multi-Status

        return func.HttpResponse(
            json.dumps(response_body, indent=2),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        logging.error("Unexpected error: %s", str(e), exc_info=True)
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "error",
                    "message": "internal server error",
                    "details": {"exception": str(e)},
                }
            ),
            status_code=500,
            mimetype="application/json",
        )
