import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "./Subscription-auto.css";

import {
  buildResourceGroupName,
  buildServicePrincipalName,
  buildVNetName,
  buildKeyVaultName,
} from "./Naming.jsx";

const AZURE_BASE = "http://localhost:8000/api/moniter/azure";

/* ---------------------------- Helpers / Utils ---------------------------- */

const createStages = (payload) => {
  const servicePrincipalCount = payload?.servicePrincipals?.length || 0;
  const vnetCount = payload?.vnets?.length || 0;
  const keyVaultCount = payload?.keyVaults?.length || 0;

  return [
    { id: "resource-group", title: "Resource group", status: "pending", loading: false },
    {
      id: "service-principals",
      title: `Service principals (${servicePrincipalCount})`,
      status: servicePrincipalCount > 0 ? "pending" : "completed",
      loading: false,
    },
    {
      id: "virtual-networks",
      title: `Virtual networks (${vnetCount})`,
      status: vnetCount > 0 ? "pending" : "completed",
      loading: false,
    },
    {
      id: "key-vaults",
      title: `Key vaults (${keyVaultCount})`,
      status: keyVaultCount > 0 ? "pending" : "completed",
      loading: false,
    },
  ];
};

const sanitize = (v) => (v || "").toLowerCase().replace(/[^a-z0-9]/g, "");

const tagsFor = (item, payload) => {
  const loc =
    sanitize(item?.locationType) ||
    sanitize(payload?.locationType) ||
    sanitize(payload?.tags?.locationType);

  const env =
    sanitize(item?.environment) ||
    sanitize(payload?.environment) ||
    sanitize(payload?.tags?.environment);

  const role =
    sanitize(item?.role) ||
    sanitize(payload?.role) ||
    sanitize(payload?.tags?.role);

  return { locationType: loc, environment: env, role };
};

const kvNameValid = (name) =>
  /^[a-z][a-z0-9-]{1,22}[a-z0-9]$/.test(name) && name.length >= 3 && name.length <= 24;

const toText = (val, fallback = "N/A") => {
  if (val == null) return fallback;
  if (typeof val === "string" || typeof val === "number") return String(val);
  return val.name ?? val.displayName ?? val.appId ?? val.id ?? fallback;
};

const safeList = (arr, getter) =>
  (arr || [])
    .map((item) => {
      try {
        return getter(item);
      } catch {
        return "Unnamed";
      }
    })
    .join(", ");

const normalizeScopeTypeForAssignAPI = (scopeType) => {
  const s = (scopeType || "").toLowerCase();
  if (s === "resource-group") return "resourceGroup";
  if (s === "subscription") return "subscription";
  if (s === "custom") return "custom";
  if (s === "resourcegroup") return "resourceGroup";
  return scopeType;
};

/* -------------------------------- Component -------------------------------- */

