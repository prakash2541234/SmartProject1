"""
Test script to verify Azure connection with your credentials.

Run from Django project root:
    python manage.py shell < test_azure_connection.py

OR run directly:
    python test_azure_connection.py
"""

import os
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stl.settings")
django.setup()

from django.conf import settings
from stl.azure_client import get_credentials, get_storage_management_client


def _mask(value: str, visible: int = 4) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= visible:
        return "*" * len(raw)
    return f"{raw[:visible]}***{raw[-visible:]}"


def test_credentials():
    """Test whether Django can see the Azure credentials."""
    print("=" * 60)
    print("TESTING AZURE CREDENTIALS")
    print("=" * 60)

    env_keys = [
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_SUBSCRIPTION_ID",
    ]

    print("\nProcess environment:")
    for key in env_keys:
        value = os.environ.get(key, "")
        print(f"{key}: {_mask(value, 6) if value else 'Not set'}")

    print("\nLoaded by Django settings:")
    print(f"AZURE_TENANT_ID: {_mask(settings.AZURE_TENANT_ID, 6) if settings.AZURE_TENANT_ID else 'Not set'}")
    print(f"AZURE_CLIENT_ID: {_mask(settings.AZURE_CLIENT_ID, 6) if settings.AZURE_CLIENT_ID else 'Not set'}")
    print(f"AZURE_CLIENT_SECRET: {'set' if settings.AZURE_CLIENT_SECRET else 'Not set'}")
    print(f"AZURE_SUBSCRIPTION_ID: {_mask(settings.AZURE_SUBSCRIPTION_ID, 6) if settings.AZURE_SUBSCRIPTION_ID else 'Not set'}")

    if not all([
        settings.AZURE_TENANT_ID,
        settings.AZURE_CLIENT_ID,
        settings.AZURE_CLIENT_SECRET,
        settings.AZURE_SUBSCRIPTION_ID,
    ]):
        print("\nERROR: Some credentials are missing from Django settings.")
        return False

    print("\nAll credentials are loaded into Django settings.")
    return True


def test_client_connection():
    """Test Azure authentication and client creation."""
    print("\n" + "=" * 60)
    print("TESTING AZURE AUTHENTICATION")
    print("=" * 60)

    try:
        print("\nCreating Azure credentials...")
        cred = get_credentials()
        print("Credentials created successfully.")

        print("\nCreating Storage Management Client...")
        _client = get_storage_management_client()
        print("Storage Management Client created.")

        return True
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False


if __name__ == "__main__":
    results = []

    results.append(("Credentials Load", test_credentials()))
    results.append(("Azure Authentication", test_client_connection()))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"{test_name}: {status}")

    all_passed = all(result for _, result in results)
    print("\n" + ("ALL TESTS PASSED!" if all_passed else "SOME TESTS FAILED!"))
