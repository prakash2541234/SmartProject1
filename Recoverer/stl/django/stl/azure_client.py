"""
Azure integration helpers for this Django project.

Usage:
- Edit Azure credentials in `stl/settings.py`.
- Install required packages (see `requirements.txt`).

This module provides:
- `get_credentials()` -> `azure.identity.ClientSecretCredential`
- `get_storage_management_client()` -> `azure.mgmt.storage.StorageManagementClient`
- `get_blob_service_client(account_url)` -> `azure.storage.blob.BlobServiceClient`

You can import and call these helpers from Django code. The module raises
friendly ImportError messages when required packages are missing.
"""

from typing import Optional
from django.conf import settings


def _azure_setting(name: str, default: str = "") -> str:
    return (getattr(settings, name, default) or "").strip()


def get_credentials():
    """Return a ClientSecretCredential using configured env vars.

    Raises:
        ImportError: if `azure-identity` is not installed.
        RuntimeError: if required env vars are missing.
    """
    try:
        from azure.identity import ClientSecretCredential
    except ImportError as exc:
        raise ImportError("Install azure-identity: pip install azure-identity") from exc

    tenant_id = _azure_setting("AZURE_TENANT_ID")
    client_id = _azure_setting("AZURE_CLIENT_ID")
    client_secret = _azure_setting("AZURE_CLIENT_SECRET")

    if not (tenant_id and client_id and client_secret):
        raise RuntimeError(
            "Azure credentials not set. Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET."
        )

    return ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )


def get_storage_management_client():
    """Return an instance of `azure.mgmt.storage.StorageManagementClient`.

    Raises ImportError if `azure-mgmt-storage` is not installed.
    Requires `AZURE_SUBSCRIPTION_ID` to be set.
    """
    try:
        from azure.mgmt.storage import StorageManagementClient
    except ImportError as exc:
        raise ImportError("Install azure-mgmt-storage: pip install azure-mgmt-storage") from exc

    subscription_id = _azure_setting("AZURE_SUBSCRIPTION_ID")
    if not subscription_id:
        raise RuntimeError("AZURE_SUBSCRIPTION_ID is not set in environment.")

    cred = get_credentials()
    return StorageManagementClient(cred, subscription_id)


def get_blob_service_client(account_url: Optional[str] = None, credential: Optional[object] = None):
    """Return `azure.storage.blob.BlobServiceClient` for data-plane operations.

    `account_url` should be like https://<account>.blob.core.windows.net
    If `credential` is omitted, `get_credentials()` will be used (ClientSecretCredential).

    Raises ImportError if `azure-storage-blob` is not installed.
    """
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise ImportError("Install azure-storage-blob: pip install azure-storage-blob") from exc

    if not account_url:
        raise ValueError("`account_url` is required (e.g. https://<account>.blob.core.windows.net)")

    cred = credential or get_credentials()
    return BlobServiceClient(account_url=account_url, credential=cred)
