from rest_framework import serializers


class MessageSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(max_length=100)
    message = serializers.CharField()
    timestamp = serializers.DateTimeField(read_only=True)


class AssignRoleSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=128)
    role = serializers.ChoiceField(choices=["reader", "contributor"])
    user_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    user_email = serializers.EmailField(required=False, allow_blank=True)
    principal_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    scope = serializers.CharField(max_length=512, required=False, allow_blank=True)


class VNetSubnetSerializer(serializers.Serializer):
    subnetName = serializers.CharField(max_length=80)
    addressPrefix = serializers.CharField(max_length=64)

class VNetRouteSerializer(serializers.Serializer):
    routeName = serializers.CharField(max_length=80)
    destination = serializers.CharField(max_length=64)
    nextHop = serializers.ChoiceField(
        choices=[
            "Internet",
            "VirtualNetworkGateway",
            "VirtualAppliance",
            "VnetLocal",
            "None",
        ]
    )
    nextHopIp = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["nextHop"] == "VirtualAppliance" and not attrs.get("nextHopIp"):
            raise serializers.ValidationError("nextHopIp is required when nextHop is VirtualAppliance.")
        return attrs


class VNetRouteTableSerializer(serializers.Serializer):
    routeTableName = serializers.CharField(max_length=80)
    routes = VNetRouteSerializer(many=True, required=False)


class CreateVNetSerializer(serializers.Serializer):
    subscription = serializers.CharField(max_length=128)
    resourceGroup = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=80)
    vnetName = serializers.CharField(max_length=80)
    addressSpace = serializers.CharField(max_length=64)
    subnets = VNetSubnetSerializer(many=True)
    enableCustomRouting = serializers.ChoiceField(choices=["Yes", "No"])
    routeTable = VNetRouteTableSerializer(required=False, allow_null=True)
    routeTableName = serializers.CharField(max_length=80, required=False, allow_blank=True)
    tags = serializers.DictField(
        child=serializers.CharField(max_length=256, allow_blank=True),
        required=False,
        default=dict,
    )
    dryRun = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        if not attrs.get("subnets"):
            raise serializers.ValidationError("At least one subnet is required.")

        custom_routing_enabled = attrs.get("enableCustomRouting") == "Yes"
        route_table = attrs.get("routeTable")
        route_table_name = attrs.get("routeTableName", "").strip()

        if custom_routing_enabled:
            if not route_table and not route_table_name:
                raise serializers.ValidationError(
                    "routeTable or routeTableName is required when custom routing is enabled."
                )
        else:
            attrs["routeTable"] = None
            attrs["routeTableName"] = ""

        if route_table and not route_table.get("routeTableName") and route_table_name:
            route_table["routeTableName"] = route_table_name

        return attrs


class CreateResourceGroupSerializer(serializers.Serializer):
    subscription = serializers.CharField(max_length=128)
    resourceGroup = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=80)
    tags = serializers.DictField(
        child=serializers.CharField(max_length=256, allow_blank=True),
        required=False,
        default=dict,
    )
    dryRun = serializers.BooleanField(required=False, default=False)


class VmImageSerializer(serializers.Serializer):
    publisher = serializers.CharField(max_length=120)
    offer = serializers.CharField(max_length=120)
    sku = serializers.CharField(max_length=120)
    version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="latest")


class VmAdminSerializer(serializers.Serializer):
    username = serializers.RegexField(
        regex=r"^[A-Za-z][A-Za-z0-9._-]{2,31}$",
        max_length=32,
        error_messages={
            "invalid": (
                "username must be 3-32 characters, start with a letter, and use only "
                "letters, numbers, dot, underscore, or hyphen."
            ),
        },
    )
    authenticationType = serializers.ChoiceField(choices=["password", "ssh"])
    password = serializers.CharField(required=False, allow_blank=True, max_length=128)
    sshPublicKey = serializers.CharField(required=False, allow_blank=True, max_length=4096)

    def validate(self, attrs):
        auth_type = attrs.get("authenticationType")
        password = attrs.get("password", "")
        ssh_key = (attrs.get("sshPublicKey") or "").strip()

        if auth_type == "password":
            checks = [
                (len(password) >= 12, "password must be at least 12 characters."),
                (any(ch.isupper() for ch in password), "password must include an uppercase letter."),
                (any(ch.islower() for ch in password), "password must include a lowercase letter."),
                (any(ch.isdigit() for ch in password), "password must include a number."),
                (
                    any(not ch.isalnum() for ch in password),
                    "password must include a special character.",
                ),
            ]
            for ok, message in checks:
                if not ok:
                    raise serializers.ValidationError({"password": message})
            attrs["sshPublicKey"] = ""
            return attrs

        if not ssh_key:
            raise serializers.ValidationError({"sshPublicKey": "sshPublicKey is required for SSH authentication."})
        if not (
            ssh_key.startswith("ssh-rsa ")
            or ssh_key.startswith("ssh-ed25519 ")
            or ssh_key.startswith("ssh-ecdsa ")
        ):
            raise serializers.ValidationError(
                {"sshPublicKey": "sshPublicKey must start with ssh-rsa, ssh-ed25519, or ssh-ecdsa."}
            )

        attrs["password"] = ""
        attrs["sshPublicKey"] = ssh_key
        return attrs


