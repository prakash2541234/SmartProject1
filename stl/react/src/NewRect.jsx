import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./NewRect.css";

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

const parseServerError = (payload, fallback) => {
  if (payload?.message) return payload.message;
  if (payload?.errors && typeof payload.errors === "object") {
    const key = Object.keys(payload.errors)[0];
    const value = payload.errors[key];
    if (Array.isArray(value) && value[0]) {
      return `${key}: ${value[0]}`;
    }
    if (typeof value === "string") {
      return `${key}: ${value}`;
    }
  }
  return fallback;
};

export default function NewRect() {
  const navigate = useNavigate();

  const [subscription, setSubscription] = useState("");
  const [subscriptions, setSubscriptions] = useState([]);
  const [loadingSubscriptions, setLoadingSubscriptions] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState("");

  const [resourceGroup, setResourceGroup] = useState("");
  const [region, setRegion] = useState("");
  const [applyInAzure, setApplyInAzure] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const fetchSubscriptions = async () => {
    setLoadingSubscriptions(true);
    setSubscriptionError("");
    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/azure/subscriptions/"
      );
      const data = await response.json();
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Unable to fetch subscriptions.");
      }

      const list = data.subscriptions || [];
      setSubscriptions(list);

      if (!subscription) {
        if (list.length === 1) {
          setSubscription(list[0].subscription_id || "");
        } else if (
          data.default_subscription_id &&
          list.some((item) => item.subscription_id === data.default_subscription_id)
        ) {
          setSubscription(data.default_subscription_id);
        }
      }
    } catch (fetchError) {
      setSubscriptionError(fetchError.message || "Subscription lookup failed.");
      setSubscriptions([]);
    } finally {
      setLoadingSubscriptions(false);
    }
  };

  useEffect(() => {
    fetchSubscriptions();
  }, []);

  const canSubmit = Boolean(
    subscription.trim() && resourceGroup.trim() && region.trim()
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");

    if (!canSubmit) {
      setError("Resource group name, region, and subscription are required.");
      return;
    }

    const payload = {
      subscription,
      resourceGroup: resourceGroup.trim(),
      region,
      dryRun: !applyInAzure,
    };

    setSubmitting(true);
    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/react/create-resource-group/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(parseServerError(data, "Failed to submit request."));
      }

      if (data.status === "accepted") {
        setMessage("Dry run succeeded. Payload is valid.");
      } else {
        setMessage("Resource group creation is in progress.");
      }
    } catch (submitError) {
      setError(submitError.message || "Unable to create resource group.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setSubscription("");
    setResourceGroup("");
    setRegion("");
    setApplyInAzure(false);
    setMessage("");
    setError("");
  };

  return (
    <div className="new-rect">
      <div className="nr-header">
        <button className="nr-back" onClick={() => navigate("/")}>
          {"<- Home"}
        </button>
        <h1>Create Resource Group</h1>
      </div>
      <p className="nr-summary">
        Enter a subscription, give your resource group a name, and pick a region
        to continue.
      </p>
      <form className="nr-form" onSubmit={handleSubmit}>
        <label>
          Subscription
          <div className="nr-field-row">
            <select
              value={subscription}
              onChange={(e) => setSubscription(e.target.value)}
              required
            >
              <option value="">Select subscription</option>
              {subscriptions.map((sub) => (
                <option key={sub.subscription_id} value={sub.subscription_id}>
                  {sub.display_name || sub.subscription_id}
                  {sub.state ? ` (${sub.state})` : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={fetchSubscriptions}
              disabled={loadingSubscriptions}
            >
              {loadingSubscriptions ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          <span className="nr-hint">
            {subscriptions.length} subscription
            {subscriptions.length === 1 ? "" : "s"} available.
          </span>
          {subscriptionError && (
            <span className="nr-error-text">{subscriptionError}</span>
          )}
        </label>

        <label>
          Resource group name
          <input
            type="text"
            placeholder="my-resource-group"
            value={resourceGroup}
            onChange={(e) => setResourceGroup(e.target.value)}
            required
          />
        </label>

        <label>
          Region
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            required
          >
            <option value="">Select region</option>
            {REGION_OPTIONS.map((regionOption) => (
              <option key={regionOption} value={regionOption}>
                {regionOption}
              </option>
            ))}
          </select>
        </label>

        <label className="nr-apply-toggle">
          <input
            type="checkbox"
            checked={applyInAzure}
            onChange={(e) => setApplyInAzure(e.target.checked)}
          />
          Apply changes in Azure now
        </label>

        <div className="nr-actions">
          <button type="submit" disabled={!canSubmit || submitting}>
            {submitting ? "Sending..." : "Create"}
          </button>
          <button
            type="button"
            className="nr-secondary"
            onClick={handleReset}
            disabled={submitting}
          >
            Reset
          </button>
        </div>

        {error && <p className="nr-error">{error}</p>}
        {message && <p className="nr-success">{message}</p>}
      </form>
    </div>
  );
}
