// src/pages/Template.jsx

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

/* -------------------------------------------------------
   Azure Region Options
------------------------------------------------------- */
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

/* =======================================================
   Template Component
======================================================= */

export default function Template() {
  const navigate = useNavigate();

  const [subscriptions, setSubscriptions] = useState([]);
  const [tenantList, setTenantList] = useState([]);

  const [tenantId, setTenantId] = useState("");
  const [subscriptionId, setSubscriptionId] = useState("");
  const [role, setRole] = useState("owner");
  const [projectName, setProjectName] = useState("");
  const [region, setRegion] = useState("");

  const [createVNet, setCreateVNet] = useState(false);
  const [subnetCount, setSubnetCount] = useState(1);

  const [loadingSubs, setLoadingSubs] = useState(false);

  /* -------------------------------------------------------
     Load Subscriptions
  ------------------------------------------------------- */
  useEffect(() => {
    loadSubscriptions();
  }, []);

  const loadSubscriptions = async () => {
    setLoadingSubs(true);

    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/azure/subscriptions/"
      );

      const data = await response.json();

      if (response.ok && data.status === "success") {
        const subs = data.subscriptions || [];
        setSubscriptions(subs);

        const tenants = [...new Set(subs.map((s) => s.tenant_id))];
        setTenantList(tenants);

        /* Auto select first tenant */
        if (tenants.length > 0) {
          setTenantId(tenants[0]);
        }
      } else {
        console.error("Failed to load subscriptions");
      }
    } catch (error) {
      console.error("Subscription fetch error", error);
    } finally {
      setLoadingSubs(false);
    }
  };

  /* -------------------------------------------------------
     Filter Subscriptions by Tenant
  ------------------------------------------------------- */
  const filteredSubscriptions = tenantId
    ? subscriptions.filter((s) => s.tenant_id === tenantId)
    : [];

  /* Auto select first subscription */
  useEffect(() => {
    if (filteredSubscriptions.length > 0) {
      setSubscriptionId(filteredSubscriptions[0].subscription_id);
    }
  }, [tenantId]);

  /* -------------------------------------------------------
     Validation
  ------------------------------------------------------- */
  const isValidRegion = (value) => REGION_OPTIONS.includes(value.trim());

  const isValidSubnetCount = (n) =>
    Number.isInteger(n) && n >= 1 && n <= 20;

  const isFormValid =
    tenantId &&
    subscriptionId &&
    projectName.trim() &&
    isValidRegion(region) &&
    (!createVNet || isValidSubnetCount(subnetCount));

  /* -------------------------------------------------------
     Submit Handler
  ------------------------------------------------------- */
  const handleSubmit = (e) => {
    e.preventDefault();

    if (!isFormValid) {
      alert("Please complete all required fields correctly.");
      return;
    }

    const outboundState = {
      tenantId,
      subscriptionId,
      projectName: projectName.trim().toLowerCase(),
      region,
      role,
      createVNet,
      subnetCount: createVNet ? subnetCount : 0,
    };

    navigate("/subscription-auto", {
      state: outboundState,
    });
  };

  /* =======================================================
     UI
  ======================================================= */

  return (
    <div className="template-page">
      <h1>Azure Subscription Template</h1>
      <br />
      <form onSubmit={handleSubmit}>
        {/* TENANT */}
        <label>Tenant ID</label>
        <select
          value={tenantId}
          onChange={(e) => {
            setTenantId(e.target.value);
            setSubscriptionId("");
          }}
        >
          <option value="">
            {loadingSubs ? "Loading..." : "Select Tenant"}
          </option>
          {tenantList.map((tenant) => (
            <option key={tenant} value={tenant}>
              {tenant}
            </option>
          ))}
        </select>
        <br />
        {/* SUBSCRIPTION */}
        <label>Subscription</label>
        <select
          value={subscriptionId}
          onChange={(e) => setSubscriptionId(e.target.value)}
          disabled={!tenantId}
        >
          <option value="">
            {tenantId ? "Select Subscription" : "Select Tenant First"}
          </option>
          {filteredSubscriptions.map((sub) => (
            <option key={sub.subscription_id} value={sub.subscription_id}>
              {sub.display_name} ({sub.subscription_id})
            </option>
          ))}
        </select>
        <br />
        {/* ROLE */}
        <label>Role Assignment</label>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="owner">Owner</option>
          <option value="contributor">Contributor</option>
          <option value="reader">Reader</option>
        </select>
        <br />
        {/* PROJECT NAME */}
        <label>Project Name</label>
        <input
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
          placeholder="example-project"
        />
        <br />
        {/* REGION */}
        <label>Region</label>
        <input
          list="region-options"
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        />
        <datalist id="region-options">
          {REGION_OPTIONS.map((r) => (
            <option key={r} value={r} />
          ))}
        </datalist>
        <br />
        {/* VNET OPTION */}
        <label>
          <input
            type="checkbox"
            checked={createVNet}
            onChange={(e) => setCreateVNet(e.target.checked)}
          />
          &nbsp;Create Virtual Network (VNet)
        </label>
        <br />
        {/* SUBNET COUNT */}
        {createVNet && (
          <>
            <label>Number of Subnets</label>
            <input
              type="number"
              min="1"
              max="20"
              value={subnetCount}
              onChange={(e) => setSubnetCount(Number(e.target.value))}
            />
            <br />
          </>
        )}
        <button type="submit" disabled={!isFormValid}>
          Start Automation
        </button>
      </form>
    </div>
  );
}