import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateKeyVault.css";

const INITIAL_FORM = {
  subscription: "",
  resourceGroup: "",
  region: "",
  keyVaultName: "",
  skuName: "standard",
  tenantId: "",
};

const INITIAL_PRIVATE_ENDPOINT = {
  name: "",
  vnet: "",
  subnet: "",
};

// ---------------------------
// VALIDATION
// ---------------------------
const KV_ALLOWED = /^[A-Za-z0-9-]{3,24}$/;
const KV_START = /^[A-Za-z]/;
const KV_END = /[A-Za-z0-9]$/;

const REGION_OPTIONS = [
  "(Africa) South Africa North",
  "(Asia Pacific) Central India",
  "(US) East US",
  "(Europe) West Europe",
  "Other",
];

export default function CreateKeyVault1() {
  const navigate = useNavigate();

  const [form, setForm] = useState(INITIAL_FORM);
  const [endpoint, setEndpoint] = useState(INITIAL_PRIVATE_ENDPOINT);

  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]);

  const [vnets, setVnets] = useState([]);
  const [subnets, setSubnets] = useState([]);

  const [loadingVnets, setLoadingVnets] = useState(false);
  const [loadingSubnets, setLoadingSubnets] = useState(false);

  const [submitError, setSubmitError] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [region, setRegion] = useState(REGION_OPTIONS[0]);

  useEffect(() => {
    const loadSubscriptions = async () => {
      try {
        const res = await fetch(
          "http://localhost:8000/api/moniter/azure/subscriptions/"
        );
        const data = await res.json();

        if (!res.ok) {
          throw new Error(
            data.hint || data.message || "Failed to load subscriptions."
          );
        }

        setSubscriptions(data.subscriptions || []);
      } catch (err) {
        setSubmitError(err.message);
        setSubscriptions([]);
      }
    };

    loadSubscriptions();
  }, []);

  useEffect(() => {
    if (!form.subscription) return;

    const loadResourceGroups = async () => {
      try {
        const res = await fetch(
          `http://localhost:8000/api/moniter/azure/resource-groups/?subscription_id=${form.subscription}`
        );
        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.hint || data.message || "Failed to load resource groups.");
        }

        setResourceGroups(data.resource_groups || []);
      } catch (err) {
        setSubmitError(err.message);
        setResourceGroups([]);
      }
    };

    loadResourceGroups();
  }, [form.subscription]);

  const loadVnets = async () => {
    if (!form.subscription || !form.resourceGroup) {
      alert("Select subscription and resource group first.");
      return;
    }

    setLoadingVnets(true);

    try {
      const res = await fetch(
        `http://localhost:8000/api/moniter/azure/vnets/?subscription_id=${form.subscription}&resource_group=${form.resourceGroup}`
      );

      const data = await res.json();

      if (!res.ok) throw new Error(data.hint || data.message);

      setVnets(data.vnets || []);
    } catch (err) {
      alert(err.message);
      setVnets([]);
    }

    setLoadingVnets(false);
  };

  // ---------------------------
  // LOAD SUBNETS
  // ---------------------------
  const loadSubnets = async (vnetName) => {
    if (!vnetName) {
      alert("Select VNet first.");
      return;
    }

    setLoadingSubnets(true);

    try {
      const res = await fetch(
        `http://localhost:8000/api/moniter/azure/subnets/?subscription_id=${form.subscription}&resource_group=${form.resourceGroup}&vnet=${vnetName}`
      );

      const data = await res.json();

      if (!res.ok) throw new Error(data.hint || data.message);

      setSubnets(data.subnets || []);
    } catch (err) {
      alert(err.message);
      setSubnets([]);
    }

    setLoadingSubnets(false);
  };

  // ---------------------------
  // VALIDATION
  // ---------------------------
  const keyVaultName = form.keyVaultName.trim();
  const validationOK =
    KV_ALLOWED.test(keyVaultName) &&
    KV_START.test(keyVaultName) &&
    KV_END.test(keyVaultName) &&
    !keyVaultName.includes("--");

  // ---------------------------
  // SUBMIT
  // ---------------------------
  const handleSubmit = async (e) => {
    e.preventDefault();

    setSubmitting(true);
    setSubmitError("");
    setMessage("");

    if (!form.subscription || !form.resourceGroup || !form.region) {
      setSubmitError("Fill all required fields.");
      setSubmitting(false);
      return;
    }

    if (!validationOK) {
      setSubmitError("Invalid Key Vault name.");
      setSubmitting(false);
      return;
    }

    if (!endpoint.name || !endpoint.vnet || !endpoint.subnet) {
      setSubmitError("Private Endpoint details required.");
      setSubmitting(false);
      return;
    }

    // 🔥 FINAL CORRECT PAYLOAD
    const payload = {
      keyVault: {
        subscription: form.subscription,
        resourceGroup: form.resourceGroup,

        // 🔥 FIX REGION FORMAT
        region: form.region.toLowerCase().replace(/\s+/g, ""),

        keyVaultName: form.keyVaultName,
        skuName: form.skuName,
        tenantId: form.tenantId,

        // 🔥 REQUIRED AZURE SETTINGS
        enableRbacAuthorization: true,
        publicNetworkAccess: "Disabled",
        enablePurgeProtection: true,
        enabledForDeployment: true,
        enabledForDiskEncryption: true,
        enabledForTemplateDeployment: true,
      },

      privateEndpoint: {
        name: endpoint.name,
        vnet: endpoint.vnet,
        subnet: endpoint.subnet,
      },

      dryRun: false,
    };

    console.log("🚀 FINAL PAYLOAD:", payload);

    try {
      const res = await fetch(
        "http://localhost:8000/api/moniter/react/create-keyvault-with-pe/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const data = await res.json();

      console.log("🔥 RESPONSE:", data);

      if (!res.ok) {
        throw new Error(data.hint || data.message || "Request failed");
      }

      if (data.status === "success") {
        setMessage("✅ Key Vault & Private Endpoint CREATED!");
      } else if (data.status === "accepted") {
        setMessage("⚠️ Dry run success. Set dryRun=false.");
      } else {
        throw new Error(data.message);
      }
    } catch (err) {
      setSubmitError(err.message);
    }

    setSubmitting(false);
  };

  // ---------------------------
  // UI
  // ---------------------------
  return (
    <div className="keyvault-page">
      <div className="keyvault-header">
        <button className="keyvault-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create Key Vault</h1>
      </div>

      <form className="keyvault-form" onSubmit={handleSubmit}>
        <section className="keyvault-section">
          <h2>Key Vault</h2>

          {/* 🔥 SUBSCRIPTION */}
          <select
            value={form.subscription}
            onChange={(e) =>
              setForm((p) => ({ ...p, subscription: e.target.value }))
            }
          >
            <option value="">Select Subscription</option>
            {subscriptions.map((s) => (
              <option key={s.subscription_id} value={s.subscription_id}>
                {s.subscription_id}
              </option>
            ))}
          </select>

          {/* RESOURCE GROUP */}
          <select
            value={form.resourceGroup}
            onChange={(e) => {
              const rg = resourceGroups.find((r) => r.name === e.target.value);

              setForm((prev) => ({
                ...prev,
                resourceGroup: e.target.value,
                region: rg?.location || "",
              }));
            }}
          >
            <option value="">Select RG</option>
            {resourceGroups.map((rg) => (
              <option key={rg.name}>{rg.name}</option>
            ))}
          </select>

          <input value={form.region} disabled />

          <input
            placeholder="KeyVault Name"
            value={form.keyVaultName}
            onChange={(e) =>
              setForm((p) => ({ ...p, keyVaultName: e.target.value }))
            }
          />

          <select
            value={form.skuName}
            onChange={(e) =>
              setForm((p) => ({ ...p, skuName: e.target.value }))
            }
          >
            <option value="standard">Standard</option>
            <option value="premium">Premium</option>
          </select>
        </section>

        <section className="keyvault-section">
          <h2>Private Endpoint</h2>

          <input
            placeholder="PE Name"
            value={endpoint.name}
            onChange={(e) =>
              setEndpoint((p) => ({ ...p, name: e.target.value }))
            }
          />

          <select
            value={endpoint.vnet}
            onChange={(e) =>
              setEndpoint((p) => ({ ...p, vnet: e.target.value }))
            }
          >
            <option value="">Select VNET</option>
            {vnets.map((v) => (
              <option key={v.name}>{v.name}</option>
            ))}
          </select>

          <button type="button" onClick={loadVnets}>
            {loadingVnets ? "Loading..." : "Load VNETs"}
          </button>

          <select
            value={endpoint.subnet}
            onChange={(e) =>
              setEndpoint((p) => ({ ...p, subnet: e.target.value }))
            }
          >
            <option value="">Select Subnet</option>
            {subnets.map((s) => (
              <option key={s.name}>{s.name}</option>
            ))}
          </select>

          <button type="button" onClick={() => loadSubnets(endpoint.vnet)}>
            {loadingSubnets ? "Loading..." : "Load Subnets"}
          </button>
        </section>

        <button type="submit" disabled={submitting}>
          {submitting ? "Creating..." : "Create"}
        </button>

        {submitError && <p className="keyvault-error">{submitError}</p>}
        {message && <p className="keyvault-message">{message}</p>}
      </form>
    </div>
  );
}
