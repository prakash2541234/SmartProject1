import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateVNet.css";

/* ---------------------------------- Helpers ---------------------------------- */
const createEmptySubnet = () => ({
  subnetName: "",
  addressPrefix: "",
});

const createEmptyRoute = () => ({
  routeName: "",
  destination: "",
  nextHop: "Internet",
  nextHopIp: "",
});
const createEmptyVNet = () => ({
  // vnetName: "",                 // REMOVED: will be auto-generated
  addressSpace: "",
  locationType: "",
  environment: "dev",
  role: "contributor",
  subnets: [createEmptySubnet()],
  tags: {},
  tagKey: "",
  tagValue: "",
});

const createEmptyKeyVault = () => ({
  // keyVaultName: "",             // REMOVED: will be auto-generated,
  skuName: "standard",
  tenantId: "",
  enableRbacAuthorization: true,
  publicNetworkAccess: "Enabled",
  softDeleteRetentionInDays: 90,
  enablePurgeProtection: false,
  enabledForDeployment: false,
  enabledForDiskEncryption: false,
  enabledForTemplateDeployment: false,
  locationType: "",
  environment: "dev",
  role: "contributor",
  tags: {},
  tagKey: "",
  tagValue: "",
});

const createServicePrincipalTemplate = () => ({
  // name: "",                     // REMOVED: will be auto-generated
  tenantId: "",
  role: "contributor",
  scopeType: "subscription",
  resourceGroup: "",
  customScope: "",
  credentialType: "client-secret",
  secretDisplayName: "sp-client-secret",
  secretValidityMonths: 12,
  environment: "dev",
  locationType: "",
  createIfMissing: true,
  assignRoleNow: false,
  tags: {},
  tagKey: "",
  tagValue: "",
});

/* ------------------------------- Static Options ------------------------------- */
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
  "Other",
  "(Asia Pacific) Australia Central",
  "(Asia Pacific) Australia Southeast",
  "(Asia Pacific) Korea South",
  "(Asia Pacific) South India",
  "(Asia Pacific) West India",
  "(Canada) Canada East",
  "(UK) UK West",
  "(US) East US 2",
  "(US) North Central US",
  "(US) South Central US",
  "(US) West Central US",
  "(US) West US",
  "(US) West US 3",
];

const SP_NAME_REGEX = /^[A-Za-z][A-Za-z0-9-_]{2,119}$/; // kept if you later re-enable manual names

const ENV_OPTIONS = [
  { value: "dev", label: "Development (dev)" },
  { value: "stage", label: "Staging (stage)" },
  { value: "prod", label: "Production (prod)" },
];

const LOCATION_TYPE_OPTIONS = [
  { value: "", label: "Select" },
  { value: "select", label: "Select" },
  { value: "ind", label: "Ind" },
];

const ROLE_OPTIONS = [
  { value: "owner", label: "Owner" },
  { value: "contributor", label: "Contributor" },
  { value: "reader", label: "Reader" },
];

const sanitize = (v) => (v || "").toLowerCase().replace(/[^a-z0-9]/g, "");