class VmNetworkSerializer(serializers.Serializer):
    virtualNetworkName = serializers.CharField(max_length=80)
    subnetName = serializers.CharField(max_length=80)
    enablePublicIp = serializers.BooleanField(required=False, default=True)
    publicIpSku = serializers.ChoiceField(choices=["Standard", "Basic"], required=False, default="Standard")

    def validate(self, attrs):
        if not attrs.get("enablePublicIp", True):
            attrs["publicIpSku"] = "Standard"
        return attrs


class VmStorageSerializer(serializers.Serializer):
    osDiskType = serializers.ChoiceField(choices=["Premium_LRS", "StandardSSD_LRS", "Standard_LRS"])
    osDiskSizeGb = serializers.IntegerField(min_value=30, max_value=4095)


class CreateVMSerializer(serializers.Serializer):
    subscription = serializers.CharField(max_length=128)
    resourceGroup = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=80)
    vmName = serializers.RegexField(
        regex=r"^[A-Za-z][A-Za-z0-9-]{1,63}$",
        max_length=64,
        error_messages={
            "invalid": (
                "vmName must be 2-64 characters, start with a letter, and use only "
                "letters, numbers, or hyphen."
            ),
        },
    )
    vmSize = serializers.CharField(max_length=64)
    osType = serializers.ChoiceField(choices=["Linux", "Windows"])
    image = VmImageSerializer()
    admin = VmAdminSerializer()
    network = VmNetworkSerializer()
    storage = VmStorageSerializer()
    tags = serializers.DictField(
        child=serializers.CharField(max_length=256, allow_blank=True),
        required=False,
        default=dict,
    )
    dryRun = serializers.BooleanField(required=False, default=True)

    def validate_region(self, value):
        normalized = (value or "").strip()
        if normalized.lower() == "other":
            raise serializers.ValidationError("Region cannot be 'Other'. Select or type a valid Azure region.")
        return normalized

    def validate(self, attrs):
        os_type = attrs.get("osType")
        admin = attrs.get("admin") or {}
        auth_type = admin.get("authenticationType")

        if os_type == "Windows" and auth_type == "ssh":
            raise serializers.ValidationError(
                {"admin": "SSH authentication is not supported for Windows VM in this flow. Use password."}
            )

        return attrs


