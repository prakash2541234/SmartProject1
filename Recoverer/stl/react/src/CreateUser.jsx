import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateUser.css";
import { API_BASE_URL, readBackendJson, formatApiError } from "./api/apiHelpers";

const INITIAL_FORM = {
  displayName: "",
  userPrincipalName: "",
  mailNickname: "",
  password: "",
  forceChangePasswordNextSignIn: true,
  accountEnabled: true,
  tenantId: "",
};

const MAIL_NICKNAME_REGEX = /^[A-Za-z0-9._-]{1,64}$/;

export default function CreateUser() {
  const navigate = useNavigate();

  const [form, setForm] = useState(INITIAL_FORM);
  const [verifiedDomains, setVerifiedDomains] = useState([]);
  const [loadingDomains, setLoadingDomains] = useState(false);
  const [domainsError, setDomainsError] = useState("");

  const [submitting, setSubmitting] = useState(false);

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [generatedPassword, setGeneratedPassword] = useState("");

  const [, setStage] = useState("pending");

  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const userPrincipalDomain = (form.userPrincipalName || "").includes("@")
    ? form.userPrincipalName.split("@").pop().trim().toLowerCase()
    : "";

  const fetchVerifiedDomains = async () => {
    setLoadingDomains(true);
    setDomainsError("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/monitor/azure/verified-domains/`
      );
      const data = await readBackendJson(response);

      if (!response.ok || data.status !== "success") {
        throw new Error(formatApiError(data, "Failed to fetch verified domains."));
      }

      const domains = (data.domains || [])
        .map((item) => item.domain)
        .filter(Boolean);

      setVerifiedDomains(domains);

      if (!form.userPrincipalName && domains.length > 0) {
        updateField("userPrincipalName", `user@${domains[0]}`);
      }
    } catch (err) {
      setVerifiedDomains([]);
      setDomainsError(err.message || "Unable to load verified domains.");
    } finally {
      setLoadingDomains(false);
    }
  };

  useEffect(() => {
    fetchVerifiedDomains();
  }, []);

  const checks = [
    { id: "name", ok: Boolean(form.displayName.trim()) },
    {
      id: "upn",
      ok:
        Boolean(form.userPrincipalName.trim()) &&
        form.userPrincipalName.includes("@"),
    },
    {
      id: "upn-domain",
      ok:
        !form.userPrincipalName.trim() ||
        verifiedDomains.length === 0 ||
        verifiedDomains.includes(userPrincipalDomain),
    },
    {
      id: "nickname",
      ok: MAIL_NICKNAME_REGEX.test(form.mailNickname.trim()),
    },
  ];

  const canSubmit = checks.every((item) => item.ok);

  const handleSubmit = async (e) => {
    e.preventDefault();

    setMessage("");
    setError("");
    setGeneratedPassword("");
    setStage("pending");

    if (!canSubmit) {
      setError("Please complete all required checks.");
      return;
    }

    const payload = {
      ...form,
      dryRun: false,
    };

    if (!payload.password) {
      delete payload.password;
    }

    setSubmitting(true);

    try {
      setStage("processing");

      const response = await fetch(
        `${API_BASE_URL}/api/monitor/react/create-user/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        }
      );

      const data = await readBackendJson(response);

      if (!response.ok) {
        throw new Error(
          formatApiError(data, `Create user failed (${response.status})`)
        );
      }

      if (data.status === "error") {
        throw new Error(formatApiError(data, "Create user failed."));
      }

      if (data.status === "accepted") {
        setMessage(data.message || "Dry run successful.");
        setStage("accepted");
      }

      if (data.status === "success") {
        const action = data?.user?.action;

        if (action === "created") {
          setMessage("User created successfully in Azure.");
        } else if (action === "existing") {
          setMessage("User already exists.");
        } else {
          setMessage(data.message || "User request completed.");
        }

        setStage("success");

        if (data.request_id) {
          const dashboardState = {
            requestId: data.request_id,
            processName: "User Creation",
            status: data.status || "success",
            inputPayload: payload,
            outputPayload: data,
          };
          navigate("/dashboard", { state: dashboardState });
          return;
        }
      }

      if (data.generated_password) {
        setGeneratedPassword(data.generated_password);
      }
    } catch (err) {
      setStage("failed");
      setError(err.message || "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setForm(INITIAL_FORM);
    setMessage("");
    setError("");
    setGeneratedPassword("");
    setStage("pending");
  };

  return (
    <div className="user-page">
      <div className="user-header">
        <button className="user-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create User</h1>
      </div>

      <form className="user-form" onSubmit={handleSubmit}>
        <section className="user-section">
          <h2>Basic Details</h2>

          <div className="user-grid">
            <input
              type="text"
              placeholder="Display Name"
              value={form.displayName}
              onChange={(e) => updateField("displayName", e.target.value)}
              required
            />

            <input
              type="email"
              placeholder="User Principal Name"
              value={form.userPrincipalName}
              onChange={(e) => updateField("userPrincipalName", e.target.value)}
              required
            />

            <input
              type="text"
              placeholder="Mail Nickname"
              value={form.mailNickname}
              onChange={(e) => updateField("mailNickname", e.target.value)}
              required
            />

            <input
              type="text"
              placeholder="Password (Optional)"
              value={form.password}
              onChange={(e) => updateField("password", e.target.value)}
            />
          </div>
        </section>

        <div className="user-actions">
          <button type="submit" disabled={!canSubmit || submitting}>
            {submitting ? "Submitting..." : "Submit"}
          </button>

          <button type="button" onClick={handleReset}>
            Reset
          </button>
        </div>

        {error && <p className="user-error">{error}</p>}
        {message && <p className="user-message">{message}</p>}

        {generatedPassword && (
          <div className="secret-box">
            <p>Generated Password:</p>
            <code>{generatedPassword}</code>
          </div>
        )}
      </form>

    </div>
  );
}
