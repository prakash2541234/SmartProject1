import os
import random
import json
import logging
import requests
from datetime import datetime
from uuid import uuid4

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers
from apis.moniter.serializers import (
    MessageSerializer,
    AssignRoleSerializer,
    CreateVNetSerializer,
    CreateVMSerializer,
    CreateResourceGroupSerializer,
    CreateKeyVaultSerializer,
    CreateKeyVaultWithPrivateEndpointSerializer,
    CreateBackupSerializer,
    CreateServicePrincipalSerializer,
    CreateUserSerializer,
    CreateGroupSerializer,
)
from apis.moniter.azure.views import (
    assign_role_to_principal,
    provision_vnet_from_payload,
    provision_vm_from_payload,
    provision_resource_group_from_payload,
    provision_key_vault_from_payload,
    provision_backup_from_payload,
    provision_service_principal_from_payload,
    provision_user_from_payload,
    provision_group_from_payload,
    AzureGraphAPIError,
    save_input_payload,
    save_output_payload,
    update_status,
)
from .process_tracking import query_process_status, record_dispatch_failure
from .process_tracking import query_process_details


def _is_graph_permission_error(error_code: str = "", message: str = "") -> bool:
    code = (error_code or "").strip().lower()
    text = (message or "").lower()
    if code in {"authorization_requestdenied", "accessdenied", "insufficientprivileges"}:
        return True

    markers = [
        "insufficient privileges",
        "authorization_requestdenied",
        "does not have permission",
        "permission denied",
    ]
    return any(marker in text for marker in markers)


def _is_graph_sp_app_reference_error(error_code: str = "", message: str = "") -> bool:
    code = (error_code or "").strip().lower()
    text = (message or "").lower()
    return (
        code in {"request_badrequest", "badrequest"}
        and "does not reference a valid application object" in text
    )


def _is_graph_invalid_upn_domain_error(error_code: str = "", message: str = "") -> bool:
    code = (error_code or "").strip().lower()
    text = (message or "").lower()
    return (
        code in {"request_badrequest", "badrequest", "invalid_upn_domain"}
        and (
            "domain portion of the userprincipalname property is invalid" in text
            or "domain part of userprincipalname is invalid" in text
        )
    )


def _graph_request_context(details: dict):
    inner = (details or {}).get("inner_error") or {}
    context = {}
    if inner.get("date"):
        context["date"] = inner.get("date")
    if inner.get("request-id"):
        context["request_id"] = inner.get("request-id")
    if inner.get("client-request-id"):
        context["client_request_id"] = inner.get("client-request-id")
    return context


PROCESS_STATUS = {}
PROCESS_CATALOG_TASK_SYSID = {}
logger = logging.getLogger(__name__)

STORAGE_LOCATION_CHOICES = [
    "centralindia",
    "eastus",
    "westus2",
    "westeurope",
    "southeastasia",
]

STORAGE_SKU_CHOICES = [
    "Standard_LRS",
    "Standard_GRS",
    "Premium_LRS",
]

STORAGE_KIND_CHOICES = [
    "StorageV2",
    "Storage",
    "BlobStorage",
]

SUBSCRIPTION_ROLE_CHOICES = [
    "Contributor",
    "Storage Account Contributor",
    "Reader",
]


def _normalize_process_status(value: str) -> str:
    status_value = (value or "").strip().upper()
    if status_value not in {"PROCESSING", "OK", "FAILED"}:
        raise ValueError("status must be one of: PROCESSING, OK, FAILED")
    return status_value


def _read_json_body(request):
    if not request.body:
        return {}

    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Request body must be valid JSON.")

    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object.")

    return body


def _store_process_status(ritm_number: str, catalog_task_sysid: str, status_value: str):
    PROCESS_STATUS[ritm_number] = status_value
    PROCESS_CATALOG_TASK_SYSID[ritm_number] = catalog_task_sysid


class StatusUpdateSerializer(serializers.Serializer):
    storageAccountName = serializers.CharField(required=False, allow_blank=False, allow_null=False)
    ritm_number = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    catalog_task_sysid = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    u_state = serializers.CharField(required=False, allow_blank=False, allow_null=False)
    u_result = serializers.CharField(required=False, allow_blank=False, allow_null=False)
    name = serializers.CharField(required=False, allow_blank=False, allow_null=False)
    status = serializers.CharField(required=True, allow_blank=False, allow_null=False)

    def validate_status(self, value):
        normalized = value.strip().upper()
        allowed = {"SUCCESS", "FAILED"}
        if normalized not in allowed:
            raise serializers.ValidationError(
                f"status must be one of: {', '.join(sorted(allowed))}"
            )
        return normalized


