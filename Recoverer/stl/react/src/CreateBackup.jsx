import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateBackup.css";

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

const INITIAL_FORM = {
  subscription: "",
  resourceGroup: "",
  region: "",
  backupVaultName: "",
  publicNetworkAccess: "Enabled",
};

const BACKUP_VAULT_NAME_REGEX = /^[A-Za-z][A-Za-z0-9-]{1,49}$/;

export default function CreateBackup() {
  const navigate = useNavigate();
  const [form, setForm] = useState(INITIAL_FORM);
  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]);
  const [tags, setTags] = useState({});
  const [newTagKey, setNewTagKey] = useState("");
  const [newTagValue, setNewTagValue] = useState("");
  const [loadingMeta, setLoadingMeta] = useState({
    subscriptions: false,
    resourceGroups: false,
  });
  const [metaError, setMetaError] = useState({
    subscriptions: "",
    resourceGroups: "",
  });

  const [applyInAzure, setApplyInAzure] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const setMetaLoading = (key, value) => {
    setLoadingMeta((prev) => ({ ...prev, [key]: value }));
  };

  const setMetaErrorValue = (key, value) => {
    setMetaError((prev) => ({ ...prev, [key]: value }));
  };

  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
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

  const fetchResourceGroups = async (subscriptionId) => {
    if (!subscriptionId) {
      setResourceGroups([]);
      return;
    }
    setMetaLoading("resourceGroups", true);
    setMetaErrorValue("resourceGroups", "");
    try {
      const response = await fetch(
        `http://localhost:8000/api/moniter/azure/resource-groups/?subscription_id=${encodeURIComponent(subscriptionId)}`
      );
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to fetch resource groups.");
      }
      const groups = data.resource_groups || [];
      setResourceGroups(groups);
      if (groups.length === 1 && !form.resourceGroup) {
        updateField("resourceGroup", groups[0].name || "");
      }
    } catch (err) {
      setResourceGroups([]);
      setMetaErrorValue("resourceGroups", err.message || "Unable to fetch resource groups.");
    } finally {
      setMetaLoading("resourceGroups", false);
    }
  };

  const fetchSubscriptions = async () => {
    setMetaLoading("subscriptions", true);
    setMetaErrorValue("subscriptions", "");
    try {
      const response = await fetch("http://localhost:8000/api/moniter/azure/subscriptions/");
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to fetch subscriptions.");
      }
      const items = data.subscriptions || [];
      setSubscriptions(items);
      const defaultSub = data.default_subscription_id || "";
      const hasDefault = items.some((item) => item.subscription_id === defaultSub);
      if (!form.subscription) {
        if (items.length === 1) {
          const onlySub = items[0].subscription_id || "";
          updateField("subscription", onlySub);
          if (onlySub) {
            await fetchResourceGroups(onlySub);
          }
        } else if (hasDefault) {
          updateField("subscription", defaultSub);
          await fetchResourceGroups(defaultSub);
        }
      }
    } catch (err) {
      setSubscriptions([]);
      setMetaErrorValue("subscriptions", err.message || "Unable to fetch subscriptions.");
    } finally {
      setMetaLoading("subscriptions", false);
    }
  };

  useEffect(() => {
    fetchSubscriptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const parseApiError = (data, fallback) => {
    const lines = [];
    lines.push(data?.message || fallback);
    if (Array.isArray(data?.troubleshooting) && data.troubleshooting.length > 0) {
      lines.push(`How to fix: ${data.troubleshooting.join(" ")}`);
    }
    if (Array.isArray(data?.required_permissions) && data.required_permissions.length > 0) {
      lines.push(`Required permissions: ${data.required_permissions.join(", ")}`);
    }
    if (data?.request_context?.request_id || data?.request_context?.client_request_id) {
      lines.push(
        `Request IDs: request_id=${data?.request_context?.request_id || "n/a"}, client_request_id=${data?.request_context?.client_request_id || "n/a"}`
      );
    }
    if (data?.azure_error_code) {
      lines.push(`Azure error code: ${data.azure_error_code}`);
    }
    const serializerErrors = data?.errors;
    if (serializerErrors && typeof serializerErrors === "object") {
      const key = Object.keys(serializerErrors)[0];
      const value = serializerErrors[key];
      if (Array.isArray(value) && value[0]) {
        lines.push(`${key}: ${value[0]}`);
      } else if (typeof value === "string") {
        lines.push(`${key}: ${value}`);
      }
    }
    return lines.join("\n");
  };

  const checks = [
    { id: "sub", label: "Subscription is selected", ok: Boolean(form.subscription.trim()) },
    { id: "rg", label: "Resource group is selected or typed", ok: Boolean(form.resourceGroup.trim()) },
    { id: "region", label: "Region is selected", ok: Boolean(form.region.trim()) },
    {
      id: "name",
      label: "Backup vault name is valid",
      ok: BACKUP_VAULT_NAME_REGEX.test(form.backupVaultName.trim()),
    },
  ];
  const canSubmit = checks.every((item) => item.ok);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");

    if (!canSubmit) {
      setError("Please complete all required checks.");
      return;
    }

    const payload = {
      subscription: form.subscription,
      resourceGroup: form.resourceGroup,
      region: form.region,
      backupVaultName: form.backupVaultName,
      publicNetworkAccess: form.publicNetworkAccess,
      tags,
      dryRun: !applyInAzure,
    };

    setSubmitting(true);
    try {
      const response = await fetch("http://localhost:8000/api/moniter/react/create-backup/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(parseApiError(data, "Create backup API request failed."));
      }

      if (data.status === "accepted") {
        setMessage("Dry run successful. Backup payload is valid.");
      } else {
        setMessage("Backup vault request submitted successfully.");
      }
    } catch (err) {
      setError(err.message || "Failed to create backup vault.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setForm(INITIAL_FORM);
    setApplyInAzure(false);
    setMessage("");
    setError("");
    setTags({});
    setNewTagKey("");
    setNewTagValue("");
  };

  return (
    <div className="backup-page">
      <div className="backup-header">
        <button className="backup-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create Backup</h1>
      </div>

      <form className="backup-form" onSubmit={handleSubmit}>
        <section className="backup-section">
          <h2>Basic Details</h2>
          <div className="backup-grid">
            <label className="full-width">
              Subscription:
              <div className="field-inline">
                <input
                  type="text"
                  list="backup-sub-options"
                  value={form.subscription}
                  onChange={(e) => {
                    const value = e.target.value;
                    updateField("subscription", value);
                    if (subscriptions.some((item) => item.subscription_id === value)) {
                      fetchResourceGroups(value);
                    } else {
                      setResourceGroups([]);
                    }
                  }}
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
              <datalist id="backup-sub-options">
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
              <input
                type="text"
                list="backup-rg-options"
                value={form.resourceGroup}
                onChange={(e) => updateField("resourceGroup", e.target.value)}
                required
              />
              <datalist id="backup-rg-options">
                {resourceGroups.map((group) => (
                  <option key={group.id || group.name} value={group.name} />
                ))}
              </datalist>
              <span className="hint">Available groups: {resourceGroups.length}</span>
              {metaError.resourceGroups && <span className="error-text">{metaError.resourceGroups}</span>}
            </label>

            <label>
              Region:
              <input
                type="text"
                list="backup-region-options"
                value={form.region}
                onChange={(e) => updateField("region", e.target.value)}
                required
              />
              <datalist id="backup-region-options">
                {REGION_OPTIONS.map((region) => (
                  <option key={region} value={region} />
                ))}
              </datalist>
            </label>

            <label>
              Backup Vault Name:
              <input
                type="text"
                value={form.backupVaultName}
                onChange={(e) => updateField("backupVaultName", e.target.value)}
                placeholder="2-50 chars, start with letter"
                required
              />
            </label>
          </div>
        </section>

        <section className="backup-section">
          <h2>Backup Settings</h2>
          <div className="backup-grid">
            <label>
              Public Network Access:
              <select
                value={form.publicNetworkAccess}
                onChange={(e) => updateField("publicNetworkAccess", e.target.value)}
              >
                <option value="Enabled">Enabled</option>
                <option value="Disabled">Disabled</option>
              </select>
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

        <section className="backup-section">
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

        <div className="backup-actions">
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

        {error && <p className="backup-error">{error}</p>}
        {message && <p className="backup-message">{message}</p>}
      </form>
    </div>
  );
}
