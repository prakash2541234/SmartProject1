import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Vm.css";

const REGION_OPTIONS = [
  "(Africa) South Africa North",
  "(Asia Pacific) Australia East",
  "(Asia Pacific) Central India",
  "(Asia Pacific) East Asia",
  "(Asia Pacific) Indonesia Central",
  "(Asia Pacific) Japan East",
  "(Asia Pacific) Japan West",
  "(Asia Pacific) Korea Central",
  "(Asia Pacific) Malaysia West",
  "(Asia Pacific) New Zealand North",
  "(Asia Pacific) Southeast Asia",
  "(Canada) Canada Central",
  "(Europe) Austria East",
  "(Europe) Belgium Central",
  "(Europe) France Central",
  "(Europe) Germany West Central",
  "(Europe) Italy North",
  "(Europe) North Europe",
  "(Europe) Norway East",
  "(Europe) Poland Central",
  "(Europe) Spain Central",
  "(Europe) Sweden Central",
  "(Europe) Switzerland North",
  "(Europe) West Europe",
  "(Mexico) Mexico Central",
  "(Middle East) Israel Central",
  "(Middle East) Qatar Central",
  "(Middle East) UAE North",
  "(South America) Brazil South",
  "(South America) Chile Central",
  "(UK) UK South",
  "(US) Central US",
  "(US) East US",
  "(US) West US 2",
  "(US) East US 2",
  "(US) North Central US",
  "(US) South Central US",
  "(US) West Central US",
  "(US) West US",
  "(US) West US 3",
];

const VM_SIZE_OPTIONS = [
  "Standard_B2s",
  "Standard_B4ms",
  "Standard_D2s_v5",
  "Standard_D4s_v5",
  "Standard_D8s_v5",
  "Standard_E2s_v5",
  "Standard_E4s_v5",
];

const IMAGE_PRESETS = {
  Linux: {
    publisher: "Canonical",
    offer: "0001-com-ubuntu-server-jammy",
    sku: "22_04-lts-gen2",
  },
  Windows: {
    publisher: "MicrosoftWindowsServer",
    offer: "WindowsServer",
    sku: "2022-datacenter-azure-edition",
  },
};

// Validation regex
const VM_NAME_REGEX = /^[A-Za-z][A-Za-z0-9-]{1,63}$/;
const ADMIN_USERNAME_REGEX = /^[A-Za-z][A-Za-z0-9._-]{2,31}$/;
const SSH_KEY_REGEX = /^ssh-(rsa|ed25519|ecdsa)\s+\S+/;

// Windows computer name additional rule set
const WINDOWS_HOSTNAME_INVALID_CHARS = /[~!@#$%^&*()=+\[\]{}\\|;:.'",<>/?]/;

// Normalize username candidates from users API
const toAdminUsernameCandidate = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";

  const beforeDomain = raw.includes("@") ? raw.split("@")[0] : raw;
  const cleaned = beforeDomain.replace(/[^A-Za-z0-9._-]/g, "").slice(0, 32);

  if (cleaned.length < 3) return "";
  if (!/^[A-Za-z]/.test(cleaned)) return "";
  return cleaned;
};

const buildInitialForm = () => ({
  subscription: "",
  resourceGroup: "",
  region: "",
  vmName: "",
  vmSize: VM_SIZE_OPTIONS[0],
  osType: "Linux",
  imagePublisher: IMAGE_PRESETS.Linux.publisher,
  imageOffer: IMAGE_PRESETS.Linux.offer,
  imageSku: IMAGE_PRESETS.Linux.sku,
  adminUsername: "",
  authenticationType: "password",
  adminPassword: "",
  sshPublicKey: "",
  virtualNetworkName: "",
  subnetName: "",
  osDiskType: "Premium_LRS",
  osDiskSizeGb: 64,
  enablePublicIp: true,
  publicIpSku: "Standard",
});

// Backend base—aligns with your Django urls.py (/api/moniter/azure/create-vm/)
const AZURE_BASE = "http://localhost:8000/api/moniter/azure";