class CreateKeyVaultSerializer(serializers.Serializer):
    subscription = serializers.CharField(max_length=128)
    resourceGroup = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=80)
    keyVaultName = serializers.RegexField(
        regex=r"^[a-zA-Z0-9-]{3,24}$",
        max_length=24,
        error_messages={
            "invalid": "Key Vault name must be 3-24 characters and only letters, numbers, and hyphens.",
        },
    )
    skuName = serializers.ChoiceField(choices=["standard", "premium"], required=False, default="standard")
    tenantId = serializers.CharField(max_length=64, required=False, allow_blank=True)
    enableRbacAuthorization = serializers.BooleanField(required=False, default=True)
    publicNetworkAccess = serializers.ChoiceField(choices=["Enabled", "Disabled"], required=False, default="Enabled")
    softDeleteRetentionInDays = serializers.IntegerField(required=False, min_value=7, max_value=90, default=90)
    enablePurgeProtection = serializers.BooleanField(required=False, default=False)
    enabledForDeployment = serializers.BooleanField(required=False, default=False)
    enabledForDiskEncryption = serializers.BooleanField(required=False, default=False)
    enabledForTemplateDeployment = serializers.BooleanField(required=False, default=False)
    tags = serializers.DictField(
        child=serializers.CharField(max_length=256, allow_blank=True),
        required=False,
        default=dict,
    )
    dryRun = serializers.BooleanField(required=False, default=True)

    def validate_region(self, value):
        normalized = (value or "").strip()
        if normalized.lower() == "other":
            raise serializers.ValidationError("Region cannot be 'Other'. Select or type a valid Azure region.")
        return normalized

    def validate_keyVaultName(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Key Vault name is required.")
        if not name[0].isalpha():
            raise serializers.ValidationError("Key Vault name must start with a letter.")
        if not name[-1].isalnum():
            raise serializers.ValidationError("Key Vault name must end with a letter or number.")
        if "--" in name:
            raise serializers.ValidationError("Key Vault name cannot contain consecutive hyphens.")
        return name


class PrivateEndpointSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    targetSubResource = serializers.CharField(max_length=64, default="vault")
    vnet = serializers.CharField(max_length=120)
    subnet = serializers.CharField(max_length=120)
    privateDnsEnabled = serializers.BooleanField(required=False, default=True)


class CreateKeyVaultWithPrivateEndpointSerializer(serializers.Serializer):
    keyVault = CreateKeyVaultSerializer()
    privateEndpoint = PrivateEndpointSerializer()


from rest_framework import serializers


class CreateServicePrincipalSerializer(serializers.Serializer):

    subscription = serializers.CharField(max_length=128)

    servicePrincipalName = serializers.RegexField(
        regex=r"^[A-Za-z][A-Za-z0-9-_]{2,119}$",
        max_length=120,
        error_messages={
            "invalid": (
                "Service Principal name must be 3-120 characters, start with a letter, "
                "and use only letters, numbers, hyphen, or underscore."
            ),
        },
    )

    tenantId = serializers.CharField(max_length=64, required=False, allow_blank=True)

    # Role will come from frontend (Template)
    role = serializers.ChoiceField(
        choices=["reader", "contributor", "owner"],
        default="reader"
    )

    scopeType = serializers.ChoiceField(
        choices=["subscription", "resource-group", "custom"],
        default="subscription"
    )

    resourceGroup = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
    )

    customScope = serializers.CharField(
        max_length=512,
        required=False,
        allow_blank=True
    )

    credentialType = serializers.ChoiceField(
        choices=["client-secret", "certificate"],
        default="client-secret"
    )

    secretDisplayName = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True
    )

    secretValidityMonths = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=24,
        default=12
    )

    createIfMissing = serializers.BooleanField(
        required=False,
        default=True
    )

    assignRoleNow = serializers.BooleanField(
        required=False,
        default=True
    )

    tags = serializers.DictField(
        child=serializers.CharField(max_length=256, allow_blank=True),
        required=False,
        default=dict,
    )

    dryRun = serializers.BooleanField(
        required=False,
        default=True
    )

    def validate(self, attrs):

        scope_type = attrs.get("scopeType")
        custom_scope = (attrs.get("customScope") or "").strip()
        credential_type = attrs.get("credentialType")
        secret_name = (attrs.get("secretDisplayName") or "").strip()
        resource_group = (attrs.get("resourceGroup") or "").strip()

        # Validate custom scope
        if scope_type == "custom":

            if not custom_scope:
                raise serializers.ValidationError({
                    "customScope": "customScope is required for custom scope."
                })

            if not custom_scope.startswith("/"):
                raise serializers.ValidationError({
                    "customScope": "customScope must start with '/'."
                })

        # Auto create secret name if missing
        if credential_type == "client-secret" and not secret_name:

            sp_name = attrs.get("servicePrincipalName", "")
            attrs["secretDisplayName"] = f"{sp_name}-secret"

        # Certificate flow validation
        if credential_type == "certificate" and not attrs.get("dryRun", True):

            raise serializers.ValidationError({
                "credentialType":
                "certificate flow is not implemented yet. Use client-secret or set dryRun=true."
            })

        if scope_type == "resource-group":
            if not resource_group:
                raise serializers.ValidationError({
                    "resourceGroup": "resourceGroup is required when scopeType is resource-group."
                })

        attrs["resourceGroup"] = resource_group

        return attrs
