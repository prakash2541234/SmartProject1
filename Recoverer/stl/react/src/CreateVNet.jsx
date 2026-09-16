import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateVNet.css";

// ---------------------- Helpers ----------------------
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

// ---------------------- Region Options ----------------------
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

export default function CreateVNet() {
  const navigate = useNavigate();

  // ------------ Form State ------------
  const [form, setForm] = useState({
    subscription: "",
    resourceGroup: "",
    region: "",
    vnetName: "",
    addressSpace: "",
    enableCustomRouting: "No",
    routeTableName: "",
  });

  const [subnets, setSubnets] = useState([createEmptySubnet()]);
  const [routes, setRoutes] = useState([createEmptyRoute()]);
  const [tags, setTags] = useState({});
  const [newTagKey, setNewTagKey] = useState("");
  const [newTagValue, setNewTagValue] = useState("");

  const [message, setMessage] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [applyInAzure, setApplyInAzure] = useState(false);

  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]);

  const [loadingMeta, setLoadingMeta] = useState({
    subscriptions: false,
    resourceGroups: false,
  });
  const [metaError, setMetaError] = useState({
    subscriptions: "",
    resourceGroups: "",
  });

  const setMetaLoading = (key, value) => {
    setLoadingMeta((prev) => ({ ...prev, [key]: value }));
  };
  const setMetaErrorValue = (key, value) => {
    setMetaError((prev) => ({ ...prev, [key]: value }));
  };

  const parseApiResponse = async (response) => {
    const contentType = response.headers.get("content-type") || "";
    const bodyText = await response.text();

    if (contentType.includes("application/json")) {
      try {
        return bodyText ? JSON.parse(bodyText) : {};
      } catch {
        return {
          message: bodyText || `Request failed with status ${response.status}`,
        };
      }
    }

    return { message: bodyText || `Request failed with status ${response.status}` };
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
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  // ------------ Subnet Updates ------------
  const updateSubnet = (index, field, value) => {
    setSubnets((prev) =>
      prev.map((s, i) => (i === index ? { ...s, [field]: value } : s))
    );
  };
  const addSubnet = () => setSubnets((prev) => [...prev, createEmptySubnet()]);
  const removeSubnet = (index) =>
    setSubnets((prev) => prev.filter((_, i) => i !== index));

  // ------------ Routes Updates ------------
  const updateRoute = (index, field, value) => {
    setRoutes((prev) =>
      prev.map((r, i) => {
        if (i !== index) return r;
        if (field === "nextHop" && value !== "VirtualAppliance") {
          return { ...r, nextHop: value, nextHopIp: "" };
        }
        return { ...r, [field]: value };
      })
    );
  };
  const addRoute = () => setRoutes((p) => [...p, createEmptyRoute()]);
  const removeRoute = (i) => setRoutes((p) => p.filter((_, idx) => idx !== i));

  // ---------------------- Fetch Subscriptions ----------------------
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

  // ---------------------- Fetch Resource Groups ----------------------
  const fetchResourceGroups = async (subscriptionId) => {
    if (!subscriptionId) {
      setResourceGroups([]);
      return;
    }

    setMetaLoading("resourceGroups", true);
    setMetaErrorValue("resourceGroups", "");

    try {
      const response = await fetch(
        `http://localhost:8000/api/moniter/azure/resource-groups/?subscription_id=${subscriptionId}`
      );
      const data = await response.json();

      if (!response.ok || data.status !== "success") {
        throw new Error(data.message);
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
    await fetchResourceGroups(sid);
  };

  useEffect(() => {
    fetchSubscriptions();
  }, []);

  // ---------------------- RESET ----------------------
  const handleReset = () => {
    setForm({
      subscription: "",
      resourceGroup: "",
      region: "",
      vnetName: "",
      addressSpace: "",
      enableCustomRouting: "No",
      routeTableName: "",
    });
    setSubnets([createEmptySubnet()]);
    setRoutes([createEmptyRoute()]);
    setResourceGroups([]);
    setMessage("");
    setSubmitError("");
    setApplyInAzure(false);
    setTags({});
    setNewTagKey("");
    setNewTagValue("");
  };

  // ---------------------- SUBMIT ----------------------
  const handleSubmit = async (e) => {
    e.preventDefault();

    setMessage("");
    setSubmitError("");

    const selectedSubscription = subscriptions.find(
      (s) => s.subscription_id === form.subscription
    );

    const payload = {
      ...form,
      subscriptionName: selectedSubscription?.display_name || "",
      subnets,
      routeTable:
        form.enableCustomRouting === "Yes"
          ? { routeTableName: form.routeTableName, routes }
          : null,
      tags,
      dryRun: !applyInAzure,
    };

    setSubmitting(true);

    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/react/create-vnet/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const data = await parseApiResponse(response);
      if (!response.ok) throw new Error(data.message || "VNet creation failed.");

      setMessage(
        data.status === "accepted"
          ? "Dry run validated successfully."
          : "VNet creation submitted successfully."
      );
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // ---------------------- UI Render ----------------------
  return (
    <div className="vnet-page">
      <div className="vnet-header">
        <button className="vnet-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create VNet</h1>
      </div>

      <form className="vnet-form" onSubmit={handleSubmit}>
        
        {/* ---------------- REQUIRED BASIC DETAILS ---------------- */}
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
            </label>

            {/* Resource Group */}
            <label className="full-width">
              Resource Group:
              <select
                value={resourceGroups.some((g) => g.name === form.resourceGroup) ? form.resourceGroup : ""}
                onChange={(e) => updateFormField("resourceGroup", e.target.value)}
                disabled={resourceGroups.length === 0}
                required
              >
                <option value="">Select Resource Group</option>
                {resourceGroups.map((group) => (
                  <option key={group.name} value={group.name}>
                    {group.name} {group.location ? `(${group.location})` : ""}
                  </option>
                ))}
              </select>
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

            {/* VNet Name */}
            <label>
              VNet Name:
              <input
                type="text"
                value={form.vnetName}
                onChange={(e) => updateFormField("vnetName", e.target.value)}
                required
              />
            </label>

            {/* Address Space */}
            <label className="full-width">
              Address Space:
              <input
                type="text"
                value={form.addressSpace}
                onChange={(e) => updateFormField("addressSpace", e.target.value)}
                placeholder="e.g. 10.0.0.0/16"
                required
              />
            </label>
          </div>
        </section>

        {/* ---------------- REQUIRED SUBNETS ---------------- */}
        <section className="vnet-section">
          <div className="section-row">
            <h2>Subnets (Required)</h2>
            <button type="button" className="small-btn" onClick={addSubnet}>
              + Add Subnet
            </button>
          </div>

          <div className="stack">
            {subnets.map((subnet, index) => (
              <div className="card" key={`subnet-${index}`}>
                <div className="card-head">
                  <h3>Subnet {index + 1}</h3>
                  {subnets.length > 1 && (
                    <button
                      type="button"
                      className="link-btn danger"
                      onClick={() => removeSubnet(index)}
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
                      onChange={(e) => updateSubnet(index, "subnetName", e.target.value)}
                      required
                    />
                  </label>

                  <label>
                    Address Prefix:
                    <input
                      type="text"
                      value={subnet.addressPrefix}
                      onChange={(e) => updateSubnet(index, "addressPrefix", e.target.value)}
                      required
                    />
                  </label>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------- OPTIONAL ROUTING ---------------- */}
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
                <button type="button" className="small-btn" onClick={addRoute}>
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
                          onClick={() => removeRoute(index)}
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
                          onChange={(e) => updateRoute(index, "routeName", e.target.value)}
                          required
                        />
                      </label>

                      <label>
                        Destination:
                        <input
                          type="text"
                          value={route.destination}
                          onChange={(e) => updateRoute(index, "destination", e.target.value)}
                          required
                        />
                      </label>

                      <label>
                        Next Hop:
                        <select
                          value={route.nextHop}
                          onChange={(e) => updateRoute(index, "nextHop", e.target.value)}
                        >
                          <option value="Internet">Internet</option>
                          <option value="VirtualNetworkGateway">VirtualNetworkGateway</option>
                          <option value="VirtualAppliance">VirtualAppliance</option>
                          <option value="VnetLocal">VnetLocal</option>
                          <option value="None">None</option>
                        </select>
                      </label>

                      {route.nextHop === "VirtualAppliance" && (
                        <label>
                          Next Hop IP:
                          <input
                            type="text"
                            value={route.nextHopIp}
                            onChange={(e) =>
                              updateRoute(index, "nextHopIp", e.target.value)
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

        {/* ---------------- TAGS ---------------- */}
        <section className="vnet-section">
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

        {/* ---------------- ACTIONS ---------------- */}
        <div className="vnet-actions">
          <label className="execute-toggle">
            <input
              type="checkbox"
              checked={applyInAzure}
              onChange={(e) => setApplyInAzure(e.target.checked)}
            />
            Apply changes in Azure now
          </label>

          <button type="submit" className="submit-btn" disabled={submitting}>
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

        {submitError && <p className="vnet-error">{submitError}</p>}
        {message && <p className="vnet-message">{message}</p>}
      </form>
    </div>
  );
}
