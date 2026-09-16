import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "./Subscription-auto.css";

import {
  buildResourceGroupName,
  buildServicePrincipalName,
} from "./Naming";

/* ---------------------------------------------------------
Region Mapping
--------------------------------------------------------- */

const AZURE_REGION_MAP = {
  "(Asia Pacific) Central India": "centralindia",
  "(Asia Pacific) East Asia": "eastasia",
  "(Europe) West Europe": "westeurope",
  "(Europe) North Europe": "northeurope",
  "(US) East US": "eastus",
  "(US) East US 2": "eastus2",
  "(US) West US": "westus",
  "(US) West US 2": "westus2",
  "(US) West US 3": "westus3",
  "(US) Central US": "centralus",
  "(US) North Central US": "northcentralus",
  "(US) South Central US": "southcentralus",
};

/* ---------------------------------------------------------
Pipeline Stages
--------------------------------------------------------- */

const PIPELINE_STAGES = [
  { id: "subscription", title: "Subscription" },
  { id: "resource-group", title: "Resource Group" },
  { id: "service-principal", title: "Service Principal" },
  { id: "get-token", title: "Get Token from SP" },
];

export default function SubscriptionAuto() {

  const navigate = useNavigate();
  const { state } = useLocation();
  const taskStartedRef = useRef(false);

  const [backendError, setBackendError] = useState("");

  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [accessToken, setAccessToken] = useState("");

  const [steps, setSteps] = useState(
    PIPELINE_STAGES.map((stage, index) => ({
      ...stage,
      status: index === 0 ? "completed" : "pending",
      loading: false,
    }))
  );

  /* ---------------------------------------------------------
  Build Payload
  --------------------------------------------------------- */

  const payload = useMemo(() => {

    if (!state) return null;

    const {
      subscriptionId,
      tenantId,
      projectName,
      region,
      createVNet,
      subnetCount,
    } = state;

    const azureRegion =
      AZURE_REGION_MAP[region] || region.toLowerCase().replace(/\s+/g, "");

    return {
      subscription: subscriptionId,
      tenantId,
      projectName,
      region: azureRegion,
      resourceGroup: buildResourceGroupName(projectName),
      servicePrincipalName: buildServicePrincipalName(projectName),

      credentialType: "client-secret",
      secretDisplayName: "sp-client-secret",
      secretValidityMonths: 12,

      createIfMissing: true,
      assignRoleNow: false,
      dryRun: false,

      createVNet: !!createVNet,
      subnetCount: createVNet ? subnetCount : 0,
    };

  }, [state]);

  useEffect(() => {

    if (!payload) {
      navigate("/");
      return;
    }

    if (!taskStartedRef.current) {
      taskStartedRef.current = true;
      runAutomation();
    }

  }, [payload]);

  const updateStep = (index, updates) => {

    setSteps((prev) =>
      prev.map((s, i) => (i === index ? { ...s, ...updates } : s))
    );

  };

  /* ---------------------------------------------------------
  MAIN PIPELINE
  --------------------------------------------------------- */

  const runAutomation = async () => {

    const rgOk = await createResourceGroup();
    if (!rgOk) return;

    const spOk = await createServicePrincipal();
    if (!spOk) return;

    /* Azure propagation delay */
    console.log("Waiting 15 seconds for Azure propagation...");

    await new Promise((resolve) => setTimeout(resolve, 15000));

    await generateToken();
  };

  /* ---------------------------------------------------------
  CREATE RESOURCE GROUP
  --------------------------------------------------------- */

  const createResourceGroup = async () => {

    try {

      updateStep(1, { loading: true });

      const response = await fetch(
        "http://localhost:8000/api/moniter/azure/create-resource-group/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },

          body: JSON.stringify({
            subscription: payload.subscription,
            resourceGroup: payload.resourceGroup,
            region: payload.region,
          }),
        }
      );

      const data = await response.json();

      console.log("RG RESPONSE:", data);

      if (!response.ok) {
        throw new Error(data.message || JSON.stringify(data));
      }

      updateStep(1, {
        loading: false,
        status: "completed",
      });

      return true;

    } catch (err) {

      console.error("RG ERROR:", err);

      setBackendError(err.message);

      updateStep(1, {
        loading: false,
        status: "failed",
      });

      return false;
    }
  };

  /* ---------------------------------------------------------
  CREATE SERVICE PRINCIPAL
  --------------------------------------------------------- */

  const createServicePrincipal = async () => {

    try {

      updateStep(2, { loading: true });

      const response = await fetch(
        "http://localhost:8000/api/moniter/react/create-service-principal/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const data = await response.json();

      console.log("SP RESPONSE:", data);

      if (!response.ok) {
        throw new Error(
          data.message ||
            data.error ||
            data.stderr ||
            JSON.stringify(data)
        );
      }

      const id = data?.appId;
      const secret = data?.credential?.secret_text;

      if (!id || !secret) {
        throw new Error("Client ID or Client Secret missing from backend response");
      }

      setClientId(id);
      setClientSecret(secret);

      updateStep(2, {
        loading: false,
        status: "completed",
      });

      return true;

    } catch (err) {

      console.error("SP ERROR:", err);

      setBackendError(err.message);

      updateStep(2, {
        loading: false,
        status: "failed",
      });

      return false;
    }
  };

  /* ---------------------------------------------------------
  GENERATE ACCESS TOKEN
  --------------------------------------------------------- */

  const generateToken = async () => {

    try {

      updateStep(3, { loading: true });

      const response = await fetch(
        "http://localhost:8000/api/moniter/azure/get-access-token/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },

          body: JSON.stringify({
            clientId,
            clientSecret,
            tenantId: payload.tenantId,
          }),
        }
      );

      const data = await response.json();

      console.log("TOKEN RESPONSE:", data);

      if (!response.ok) {
        throw new Error(data.message || JSON.stringify(data));
      }

      setAccessToken(data.access_token);

      updateStep(3, {
        loading: false,
        status: "completed",
      });

      return true;

    } catch (err) {

      console.error("TOKEN ERROR:", err);

      setBackendError(err.message);

      updateStep(3, {
        loading: false,
        status: "failed",
      });

      return false;
    }
  };

  /* ---------------------------------------------------------
  Progress
  --------------------------------------------------------- */

  const progressPercent =
    (steps.filter((s) => s.status === "completed").length /
      steps.length) *
    100;

  /* ---------------------------------------------------------
  UI
  --------------------------------------------------------- */

  return (
    <div className="sa-page">

      <div className="sa-header">
        <h1>Automation Pipeline</h1>
      </div>

      <section className="sa-pipeline">

        <div className="sa-line-track">
          <div
            className="sa-line-fill"
            style={{ width: `${progressPercent}%` }}
          />
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

      {accessToken && (
        <div className="secret-box">
          <p>Access Token</p>
          <code>{accessToken.substring(0,120)}...</code>
        </div>
      )}

      {backendError && (
        <div className="error-box">
          <strong>Error</strong>
          <pre>{backendError}</pre>
        </div>
      )}

    </div>
  );
}