class CreateUserSerializer(serializers.Serializer):
    displayName = serializers.CharField(max_length=150)
    userPrincipalName = serializers.EmailField(max_length=254)
    mailNickname = serializers.RegexField(
        regex=r"^[A-Za-z0-9._-]{1,64}$",
        max_length=64,
        error_messages={
            "invalid": "mailNickname supports letters, numbers, dot, underscore, and hyphen only.",
        },
    )
    password = serializers.CharField(required=False, allow_blank=True, max_length=128)
    forceChangePasswordNextSignIn = serializers.BooleanField(required=False, default=True)
    accountEnabled = serializers.BooleanField(required=False, default=True)
    tenantId = serializers.CharField(max_length=64, required=False, allow_blank=True)
    dryRun = serializers.BooleanField(required=False, default=True)


class CreateGroupSerializer(serializers.Serializer):
    displayName = serializers.CharField(max_length=150)
    mailNickname = serializers.RegexField(
        regex=r"^[A-Za-z0-9._-]{1,64}$",
        max_length=64,
        error_messages={
            "invalid": "mailNickname supports letters, numbers, dot, underscore, and hyphen only.",
        },
    )
    description = serializers.CharField(max_length=512, required=False, allow_blank=True)
    mailEnabled = serializers.BooleanField(required=False, default=False)
    securityEnabled = serializers.BooleanField(required=False, default=True)
    groupTypes = serializers.ListField(
        child=serializers.CharField(max_length=32),
        required=False,
        allow_empty=True,
        default=list,
    )
    memberUserIds = serializers.ListField(
        child=serializers.CharField(max_length=128),
        required=False,
        allow_empty=True,
        default=list,
    )
    tenantId = serializers.CharField(max_length=64, required=False, allow_blank=True)
    tags = serializers.DictField(
        child=serializers.CharField(max_length=256, allow_blank=True),
        required=False,
        default=dict,
    )
    dryRun = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        mail_enabled = bool(attrs.get("mailEnabled", False))
        security_enabled = bool(attrs.get("securityEnabled", True))
        group_types = attrs.get("groupTypes", []) or []

        if "Unified" in group_types and not mail_enabled:
            raise serializers.ValidationError({"groupTypes": "Unified group requires mailEnabled=true."})

        if not mail_enabled and not security_enabled:
            raise serializers.ValidationError("At least one of mailEnabled or securityEnabled must be true.")

        return attrs


class CreateBackupSerializer(serializers.Serializer):
    subscription = serializers.CharField(max_length=128)
    resourceGroup = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=80)
    backupVaultName = serializers.RegexField(
        regex=r"^[A-Za-z][A-Za-z0-9-]{1,49}$",
        max_length=50,
        error_messages={
            "invalid": (
                "Backup vault name must be 2-50 characters, start with a letter, "
                "and use only letters, numbers, or hyphen."
            ),
        },
    )
    publicNetworkAccess = serializers.ChoiceField(
        choices=["Enabled", "Disabled"],
        required=False,
        default="Enabled",
    )
    tags = serializers.DictField(
        child=serializers.CharField(max_length=256, allow_blank=True),
        required=False,
        default=dict,
    )
    dryRun = serializers.BooleanField(required=False, default=True)

    def validate_region(self, value):
        normalized = (value or "").strip()
        if normalized.lower() == "other":
            raise serializers.ValidationError("Region cannot be 'Other'. Select or type a valid Azure region.")
        return normalized

class AssignServicePrincipalRoleSerializer(serializers.Serializer):
    principal_id = serializers.CharField(max_length=128)  # REQUIRED
    role = serializers.ChoiceField(choices=["reader", "contributor", "owner"])
    scope_type = serializers.ChoiceField(
        choices=["subscription", "resourceGroup", "vnet", "keyvault", "custom"]
    )
    subscription = serializers.CharField(max_length=128)
    resource_group = serializers.CharField(max_length=128, required=False, allow_blank=True)
    vnet = serializers.CharField(max_length=128, required=False, allow_blank=True)
    keyvault = serializers.CharField(max_length=128, required=False, allow_blank=True)
    scope = serializers.CharField(max_length=512, required=False, allow_blank=True)


