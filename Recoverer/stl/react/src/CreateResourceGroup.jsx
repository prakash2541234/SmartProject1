import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateResourceGroup.css";

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
  tags: {}, // <-- TAG STORAGE
};

export default function CreateResourceGroup() {
  const navigate = useNavigate();

  const [form, setForm] = useState(INITIAL_FORM);
  const [subscriptions, setSubscriptions] = useState([]);
  const [loadingSubscriptions, setLoadingSubscriptions] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState("");

  const [applyInAzure, setApplyInAzure] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  // TAG STATES
  const [newTagKey, setNewTagKey] = useState("");
  const [newTagValue, setNewTagValue] = useState("");

  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const addTag = () => {
    if (!newTagKey.trim() || !newTagValue.trim()) return;

    setForm((prev) => ({
      ...prev,
      tags: { ...prev.tags, [newTagKey.trim()]: newTagValue.trim() },
    }));

    setNewTagKey("");
    setNewTagValue("");
  };

  const removeTag = (key) => {
    setForm((prev) => {
      const updated = { ...prev.tags };
      delete updated[key];
      return { ...prev, tags: updated };
    });
  };

  const fetchSubscriptions = async () => {
    setLoadingSubscriptions(true);
    setSubscriptionError("");
    try {
      const response = await fetch("http://localhost:8000/api/moniter/azure/subscriptions/");
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to fetch subscriptions.");
      }

      const items = data.subscriptions || [];
      setSubscriptions(items);

      const defaultSub = data.default_subscription_id || "";
      const hasDefault = items.some((s) => s.subscription_id === defaultSub);

      if (!form.subscription) {
        if (items.length === 1) {
          setForm((prev) => ({ ...prev, subscription: items[0].subscription_id || "" }));
        } else if (hasDefault) {
          setForm((prev) => ({ ...prev, subscription: defaultSub }));
        }
      }
    } catch (err) {
      setSubscriptions([]);
      setSubscriptionError(err.message || "Unable to fetch subscriptions.");
    } finally {
      setLoadingSubscriptions(false);
    }
  };

  useEffect(() => {
    fetchSubscriptions();
  }, []);

  const checks = [
    { id: "sub", label: "Subscription is selected", ok: Boolean(form.subscription.trim()) },
    { id: "rg", label: "Resource group name is provided", ok: Boolean(form.resourceGroup.trim()) },
    { id: "region", label: "Region is selected", ok: Boolean(form.region.trim()) },
  ];
  const canSubmit = checks.every((c) => c.ok);

  const parseError = (data, fallback) => {
    if (data?.message) return data.message;
    if (data?.errors && typeof data.errors === "object") {
      const key = Object.keys(data.errors)[0];
      const value = data.errors[key];
      if (Array.isArray(value) && value[0]) return `${key}: ${value[0]}`;
      if (typeof value === "string") return `${key}: ${value}`;
    }
    return fallback;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");

    if (!canSubmit) {
      setError("Please complete all required checks.");
      return;
    }

    const payload = {
      ...form,
      dryRun: !applyInAzure,
    };

    setSubmitting(true);
    try {
      const response = await fetch("http://localhost:8000/api/moniter/react/create-resource-group/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(parseError(data, "Create resource group API request failed."));
      }

      if (data.status === "accepted") {
        setMessage("Dry run successful. Resource group payload is valid.");
      } else {
        setMessage("Resource group request submitted successfully.");
      }
    } catch (err) {
      setError(err.message || "Failed to create resource group.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setForm(INITIAL_FORM);
    setApplyInAzure(false);
    setMessage("");
    setError("");
  };

  return (
    <div className="rg-page">
      <div className="rg-header">
        <button className="rg-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create Resource Group</h1>
      </div>

      <form className="rg-form" onSubmit={handleSubmit}>
        {/* BASIC DETAILS */}
        <section className="rg-section">
          <h2>Basic Details</h2>
          <div className="rg-grid">
            {/* SUBSCRIPTION */}
            <label className="full-width">
              Subscription:
              <div className="field-inline">
                <input
                  type="text"
                  list="rg-sub-options"
                  value={form.subscription}
                  onChange={(e) => updateField("subscription", e.target.value)}
                  required
                />
                <button type="button" className="mini-btn" onClick={fetchSubscriptions} disabled={loadingSubscriptions}>
                  {loadingSubscriptions ? "Refreshing..." : "Refresh"}
                </button>
              </div>

              <datalist id="rg-sub-options">
                {subscriptions.map((sub) => (
                  <option
                    key={sub.subscription_id}
                    value={sub.subscription_id}
                    label={`${sub.display_name || "Unnamed"} (${sub.state || "Unknown"})`}
                  />
                ))}
              </datalist>

              <span className="hint">Found: {subscriptions.length} subscription(s).</span>
              {subscriptionError && <span className="error-text">{subscriptionError}</span>}
            </label>

            {/* RG NAME */}
            <label>
              Resource Group Name:
              <input
                type="text"
                value={form.resourceGroup}
                onChange={(e) => updateField("resourceGroup", e.target.value)}
                required
              />
            </label>

            {/* REGION */}
            <label>
              Region:
              <input
                type="text"
                list="rg-region-options"
                value={form.region}
                onChange={(e) => updateField("region", e.target.value)}
                required
              />
              <datalist id="rg-region-options">
                {REGION_OPTIONS.map((region) => (
                  <option key={region} value={region} />
                ))}
              </datalist>
            </label>
          </div>
        </section>

        {/* TAGS SECTION */}
        <section className="rg-section">
          <h2>Tags</h2>

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
            <button type="button" className="mini-btn" onClick={addTag}>
              Add
            </button>
          </div>

          <ul className="tag-list">
            {Object.entries(form.tags).map(([key, value]) => (
              <li key={key} className="tag-item">
                <span>{key}: {value}</span>
                <button type="button" className="remove-tag-btn" onClick={() => removeTag(key)}>
                  ✕
                </button>
              </li>
            ))}
          </ul>
        </section>

        {/* VALIDATION */}
        <section className="rg-section">
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

        {/* ACTION BUTTONS */}
        <div className="rg-actions">
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

        {error && <p className="rg-error">{error}</p>}
        {message && <p className="rg-message">{message}</p>}
      </form>
    </div>
  );
}