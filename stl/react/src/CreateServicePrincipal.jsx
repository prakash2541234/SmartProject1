// src/pages/CreateServicePrincipal.jsx
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateServicePrincipal.css";

const SP_NAME_REGEX = /^[A-Za-z][A-Za-z0-9-_]{2,119}$/;

export default function CreateServicePrincipal() {
  const navigate = useNavigate();

  const INITIAL_FORM = {
    subscription: "",
    servicePrincipalName: "",
    tenantId: "",
    role: "contributor",
    scopeType: "subscription",
    resourceGroup: "",
    customScope: "",
    credentialType: "client-secret",
    secretDisplayName: "sp-client-secret",
    secretValidityMonths: 12,
    createIfMissing: true,
    assignRoleNow: true,
  };

  const [form, setForm] = useState(INITIAL_FORM);
  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]);
  const [tags, setTags] = useState({});
  const [newTagKey, setNewTagKey] = useState("");
  const [newTagValue, setNewTagValue] = useState("");

  const [loadingSubs, setLoadingSubs] = useState(false);
  const [loadingRGs, setLoadingRGs] = useState(false);

  const [message, setMessage] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [generatedSecret, setGeneratedSecret] = useState("");

  const updateField = (field, value) =>
    setForm((prev) => ({ ...prev, [field]: value }));

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

  // -------------------------------------------------------------------
  // Load Subscriptions
  // -------------------------------------------------------------------
  const fetchSubscriptions = async () => {
    setLoadingSubs(true);
    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/azure/subscriptions/"
      );
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setSubscriptions(data.subscriptions || []);

        // Auto-select the first subscription
        if (!form.subscription && data.subscriptions.length > 0) {
          const firstSub = data.subscriptions[0].subscription_id;
          updateField("subscription", firstSub);
          fetchResourceGroups(firstSub);
        }
      } else {
        setSubmitError(data.message || "Failed to load subscriptions");
      }
    } catch (err) {
      setSubmitError("Unable to load subscriptions.");
    } finally {
      setLoadingSubs(false);
    }
  };

  // -------------------------------------------------------------------
  // Load Resource Groups (only if needed)
  // -------------------------------------------------------------------
  const fetchResourceGroups = async (subId) => {
    if (!subId) return;
    setLoadingRGs(true);
    try {
      const response = await fetch(
        `http://localhost:8000/api/moniter/azure/resource-groups/?subscription_id=${encodeURIComponent(
          subId
        )}`
      );
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResourceGroups(data.resource_groups || []);
      } else {
        setResourceGroups([]);
      }
    } catch (err) {
      setResourceGroups([]);
    } finally {
      setLoadingRGs(false);
    }
  };

  useEffect(() => {
    fetchSubscriptions();
  }, []);

  // -------------------------------------------------------------------
  // Form Validation
  // -------------------------------------------------------------------
  const validName = SP_NAME_REGEX.test(form.servicePrincipalName.trim());

  const canSubmit =
    form.subscription &&
    validName &&
    (form.scopeType !== "custom" ||
      form.customScope.trim().startsWith("/"));

  // -------------------------------------------------------------------
  // Submit Handler
  // -------------------------------------------------------------------
  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitError("");
    setMessage("");
    setGeneratedSecret("");

    if (!canSubmit) {
      setSubmitError("Please complete all required fields.");
      return;
    }

    const effectiveScope =
      form.scopeType === "subscription"
        ? `/subscriptions/${form.subscription}`
        : form.scopeType === "resource-group"
        ? `/subscriptions/${form.subscription}/resourceGroups/${form.resourceGroup}`
        : form.customScope;

    const payload = {
      ...form,
      tags,
      scope: effectiveScope,
      secretValidityMonths: Number(form.secretValidityMonths),
      dryRun: false,
    };

    setSubmitting(true);
    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/react/create-service-principal/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || "Failed to create SP");
      }

      setMessage("Service Principal created successfully.");

      if (data?.credential?.secret_text) {
        setGeneratedSecret(data.credential.secret_text);
      }
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setForm(INITIAL_FORM);
    setResourceGroups([]);
    setMessage("");
    setSubmitError("");
    setGeneratedSecret("");
    setTags({});
    setNewTagKey("");
    setNewTagValue("");
  };

  return (
    <div className="sp-page">
      <div className="sp-header">
        <button className="sp-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create Service Principal</h1>
      </div>

      <form className="sp-form" onSubmit={handleSubmit}>
        {/* ---------- BASIC DETAILS ---------- */}
        <section className="sp-section">
          <h2>Basic Details</h2>
          <label>
            Subscription:
            <select
              value={form.subscription}
              onChange={(e) => {
                updateField("subscription", e.target.value);
                fetchResourceGroups(e.target.value);
              }}
            >
              <option value="">
                {loadingSubs ? "Loading..." : "Select Subscription"}
              </option>
              {subscriptions.map((item) => (
                <option
                  key={item.subscription_id}
                  value={item.subscription_id}
                >
                  {item.display_name} ({item.subscription_id})
                </option>
              ))}
            </select>
          </label>

          <label>
            Service Principal Name:
            <input
              type="text"
              value={form.servicePrincipalName}
              onChange={(e) =>
                updateField("servicePrincipalName", e.target.value)
              }
              placeholder="example: automation-app"
              required
            />
          </label>

          <label>
            Tenant ID (optional):
            <input
              type="text"
              value={form.tenantId}
              onChange={(e) => updateField("tenantId", e.target.value)}
              placeholder="Leave empty to use backend tenant"
            />
          </label>
        </section>

        {/* ---------- PERMISSIONS ---------- */}
        <section className="sp-section">
          <h2>Permissions</h2>

          <label>
            Role:
            <select
              value={form.role}
              onChange={(e) => updateField("role", e.target.value)}
            >
              <option value="reader">Reader</option>
              <option value="contributor">Contributor</option>
              <option value="owner">Owner</option>
            </select>
          </label>

          <label>
            Scope Type:
            <select
              value={form.scopeType}
              onChange={(e) => updateField("scopeType", e.target.value)}
            >
              <option value="subscription">Subscription</option>
              <option value="resource-group">Resource Group</option>
              <option value="custom">Custom</option>
            </select>
          </label>

          {form.scopeType === "resource-group" && (
            <label>
              Resource Group:
              <select
                value={form.resourceGroup}
                onChange={(e) =>
                  updateField("resourceGroup", e.target.value)
                }
                disabled={loadingRGs}
              >
                <option value="">
                  {loadingRGs ? "Loading..." : "Select RG"}
                </option>
                {resourceGroups.map((rg) => (
                  <option key={rg.name} value={rg.name}>
                    {rg.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          {form.scopeType === "custom" && (
            <label>
              Custom Scope:
              <input
                type="text"
                value={form.customScope}
                onChange={(e) =>
                  updateField("customScope", e.target.value)
                }
                placeholder="/subscriptions/<id>/resourceGroups/<rg>/..."
                required
              />
            </label>
          )}
        </section>

        {/* ---------- CREDENTIALS ---------- */}
        <section className="sp-section">
          <h2>Credentials</h2>

          <label>
            Credential Type:
            <select
              value={form.credentialType}
              onChange={(e) =>
                updateField("credentialType", e.target.value)
              }
            >
              <option value="client-secret">Client Secret</option>
              <option value="certificate">
                Certificate (not implemented)
              </option>
            </select>
          </label>

          {form.credentialType === "client-secret" && (
            <>
              <label>
                Secret Display Name:
                <input
                  type="text"
                  value={form.secretDisplayName}
                  onChange={(e) =>
                    updateField("secretDisplayName", e.target.value)
                  }
                  required
                />
              </label>

              <label>
                Secret Validity (Months):
                <input
                  type="number"
                  min="1"
                  max="24"
                  value={form.secretValidityMonths}
                  onChange={(e) =>
                    updateField("secretValidityMonths", e.target.value)
                  }
                  required
                />
              </label>
            </>
          )}

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.createIfMissing}
              onChange={(e) =>
                updateField("createIfMissing", e.target.checked)
              }
            />
            Create App Registration if missing
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.assignRoleNow}
              onChange={(e) =>
                updateField("assignRoleNow", e.target.checked)
              }
            />
            Assign role immediately
          </label>
        </section>

        <section className="sp-section">
          <h2>Tags (Optional)</h2>
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
        </section>

        {/* ---------- ACTION BUTTONS ---------- */}
        <div className="sp-actions">
          <button
            type="submit"
            className="submit-btn"
            disabled={!canSubmit || submitting}
          >
            {submitting ? "Submitting..." : "Submit"}
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

        {submitError && <p className="sp-error">{submitError}</p>}
        {message && <p className="sp-message">{message}</p>}

        {generatedSecret && (
          <div className="secret-box">
            <p>
              Generated Client Secret (copy now — Azure shows this only once)
            </p>
            <code>{generatedSecret}</code>
          </div>
        )}
      </form>
    </div>
  );
}
