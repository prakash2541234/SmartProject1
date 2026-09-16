from django.urls import path
from .views import (
    MessageListAPIView,
    HealthCheckAPIView,
    AssignRoleAPIView,
    StartProcessAPIView,
    ProcessStatusAPIView,
    ProcessDetailsAPIView,
    CreateVNetAPIView,
    CreateVMAPIView,
    CreateResourceGroupAPIView,
    CreateKeyVaultAPIView,
    CreateKeyVaultWithPrivateEndpointAPIView,
    CreateBackupAPIView,
    CreateServicePrincipalAPIView,
    CreateUserAPIView,
    CreateGroupAPIView,
    TriggerLogicAppAPIView,
)

app_name = 'moniter_react'  # Ensured uniqueness

urlpatterns = [
    path('messages/', MessageListAPIView.as_view(), name='message-list'),
    path('health/', HealthCheckAPIView.as_view(), name='health-check'),
    path('assign-role/', AssignRoleAPIView.as_view(), name='assign-role'),
    path('start-process/', StartProcessAPIView.as_view(), name='start-process'),
    path('process-status/', ProcessStatusAPIView.as_view(), name='process-status'),
    path('process-status/<str:ritm_number>/', ProcessStatusAPIView.as_view(), name='process-status-detail'),
    path('process-details/', ProcessDetailsAPIView.as_view(), name='process-details'),
    path('create-vnet/', CreateVNetAPIView.as_view(), name='create-vnet'),
    path('create-vm/', CreateVMAPIView.as_view(), name='create-vm'),
    path('create-resource-group/', CreateResourceGroupAPIView.as_view(), name='create-resource-group'),
    path('create-key-vault/', CreateKeyVaultAPIView.as_view(), name='create-key-vault'),
    path('create-keyvault-with-pe/', CreateKeyVaultWithPrivateEndpointAPIView.as_view(), name='create-keyvault-with-pe'),
    path('create-backup/', CreateBackupAPIView.as_view(), name='create-backup'),
    path('create-service-principal/', CreateServicePrincipalAPIView.as_view(), name='create-service-principal'),
    path('create-user/', CreateUserAPIView.as_view(), name='create-user'),
    path('create-group/', CreateGroupAPIView.as_view(), name='create-group'),
    path('trigger-logic-app/', TriggerLogicAppAPIView.as_view(), name='trigger-logic-app'),
]
