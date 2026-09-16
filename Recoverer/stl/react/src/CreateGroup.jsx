import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateGroup.css";

const INITIAL_FORM = {
  displayName: "",
  mailNickname: "",
  description: "",
  mailEnabled: false,
  securityEnabled: true,
  unifiedGroup: false,
  tenantId: "",
  memberUserIds: [],
};

const MAIL_NICKNAME_REGEX = /^[A-Za-z0-9._-]{1,64}$/;

export default function CreateGroup() {
  const navigate = useNavigate();

  const [form, setForm] = useState(INITIAL_FORM);
  const [applyInAzure, setApplyInAzure] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usersError, setUsersError] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [tags, setTags] = useState({});
  const [newTagKey, setNewTagKey] = useState("");
  const [newTagValue, setNewTagValue] = useState("");

  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const fetchUsers = async () => {
    setLoadingUsers(true);
    setUsersError("");
    try {
      const response = await fetch("http://localhost:8000/api/moniter/azure/ad-users/?limit=200");
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Failed to fetch Azure AD users.");
      }

      const fetchedUsers = data.users || [];
      setUsers(fetchedUsers);
      if (form.memberUserIds.length > 0) {
        const validIds = new Set(fetchedUsers.map((u) => u.id));
        updateField(
          "memberUserIds",
          form.memberUserIds.filter((id) => validIds.has(id))
        );
      }
    } catch (err) {
      setUsers([]);
      setUsersError(err.message || "Unable to fetch Azure AD users.");
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    fetchUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredUsers = useMemo(() => {
    const needle = userSearch.trim().toLowerCase();
    if (!needle) {
      return users;
    }
    return users.filter((user) => {
      const display = (user.display_name || "").toLowerCase();
      const upn = (user.user_principal_name || "").toLowerCase();
      const mail = (user.mail || "").toLowerCase();
      return display.includes(needle) || upn.includes(needle) || mail.includes(needle);
    });
  }, [users, userSearch]);

  const toggleMemberSelection = (userId) => {
    updateField(
      "memberUserIds",
      form.memberUserIds.includes(userId)
        ? form.memberUserIds.filter((id) => id !== userId)
        : [...form.memberUserIds, userId]
    );
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

  const checks = [
    { id: "name", label: "Group display name is provided", ok: Boolean(form.displayName.trim()) },
    {
      id: "nickname",
      label: "Mail nickname format is valid",
      ok: MAIL_NICKNAME_REGEX.test(form.mailNickname.trim()),
    },
    {
      id: "type",
      label: "At least one group capability is enabled",
      ok: form.mailEnabled || form.securityEnabled,
    },
    {
      id: "users",
      label: "Users can be selected to add into this group",
      ok: users.length > 0 || Boolean(usersError),
    },
  ];
  const canSubmit = checks.every((item) => item.ok);

  const parseApiError = (data, fallback) => {
    const lines = [];
    lines.push(data?.message || fallback);
    if (Array.isArray(data?.required_permissions) && data.required_permissions.length > 0) {
      lines.push(`Required permissions: ${data.required_permissions.join(", ")}`);
    }
    if (Array.isArray(data?.troubleshooting) && data.troubleshooting.length > 0) {
      lines.push(`How to fix: ${data.troubleshooting.join(" ")}`);
    }
    if (data?.request_context?.request_id || data?.request_context?.client_request_id) {
      lines.push(
        `Request IDs: request_id=${data?.request_context?.request_id || "n/a"}, client_request_id=${data?.request_context?.client_request_id || "n/a"}`
      );
    }
    if (data?.azure_error_code) {
      lines.push(`Azure error code: ${data.azure_error_code}`);
    }
    if (Array.isArray(data?.verified_domains) && data.verified_domains.length > 0) {
      lines.push(`Verified domains: ${data.verified_domains.join(", ")}`);
    }
    if (data?.provided_domain) {
      lines.push(`Provided domain: ${data.provided_domain}`);
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");

    if (!canSubmit) {
      setError("Please complete all required checks.");
      return;
    }

    const payload = {
      displayName: form.displayName,
      mailNickname: form.mailNickname,
      description: form.description,
      mailEnabled: form.unifiedGroup ? true : form.mailEnabled,
      securityEnabled: form.unifiedGroup ? false : form.securityEnabled,
      groupTypes: form.unifiedGroup ? ["Unified"] : [],
      memberUserIds: form.memberUserIds,
      tenantId: form.tenantId,
      tags,
      dryRun: !applyInAzure,
    };

    setSubmitting(true);
    try {
      const response = await fetch("http://localhost:8000/api/moniter/react/create-group/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(parseApiError(data, "Create group API request failed."));
      }

      if (data.status === "accepted") {
        setMessage("Dry run successful. Group payload is valid.");
      } else {
        const members = data.members || {};
        const memberSummary = `Members added: ${members.added_count || 0}, already in group: ${members.already_member_count || 0}, failed: ${members.failed_count || 0}.`;
        setMessage(`Group request submitted successfully. ${memberSummary}`);
      }
    } catch (err) {
      setError(err.message || "Failed to create group.");
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
    <div className="group-page">
      <div className="group-header">
        <button className="group-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Create Group</h1>
      </div>

      <form className="group-form" onSubmit={handleSubmit}>
        <section className="group-section">
          <h2>Basic Details</h2>
          <div className="group-grid">
            <label>
              Display Name:
              <input
                type="text"
                value={form.displayName}
                onChange={(e) => updateField("displayName", e.target.value)}
                required
              />
            </label>
            <label>
              Mail Nickname:
              <input
                type="text"
                value={form.mailNickname}
                onChange={(e) => updateField("mailNickname", e.target.value)}
                required
              />
            </label>
            <label className="full-width">
              Description (Optional):
              <input
                type="text"
                value={form.description}
                onChange={(e) => updateField("description", e.target.value)}
              />
            </label>
            <label>
              Tenant ID (Optional):
              <input
                type="text"
                value={form.tenantId}
                onChange={(e) => updateField("tenantId", e.target.value)}
                placeholder="Uses backend tenant if empty"
              />
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.mailEnabled}
                onChange={(e) => updateField("mailEnabled", e.target.checked)}
                disabled={form.unifiedGroup}
              />
              Mail enabled
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.securityEnabled}
                onChange={(e) => updateField("securityEnabled", e.target.checked)}
                disabled={form.unifiedGroup}
              />
              Security enabled
            </label>
            <label className="checkbox-row full-width">
              <input
                type="checkbox"
                checked={form.unifiedGroup}
                onChange={(e) => updateField("unifiedGroup", e.target.checked)}
              />
              Microsoft 365 group (Unified)
            </label>
          </div>
        </section>

        <section className="group-section">
          <div className="section-row">
            <h2>Group Users</h2>
            <button
              type="button"
              className="mini-btn"
              onClick={fetchUsers}
              disabled={loadingUsers}
            >
              {loadingUsers ? "Refreshing..." : "Refresh Users"}
            </button>
          </div>

          <div className="group-grid">
            <label className="full-width">
              Search Users:
              <input
                type="text"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                placeholder="Search by name, email, or UPN"
              />
              <span className="hint">
                Available: {users.length}, filtered: {filteredUsers.length}, selected: {form.memberUserIds.length}
              </span>
              {usersError && <span className="error-text">{usersError}</span>}
            </label>
          </div>

          <div className="users-list">
            {filteredUsers.map((user) => {
              const labelName = user.display_name || user.user_principal_name || user.id;
              const secondary = user.mail || user.user_principal_name || "";
              const checked = form.memberUserIds.includes(user.id);
              return (
                <label key={user.id} className="user-row">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleMemberSelection(user.id)}
                  />
                  <span className="user-row-text">
                    <strong>{labelName}</strong>
                    <small>{secondary}</small>
                  </span>
                </label>
              );
            })}
            {!loadingUsers && filteredUsers.length === 0 && (
              <p className="empty-users">No users found for current filter.</p>
            )}
          </div>
        </section>

        <section className="group-section">
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

        <section className="group-section">
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

        <div className="group-actions">
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

        {error && <p className="group-error">{error}</p>}
        {message && <p className="group-message">{message}</p>}
      </form>
    </div>
  );
}