class ProcessStartSerializer(serializers.Serializer):
    project_name = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    location = serializers.ChoiceField(choices=STORAGE_LOCATION_CHOICES)
    sku = serializers.ChoiceField(choices=STORAGE_SKU_CHOICES)
    kind = serializers.ChoiceField(choices=STORAGE_KIND_CHOICES)
    subscription_role = serializers.ChoiceField(choices=SUBSCRIPTION_ROLE_CHOICES)
    requester_user_id = serializers.CharField(required=False, allow_blank=False, allow_null=False)

    def validate_project_name(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("project_name is required.")
        return cleaned


class ProcessStatusQuerySerializer(serializers.Serializer):
    ritm_number = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    catalog_task_sysid = serializers.CharField(required=False, allow_blank=False, allow_null=False)

    def validate_ritm_number(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("ritm_number is required.")
        return cleaned

    def validate_catalog_task_sysid(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("catalog_task_sysid cannot be blank.")
        return cleaned


class MessageListAPIView(APIView):
    """API view to list all messages"""
    
    def get(self, request):
        """Get all messages"""
        messages = [
            {
                'id': 1,
                'title': 'Welcome',
                'message': 'Welcome to Django REST API',
                'timestamp': datetime.now().isoformat()
            },
            {
                'id': 2,
                'title': 'Status',
                'message': 'Django and React are successfully connected!',
                'timestamp': datetime.now().isoformat()
            },
        ]
        return Response(messages, status=status.HTTP_200_OK)
    
    def post(self, request):
        """Create a new message"""
        serializer = MessageSerializer(data=request.data)
        if serializer.is_valid():
            return Response(
                {
                    'id': 3,
                    'timestamp': datetime.now().isoformat(),
                    **serializer.validated_data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HealthCheckAPIView(APIView):
    """API health check endpoint"""
    
    def get(self, request):
        """Check API health status"""
        return Response({
            'status': 'healthy',
            'message': 'Django API is running',
            'timestamp': datetime.now().isoformat()
        })


def _read_logic_app_trigger_url() -> str:
    url = (getattr(settings, "LOGIC_APP_TRIGGER_URL", "") or os.getenv("LOGIC_APP_TRIGGER_URL", "")).strip()
    if not url:
        raise RuntimeError(
            "LOGIC_APP_TRIGGER_URL is not configured. Set it to your Logic App HTTP trigger URL."
        )
    return url


def _generate_servicenow_identifiers() -> dict:
    return {
        "ritm_number": f"RITM{random.randint(1000, 99999)}",
        "catalog_task_sysid": str(uuid4()),
    }


def _build_logic_app_payload(
    ritm_number: str,
    catalog_task_sysid: str,
    requester_user_id: str,
    project_name: str,
    location: str,
    sku: str,
    kind: str,
    subscription_role: str,
) -> dict:
    return {
        "request_parameters": {
            "ritm_number": ritm_number,
            "catalog_task_sysid": catalog_task_sysid,
            "requester": {
                "user_id": requester_user_id or getattr(settings, "LOGIC_APP_REQUESTER_USER_ID", "system"),
            },
        },
        "storage_parameters": {
            "subscription_id": getattr(settings, "AZURE_SUBSCRIPTION_ID", ""),
            "subscription_role": subscription_role,
            "application_id": project_name,
        },
        "storage_info": {
            "location": location,
            "sku": {
                "name": sku,
            },
            "kind": kind,
        },
    }


def _trigger_logic_app_workflow(payload: dict) -> dict:
    trigger_url = _read_logic_app_trigger_url()
    response = requests.post(trigger_url, json=payload, timeout=30)
    response_data = {}
    if response.content:
        try:
            response_data = response.json()
        except ValueError:
            response_data = response.text.strip() or {}

    if response.status_code not in {200, 201, 202, 204}:
        response_message = response.text.strip() if response.text else ""
        detail = response_message or "No response body returned."
        raise RuntimeError(
            f"Logic App trigger failed with HTTP {response.status_code}: {detail}"
        )

    return {
        "status_code": response.status_code,
        "logic_response": response_data,
    }


class AssignRoleAPIView(APIView):
    """Handle role assignment requests for AssignRole."""

    def post(self, request):
        serializer = AssignRoleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payload = serializer.validated_data
        user_id = payload.get("user_id")
        role = payload.get("role")

        # Simulate role assignment logic
        try:
            # Replace this with actual role assignment logic
            if not user_id or not role:
                raise ValueError("Invalid user or role.")

            return Response({
                "status": "success",
                "message": f"Role '{role}' assigned to user '{user_id}'.",
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e),
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
class StartProcessAPIView(APIView):
    """Start a background process and hand it off to Logic App."""

    def post(self, request):
        serializer = ProcessStartSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for process start request.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = serializer.validated_data
        identifiers = _generate_servicenow_identifiers()
        ritm_number = identifiers["ritm_number"]
        catalog_task_sysid = identifiers["catalog_task_sysid"]
        project_name = payload["project_name"]
        requester_user_id = (payload.get("requester_user_id") or "").strip()
        logic_app_payload = _build_logic_app_payload(
            ritm_number=ritm_number,
            catalog_task_sysid=catalog_task_sysid,
            requester_user_id=requester_user_id,
            project_name=project_name,
            location=payload["location"],
            sku=payload["sku"],
            kind=payload["kind"],
            subscription_role=payload["subscription_role"],
        )
        request_id = catalog_task_sysid

        save_input_payload(
            request_id=request_id,
            process_name=project_name,
                payload={
                    **payload,
                    "ritm_number": ritm_number,
                    "catalog_task_sysid": catalog_task_sysid,
                },
        )
        update_status(request_id, "initiated")

        try:
            logic_response = _trigger_logic_app_workflow(logic_app_payload)
            save_output_payload(
                request_id=request_id,
                payload={
                    "message": "Process dispatched to Logic App.",
                    "ritm_number": ritm_number,
                    "catalog_task_sysid": catalog_task_sysid,
                    "project_name": project_name,
                    "logic_app_status_code": logic_response["status_code"],
                    "logic_app_response": logic_response["logic_response"],
                },
                status="started",
            )
            update_status(request_id, "started")
            return Response(
                {
                    "message": "Process started",
                    "status": "started",
                    "ritm_number": ritm_number,
                    "catalog_task_sysid": catalog_task_sysid,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as exc:
            error_message = str(exc)
            save_output_payload(
                request_id=request_id,
                payload={
                    "error": error_message,
                    "ritm_number": ritm_number,
                    "catalog_task_sysid": catalog_task_sysid,
                    "project_name": project_name,
                },
                status="failed",
                error_message=error_message,
            )
            update_status(request_id, "failed", error_message=error_message)
            record_dispatch_failure(
                {
                    "ritm_number": ritm_number,
                    "catalog_task_sysid": catalog_task_sysid,
                    "project_name": project_name,
                    "request_parameters": logic_app_payload["request_parameters"],
                    "storage_parameters": logic_app_payload["storage_parameters"],
                },
                error_message,
            )

            return Response(
                {
                    "status": "error",
                    "message": error_message,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ProcessStatusAPIView(APIView):
    """Read process completion state from Azure Table Storage."""

    def get(self, request, ritm_number=None):
        query_data = request.query_params.copy()
        if ritm_number:
            query_data["ritm_number"] = ritm_number

        serializer = ProcessStatusQuerySerializer(data=query_data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "ritm_number is required.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        params = serializer.validated_data
        ritm_number = (ritm_number or params["ritm_number"]).strip()
        catalog_task_sysid = (params.get("catalog_task_sysid") or "").strip()

        try:
            entity = query_process_status(
                ritm_number,
                catalog_task_sysid,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not entity:
            return Response(
                {"status": "PENDING"},
                status=status.HTTP_200_OK,
            )

        return Response(
            entity,
            status=status.HTTP_200_OK,
        )


class ProcessDetailsAPIView(APIView):
    """Read the full process record from Azure Table Storage."""

    def get(self, request):
        query_data = request.query_params.copy()
        if not (query_data.get("ritm_number") or "").strip() or not (query_data.get("catalog_task_sysid") or "").strip():
            return Response(
                {
                    "status": "error",
                    "message": "ritm_number and catalog_task_sysid are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProcessStatusQuerySerializer(data=query_data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Invalid query parameters.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        params = serializer.validated_data

        try:
            entity = query_process_details(
                params["ritm_number"],
                params["catalog_task_sysid"],
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not entity:
            return Response(
                {"status": "PENDING"},
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": "success",
                "payload": entity,
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class StatusUpdateAPIView(APIView):
    """Receive status callbacks from Azure Logic App."""

    def post(self, request):
        try:
            serializer = StatusUpdateSerializer(data=request.data)
            if not serializer.is_valid():
                errors = serializer.errors
                for field in ("ritm_number", "catalog_task_sysid", "status"):
                    if field in errors:
                        first_error = errors[field][0]
                        return Response(
                            {"error": f"Missing required field: {field}"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                return Response(
                    {"error": errors},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            data = serializer.validated_data
            ritm_number = data["ritm_number"]
            catalog_task_sysid = data["catalog_task_sysid"]
            status_value = data["status"]

            logger.info(
                "Logic App status callback received at %s: %s",
                datetime.now().isoformat(),
                dict(data),
            )

            expected_sysid = PROCESS_CATALOG_TASK_SYSID.get(ritm_number)
            if expected_sysid and expected_sysid != catalog_task_sysid:
                return Response(
                    {"error": "catalog_task_sysid does not match the active process"},
                    status=status.HTTP_409_CONFLICT,
                )

            _store_process_status(ritm_number, catalog_task_sysid, status_value)

            return Response(
                {
                    "message": "Status received successfully",
                    "data": dict(data),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.exception("Failed to process Logic App status callback")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@csrf_exempt
def get_status(request, ritm_number):
    if request.method != "GET":
        return JsonResponse({"message": "Method not allowed"}, status=405)

    ritm_number = (ritm_number or "").strip()
    status_value = PROCESS_STATUS.get(ritm_number)
    if not ritm_number or not status_value:
        return JsonResponse({"message": "Status not found"}, status=404)

    return JsonResponse(
        {
            "ritm_number": ritm_number,
            "status": status_value,
        }
    )

import uuid
from datetime import datetime

class CreateVNetAPIView(APIView):
    """React-facing endpoint for VNet create flow."""

    def post(self, request):
        # ✅ STEP 1: Generate request_id
        request_id = request.data.get("request_id") or str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        serializer = CreateVNetSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "request_id": request_id,
                    "errors": serializer.errors,
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ✅ STEP 2: Save INPUT payload
        save_input_payload(
            request_id=request_id,
            process_name="VNet Creation",
            payload=request.data
        )

        try:
            result = provision_vnet_from_payload(
                serializer.validated_data
            )

            # ✅ Dry Run
            if result.get("mode") == "dry-run":

                save_output_payload(
                    request_id=request_id,
                    payload=result,
                    status="accepted"
                )

                return Response(
                    {
                        "status": "accepted",
                        "request_id": request_id,
                        "timestamp": timestamp,
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            # ✅ SUCCESS
            save_output_payload(
                request_id=request_id,
                payload=result,
                status="success"
            )

            return Response(
                {
                    "status": "success",
                    "request_id": request_id,
                    "timestamp": timestamp,
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )

        except RuntimeError as exc:

            save_output_payload(
                request_id=request_id,
                payload={},
                status="failed",
                error_message=str(exc),
            )

            return Response(
                {
                    "status": "error",
                    "request_id": request_id,
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as exc:

            save_output_payload(
                request_id=request_id,
                payload={},
                status="failed",
                error_message=str(exc),
            )

            return Response(
                {
                    "status": "error",
                    "request_id": request_id,
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class CreateVMAPIView(APIView):
    """React-facing endpoint for VM create flow."""

    def post(self, request):
        serializer = CreateVMSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = provision_vm_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except RuntimeError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateResourceGroupAPIView(APIView):
    """React-facing endpoint for resource group create flow."""

    def post(self, request):
        serializer = CreateResourceGroupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = provision_resource_group_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except RuntimeError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateKeyVaultAPIView(APIView):
    """React-facing endpoint for Key Vault create flow."""

    def post(self, request):
        serializer = CreateKeyVaultSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for Key Vault request.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_key_vault_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except RuntimeError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateKeyVaultWithPrivateEndpointAPIView(APIView):
    """React-facing endpoint that handles a Key Vault + Private Endpoint payload."""

    def post(self, request):
        serializer = CreateKeyVaultWithPrivateEndpointSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for Key Vault with PE request.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        timestamp = datetime.now().isoformat()
        data = serializer.validated_data
        dry_run = bool(data.get("dryRun", False))
        keyvault_payload = {
            **data["keyVault"],
            "dryRun": dry_run,
        }
        private_payload = data["privateEndpoint"]

        try:
            keyvault_result = provision_key_vault_from_payload(keyvault_payload)

            response_body = {
                "status": "success" if keyvault_result.get("mode") != "dry-run" else "accepted",
                "timestamp": timestamp,
                "keyVault": keyvault_result,
                "privateEndpoint": {
                    "name": private_payload["name"],
                    "vnet": private_payload["vnet"],
                    "subnet": private_payload["subnet"],
                    "targetSubResource": private_payload.get("targetSubResource") or "vault",
                    "privateDnsEnabled": private_payload.get("privateDnsEnabled", True),
                    "status": "pending",
                    "message": "Private endpoint provisioning is not implemented yet.",
                },
            }

            if keyvault_result.get("mode") == "dry-run":
                response_body["message"] = "Key Vault payload validated. Set dryRun=false to apply."
                return Response(response_body, status=status.HTTP_202_ACCEPTED)

            response_body["message"] = "Key Vault payload applied; private endpoint plan recorded."
            return Response(response_body, status=status.HTTP_201_CREATED)

        except RuntimeError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "timestamp": timestamp,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateBackupAPIView(APIView):
    """React-facing endpoint for Backup create flow."""

    def post(self, request):
        serializer = CreateBackupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for Backup request.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_backup_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except RuntimeError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateServicePrincipalAPIView(APIView):
    """React-facing endpoint for Service Principal create flow."""

    def post(self, request):
        serializer = CreateServicePrincipalSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for Service Principal request.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_service_principal_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except AzureGraphAPIError as exc:
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response(
                    {
                        "status": "error",
                        "code": "graph_permission_denied",
                        "message": (
                            "Insufficient privileges to complete the operation. "
                            "Backend app lacks Microsoft Graph permissions required for Service Principal creation."
                        ),
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "required_permissions": [
                            "Application.ReadWrite.All",
                            "Directory.ReadWrite.All",
                        ],
                        "troubleshooting": [
                            "Open Azure Portal > App registrations > your backend app > API permissions.",
                            "Add Application permissions: Application.ReadWrite.All and Directory.ReadWrite.All.",
                            "Click Grant admin consent for the tenant.",
                            "Retry the Service Principal creation request.",
                        ],
                        "request_context": _graph_request_context(exc.details),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if _is_graph_sp_app_reference_error(exc.code, str(exc)):
                return Response(
                    {
                        "status": "error",
                        "code": "graph_app_replication_delay",
                        "message": (
                            "Azure AD app replication delay detected. "
                            "The application object is not yet fully available for service principal creation."
                        ),
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "troubleshooting": [
                            "Wait 30-60 seconds and retry the submit.",
                            "If it keeps failing, verify the application exists in Entra ID > App registrations.",
                            "Ensure tenantId in form matches backend AZURE_TENANT_ID.",
                        ],
                        "request_context": _graph_request_context(exc.details),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": "graph_api_error",
                    "message": str(exc),
                    "azure_error_code": exc.code,
                    "request_context": _graph_request_context(exc.details),
                },
                status=http_code,
            )
        except RuntimeError as exc:
            text = str(exc)
            lowered = text.lower()
            if "authorizationfailed" in lowered or "insufficient privileges" in lowered:
                return Response(
                    {
                        "status": "error",
                        "code": "arm_authorization_failed",
                        "message": (
                            "Insufficient privileges for Azure RBAC role assignment at selected scope."
                        ),
                        "azure_error_message": text,
                        "required_permissions": [
                            "Owner or User Access Administrator at the target scope",
                        ],
                        "troubleshooting": [
                            "Grant Owner or User Access Administrator on the selected subscription/resource group scope.",
                            "If scope is custom, verify the scope path is correct and accessible.",
                            "Retry the Service Principal request.",
                        ],
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            return Response(
                {
                    "status": "error",
                    "message": text,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateUserAPIView(APIView):
    """React-facing endpoint for Azure AD user create flow."""

    def post(self, request):
        serializer = CreateUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for user request.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_id = str(uuid4())
        save_input_payload(
            request_id=request_id,
            process_name="User Creation (React)",
            payload=serializer.validated_data,
        )

        try:
            result = provision_user_from_payload(
                serializer.validated_data,
                request_id=request_id,
            )
            payload_status = "accepted" if result.get("mode") == "dry-run" else "success"
            save_output_payload(
                request_id=request_id,
                payload=result,
                status=payload_status,
            )

            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except AzureGraphAPIError as exc:
            save_output_payload(
                request_id=request_id,
                payload={},
                status="failed",
                error_message=str(exc),
            )
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response(
                    {
                        "status": "error",
                        "code": "graph_permission_denied",
                        "message": "Cannot create user due to insufficient Microsoft Graph permissions.",
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "required_permissions": [
                            "User.ReadWrite.All",
                            "Directory.ReadWrite.All",
                        ],
                        "request_context": _graph_request_context(exc.details),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if exc.code == "invalid_upn_domain" or _is_graph_invalid_upn_domain_error(exc.code, str(exc)):
                details = exc.details or {}
                return Response(
                    {
                        "status": "error",
                        "code": "invalid_upn_domain",
                        "message": (
                            "The domain portion of userPrincipalName is invalid. "
                            "Use one of the verified domains in your organization."
                        ),
                        "provided_domain": details.get("provided_domain", ""),
                        "verified_domains": details.get("verified_domains", []),
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "request_context": _graph_request_context(details),
                        "troubleshooting": [
                            "Use UPN format: user@<verified-domain>.",
                            "If domain is missing, verify it in Microsoft Entra ID > Custom domain names.",
                        ],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": "graph_api_error",
                    "message": str(exc),
                    "azure_error_code": exc.code,
                    "request_context": _graph_request_context(exc.details),
                },
                status=http_code,
            )
        except RuntimeError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateGroupAPIView(APIView):
    """React-facing endpoint for Azure AD group create flow."""

    def post(self, request):
        serializer = CreateGroupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validation failed for group request.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provision_group_from_payload(serializer.validated_data)
            if result.get("mode") == "dry-run":
                return Response(
                    {
                        "status": "accepted",
                        **result,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "status": "success",
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except AzureGraphAPIError as exc:
            if _is_graph_permission_error(exc.code, str(exc)):
                return Response(
                    {
                        "status": "error",
                        "code": "graph_permission_denied",
                        "message": "Cannot create group due to insufficient Microsoft Graph permissions.",
                        "azure_error_code": exc.code,
                        "azure_error_message": str(exc),
                        "required_permissions": [
                            "Group.ReadWrite.All",
                            "Directory.ReadWrite.All",
                        ],
                        "request_context": _graph_request_context(exc.details),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            http_code = exc.status_code if exc.status_code >= 400 else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "status": "error",
                    "code": "graph_api_error",
                    "message": str(exc),
                    "azure_error_code": exc.code,
                    "request_context": _graph_request_context(exc.details),
                },
                status=http_code,
            )
        except RuntimeError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TriggerLogicAppAPIView(APIView):
    def post(self, request, *args, **kwargs):
        try:
            # Extract JSON payload from the request
            payload = request.data

            if not isinstance(payload, dict):
                return Response(
                    {"error": "Request body must be a JSON object."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # URL of the Azure Logic App HTTP trigger
            logic_app_url = _read_logic_app_trigger_url()

            normalized_payload = dict(payload)
            normalized_payload.setdefault("u_state", "")
            normalized_payload.setdefault("u_result", "")
            if "u_catalog_task_sysid" not in normalized_payload and "catalog_task_sysid" in payload:
                normalized_payload["u_catalog_task_sysid"] = payload["catalog_task_sysid"]
            if "u_ritm_number" not in normalized_payload and "ritm_number" in payload:
                normalized_payload["u_ritm_number"] = payload["ritm_number"]

            # Validate the payload structure
            expected_keys = ["u_catalog_task_sysid", "u_ritm_number"]
            for key in expected_keys:
                if key not in normalized_payload:
                    return Response({"error": f"Missing required field: {key}"}, status=status.HTTP_400_BAD_REQUEST)

            # Forward the payload to the Logic App
            response = requests.post(logic_app_url, json=normalized_payload, timeout=30)

            # Check if the Logic App responded successfully
            if response.ok:
                response_data = {}
                if response.content:
                    try:
                        response_data = response.json()
                    except ValueError:
                        response_data = response.text.strip() or {}
                return Response(response_data, status=response.status_code)

            return Response({
                "error": "Failed to trigger Logic App",
                "details": response.text
            }, status=response.status_code)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