class AzureNSGSerializer(serializers.Serializer):
    # Basic Info
    subscription_id = serializers.CharField(max_length=100)
    resource_group = serializers.CharField(max_length=100)
    location = serializers.CharField(max_length=100)
    nsg_name = serializers.CharField(max_length=100)

    # Security Rules (Optional)
    security_rules = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )

    # Mode (dry-run or actual)
    mode = serializers.ChoiceField(
        choices=["create", "dry-run"],
        default="create",
        required=False
    )

    def validate_nsg_name(self, value):
        if " " in value:
            raise serializers.ValidationError("NSG name should not contain spaces.")
        return value

    def validate_security_rules(self, value):
        for rule in value:
            required_fields = ["name", "priority", "direction", "access", "protocol"]

            for field in required_fields:
                if field not in rule:
                    raise serializers.ValidationError(
                        f"Missing '{field}' in security rule."
                    )

        return value

from rest_framework import serializers

# -------------------------------
# KEY VAULT SERIALIZER
# -------------------------------
class KeyVaultSerializer(serializers.Serializer):
    subscription = serializers.CharField()
    resourceGroup = serializers.CharField()
    region = serializers.CharField()
    keyVaultName = serializers.CharField()
    tenantId = serializers.CharField(required=False, allow_blank=True)
    skuName = serializers.ChoiceField(choices=["standard", "premium"], default="standard")

    # 🔥 FORCE BACKEND RULES
    enableRbacAuthorization = serializers.BooleanField(default=True)
    publicNetworkAccess = serializers.ChoiceField(
        choices=["Enabled", "Disabled"], default="Disabled"
    )
    enablePurgeProtection = serializers.BooleanField(default=True)
    enabledForDeployment = serializers.BooleanField(default=True)
    enabledForDiskEncryption = serializers.BooleanField(default=True)
    enabledForTemplateDeployment = serializers.BooleanField(default=True)

    # -------------------------------
    # VALIDATION
    # -------------------------------
    def validate_keyVaultName(self, value):
        if len(value) < 3 or len(value) > 24:
            raise serializers.ValidationError("Key Vault name must be 3-24 chars")

        if not value[0].isalpha():
            raise serializers.ValidationError("Must start with a letter")

        if not value[-1].isalnum():
            raise serializers.ValidationError("Must end with letter or number")

        if "--" in value:
            raise serializers.ValidationError("No consecutive hyphens allowed")

        return value

    def validate_region(self, value):
        # 🔥 Normalize region for Azure
        return value.lower().replace(" ", "")


# -------------------------------
# PRIVATE ENDPOINT SERIALIZER
# -------------------------------
class PrivateEndpointSerializer(serializers.Serializer):
    name = serializers.CharField()
    vnet = serializers.CharField()
    subnet = serializers.CharField()


# -------------------------------
# MAIN SERIALIZER
# -------------------------------
class KeyVaultWithPESerializer(serializers.Serializer):
    keyVault = KeyVaultSerializer()
    privateEndpoint = PrivateEndpointSerializer()
    dryRun = serializers.BooleanField(required=False, default=True)

class AssignRole1Serializer(serializers.Serializer):
    principal_id = serializers.CharField(required=True, allow_blank=False)
    role_definition_id = serializers.CharField(required=True, allow_blank=False)
    scope = serializers.CharField(required=True, allow_blank=False)

    # ---------------- SCOPE VALIDATION ----------------
    def validate_scope(self, value):
        if not value:
            raise serializers.ValidationError("Scope is required")

        if not value.startswith("/subscriptions/"):
            raise serializers.ValidationError(
                "Scope must start with '/subscriptions/'"
            )

        parts = value.strip("/").split("/")

        # Subscription level
        if len(parts) == 2:
            if parts[0] != "subscriptions":
                raise serializers.ValidationError("Invalid subscription scope")
            return value

        # Resource group level
        if len(parts) == 4:
            if parts[0] != "subscriptions" or parts[2] != "resourceGroups":
                raise serializers.ValidationError("Invalid resource group scope")
            return value

        # Resource level
        if len(parts) >= 6:
            if parts[0] != "subscriptions" or parts[2] != "resourceGroups":
                raise serializers.ValidationError("Invalid resource scope")
            if "providers" not in parts:
                raise serializers.ValidationError("Invalid resource scope (missing providers)")
            return value

        raise serializers.ValidationError("Invalid scope structure")

    # ---------------- FULL VALIDATION ----------------
    def validate(self, data):
        if not data.get("principal_id"):
            raise serializers.ValidationError({
                "principal_id": "principal_id is required"
            })

        if not data.get("scope"):
            raise serializers.ValidationError({
                "scope": "scope is required"
            })

        if not data.get("role_definition_id"):
            raise serializers.ValidationError({
                "role_definition_id": "role_definition_id is required"
            })

        return data