export default function Vm() {
  const navigate = useNavigate();

  const [form, setForm] = useState(buildInitialForm());
  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]);
  const [vnets, setVnets] = useState([]); // <-- NEW: VNET state
  const [tags, setTags] = useState({});
  const [newTagKey, setNewTagKey] = useState("");
  const [newTagValue, setNewTagValue] = useState("");
  const [azureUsers, setAzureUsers] = useState([]);
  const [loadingMeta, setLoadingMeta] = useState({
    subscriptions: false,
    resourceGroups: false,
    users: false,
    vnets: false, // <-- NEW: loading flag
  });
  const [metaError, setMetaError] = useState({
    subscriptions: "",
    resourceGroups: "",
    users: "",
    vnets: "", // <-- NEW: error string
  });

  const [applyInAzure, setApplyInAzure] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [lastPayload, setLastPayload] = useState(null);

  const setMetaLoading = (field, value) => {
    setLoadingMeta((prev) => ({ ...prev, [field]: value }));
  };

  const setMetaErrorValue = (field, value) => {
    setMetaError((prev) => ({ ...prev, [field]: value }));
  };

  const addTag = () => {
    const key = newTagKey.trim();
    const value = newTagValue.trim();
    if (!key || !value) return;

    setTags((prev) => ({ ...prev, [key]: value }));
    setNewTagKey("");
    setNewTagValue("");
  };

  const removeTag = (key) => {
    setTags((prev) => {
      const updated = { ...prev };
      delete updated[key];
      return updated;
    });
  };

  const updateField = (field, value) => {
    if (field === "osType") {
      const preset = IMAGE_PRESETS[value] || IMAGE_PRESETS.Linux;
      setForm((prev) => ({
        ...prev,
        osType: value,
        imagePublisher: preset.publisher,
        imageOffer: preset.offer,
        imageSku: preset.sku,
      }));
      return;
    }

    if (field === "authenticationType") {
      setForm((prev) => ({
        ...prev,
        authenticationType: value,
        // keep only relevant credential field populated
        adminPassword: value === "password" ? prev.adminPassword : "",
        sshPublicKey: value === "ssh" ? prev.sshPublicKey : "",
      }));
      return;
    }

    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const fetchResourceGroups = async (subscriptionId) => {
    if (!subscriptionId) {
      setResourceGroups([]);
      return;
    }

    setMetaLoading("resourceGroups", true);
    setMetaErrorValue("resourceGroups", "");
    try {
      const response = await fetch(
        `${AZURE_BASE}/resource-groups/?subscription_id=${encodeURIComponent(subscriptionId)}`
      );
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to fetch resource groups.");
      }

      const groups = data.resource_groups || [];
      setResourceGroups(groups);

      // Reset vnets when RG changes later
    } catch (err) {
      setResourceGroups([]);
      setMetaErrorValue("resourceGroups", err.message || "Unable to fetch resource groups.");
    } finally {
      setMetaLoading("resourceGroups", false);
    }
  };

  // NEW: Fetch VNets for selected sub + RG
  const fetchVnets = async (subscriptionId, resourceGroup) => {
    if (!subscriptionId || !resourceGroup) {
      setVnets([]);
      return;
    }

    setMetaLoading("vnets", true);
    setMetaErrorValue("vnets", "");
    try {
      const url = `${AZURE_BASE}/vnets/?subscription_id=${encodeURIComponent(
        subscriptionId
      )}&resource_group=${encodeURIComponent(resourceGroup)}`;
      const response = await fetch(url);
      const data = await response.json().catch(() => ({}));

      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to fetch VNets.");
      }

      // Expecting data like: { status: 'success', vnets: [{ id, name, addressSpace, ... }, ...] }
      const list = Array.isArray(data.vnets) ? data.vnets : [];
      setVnets(list);

      // If only one VNet & none selected, preselect it
      if (list.length === 1 && !form.virtualNetworkName) {
        setForm((prev) => ({ ...prev, virtualNetworkName: list[0].name || "" }));
      }
    } catch (err) {
      setVnets([]);
      setMetaErrorValue("vnets", err.message || "Unable to fetch virtual networks.");
    } finally {
      setMetaLoading("vnets", false);
    }
  };

  const fetchSubscriptions = async () => {
    setMetaLoading("subscriptions", true);
    setMetaErrorValue("subscriptions", "");

    try {
      const response = await fetch(`${AZURE_BASE}/subscriptions/`);
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to fetch subscriptions.");
      }

      const items = data.subscriptions || [];
      setSubscriptions(items);

      const defaultSub = data.default_subscription_id || "";
      const hasDefault = items.some((item) => item.subscription_id === defaultSub);
      const currentExists = items.some((item) => item.subscription_id === form.subscription);

      if (currentExists && form.subscription) {
        await fetchResourceGroups(form.subscription);
      } else {
        let nextSubscription = "";
        if (items.length === 1) {
          nextSubscription = items[0].subscription_id || "";
        } else if (hasDefault) {
          nextSubscription = defaultSub;
        } else if (items.length > 0) {
          nextSubscription = items[0].subscription_id || "";
        }

        if (nextSubscription) {
          setForm((prev) => ({ ...prev, subscription: nextSubscription }));
          await fetchResourceGroups(nextSubscription);
        }
      }
    } catch (err) {
      setSubscriptions([]);
      setMetaErrorValue("subscriptions", err.message || "Unable to fetch subscriptions.");
    } finally {
      setMetaLoading("subscriptions", false);
    }
  };

  const fetchAzureUsers = async () => {
    setMetaLoading("users", true);
    setMetaErrorValue("users", "");
    try {
      const response = await fetch(`${AZURE_BASE}/ad-users/?limit=200`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to fetch Azure AD users.");
      }
      setAzureUsers(data.users || []);
    } catch (err) {
      setAzureUsers([]);
      setMetaErrorValue("users", err.message || "Unable to fetch Azure AD users.");
    } finally {
      setMetaLoading("users", false);
    }
  };

  useEffect(() => {
    fetchSubscriptions();
    fetchAzureUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When subscription changes, reset dependent fields and data
  useEffect(() => {
    // Reset RG/VNET when subscription changes
    setForm((prev) => ({
      ...prev,
      resourceGroup: prev.subscription === form.subscription ? prev.resourceGroup : "",
      virtualNetworkName: "",
    }));
    setVnets([]);
  }, [form.subscription]);

  // Auto-fetch VNets when RG or subscription changes
  useEffect(() => {
    if (form.subscription && form.resourceGroup) {
      fetchVnets(form.subscription, form.resourceGroup);
    } else {
      setVnets([]);
      setForm((prev) => ({ ...prev, virtualNetworkName: "", subnetName: "" }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.subscription, form.resourceGroup]);

  const selectedVnet = useMemo(
    () => vnets.find((vnet) => vnet?.name === form.virtualNetworkName) || null,
    [vnets, form.virtualNetworkName]
  );

  const subnetOptions = Array.isArray(selectedVnet?.subnets) ? selectedVnet.subnets : [];

  useEffect(() => {
    if (!selectedVnet) {
      setForm((prev) => (prev.subnetName ? { ...prev, subnetName: "" } : prev));
      return;
    }

    setForm((prev) => {
      const available = Array.isArray(selectedVnet.subnets) ? selectedVnet.subnets : [];
      const hasMatch = prev.subnetName && available.some((sn) => sn.name === prev.subnetName);
      if (hasMatch) return prev;
      if (available.length === 1) {
        return { ...prev, subnetName: available[0].name || "" };
      }
      if (prev.subnetName && available.length > 1) {
        return { ...prev, subnetName: "" };
      }
      return prev;
    });
  }, [selectedVnet]);

  const adminUserOptions = useMemo(() => {
    const seen = new Set();
    return (azureUsers || [])
      .map((user) => {
        const candidate =
          toAdminUsernameCandidate(user.user_principal_name) ||
          toAdminUsernameCandidate(user.mail) ||
          toAdminUsernameCandidate(user.display_name);

        if (!candidate) return null;
        const dedupeKey = candidate.toLowerCase();
        if (seen.has(dedupeKey)) return null;
        seen.add(dedupeKey);

        const title = user.display_name || candidate;
        const secondary = user.user_principal_name || user.mail || "";
        return {
          key: user.id || candidate,
          value: candidate,
          label: secondary ? `${title} (${secondary})` : title,
        };
      })
      .filter(Boolean);
  }, [azureUsers]);

  // ---- Validation booleans
  const isPasswordAuth = form.authenticationType === "password";
  const isSshAuth = form.authenticationType === "ssh";
  const isWindows = form.osType === "Windows";

  const password = String(form.adminPassword || "");
  const passwordPolicyValid =
    password.length >= 12 &&
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /\d/.test(password) &&
    /[^A-Za-z0-9]/.test(password);

  const sshKeyValid = SSH_KEY_REGEX.test((form.sshPublicKey || "").trim());

  // Backend forbids Windows + SSH (you check this in serializer). Block in UI too.
  const windowsSshInvalid = isWindows && isSshAuth;

  // Windows computer name rules (based on VM name used as hostname)
  const windowsHostnameValid =
    !isWindows ||
    (form.vmName.trim().length <= 15 &&
      !WINDOWS_HOSTNAME_INVALID_CHARS.test(form.vmName.trim()) &&
      !/^\d+$/.test(form.vmName.trim()));

  // Final "auth valid" logic
  const authValid =
    !windowsSshInvalid &&
    ((isPasswordAuth && passwordPolicyValid) || (isSshAuth && sshKeyValid));

  // Detailed password issues to show the user
  const passwordIssues = (() => {
    const pwd = String(form.adminPassword || "");
    const issues = [];
    if (pwd.length < 12) issues.push("Length must be at least 12 characters.");
    if (!/[A-Z]/.test(pwd)) issues.push("Must include at least one uppercase letter.");
    if (!/[a-z]/.test(pwd)) issues.push("Must include at least one lowercase letter.");
    if (!/\d/.test(pwd)) issues.push("Must include at least one number.");
    if (!/[^A-Za-z0-9]/.test(pwd)) issues.push("Must include at least one special character.");
    return issues;
  })();

  // Top-level checks for enabling Submit
  const checks = [
    { id: "sub", label: "Subscription is selected", ok: Boolean(form.subscription.trim()) },
    { id: "rg", label: "Resource group is selected or typed", ok: Boolean(form.resourceGroup.trim()) },
    { id: "region", label: "Region is selected", ok: Boolean(form.region.trim()) },
    { id: "name", label: "VM name is valid (2-64, starts with letter)", ok: VM_NAME_REGEX.test(form.vmName.trim()) },
    { id: "win-host", label: "Windows computer name rules ok (if Windows)", ok: windowsHostnameValid },
    { id: "size", label: "VM size is selected", ok: Boolean(form.vmSize.trim()) },
    {
      id: "admin-user",
      label: "Admin username is valid (3-32, letters/numbers/._-)",
      ok: ADMIN_USERNAME_REGEX.test(form.adminUsername.trim()),
    },
    {
      id: "windows-ssh",
      label: "Windows VM cannot use SSH authentication",
      ok: !windowsSshInvalid,
    },
    {
      id: "auth",
      label: "Admin authentication details are valid",
      ok: authValid,
    },
    {
      id: "network",
      label: "Virtual network and subnet names are provided",
      ok: Boolean(form.virtualNetworkName.trim()) && Boolean(form.subnetName.trim()),
    },
    {
      id: "disk",
      label: "OS disk size is between 30 and 4095 GB",
      ok: Number(form.osDiskSizeGb) >= 30 && Number(form.osDiskSizeGb) <= 4095,
    },
  ];

  const canSubmit = checks.every((item) => item.ok);

  const parseApiError = (data, fallback) => {
    if (data?.message) {
      return data.message;
    }

    const errors = data?.errors || data;
    if (errors && typeof errors === "object") {
      const firstField = Object.keys(errors)[0];
      const firstValue = errors[firstField];
      if (Array.isArray(firstValue) && firstValue.length > 0) {
        return `${firstField}: ${firstValue[0]}`;
      }
      if (typeof firstValue === "string") {
        return `${firstField}: ${firstValue}`;
      }
      if (typeof firstValue === "object" && firstValue !== null) {
        const nestedField = Object.keys(firstValue)[0];
        const nestedValue = firstValue[nestedField];
        if (Array.isArray(nestedValue) && nestedValue.length > 0) {
          return `${firstField}.${nestedField}: ${nestedValue[0]}`;
        }
        if (typeof nestedValue === "string") {
          return `${firstField}.${nestedField}: ${nestedValue}`;
        }
      }
    }

    return fallback;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");

    if (!canSubmit) {
      // Provide a friendlier reason when auth or name is the blocker
      if (!windowsHostnameValid) {
        setError(
          "Windows computer name must be ≤ 15 characters, cannot be all numbers, and cannot contain special characters (~ ! @ # $ % ^ & * ( ) = + _ [ ] { } \\ | ; : . ' \" , < > / ?)."
        );
      } else if (windowsSshInvalid) {
        setError("Windows VM cannot use SSH authentication. Switch to Password.");
      } else if (isPasswordAuth && !passwordPolicyValid) {
        setError("Password does not meet complexity requirements. See the checklist below.");
      } else if (isSshAuth && !sshKeyValid) {
        setError("SSH public key format is invalid. It must be a single line starting with ssh-rsa, ssh-ed25519, or ssh-ecdsa.");
      } else {
        setError("Please complete all required checks before continuing.");
      }
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        subscription: form.subscription.trim(),
        resourceGroup: form.resourceGroup.trim(),
        region: form.region.trim(),
        vmName: form.vmName.trim(),
        vmSize: form.vmSize,
        osType: form.osType,
        image: {
          publisher: form.imagePublisher.trim(),
          offer: form.imageOffer.trim(),
          sku: form.imageSku.trim(),
        },
        admin: {
          username: form.adminUsername.trim(),
          authenticationType: form.authenticationType,
          password: isPasswordAuth ? form.adminPassword : "",
          sshPublicKey: isSshAuth ? form.sshPublicKey.trim() : "",
        },
        network: {
          virtualNetworkName: form.virtualNetworkName.trim(),
          subnetName: form.subnetName.trim(),
          enablePublicIp: Boolean(form.enablePublicIp),
          ...(form.enablePublicIp ? { publicIpSku: form.publicIpSku } : {}),
        },
        storage: {
          osDiskType: form.osDiskType,
          osDiskSizeGb: Number(form.osDiskSizeGb),
        },
        tags,
        // If checkbox is on, apply in Azure (dryRun=false); otherwise only validate (dryRun=true)
        dryRun: !applyInAzure,
      };

      // NOTE: Use your backend URL that exists in urls.py
      const response = await fetch(`${AZURE_BASE}/create-vm/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(parseApiError(data, "Create VM API request failed."));
      }

      setLastPayload(data.plan || payload);
      if (data.status === "accepted" || data.mode === "dry-run") {
        setMessage("Dry run successful. VM payload is valid.");
      } else {
        setMessage("Virtual machine request submitted successfully.");
      }
    } catch (err) {
      setError(err.message || "Failed to submit VM request.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setForm(buildInitialForm());
    setResourceGroups([]);
    setVnets([]);
    setApplyInAzure(false);
    setMessage("");
    setError("");
    setLastPayload(null);
    fetchSubscriptions();
    setTags({});
    setNewTagKey("");
    setNewTagValue("");
  };

  return (
    <div className="vm-page">
      <div className="vm-header">
        <button className="vm-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create Virtual Machine</h1>
      </div>

      <form className="vm-form" onSubmit={handleSubmit}>
        {/* ---- Basic Details ---- */}
        <section className="vm-section">
          <h2>Basic Details</h2>
          <div className="vm-grid">
            <label className="full-width">
              Subscription:
              <div className="field-inline">
                <input
                  type="text"
                  list="vm-sub-options"
                  value={form.subscription}
                  onChange={(e) => {
                    const value = e.target.value;
                    updateField("subscription", value);
                    if (subscriptions.some((item) => item.subscription_id === value)) {
                      fetchResourceGroups(value);
                    } else {
                      setResourceGroups([]);
                      setVnets([]);
                      setForm((prev) => ({ ...prev, resourceGroup: "", virtualNetworkName: "" }));
                    }
                  }}
                  placeholder="Select subscription ID or type manually"
                  required
                />
                <button
                  type="button"
                  className="mini-btn"
                  onClick={fetchSubscriptions}
                  disabled={loadingMeta.subscriptions}
                >
                  {loadingMeta.subscriptions ? "Refreshing..." : "Refresh"}
                </button>
              </div>
              <datalist id="vm-sub-options">
                {subscriptions.map((sub) => (
                  <option
                    key={sub.subscription_id}
                    value={sub.subscription_id}
                    label={`${sub.display_name || "Unnamed"} (${sub.state || "Unknown"})`}
                  />
                ))}
              </datalist>
              <span className="hint">Found: {subscriptions.length} subscription(s).</span>
              {metaError.subscriptions && <span className="error-text">{metaError.subscriptions}</span>}
            </label>

            <label>
              Resource Group:
              <div className="field-inline">
                <input
                  type="text"
                  list="vm-rg-options"
                  value={form.resourceGroup}
                  onChange={(e) => {
                    updateField("resourceGroup", e.target.value);
                    // Trigger VNet fetch when a user types a known RG name
                    if (subscriptions.some((item) => item.subscription_id === form.subscription) && e.target.value) {
                      fetchVnets(form.subscription, e.target.value);
                    } else {
                      setVnets([]);
                      setForm((prev) => ({ ...prev, virtualNetworkName: "" }));
                    }
                  }}
                  placeholder="Select or type resource group"
                  required
                />
                <button
                  type="button"
                  className="mini-btn"
                  onClick={() => fetchResourceGroups(form.subscription)}
                  disabled={!form.subscription || loadingMeta.resourceGroups}
                >
                  {loadingMeta.resourceGroups ? "Refreshing..." : "Refresh RG"}
                </button>
              </div>
              <datalist id="vm-rg-options">
                {resourceGroups.map((group) => (
                  <option
                    key={group.id || group.name}
                    value={group.name}
                    label={group.location ? `${group.name} (${group.location})` : group.name}
                  />
                ))}
              </datalist>
              <span className="hint">Available groups: {resourceGroups.length}</span>
              {metaError.resourceGroups && <span className="error-text">{metaError.resourceGroups}</span>}
            </label>

            <label>
              Region:
              <input
                type="text"
                list="vm-region-options"
                value={form.region}
                onChange={(e) => updateField("region", e.target.value)}
                placeholder="Select region or type manually"
                required
              />
              <datalist id="vm-region-options">
                {REGION_OPTIONS.map((region) => (
                  <option key={region} value={region} />
                ))}
              </datalist>
            </label>

            <label>
              VM Name:
              <input
                type="text"
                value={form.vmName}
                onChange={(e) => updateField("vmName", e.target.value)}
                placeholder="Example: app-prod-vm-01"
                minLength={2}
                maxLength={64}
                required
              />
              {isWindows && !windowsHostnameValid && (
                <p className="error-text">
                  Windows computer name must be ≤ 15 chars, not all numbers, and cannot contain
                  special characters: ~ ! @ # $ % ^ & * ( ) = + _ [ ] { } \ | ; : . ' " , &lt; &gt; / ?
                </p>
              )}
            </label>

            <label>
              VM Size:
              <select value={form.vmSize} onChange={(e) => updateField("vmSize", e.target.value)}>
                {VM_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>

            <label>
              OS Type:
              <select value={form.osType} onChange={(e) => updateField("osType", e.target.value)}>
                <option value="Linux">Linux</option>
                <option value="Windows">Windows</option>
              </select>
            </label>

            <label>
              Image Publisher:
              <input
                type="text"
                value={form.imagePublisher}
                onChange={(e) => updateField("imagePublisher", e.target.value)}
                required
              />
            </label>

            <label>
              Image Offer:
              <input
                type="text"
                value={form.imageOffer}
                onChange={(e) => updateField("imageOffer", e.target.value)}
                required
              />
            </label>

            <label>
              Image SKU:
              <input
                type="text"
                value={form.imageSku}
                onChange={(e) => updateField("imageSku", e.target.value)}
                required
              />
            </label>
          </div>
        </section>

        <section className="vm-section">
          <h2>Admin Access</h2>
          <div className="vm-grid">
            <label className="full-width">
              Admin Username:
              <div className="field-inline">
                <input
                  type="text"
                  list="vm-admin-user-options"
                  value={form.adminUsername}
                  onChange={(e) => updateField("adminUsername", e.target.value)}
                  placeholder="Select user or type username (3-32 chars)"
                  minLength={3}
                  maxLength={32}
                  required
                />
                <button
                  type="button"
                  className="mini-btn"
                  onClick={fetchAzureUsers}
                  disabled={loadingMeta.users}
                >
                  {loadingMeta.users ? "Refreshing..." : "Refresh Users"}
                </button>
              </div>
              <datalist id="vm-admin-user-options">
                {adminUserOptions.map((user) => (
                  <option key={user.key} value={user.value} label={user.label} />
                ))}
              </datalist>
              <span className="hint">
                Available users: {adminUserOptions.length}. You can also enter a username manually.
              </span>
              {metaError.users && <span className="error-text">{metaError.users}</span>}
            </label>

            <label>
              Authentication Type:
              <select
                value={form.authenticationType}
                onChange={(e) => updateField("authenticationType", e.target.value)}
              >
                <option value="password">Password</option>
                <option value="ssh">SSH Public Key</option>
              </select>
            </label>
            {form.authenticationType === "password" && (
              <label className="full-width">
                Admin Password:
                <input
                  type="password"
                  value={form.adminPassword}
                  onChange={(e) => updateField("adminPassword", e.target.value)}
                  placeholder="Min 12 chars, upper/lower/number/symbol"
                  autoComplete="new-password"
                  required={isPasswordAuth}
                />
                {!passwordPolicyValid && isPasswordAuth && (
                  <ul className="hint-list">
                    {passwordIssues.map((msg) => (
                      <li key={msg} className="error-text">
                        {msg}
                      </li>
                    ))}
                  </ul>
                )}
              </label>
            )}
            {form.authenticationType === "ssh" && (
              <label className="full-width">
                SSH Public Key:
                <textarea
                  value={form.sshPublicKey}
                  onChange={(e) => updateField("sshPublicKey", e.target.value)}
                  placeholder="ssh-rsa AAAAB3... user@host"
                  required={isSshAuth}
                />
                {!sshKeyValid && isSshAuth && (
                  <p className="error-text">
                    SSH public key must be a single line starting with ssh-rsa, ssh-ed25519, or ssh-ecdsa.
                  </p>
                )}
                {windowsSshInvalid && (
                  <p className="error-text">Windows VM cannot use SSH authentication. Switch to Password.</p>
                )}
              </label>
            )}
          </div>
        </section>
        <section className="vm-section">
          <h2>Network and Storage</h2>
          <div className="vm-grid">
            <label>
              Virtual Network:
              <div className="field-inline">
                <select
                  value={form.virtualNetworkName}
                  onChange={(e) => updateField("virtualNetworkName", e.target.value)}
                  required
                >
                  <option value="">Select a VNET</option>
                  {vnets.map((vnet) => {
                    const name = vnet?.name || "(unnamed)";
                    // Best effort display of address space or a hint
                    const addr =
                      (vnet?.addressSpace && (vnet.addressSpace.addressPrefixes || vnet.addressSpace)) ||
                      vnet?.ipAddress ||
                      "";
                    const suffix =
                      Array.isArray(addr) && addr.length ? ` (${addr[0]})` : addr ? ` (${addr})` : "";
                    return (
                      <option key={vnet?.id || name} value={name}>
                        {name}
                        {suffix}
                      </option>
                    );
                  })}
                </select>
                <button
                  type="button"
                  className="mini-btn"
                  onClick={() => fetchVnets(form.subscription, form.resourceGroup)}
                  disabled={!form.subscription || !form.resourceGroup || loadingMeta.vnets}
                >
                  {loadingMeta.vnets ? "Loading..." : "Refresh VNets"}
                </button>
              </div>
              {metaError.vnets && <span className="error-text">{metaError.vnets}</span>}
            </label>
            <label>
              Subnet Name:
              <input
                type="text"
                list="vm-subnet-options"
                value={form.subnetName}
                onChange={(e) => updateField("subnetName", e.target.value)}
                placeholder={
                  subnetOptions.length
                    ? "Select a subnet from the list"
                    : "Enter subnet name"
                }
                required
              />
              <datalist id="vm-subnet-options">
                {subnetOptions.map((subnet) => (
                  <option
                    key={subnet.id || subnet.name}
                    value={subnet.name}
                    label={
                      subnet.addressPrefix
                        ? `${subnet.name} (${subnet.addressPrefix})`
                        : subnet.name
                    }
                  />
                ))}
              </datalist>
              <span className="hint">
                Related subnets: {subnetOptions.length}
              </span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.enablePublicIp}
                onChange={(e) => updateField("enablePublicIp", e.target.checked)}
              />
              Attach Public IP
            </label>
            <label>
              Public IP SKU:
              <select
                value={form.publicIpSku}
                onChange={(e) => updateField("publicIpSku", e.target.value)}
                disabled={!form.enablePublicIp}
              >
                <option value="Standard">Standard</option>
                <option value="Basic">Basic</option>
              </select>
            </label>
            <label>
              OS Disk Type:
              <select value={form.osDiskType} onChange={(e) => updateField("osDiskType", e.target.value)}>
                <option value="Premium_LRS">Premium SSD</option>
                <option value="StandardSSD_LRS">Standard SSD</option>
                <option value="Standard_LRS">Standard HDD</option>
              </select>
            </label>
            <label>
              OS Disk Size (GB):
              <input
                type="number"
                min="30"
                max="4095"
                value={form.osDiskSizeGb}
                onChange={(e) => updateField("osDiskSizeGb", e.target.value)}
                required
              />
            </label>
            <div className="full-width">
              <h3>Tags (Optional)</h3>
              <div className="tag-input-row">
                <input
                  type="text"
                  placeholder="Tag key"
                  value={newTagKey}
                  onChange={(e) => setNewTagKey(e.target.value)}
                />
                <input
                  type="text"
                  placeholder="Tag value"
                  value={newTagValue}
                  onChange={(e) => setNewTagValue(e.target.value)}
                />
                <button
                  type="button"
                  className="mini-btn"
                  onClick={addTag}
                  disabled={!newTagKey.trim() || !newTagValue.trim()}
                >
                  Add
                </button>
              </div>
              <ul className="tag-list">
                {Object.entries(tags).map(([key, value]) => (
                  <li key={key} className="tag-item">
                    <span>
                      <strong>{key}</strong>: {value}
                    </span>
                    <button
                      type="button"
                      className="remove-tag-btn"
                      onClick={() => removeTag(key)}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
        <section className="vm-section">
          <h2>Validation Status</h2>
          <ul className="requirement-list">
            {checks.map((check) => (
              <li key={check.id} className={`requirement-item ${check.ok ? "ok" : "bad"}`}>
                <span className={`status-dot ${check.ok ? "ok" : "bad"}`} />
                <span>{check.label}</span>
              </li>
            ))}
          </ul>
        </section>
        <div className="vm-actions">
          <label className="execute-toggle">
            <input
              type="checkbox"
              checked={applyInAzure}
              onChange={(e) => setApplyInAzure(e.target.checked)}
              disabled={submitting}
            />
            Apply changes in Azure now
          </label>
          <button type="submit" className="submit-btn" disabled={!canSubmit || submitting}>
            {submitting ? "Submitting..." : "Submit"}
          </button>
          <button type="button" className="reset-btn" onClick={handleReset} disabled={submitting}>
            Reset
          </button>
        </div>
        {error && <p className="vm-error">{error}</p>}
        {message && <p className="vm-message">{message}</p>}
        {lastPayload && (
          <section className="payload-box">
            <h3>Submitted Plan Preview</h3>
            <pre>{JSON.stringify(lastPayload, null, 2)}</pre>
          </section>
        )}
      </form>
    </div>
  );
}