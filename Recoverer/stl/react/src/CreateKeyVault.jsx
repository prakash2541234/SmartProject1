import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateKeyVault.css";

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

const INITIAL_FORM = {
  subscription: "",
  resourceGroup: "",
  region: "",
  keyVaultName: "",
  skuName: "standard",
  tenantId: "",
  enableRbacAuthorization: true,
  publicNetworkAccess: "Disabled",
  softDeleteRetentionInDays: 90,
  enablePurgeProtection: true,
  enabledForDeployment: true,
  enabledForDiskEncryption: true,
  enabledForTemplateDeployment: true,
};

const KEY_VAULT_ALLOWED_CHARS_REGEX = /^[A-Za-z0-9-]{3,24}$/;
const KEY_VAULT_STARTS_WITH_LETTER_REGEX = /^[A-Za-z]/;
const KEY_VAULT_ENDS_WITH_ALNUM_REGEX = /[A-Za-z0-9]$/;

export default function CreateKeyVault() {
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

  // (Kept — Option B)
  const [newResourceGroupName, setNewResourceGroupName] = useState("");
  const [creatingResourceGroup, setCreatingResourceGroup] =
    useState(false);
  const [resourceGroupActionMessage, setResourceGroupActionMessage] =
    useState("");
  const [resourceGroupActionError, setResourceGroupActionError] =
    useState("");

  const [message, setMessage] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [applyInAzure, setApplyInAzure] = useState(false);

  const keyVaultName = (form.keyVaultName || "").trim();
  const regionValue = (form.region || "").trim();
  const softDeleteDays = Number(form.softDeleteRetentionInDays);

  const requirementChecks = [
    {
      id: "subscription",
      label: "Subscription is selected",
      ok: Boolean((form.subscription || "").trim()),
    },
    {
      id: "resource-group",
      label: "Resource Group is selected or typed",
      ok: Boolean((form.resourceGroup || "").trim()),
    },
    {
      id: "region",
      label: "Region is selected and not 'Other'",
      ok:
        Boolean(regionValue) &&
        regionValue.toLowerCase() !== "other",
    },
    {
      id: "name-length",
      label: "Key Vault name is 3 to 24 characters",
      ok: keyVaultName.length >= 3 && keyVaultName.length <= 24,
    },
    {
      id: "name-chars",
      label:
        "Key Vault name uses only letters, numbers, and hyphens (-)",
      ok: KEY_VAULT_ALLOWED_CHARS_REGEX.test(keyVaultName),
    },
    {
      id: "name-start",
      label: "Key Vault name starts with a letter",
      ok: KEY_VAULT_STARTS_WITH_LETTER_REGEX.test(
        keyVaultName
      ),
    },
    {
      id: "name-end",
      label: "Key Vault name ends with letter or number",
      ok: KEY_VAULT_ENDS_WITH_ALNUM_REGEX.test(keyVaultName),
    },
    {
      id: "name-double-hyphen",
      label:
        "Key Vault name does not contain consecutive hyphens (--)",
      ok: !keyVaultName.includes("--"),
    },
    {
      id: "soft-delete",
      label: "Soft Delete Retention is between 7 and 90 days",
      ok:
        Number.isFinite(softDeleteDays) &&
        softDeleteDays >= 7 &&
        softDeleteDays <= 90,
    },
  ];

  const allRequirementsMet = requirementChecks.every(
    (rule) => rule.ok
  );

  const parseApiError = (data, fallback) => {
    if (data?.message) {
      return data.message;
    }

    const errors = data?.errors || data;
    if (errors && typeof errors === "object") {
      const firstField = Object.keys(errors)[0];
      const firstValue = errors[firstField];
      if (
        Array.isArray(firstValue) &&
        firstValue.length > 0
      ) {
        return `${firstField}: ${firstValue[0]}`;
      }
      if (typeof firstValue === "string") {
        return `${firstField}: ${firstValue}`;
      }
    }

    return fallback;
  };

  const setMetaLoading = (key, value) => {
    setLoadingMeta((prev) => ({ ...prev, [key]: value }));
  };

  const setMetaErrorValue = (key, value) => {
    setMetaError((prev) => ({ ...prev, [key]: value }));
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

  const updateFormField = (field, value) => {
    if (
      field === "subscription" ||
      field === "resourceGroup" ||
      field === "region"
    ) {
      setResourceGroupActionMessage("");
      setResourceGroupActionError("");
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
        `http://localhost:8000/api/moniter/azure/resource-groups/?subscription_id=${encodeURIComponent(
          subscriptionId
        )}`
      );
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(
          data.message || "Failed to fetch resource groups."
        );
      }

      const nextGroups = data.resource_groups || [];
      setResourceGroups(nextGroups);

      if (nextGroups.length === 1) {
        const g = nextGroups[0];
        setForm((prev) => ({
          ...prev,
          resourceGroup: prev.resourceGroup || g.name,
          region: g.location || "",
        }));
      }
    } catch (error) {
      setResourceGroups([]);
      setMetaErrorValue(
        "resourceGroups",
        error.message || "Unable to fetch resource groups."
      );
    } finally {
      setMetaLoading("resourceGroups", false);
    }
  };

  const loadSubscriptionMetadata = async (
    subscriptionIdParam
  ) => {
    const subscriptionId = (
      subscriptionIdParam ||
      form.subscription ||
      ""
    ).trim();

    if (!subscriptionId) {
      setMetaErrorValue(
        "resourceGroups",
        "Enter or select a subscription first."
      );
      return;
    }

    await fetchResourceGroups(subscriptionId);
  };

  const fetchSubscriptions = async () => {
    setMetaLoading("subscriptions", true);
    setMetaErrorValue("subscriptions", "");
    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/azure/subscriptions/"
      );
      const data = await response.json();
      if (
        !response.ok ||
        data.status !== "success"
      ) {
        throw new Error(
          data.message || "Failed to fetch subscriptions."
        );
      }

      const nextSubscriptions = data.subscriptions || [];
      setSubscriptions(nextSubscriptions);

      const defaultSub =
        data.default_subscription_id || "";
      const hasDefault = nextSubscriptions.some(
        (s) => s.subscription_id === defaultSub
      );

      if (!form.subscription) {
        if (nextSubscriptions.length === 1) {
          const onlySub =
            nextSubscriptions[0].subscription_id || "";
          setForm((prev) => ({
            ...prev,
            subscription: onlySub,
          }));
          if (onlySub) {
            await loadSubscriptionMetadata(onlySub);
          }
        } else if (hasDefault) {
          setForm((prev) => ({
            ...prev,
            subscription: defaultSub,
          }));
          await loadSubscriptionMetadata(defaultSub);
        }
      }
    } catch (error) {
      setSubscriptions([]);
      setMetaErrorValue(
        "subscriptions",
        error.message || "Unable to fetch subscriptions."
      );
    } finally {
      setMetaLoading("subscriptions", false);
    }
  };

  useEffect(() => {
    fetchSubscriptions();
  }, []);

  const handleReset = () => {
    setForm(INITIAL_FORM);
    setResourceGroups([]);
    setMessage("");
    setSubmitError("");
    setApplyInAzure(false);

    // (Kept — Option B)
    setNewResourceGroupName("");
    setResourceGroupActionMessage("");
    setResourceGroupActionError("");

    setTags({});
    setNewTagKey("");
    setNewTagValue("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage("");
    setSubmitError("");

    const payload = {
      ...form,
      softDeleteRetentionInDays: Number(
        form.softDeleteRetentionInDays
      ),
      tags,
      dryRun: !applyInAzure,
    };

    setSubmitting(true);
    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/react/create-key-vault/",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          parseApiError(
            data,
            "Key Vault API request failed."
          )
        );
      }

      if (data.status === "accepted") {
        setMessage(
          "Dry run successful. Payload passed validation and plan is ready."
        );
      } else {
        setMessage(
          "Key Vault request was submitted successfully to Azure."
        );
      }
      console.log(
        "Create Key Vault API response:",
        data
      );
    } catch (error) {
      setSubmitError(
        error.message ||
          "Failed to submit Create Key Vault request."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="keyvault-page">
      <div className="keyvault-header">
        <button
          className="keyvault-back"
          onClick={() => navigate("/")}
        >
          {"<- Back"}
        </button>
        <h1>Create Key Vault</h1>
      </div>

      <form
        className="keyvault-form"
        onSubmit={handleSubmit}
      >
        <section className="keyvault-section">
          <h2>Basic Details</h2>
          <div className="keyvault-grid">
            <label className="full-width">
              Subscription:
              <div className="field-inline">
                <input
                  type="text"
                  list="keyvault-subscription-options"
                  value={form.subscription}
                  onChange={(e) => {
                    const value = e.target.value;
                    updateFormField(
                      "subscription",
                      value
                    );
                    if (
                      subscriptions.some(
                        (sub) =>
                          sub.subscription_id === value
                      )
                    ) {
                      loadSubscriptionMetadata(value);
                    } else {
                      setResourceGroups([]);
                    }
                  }}
                  placeholder="Select subscription ID or type manually"
                  required
                />
                <button
                  type="button"
                  className="mini-btn"
                  onClick={fetchSubscriptions}
                  disabled={
                    loadingMeta.subscriptions
                  }
                >
                  {loadingMeta.subscriptions
                    ? "Refreshing..."
                    : "Refresh"}
                </button>
              </div>
              <datalist id="keyvault-subscription-options">
                {subscriptions.map((sub) => (
                  <option
                    key={sub.subscription_id}
                    value={sub.subscription_id}
                    label={`${
                      sub.display_name || "Unnamed"
                    } (${
                      sub.state || "Unknown"
                    })`}
                  />
                ))}
              </datalist>
              <span className="hint">
                Type or pick from list. Found:{" "}
                {subscriptions.length} subscription(s).
              </span>
              {metaError.subscriptions && (
                <span className="error-text">
                  {metaError.subscriptions}
                </span>
              )}
            </label>

            <label className="full-width">
              Resource Group:
              <div className="resource-group-summary">
                <span className="resource-group-count">
                  Available resource groups:{" "}
                  {resourceGroups.length}
                </span>
                <button
                  type="button"
                  className="mini-btn"
                  onClick={() =>
                    loadSubscriptionMetadata(
                      form.subscription
                    )
                  }
                  disabled={
                    loadingMeta.resourceGroups
                  }
                >
                  {loadingMeta.resourceGroups
                    ? "Refreshing..."
                    : "Refresh List"}
                </button>
              </div>

              <div className="resource-group-row">
                <select
                  value={
                    resourceGroups.some(
                      (group) =>
                        group.name ===
                        form.resourceGroup
                    )
                      ? form.resourceGroup
                      : ""
                  }
                  onChange={(e) => {
                    const groupName =
                      e.target.value;
                    const selected =
                      resourceGroups.find(
                        (g) =>
                          g.name === groupName
                      );

                    updateFormField(
                      "resourceGroup",
                      groupName
                    );
                    updateFormField(
                      "region",
                      selected?.location || ""
                    );
                  }}
                  disabled={
                    loadingMeta.resourceGroups ||
                    resourceGroups.length === 0
                  }
                >
                  <option value="">
                    Select existing resource group
                  </option>
                  {resourceGroups.map((group) => (
                    <option
                      key={
                        group.id || group.name
                      }
                      value={group.name}
                    >
                      {group.location
                        ? `${group.name} (${group.location})`
                        : group.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field-inline">
                <input
                  type="text"
                  list="keyvault-resource-group-options"
                  value={form.resourceGroup}
                  onChange={(e) => {
                    const val = e.target.value;
                    updateFormField(
                      "resourceGroup",
                      val
                    );

                    const selected =
                      resourceGroups.find(
                        (g) =>
                          g.name === val
                      );
                    updateFormField(
                      "region",
                      selected?.location || ""
                    );
                  }}
                  placeholder="Or type/select resource group"
                  required
                />
              </div>

              <datalist id="keyvault-resource-group-options">
                {resourceGroups.map((group) => (
                  <option
                    key={
                      group.id || group.name
                    }
                    value={group.name}
                    label={
                      group.location
                        ? `${group.name} (${group.location})`
                        : group.name
                    }
                  />
                ))}
              </datalist>

              {/* Removed Create RG Hint + Messages */}
              {metaError.resourceGroups && (
                <span className="error-text">
                  {metaError.resourceGroups}
                </span>
              )}
            </label>

            <label>
              Region (auto-selected from Resource Group):
              <input
                type="text"
                value={form.region}
                disabled
                placeholder="Region will auto-fill"
              />
            </label>

            <label>
              Key Vault Name:
              <input
                type="text"
                value={form.keyVaultName}
                onChange={(e) =>
                  updateFormField(
                    "keyVaultName",
                    e.target.value
                  )
                }
                placeholder="3-24 chars, letters/numbers/hyphen"
                minLength={3}
                maxLength={24}
                pattern="[A-Za-z0-9-]{3,24}"
                required
              />
            </label>

            <label>
              SKU:
              <select
                value={form.skuName}
                onChange={(e) =>
                  updateFormField(
                    "skuName",
                    e.target.value
                  )
                }
              >
                <option value="standard">
                  Standard
                </option>
                <option value="premium">
                  Premium
                </option>
              </select>
            </label>
          </div>
        </section>

        <section className="keyvault-section">
          <h2>Security and Access</h2>
          <div className="keyvault-grid">
            <label>
              Soft Delete Retention (Days):
              <input
                type="number"
                min="7"
                max="90"
                value={
                  form.softDeleteRetentionInDays
                }
                onChange={(e) =>
                  updateFormField(
                    "softDeleteRetentionInDays",
                    e.target.value
                  )
                }
                required
              />
            </label>
          </div>
        </section>

        <section className="keyvault-section">
          <h2>Tags (Optional)</h2>
          <div className="tag-input-row">
            <input
              type="text"
              placeholder="Tag key"
              value={newTagKey}
              onChange={(e) =>
                setNewTagKey(e.target.value)
              }
            />
            <input
              type="text"
              placeholder="Tag value"
              value={newTagValue}
              onChange={(e) =>
                setNewTagValue(e.target.value)
              }
            />
            <button
              type="button"
              className="mini-btn"
              onClick={addTag}
              disabled={
                !newTagKey.trim() ||
                !newTagValue.trim()
              }
            >
              Add
            </button>
          </div>
          <ul className="tag-list">
            {Object.entries(tags).map(
              ([key, value]) => (
                <li
                  key={key}
                  className="tag-item"
                >
                  <span>
                    <strong>{key}</strong>:{" "}
                    {value}
                  </span>
                  <button
                    type="button"
                    className="remove-tag-btn"
                    onClick={() =>
                      removeTag(key)
                    }
                  >
                    Remove
                  </button>
                </li>
              )
            )}
          </ul>
        </section>

        <div className="keyvault-actions">
          <label className="execute-toggle">
            <input
              type="checkbox"
              checked={applyInAzure}
              onChange={(e) =>
                setApplyInAzure(e.target.checked)
              }
              disabled={submitting}
            />
            Apply changes in Azure now
          </label>
          <button
            type="submit"
            className="submit-btn"
            disabled={
              submitting || !allRequirementsMet
            }
          >
            {submitting
              ? "Submitting..."
              : "Submit"}
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

        <section className="keyvault-requirements">
          <h2>Key Vault Requirements</h2>
          <ul className="requirement-list">
            {requirementChecks.map(
              (rule) => (
                <li
                  key={rule.id}
                  className={`requirement-item ${
                    rule.ok ? "ok" : "bad"
                  }`}
                >
                  <span
                    className={`status-dot ${
                      rule.ok ? "ok" : "bad"
                    }`}
                  />
                  <span>{rule.label}</span>
                </li>
              )
            )}
          </ul>
          <p
            className={`requirements-summary ${
              allRequirementsMet ? "ok" : "bad"
            }`}
          >
            {allRequirementsMet
              ? "All required checks are valid. You can submit now."
              : "Please complete the red checks before submitting."}
          </p>
        </section>

        {submitError && (
          <p className="keyvault-error">
            {submitError}
          </p>
        )}
        {message && (
          <p className="keyvault-message">
            {message}
          </p>
        )}
      </form>
    </div>
  );
}
``