/* ---------------------------------- Component --------------------------------- */
export default function CreateVNet() {
  const navigate = useNavigate();

  /* ----------------------------- Basic / Global State ----------------------------- */
  const [form, setForm] = useState({
    subscription: "",
    // resourceGroup: "",                    // REMOVED from Basic Details flow
    region: "",
    enableCustomRouting: "No",
    routeTableName: "",
  });

  // NEW: location + environment for naming (Resource Group + others)
  const [locationCode, setLocationCode] = useState("");
  const [environment, setEnvironment] = useState("dev");

  const [routes, setRoutes] = useState([createEmptyRoute()]);
  const [applyInAzure, setApplyInAzure] = useState(false);
  const [message, setMessage] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  /* ------------------------------- Azure Metadata ------------------------------- */
  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]); // kept for SP scope selection
  const [loadingMeta, setLoadingMeta] = useState({
    subscriptions: false,
    resourceGroups: false,
  });
  const [metaError, setMetaError] = useState({
    subscriptions: "",
    resourceGroups: "",
  });

  const setMetaLoading = (key, value) =>
    setLoadingMeta((prev) => ({ ...prev, [key]: value }));
  const setMetaErrorValue = (key, value) =>
    setMetaError((prev) => ({ ...prev, [key]: value }));

  const updateFormField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  /* ------------------------------ UI-only Sections ------------------------------ */
  // Resource Groups (UI only metadata rows)
  const [rgItems, setRgItems] = useState([
    { locationType: "", environment: "dev", role: "contributor" },
  ]);
  const addRgItem = () =>
    setRgItems((prev) => [
      ...prev,
      { locationType: "", environment: "dev", role: "contributor" },
    ]);
  const handleRGItemChange = (index, field, value) => {
    setRgItems((prev) =>
      prev.map((rg, i) => (i === index ? { ...rg, [field]: value } : rg))
    );
  };

  // Service Principals (UI only)
  const [servicePrincipals, setServicePrincipals] = useState([
    createServicePrincipalTemplate(),
  ]);
  const addServicePrincipal = () =>
    setServicePrincipals((prev) => [
      ...prev,
      createServicePrincipalTemplate(),
    ]);
  const handleSPChange = (index, field, value) => {
    setServicePrincipals((prev) =>
      prev.map((sp, i) => (i === index ? { ...sp, [field]: value } : sp))
    );
  };
  const removeServicePrincipal = (index) => {
    setServicePrincipals((prev) =>
      prev.length > 1 ? prev.filter((_, i) => i !== index) : prev
    );
  };

  const addServicePrincipalTag = (index) => {
    setServicePrincipals((prev) =>
      prev.map((sp, i) => {
        if (i !== index) return sp;
        const key = (sp.tagKey || "").trim();
        const value = (sp.tagValue || "").trim();
        if (!key || !value) return sp;
        return {
          ...sp,
          tags: { ...sp.tags, [key]: value },
          tagKey: "",
          tagValue: "",
        };
      })
    );
  };

  const removeServicePrincipalTag = (index, tagKey) => {
    setServicePrincipals((prev) =>
      prev.map((sp, i) => {
        if (i !== index) return sp;
        const nextTags = { ...sp.tags };
        delete nextTags[tagKey];
        return { ...sp, tags: nextTags };
      })
    );
  };

  // VNets with nested Subnets
  const [vnets, setVnets] = useState([createEmptyVNet()]);
  const addVNet = () => setVnets((prev) => [...prev, createEmptyVNet()]);
  const removeVNet = (vIndex) =>
    setVnets((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== vIndex) : prev));
  const updateVNetField = (vIndex, field, value) => {
    setVnets((prev) =>
      prev.map((v, i) => (i === vIndex ? { ...v, [field]: value } : v))
    );
  };
  const addVNetTag = (vIndex) => {
    setVnets((prev) =>
      prev.map((v, i) => {
        if (i !== vIndex) return v;
        const key = (v.tagKey || "").trim();
        const value = (v.tagValue || "").trim();
        if (!key || !value) return v;
        return {
          ...v,
          tags: { ...v.tags, [key]: value },
          tagKey: "",
          tagValue: "",
        };
      })
    );
  };
  const removeVNetTag = (vIndex, tagKey) => {
    setVnets((prev) =>
      prev.map((v, i) => {
        if (i !== vIndex) return v;
        const nextTags = { ...v.tags };
        delete nextTags[tagKey];
        return { ...v, tags: nextTags };
      })
    );
  };
  const addSubnetToVNet = (vIndex) =>
    setVnets((prev) =>
      prev.map((v, i) =>
        i === vIndex ? { ...v, subnets: [...v.subnets, createEmptySubnet()] } : v
      )
    );
  const updateSubnetInVNet = (vIndex, sIndex, field, value) =>
    setVnets((prev) =>
      prev.map((v, i) => {
        if (i !== vIndex) return v;
        const updated = v.subnets.map((s, j) =>
          j === sIndex ? { ...s, [field]: value } : s
        );
        return { ...v, subnets: updated };
      })
    );
  const removeSubnetFromVNet = (vIndex, sIndex) =>
    setVnets((prev) =>
      prev.map((v, i) => {
        if (i !== vIndex) return v;
        const next = v.subnets.filter((_, j) => j !== sIndex);
        return { ...v, subnets: next.length ? next : [createEmptySubnet()] };
      })
    );

  // Key Vaults (UI only)
  const [keyVaults, setKeyVaults] = useState([createEmptyKeyVault()]);
  const addKeyVault = () => setKeyVaults((prev) => [...prev, createEmptyKeyVault()]);
  const removeKeyVault = (kvIndex) =>
    setKeyVaults((prev) =>
      prev.length > 1 ? prev.filter((_, i) => i !== kvIndex) : prev
    );
  const updateKeyVaultField = (kvIndex, field, value) =>
    setKeyVaults((prev) =>
      prev.map((kv, i) => (i === kvIndex ? { ...kv, [field]: value } : kv))
    );
  const addKeyVaultTag = (kvIndex) => {
    setKeyVaults((prev) =>
      prev.map((kv, i) => {
        if (i !== kvIndex) return kv;
        const key = (kv.tagKey || "").trim();
        const value = (kv.tagValue || "").trim();
        if (!key || !value) return kv;
        return {
          ...kv,
          tags: { ...kv.tags, [key]: value },
          tagKey: "",
          tagValue: "",
        };
      })
    );
  };
  const removeKeyVaultTag = (kvIndex, tagKey) => {
    setKeyVaults((prev) =>
      prev.map((kv, i) => {
        if (i !== kvIndex) return kv;
        const nextTags = { ...kv.tags };
        delete nextTags[tagKey];
        return { ...kv, tags: nextTags };
      })
    );
  };

  /* --------------------------- Azure Metadata Fetching --------------------------- */
  const fetchSubscriptions = async () => {
    setMetaLoading("subscriptions", true);
    setMetaErrorValue("subscriptions", "");
    try {
      const response = await fetch("http://localhost:8000/api/moniter/azure/subscriptions/");
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to load subscriptions.");
      }
      setSubscriptions(data.subscriptions || []);
    } catch (err) {
      setSubscriptions([]);
      setMetaErrorValue("subscriptions", err.message);
    } finally {
      setMetaLoading("subscriptions", false);
    }
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
        `http://localhost:8000/api/moniter/azure/resource-groups/?subscription_id=${encodeURIComponent(
          subscriptionId
        )}`
      );
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to load resource groups.");
      }
      setResourceGroups(data.resource_groups || []);
    } catch (err) {
      setResourceGroups([]);
      setMetaErrorValue("resourceGroups", err.message);
    } finally {
      setMetaLoading("resourceGroups", false);
    }
  };

  const loadSubscriptionMetadata = async (sid) => {
    // We still load RGs for SP scope=resourceGroup selection (independent from automation RG)
    await fetchResourceGroups(sid);
  };

  useEffect(() => {
    fetchSubscriptions();
  }, []);

  useEffect(() => {
    // Auto-select if only one subscription is available
    if (subscriptions.length === 1) {
      const sid = subscriptions[0].subscription_id;
      updateFormField("subscription", sid);
      loadSubscriptionMetadata(sid);
    }
  }, [subscriptions]);

  /* ------------------------------------ Reset ----------------------------------- */
  const handleReset = () => {
    setForm({
      subscription: "",
      region: "",
      enableCustomRouting: "No",
      routeTableName: "",
    });
    setLocationCode("");
    setEnvironment("dev");
    setRoutes([createEmptyRoute()]);
    setMessage("");
    setSubmitError("");
    setRgItems([{ locationType: "", environment: "dev", role: "contributor" }]);
    setServicePrincipals([createServicePrincipalTemplate()]);
    setVnets([createEmptyVNet()]);
    setKeyVaults([createEmptyKeyVault()]);
  };

  /* ----------------------------------- Submit ----------------------------------- */
  // NOTE: Your direct create-vnet endpoint probably needs an *existing* RG.
  // Since RG is now auto-generated in Auto2, we recommend using "Run Automation".
  // You can disable Submit (or implement a pre-create of RG then call create-vnet).
  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage("");
    setSubmitError("Direct Submit is disabled. Please use 'Run Automation' so names and RG are auto-generated.");
    // If you want to support Submit, reply and I’ll wire RG auto-create + VNet create here.
  };

  const buildAutomationState = () => {
    const sanitizedRoutes = routes
      .map((route) => ({
        routeName: route.routeName.trim(),
        destination: route.destination.trim(),
        nextHop: route.nextHop,
        nextHopIp: route.nextHopIp.trim(),
      }))
      .filter((route) => route.routeName && route.destination && route.nextHop);

    const sanitizedVnets = vnets
      .map((v) => ({
        // vnetName omitted => will be generated in Auto2
        addressSpace: v.addressSpace.trim(),
        subnets: (v.subnets || [])
          .map((s) => ({
            subnetName: s.subnetName.trim(),
            addressPrefix: s.addressPrefix.trim(),
          }))
          .filter((s) => s.subnetName && s.addressPrefix),
        tags: v.tags || {},
        locationType: v.locationType,
        environment: v.environment,
        role: v.role,
      }))
      // Require only addressSpace + subnets > 0 (not vnetName)
      .filter((v) => v.addressSpace && v.subnets.length > 0);

    const sanitizedServicePrincipals = servicePrincipals.map((sp) => ({
      // servicePrincipalName omitted => will be generated in Auto2
      tenantId: sp.tenantId.trim(),
      role: sp.role,
      scopeType: sp.scopeType,
      resourceGroup: sp.resourceGroup.trim(), // optional, only used when scopeType=resourceGroup
      customScope: sp.customScope.trim(),
      credentialType: sp.credentialType,
      secretDisplayName: sp.secretDisplayName.trim() || "sp-client-secret",
      secretValidityMonths: Number(sp.secretValidityMonths) || 12,
      createIfMissing: Boolean(sp.createIfMissing),
      assignRoleNow: Boolean(sp.assignRoleNow),
      tags: sp.tags || {},
      locationType: sp.locationType,
      environment: sp.environment,
    }));
    // Do not filter them out for missing name; Auto2 generates.

    const sanitizedKeyVaults = keyVaults.map((kv) => ({
      // keyVaultName omitted => will be generated in Auto2
      skuName: kv.skuName,
      tenantId: kv.tenantId.trim(),
      enableRbacAuthorization: kv.enableRbacAuthorization,
      publicNetworkAccess: kv.publicNetworkAccess,
      softDeleteRetentionInDays: Number(kv.softDeleteRetentionInDays) || 90,
      enablePurgeProtection: kv.enablePurgeProtection,
      enabledForDeployment: kv.enabledForDeployment,
      enabledForDiskEncryption: kv.enabledForDiskEncryption,
      enabledForTemplateDeployment: kv.enabledForTemplateDeployment,
      tags: kv.tags || {},
      locationType: kv.locationType,
      environment: kv.environment,
      role: kv.role,
    }));
    // Do not filter out for missing name; Auto2 generates.

    return {
      subscription: form.subscription.trim(),
      region: form.region.trim(),
      location: sanitize(locationCode),
      environment: sanitize(environment),
      enableCustomRouting: form.enableCustomRouting,
      routeTableName: form.routeTableName.trim(),
      routes: sanitizedRoutes,
      vnets: sanitizedVnets,
      servicePrincipals: sanitizedServicePrincipals,
      keyVaults: sanitizedKeyVaults,
      // No resourceGroup here — Auto2 will generate RG using naming.js
    };
  };

  const automationReady =
    Boolean(form.subscription.trim() && form.region.trim() && locationCode.trim()) &&
    vnets.some((v) => v.addressSpace.trim() && v.subnets.length > 0);

  const handleLaunchAutomation = () => {
    const automationState = buildAutomationState();

    if (!automationState.subscription || !automationState.region || !automationState.location) {
      setSubmitError("Subscription, region, and location are required to run automation.");
      return;
    }

    if (!automationState.vnets.length) {
      setSubmitError("At least one VNet with valid subnets is required before running automation.");
      return;
    }

    navigate("/auto2", { state: automationState });
  };

  /* ----------------------------------- Render ----------------------------------- */
  return (
    <div className="vnet-page">
      <div className="vnet-header">
        <button className="vnet-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create Network & Resources</h1>
      </div>

      <form className="vnet-form" onSubmit={handleSubmit}>
        {/* ---------------- 1) BASIC DETAILS ---------------- */}
        <section className="vnet-section">
          <h2>Basic Details (Required)</h2>

          <div className="vnet-grid">
            {/* Subscription */}
            <label className="full-width">
              Subscription:
              <select
                value={form.subscription}
                onChange={(e) => {
                  const sid = e.target.value;
                  updateFormField("subscription", sid);
                  loadSubscriptionMetadata(sid);
                }}
                required
              >
                <option value="">Select Subscription</option>
                {subscriptions.map((s) => (
                  <option key={s.subscription_id} value={s.subscription_id}>
                    {s.display_name} ({s.state})
                  </option>
                ))}
              </select>
              {metaError.subscriptions && (
                <span className="error-text">{metaError.subscriptions}</span>
              )}
            </label>

            {/* Region */}
            <label>
              Region:
              <input
                type="text"
                list="region-options"
                value={form.region}
                onChange={(e) => updateFormField("region", e.target.value)}
                required
              />
              <datalist id="region-options">
                {REGION_OPTIONS.map((r) => (
                  <option key={r} value={r} />
                ))}
              </datalist>
            </label>

            {/* Location (code) used for naming */}
            <label>
              Location (code):
              <input
                type="text"
                placeholder="e.g., ind, eus, westeu"
                value={locationCode}
                onChange={(e) => setLocationCode(e.target.value)}
                required
              />
              <span className="field-hint">Automation will generate the Resource Group and other names using this code.</span>
            </label>

            {/* Environment used for naming */}
            <label>
              Environment:
              <select value={environment} onChange={(e) => setEnvironment(e.target.value)} required>
                {ENV_OPTIONS.map((env) => (
                  <option key={env.value} value={env.value}>
                    {env.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        {/* ---------------- 2) RESOURCE GROUPS (UI-ONLY METADATA) ---------------- */}
        <section className="vnet-section">
          <div className="section-row">
            <h2>Resource Groups (metadata)</h2>
            <button type="button" className="small-btn" onClick={addRgItem}>
              + Add Resource Group
            </button>
          </div>

          <div className="stack">
            {rgItems.map((rg, index) => (
              <div className="card" key={`rgitem-${index}`}>
                <div className="card-head">
                  <h3>Resource Group #{index + 1}</h3>
                </div>
                <div className="vnet-grid">
                  <label>
                    Location Type:
                    <select
                      value={rg.locationType}
                      onChange={(e) => handleRGItemChange(index, "locationType", e.target.value)}
                    >
                      {LOCATION_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Environment:
                    <select
                      value={rg.environment}
                      onChange={(e) => handleRGItemChange(index, "environment", e.target.value)}
                    >
                      <option value="">Select Environment</option>
                      <option value="dev">Dev</option>
                      <option value="stage">Stage</option>
                      <option value="prod">Prod</option>
                    </select>
                  </label>

                  <label>
                    Role:
                    <select
                      value={rg.role}
                      onChange={(e) => handleRGItemChange(index, "role", e.target.value)}
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------- 3) SERVICE PRINCIPALS (UI-ONLY) ---------------- */}
        <section className="vnet-section">
          <div className="section-row">
            <h2>Service Principals</h2>
            <button type="button" className="small-btn" onClick={addServicePrincipal}>
              + Add Service Principal
            </button>
          </div>

          <div className="stack">
            {servicePrincipals.map((sp, index) => (
              <div className="card" key={`sp-${index}`}>
                <div className="card-head">
                  <h3>Service Principal #{index + 1}</h3>
                  {servicePrincipals.length > 1 && (
                    <button
                      type="button"
                      className="link-btn danger"
                      onClick={() => removeServicePrincipal(index)}
                    >
                      Remove
                    </button>
                  )}
                </div>

                <div className="vnet-grid">
                  {/* Location Type */}
                  <label>
                    Location Type:
                    <select
                      value={sp.locationType}
                      onChange={(e) => handleSPChange(index, "locationType", e.target.value)}
                    >
                      {LOCATION_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* Environment */}
                  <label>
                    Environment:
                    <select
                      value={sp.environment}
                      onChange={(e) => handleSPChange(index, "environment", e.target.value)}
                    >
                      {ENV_OPTIONS.map((env) => (
                        <option key={env.value} value={env.value}>
                          {env.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* Name (REMOVED) */}
                  <div className="full-width">
                    <em className="field-hint">Service Principal name will be auto-generated during automation.</em>
                  </div>

                  {/* Tenant ID */}
                  <label>
                    Tenant ID (optional):
                    <input
                      type="text"
                      value={sp.tenantId}
                      onChange={(e) => handleSPChange(index, "tenantId", e.target.value)}
                      placeholder="Leave empty to use default"
                    />
                  </label>

                  {/* Role */}
                  <label>
                    Role:
                    <select
                      value={sp.role}
                      onChange={(e) => handleSPChange(index, "role", e.target.value)}
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* Scope Type */}
                  <label>
                    Scope Type:
                    <select
                      value={sp.scopeType}
                      onChange={(e) => handleSPChange(index, "scopeType", e.target.value)}
                    >
                      <option value="subscription">Subscription</option>
                      <option value="resourceGroup">Resource Group</option>
                      <option value="custom">Custom</option>
                    </select>
                  </label>

                  {/* Resource Group (for RG scope) */}
                  {sp.scopeType === "resourceGroup" && (
                    <label className="full-width">
                      Resource Group:
                      <select
                        value={sp.resourceGroup}
                        onChange={(e) => handleSPChange(index, "resourceGroup", e.target.value)}
                        disabled={resourceGroups.length === 0}
                      >
                        <option value="">Select Resource Group</option>
                        {resourceGroups.map((group) => (
                          <option key={group.name} value={group.name}>
                            {group.name} {group.location ? `(${group.location})` : ""}
                          </option>
                        ))}
                      </select>
                      {resourceGroups.length === 0 && (
                        <span className="field-hint">
                          Select a subscription first to load resource groups.
                        </span>
                      )}
                    </label>
                  )}

                  {/* Custom Scope */}
                  {sp.scopeType === "custom" && (
                    <label className="full-width">
                      Custom Scope:
                      <input
                        type="text"
                        value={sp.customScope}
                        onChange={(e) => handleSPChange(index, "customScope", e.target.value)}
                        placeholder="/subscriptions/{subId}/resourceGroups/{rg}/providers/..."
                      />
                    </label>
                  )}

                  {/* Credential Type */}
                  <label>
                    Credential Type:
                    <select
                      value={sp.credentialType}
                      onChange={(e) => handleSPChange(index, "credentialType", e.target.value)}
                    >
                      <option value="client-secret">Client Secret</option>
                      <option value="certificate">Certificate</option>
                    </select>
                  </label>

                  {/* Secret Display Name */}
                  <label>
                    Secret Display Name:
                    <input
                      type="text"
                      value={sp.secretDisplayName}
                      onChange={(e) => handleSPChange(index, "secretDisplayName", e.target.value)}
                    />
                  </label>

                  {/* Secret Validity */}
                  <label>
                    Secret Validity (Months):
                    <input
                      type="number"
                      min="1"
                      max="24"
                      value={sp.secretValidityMonths}
                      onChange={(e) =>
                        handleSPChange(index, "secretValidityMonths", Number(e.target.value))
                      }
                    />
                  </label>

                  {/* Checkboxes */}
                  <label className="full-width">
                    <input
                      type="checkbox"
                      checked={sp.createIfMissing}
                      onChange={(e) => handleSPChange(index, "createIfMissing", e.target.checked)}
                    />{" "}
                    Create if missing
                  </label>

                  <label className="full-width">
                    <input
                      type="checkbox"
                      checked={sp.assignRoleNow}
                      onChange={(e) => handleSPChange(index, "assignRoleNow", e.target.checked)}
                    />{" "}
                    Assign role now
                  </label>

                  {/* Tags */}
                  <div className="full-width">
                    <h4>Tags (Optional)</h4>
                    <div className="tag-input-row">
                      <input
                        type="text"
                        placeholder="Tag key"
                        value={sp.tagKey}
                        onChange={(e) => handleSPChange(index, "tagKey", e.target.value)}
                      />
                      <input
                        type="text"
                        placeholder="Tag value"
                        value={sp.tagValue}
                        onChange={(e) => handleSPChange(index, "tagValue", e.target.value)}
                      />
                      <button
                        type="button"
                        className="mini-btn"
                        onClick={() => addServicePrincipalTag(index)}
                        disabled={!sp.tagKey?.trim() || !sp.tagValue?.trim()}
                      >
                        Add
                      </button>
                    </div>
                    <ul className="tag-list">
                      {Object.entries(sp.tags || {}).map(([key, value]) => (
                        <li key={key} className="tag-item">
                          <span>
                            <strong>{key}</strong>: {value}
                          </span>
                          <button
                            type="button"
                            className="remove-tag-btn"
                            onClick={() => removeServicePrincipalTag(index, key)}
                          >
                            Remove
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------- 4) VIRTUAL NETWORKS ---------------- */}
        <section className="vnet-section">
          <div className="section-row">
            <h2>Virtual Networks</h2>
            <button type="button" className="small-btn" onClick={addVNet}>
              + Add VNet
            </button>
          </div>
          <div className="stack">
            {vnets.map((vnet, vIndex) => (
              <div className="card" key={`vnet-${vIndex}`}>
                <div className="card-head">
                  <h3>VNet {vIndex + 1}</h3>
                  {vnets.length > 1 && (
                    <button
                      type="button"
                      className="link-btn danger"
                      onClick={() => removeVNet(vIndex)}
                    >
                      Remove VNet
                    </button>
                  )}
                </div>

                <div className="vnet-grid">
                  {/* VNet Name removed */}
                  <div className="full-width">
                    <em className="field-hint">VNet name will be auto-generated during automation.</em>
                  </div>

                  {/* Address Space */}
                  <label>
                    Address Space:
                    <input
                      type="text"
                      value={vnet.addressSpace}
                      onChange={(e) => updateVNetField(vIndex, "addressSpace", e.target.value)}
                      placeholder="e.g. 10.1.0.0/16"
                      required
                    />
                  </label>
                  {/* Location Type */}
                  <label>
                    Location Type:
                    <select
                      value={vnet.locationType}
                      onChange={(e) => updateVNetField(vIndex, "locationType", e.target.value)}
                    >
                      {LOCATION_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* Environment */}
                  <label>
                    Environment:
                    <select
                      value={vnet.environment}
                      onChange={(e) => updateVNetField(vIndex, "environment", e.target.value)}
                    >
                      {ENV_OPTIONS.map((env) => (
                        <option key={env.value} value={env.value}>
                          {env.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* Role */}
                  <label>
                    Role:
                    <select
                      value={vnet.role}
                      onChange={(e) => updateVNetField(vIndex, "role", e.target.value)}
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {/* Subnets for this VNet */}
                <div className="section-row" style={{ marginTop: "10px" }}>
                  <h3>Subnets for VNet {vIndex + 1}</h3>
                  <button
                    type="button"
                    className="small-btn"
                    onClick={() => addSubnetToVNet(vIndex)}
                  >
                    + Add Subnet
                  </button>
                </div>

                <div className="stack">
                  {vnet.subnets.map((subnet, sIndex) => (
                    <div className="card" key={`vnet-${vIndex}-subnet-${sIndex}`}>
                      <div className="card-head">
                        <h4>Subnet {vIndex + 1}-{sIndex + 1}</h4>
                        {vnet.subnets.length > 1 && (
                          <button
                            type="button"
                            className="link-btn danger"
                            onClick={() => removeSubnetFromVNet(vIndex, sIndex)}
                          >
                            Remove
                          </button>
                        )}
                      </div>

                      <div className="vnet-grid">
                        <label>
                          Subnet Name:
                          <input
                            type="text"
                            value={subnet.subnetName}
                            onChange={(e) =>
                              updateSubnetInVNet(vIndex, sIndex, "subnetName", e.target.value)
                            }
                            required
                          />
                        </label>

                        <label>
                          Address Prefix:
                          <input
                            type="text"
                            value={subnet.addressPrefix}
                            onChange={(e) =>
                              updateSubnetInVNet(vIndex, sIndex, "addressPrefix", e.target.value)
                            }
                            required
                          />
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------- 5) KEY VAULTS ---------------- */}
        <section className="vnet-section">
          <div className="section-row">
            <h2>Key Vaults</h2>
            <button type="button" className="small-btn" onClick={addKeyVault}>
              + Add Key Vault
            </button>
          </div>

          <div className="stack">
            {keyVaults.map((kv, kvIndex) => (
              <div className="card" key={`kv-${kvIndex}`}>
                <div className="card-head">
                  <h3>Key Vault #{kvIndex + 1}</h3>
                  {keyVaults.length > 1 && (
                    <button
                      type="button"
                      className="link-btn danger"
                      onClick={() => removeKeyVault(kvIndex)}
                    >
                      Remove
                    </button>
                  )}
                </div>

                <div className="vnet-grid">
                  {/* KV Name removed */}
                  <div className="full-width">
                    <em className="field-hint">Key Vault name will be auto-generated during automation.</em>
                  </div>

                  {/* SKU */}
                  <label>
                    SKU:
                    <select
                      value={kv.skuName}
                      onChange={(e) => updateKeyVaultField(kvIndex, "skuName", e.target.value)}
                    >
                      <option value="standard">Standard</option>
                      <option value="premium">Premium</option>
                    </select>
                  </label>

                  {/* Tenant ID */}
                  <label>
                    Tenant ID (optional):
                    <input
                      type="text"
                      value={kv.tenantId}
                      onChange={(e) => updateKeyVaultField(kvIndex, "tenantId", e.target.value)}
                      placeholder="Uses backend AZURE_TENANT_ID if empty"
                    />
                  </label>

                  {/* Location Type */}
                  <label>
                    Location Type:
                    <select
                      value={kv.locationType}
                      onChange={(e) => updateKeyVaultField(kvIndex, "locationType", e.target.value)}
                    >
                      {LOCATION_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* Environment */}
                  <label>
                    Environment:
                    <select
                      value={kv.environment}
                      onChange={(e) => updateKeyVaultField(kvIndex, "environment", e.target.value)}
                    >
                      {ENV_OPTIONS.map((env) => (
                        <option key={env.value} value={env.value}>
                          {env.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* Role */}
                  <label>
                    Role:
                    <select
                      value={kv.role}
                      onChange={(e) => updateKeyVaultField(kvIndex, "role", e.target.value)}
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* RBAC */}
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={kv.enableRbacAuthorization}
                      onChange={(e) =>
                        updateKeyVaultField(kvIndex, "enableRbacAuthorization", e.target.checked)
                      }
                    />
                    Enable RBAC Authorization
                  </label>

                  {/* Network Access */}
                  <label>
                    Public Network Access:
                    <select
                      value={kv.publicNetworkAccess}
                      onChange={(e) =>
                        updateKeyVaultField(kvIndex, "publicNetworkAccess", e.target.value)
                      }
                    >
                      <option value="Enabled">Enabled</option>
                      <option value="Disabled">Disabled</option>
                    </select>
                  </label>

                  {/* Soft Delete Retention */}
                  <label>
                    Soft Delete Retention (Days):
                    <input
                      type="number"
                      min="7"
                      max="90"
                      value={kv.softDeleteRetentionInDays}
                      onChange={(e) =>
                        updateKeyVaultField(kvIndex, "softDeleteRetentionInDays", Number(e.target.value))
                      }
                      required
                    />
                  </label>

                  {/* Flags */}
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={kv.enablePurgeProtection}
                      onChange={(e) =>
                        updateKeyVaultField(kvIndex, "enablePurgeProtection", e.target.checked)
                      }
                    />
                    Enable Purge Protection
                  </label>

                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={kv.enabledForDeployment}
                      onChange={(e) =>
                        updateKeyVaultField(kvIndex, "enabledForDeployment", e.target.checked)
                      }
                    />
                    Enable For Deployment
                  </label>

                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={kv.enabledForDiskEncryption}
                      onChange={(e) =>
                        updateKeyVaultField(kvIndex, "enabledForDiskEncryption", e.target.checked)
                      }
                    />
                    Enable For Disk Encryption
                  </label>

                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={kv.enabledForTemplateDeployment}
                      onChange={(e) =>
                        updateKeyVaultField(kvIndex, "enabledForTemplateDeployment", e.target.checked)
                      }
                    />
                    Enable For Template Deployment
                  </label>

                  <div className="full-width">
                    <h4>Tags (Optional)</h4>
                    <div className="tag-input-row">
                      <input
                        type="text"
                        placeholder="Tag key"
                        value={kv.tagKey}
                        onChange={(e) => updateKeyVaultField(kvIndex, "tagKey", e.target.value)}
                      />
                      <input
                        type="text"
                        placeholder="Tag value"
                        value={kv.tagValue}
                        onChange={(e) => updateKeyVaultField(kvIndex, "tagValue", e.target.value)}
                      />
                      <button
                        type="button"
                        className="mini-btn"
                        onClick={() => addKeyVaultTag(kvIndex)}
                        disabled={!kv.tagKey?.trim() || !kv.tagValue?.trim()}
                      >
                        Add
                      </button>
                    </div>
                    <ul className="tag-list">
                      {Object.entries(kv.tags || {}).map(([key, value]) => (
                        <li key={key} className="tag-item">
                          <span>
                            <strong>{key}</strong>: {value}
                          </span>
                          <button
                            type="button"
                            className="remove-tag-btn"
                            onClick={() => removeKeyVaultTag(kvIndex, key)}
                          >
                            Remove
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------- 6) ROUTE TABLE (GLOBAL OPTIONAL) ---------------- */}
        <section className="vnet-section">
          <h2>Route Table (Optional)</h2>

          <label>
            Enable Custom Routing?
            <select
              value={form.enableCustomRouting}
              onChange={(e) => updateFormField("enableCustomRouting", e.target.value)}
            >
              <option value="No">No</option>
              <option value="Yes">Yes</option>
            </select>
          </label>

          {form.enableCustomRouting === "Yes" && (
            <>
              <label>
                Route Table Name:
                <input
                  type="text"
                  value={form.routeTableName}
                  onChange={(e) => updateFormField("routeTableName", e.target.value)}
                  required
                />
              </label>

              <div className="section-row">
                <h3>Routes</h3>
                <button
                  type="button"
                  className="small-btn"
                  onClick={() => setRoutes((p) => [...p, createEmptyRoute()])}
                >
                  + Add Route
                </button>
              </div>

              <div className="stack">
                {routes.map((route, index) => (
                  <div className="card" key={`route-${index}`}>
                    <div className="card-head">
                      <h3>Route {index + 1}</h3>
                      {routes.length > 1 && (
                        <button
                          type="button"
                          className="link-btn danger"
                          onClick={() => setRoutes((p) => p.filter((_, i) => i !== index))}
                        >
                          Remove
                        </button>
                      )}
                    </div>

                    <div className="vnet-grid">
                      <label>
                        Route Name:
                        <input
                          type="text"
                          value={route.routeName}
                          onChange={(e) =>
                            setRoutes((prev) =>
                              prev.map((r, i) => (i === index ? { ...r, routeName: e.target.value } : r))
                            )
                          }
                          required
                        />
                      </label>

                      <label>
                        Destination:
                        <input
                          type="text"
                          value={route.destination}
                          onChange={(e) =>
                            setRoutes((prev) =>
                              prev.map((r, i) => (i === index ? { ...r, destination: e.target.value } : r))
                            )
                          }
                          required
                        />
                      </label>

                      <label>
                        Next Hop:
                        <select
                          value={route.nextHop}
                          onChange={(e) =>
                            setRoutes((prev) =>
                              prev.map((r, i) => {
                                if (i !== index) return r;
                                const value = e.target.value;
                                return value !== "VirtualAppliance"
                                  ? { ...r, nextHop: value, nextHopIp: "" }
                                  : { ...r, nextHop: value };
                              })
                            )
                          }
                        >
                          <option value="Internet">Internet</option>
                          <option value="VirtualNetworkGateway">VirtualNetworkGateway</option>
                          <option value="VirtualAppliance">VirtualAppliance</option>
                          <option value="VnetLocal">VnetLocal</option>
                          <option value="None">None</option>
                        </select>
                      </label>

                      {routes[index].nextHop === "VirtualAppliance" && (
                        <label>
                          Next Hop IP:
                          <input
                            type="text"
                            value={routes[index].nextHopIp}
                            onChange={(e) =>
                              setRoutes((prev) =>
                                prev.map((r, i) => (i === index ? { ...r, nextHopIp: e.target.value } : r))
                              )
                            }
                            required
                          />
                        </label>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        {/* ---------------- 7) ACTIONS ---------------- */}
        <div className="vnet-actions">
          <label className="execute-toggle">
            <input
              type="checkbox"
              checked={applyInAzure}
              onChange={(e) => setApplyInAzure(e.target.checked)}
              disabled={submitting}
            />
            Apply changes in Azure now
          </label>

          {/* Direct submit disabled by design (see handleSubmit) */}
          <button type="submit" className="submit-btn" disabled={true}>
            Submit (use Run Automation)
          </button>

          <button
            type="button"
            className="auto-run-btn"
            onClick={handleLaunchAutomation}
            disabled={submitting || !automationReady}
          >
            Run Automation
          </button>

          <button
            type="button"
            className="reset-btn"
            onClick={handleReset}
            disabled={submitting}
          >
            Reset
          </button>
        </div>

        {submitError && <p className="vnet-error">{submitError}</p>}
        {message && <p className="vnet-message">{message}</p>}
      </form>
    </div>
  );
}