export default function Auto2() {
  const navigate = useNavigate();
  const { state } = useLocation(); // automationPayload
  const automationPayload = state;

  const initialSteps = useMemo(() => createStages(automationPayload), [automationPayload]);
  const [steps, setSteps] = useState(initialSteps);

  const [backendError, setBackendError] = useState("");
  const [finalMessage, setFinalMessage] = useState("");

  const [results, setResults] = useState({
    resourceGroup: null,
    servicePrincipals: [],
    vnets: [],
    keyVaults: [],
  });

  const rgNameRef = useRef(null);
  const taskStartedRef = useRef(false);

  const hasSummary = useMemo(() => {
    return (
      Boolean(results.resourceGroup) ||
      (results.servicePrincipals?.length || 0) > 0 ||
      (results.vnets?.length || 0) > 0 ||
      (results.keyVaults?.length || 0) > 0
    );
  }, [results]);

  /* ------------------------------ INIT ------------------------------ */

  useEffect(() => {
    if (!automationPayload) {
      navigate("/Template2");
      return;
    }
    setSteps(createStages(automationPayload));
  }, [automationPayload, navigate]);

  useEffect(() => {
    if (!automationPayload) return;
    if (taskStartedRef.current) return;
    taskStartedRef.current = true;
    runAutomation();
  }, [automationPayload]);

  const updateStep = (id, updates) => {
    setSteps((prev) => prev.map((step) => (step.id === id ? { ...step, ...updates } : step)));
  };

  /* ---------------------------- PIPELINE ---------------------------- */

  const runAutomation = async () => {
    setBackendError("");
    setFinalMessage("");

    const rgName = await ensureResourceGroup(automationPayload);
    if (!rgName) return;

    const okSP = await createServicePrincipals(automationPayload, rgName);
    if (!okSP) return;

    const okVNet = await createVirtualNetworks(automationPayload, rgName);
    if (!okVNet) return;

    const okKV = await createKeyVaults(automationPayload, rgName);
    if (!okKV) return;

    setFinalMessage("Template automation completed successfully.");
  };

  /* --------------------------- RESOURCE GROUP --------------------------- */

  const ensureResourceGroup = async (payload) => {
    updateStep("resource-group", { status: "running", loading: true });

    try {
      const tags = tagsFor(null, payload);

      const generatedRGName = await buildResourceGroupName(payload.subscription, tags);

      const res = await fetch(`${AZURE_BASE}/create-resource-group/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subscription: payload.subscription,
          resourceGroup: generatedRGName,
          region: payload.region,
          tags,
          dryRun: false,
        }),
      });

      const raw = await res.text();
      let body = {};
      try {
        body = JSON.parse(raw);
      } catch {}

      if (!res.ok) {
        if (raw.toLowerCase().includes("already")) {
          rgNameRef.current = generatedRGName;
          updateStep("resource-group", { status: "completed", loading: false });
          setResults((p) => ({
            ...p,
            resourceGroup: { __displayName: generatedRGName, __note: "Exists" },
          }));
          return generatedRGName;
        }
        throw new Error(body?.message || raw);
      }

      const rgDisplay = body.resource_group?.name ?? generatedRGName;
      rgNameRef.current = rgDisplay;

      updateStep("resource-group", { status: "completed", loading: false });
      setResults((p) => ({ ...p, resourceGroup: { __displayName: rgDisplay } }));

      return rgDisplay;

    } catch (err) {
      setBackendError(err.message);
      updateStep("resource-group", { status: "failed", loading: false });
      return null;
    }
  };

  /* ------------------------ SERVICE PRINCIPALS ------------------------ */

  const createServicePrincipals = async (payload, rgName) => {
    const principals = payload.servicePrincipals || [];

    if (!principals.length) {
      updateStep("service-principals", { status: "completed", loading: false });
      return true;
    }

    updateStep("service-principals", { status: "running", loading: true });

    const created = [];

    for (let sp of principals) {
      try {
        const tags = tagsFor(sp, payload);
        const generatedName = await buildServicePrincipalName(tags);

        const spResponse = await fetch(`${AZURE_BASE}/create-service-principal/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            subscription: payload.subscription,
            servicePrincipalName: generatedName,
            tenantId: sp.tenantId,
            role: sp.role,
            scopeType: sp.scopeType,
            resourceGroup: sp.scopeType === "resource-group" ? rgName : undefined,
            customScope: sp.scopeType === "custom" ? sp.customScope : undefined,
            dryRun: false,
          }),
        });

        const spBody = await spResponse.json();
        if (!spResponse.ok) throw new Error(spBody?.message);

        const principalId =
          spBody?.service_principal?.id ||
          spBody?.application?.id ||
          spBody?.objectId;

        if (!principalId) throw new Error("Missing ServicePrincipal ID");

        created.push({ name: generatedName, result: spBody });

      } catch (err) {
        setBackendError(err.message);
        updateStep("service-principals", { status: "failed", loading: false });
        return false;
      }
    }

    updateStep("service-principals", { status: "completed", loading: false });
    setResults((p) => ({ ...p, servicePrincipals: created }));
    return true;
  };

  /* --------------------------- CREATE VNETS --------------------------- */

  const createVirtualNetworks = async (payload, rgName) => {
    const networks = payload.vnets || [];

    if (!networks.length) {
      updateStep("virtual-networks", { status: "completed", loading: false });
      return true;
    }

    updateStep("virtual-networks", { status: "running", loading: true });

    const created = [];

    for (let vnet of networks) {
      try {
        const tags = tagsFor(vnet, payload);
        const generatedName = await buildVNetName(tags);

        const mergedTags = {
          ...(vnet.tags || {}),
          ...tags,
        };

        const response = await fetch(`${AZURE_BASE}/create-vnet/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            subscription: payload.subscription,
            resourceGroup: rgName,
            region: payload.region,
            vnetName: generatedName,
            addressSpace: vnet.addressSpace,
            subnets: vnet.subnets,
            tags: mergedTags,
            dryRun: false,
          }),
        });

        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body?.message);

        created.push({ name: generatedName, result: body });

      } catch (err) {
        setBackendError(err.message);
        updateStep("virtual-networks", { status: "failed", loading: false });
        return false;
      }
    }

    updateStep("virtual-networks", { status: "completed", loading: false });
    setResults((p) => ({ ...p, vnets: created }));
    return true;
  };

  /* --------------------- ⭐ UPDATED KEY VAULT CREATION ⭐ --------------------- */

  const createKeyVaults = async (payload, rgName) => {
    const vaults = payload.keyVaults || [];

    if (!vaults.length) {
      updateStep("key-vaults", { status: "completed", loading: false });
      return true;
    }

    updateStep("key-vaults", { status: "running", loading: true });

    const created = [];

    for (let kv of vaults) {
      try {
        // Read user inputs (only 4 fields)
        const skuName = payload.skuName || "standard";
        const locationType = payload.locationType || "";
        const environment = payload.environment || "";
        const role = payload.role || "";

        const tags = { locationType, environment, role };

        const generatedKvName = await buildKeyVaultName(tags);

        if (!kvNameValid(generatedKvName)) {
          throw new Error(`Generated Key Vault name "${generatedKvName}" is invalid.`);
        }

        // DEFAULTED Key Vault body
        const kvBody = {
          subscription: payload.subscription,
          resourceGroup: rgName,
          region: payload.region,
          keyVaultName: generatedKvName,

          skuName,
          tenantId: "",
          enableRbacAuthorization: true,
          publicNetworkAccess: "Disabled",
          privateEndpointNetworkPolicies: "Enabled",
          softDeleteRetentionInDays: 90,
          enablePurgeProtection: true,
          enabledResourceManagerForDeployment: true,
          enabledForDiskEncryption: true,
          enabledForTemplateDeployment: true,

          tags,
          dryRun: false,
        };

        const response = await fetch(`${AZURE_BASE}/create-key-vault/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(kvBody),
        });

        const raw = await response.text();
        let body = {};
        try {
          body = JSON.parse(raw);
        } catch {}

        if (!response.ok) throw new Error(body?.message || raw);

        created.push({ name: generatedKvName, result: body });

      } catch (err) {
        setBackendError(err.message);
        updateStep("key-vaults", { status: "failed", loading: false });
        return false;
      }
    }

    updateStep("key-vaults", { status: "completed", loading: false });
    setResults((p) => ({ ...p, keyVaults: created }));
    return true;
  };

  /* --------------------------- PROGRESS BAR --------------------------- */

  const progressPercent = useMemo(() => {
    const completed = steps.filter((s) => s.status === "completed").length;
    return (completed / steps.length) * 100;
  }, [steps]);

  return (
    <div className="sa-page">
      <div className="sa-header">
        <button className="sa-back" onClick={() => navigate("/Template2")}>
          {"<- Back"}
        </button>
        <h1>Template Automation</h1>
      </div>

      {/* PIPELINE */}
      <section className="sa-pipeline">
        <div className="sa-line-track">
          <div className="sa-line-fill" style={{ width: `${progressPercent}%` }} />
        </div>

        <div className="sa-stages">
          {steps.map((step, index) => (
            <div key={step.id} className={`sa-stage ${step.status}`}>
              <h3>{step.title}</h3>
              <div className={`sa-node ${step.status}`}>
                {step.loading ? "..." : index + 1}
              </div>
              <p className={`sa-stage-note ${step.status}`}>
                {step.loading
                  ? "Processing..."
                  : step.status === "pending"
                  ? "Pending"
                  : step.status === "completed"
                  ? "Completed"
                  : "Failed"}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* SUMMARY / MESSAGES */}
      {finalMessage && (
        <div className="sa-ready-box">
          <p>{finalMessage}</p>
        </div>
      )}

      {backendError && (
        <div className="error-box">
          <strong>Error:</strong>
          <p>{backendError}</p>
        </div>
      )}
      {hasSummary && (
        <section className="sa-log-box">
          <h2>Automation Summary</h2>
          <ul>
            {results.resourceGroup && (
              <li>Resource Group: {results.resourceGroup.__displayName}</li>
            )}
            {results.servicePrincipals.length > 0 && (
              <li>
                Service Principals:{" "}
                {safeList(results.servicePrincipals, (x) => toText(x?.name))}
              </li>
            )}
            {results.vnets.length > 0 && (
              <li>VNets: {safeList(results.vnets, (x) => toText(x?.name))}</li>
            )}
            {results.keyVaults.length > 0 && (
              <li>Key Vaults: {safeList(results.keyVaults, (x) => toText(x?.name))}</li>
            )}
          </ul>
        </section>
      )}
    </div>
  );
}