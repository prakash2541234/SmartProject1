"""
Compatibility exports for moniter API views.

This module keeps legacy import paths working:
`from apis.moniter.views import ...`
while real implementations live in `apis.moniter.react.views`
and `apis.moniter.azure.views`.
"""

from apis.moniter.react.views import (
    MessageListAPIView,
    HealthCheckAPIView,
    AssignRoleAPIView,
    StartProcessAPIView,
    CreateVNetAPIView,
    CreateVMAPIView,
    CreateResourceGroupAPIView,
    CreateKeyVaultAPIView,
    CreateBackupAPIView,
    CreateServicePrincipalAPIView,
    CreateUserAPIView,
    CreateGroupAPIView,
)
from apis.moniter.azure.views import (
    AzureStorageAccountsAPIView,
    AzureSubscriptionsAPIView,
    AzureResourceGroupsAPIView,
    AzureRegionsAPIView,
    AzureCreateVNetAPIView,
    AzureCreateVMAPIView,
    AzureCreateResourceGroupAPIView,
    AzureCreateKeyVaultAPIView,
    AzureCreateBackupAPIView,
    AzureCreateServicePrincipalAPIView,
    AzureVerifiedDomainsAPIView,
    AzureCreateUserAPIView,
    AzureCreateGroupAPIView,
    AzureADUsersListAPIView,
    AzureADUsersCountAPIView,
    AzureAssignRoleAPIView,
)

__all__ = [
    "MessageListAPIView",
    "HealthCheckAPIView",
    "AssignRoleAPIView",
    "StartProcessAPIView",
    "CreateVNetAPIView",
    "CreateVMAPIView",
    "CreateResourceGroupAPIView",
    "CreateKeyVaultAPIView",
    "CreateBackupAPIView",
    "CreateServicePrincipalAPIView",
    "CreateUserAPIView",
    "CreateGroupAPIView",
    "AzureStorageAccountsAPIView",
    "AzureSubscriptionsAPIView",
    "AzureResourceGroupsAPIView",
    "AzureRegionsAPIView",
    "AzureCreateVNetAPIView",
    "AzureCreateVMAPIView",
    "AzureCreateResourceGroupAPIView",
    "AzureCreateKeyVaultAPIView",
    "AzureCreateBackupAPIView",
    "AzureCreateServicePrincipalAPIView",
    "AzureVerifiedDomainsAPIView",
    "AzureCreateUserAPIView",
    "AzureCreateGroupAPIView",
    "AzureADUsersListAPIView",
    "AzureADUsersCountAPIView",
    "AzureAssignRoleAPIView",
]
