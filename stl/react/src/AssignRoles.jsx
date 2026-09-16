import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./AssignRoles.css";

export default function AssignRoles() {
  const navigate = useNavigate();
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [usersError, setUsersError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState("");
  const [apiMessage, setApiMessage] = useState("");

  const roles = [
    { id: "reader", label: "Reader", description: "Read-only access" },
    { id: "contributor", label: "Contributor", description: "Can read and write" },
  ];

  const selectedUserRecord = users.find((user) => user.id === selectedUser) || null;
  const payloadPreview = {
    user_id: selectedUser || "",
    role: selectedRole || "",
    user_name:
      selectedUserRecord?.display_name ||
      selectedUserRecord?.user_principal_name ||
      "",
    user_email: selectedUserRecord?.mail || selectedUserRecord?.user_principal_name || "",
  };

  const fetchAzureUsers = async () => {
    setLoadingUsers(true);
    setUsersError("");

    try {
      const response = await fetch("http://localhost:8000/api/moniter/azure/ad-users/?limit=200");
      const data = await response.json();

      if (!response.ok || data.status !== "success") {
        if (data.code === "graph_permission_denied") {
          const tip = Array.isArray(data.troubleshooting) ? ` ${data.troubleshooting[0]}` : "";
          throw new Error(`${data.message || "Graph permission denied."}${tip}`);
        }
        const fallback = "Unable to fetch Azure AD users.";
        throw new Error(data.message || data.details || fallback);
      }

      setUsers(data.users || []);
    } catch (error) {
      setUsers([]);
      setUsersError(error.message || "Unable to fetch Azure AD users.");
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    fetchAzureUsers();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setApiError("");
    setApiMessage("");

    if (!selectedUser || !selectedRole) {
      setApiError("Please select both a user and a role.");
      return;
    }

    /* Find the selected user from the list of fetched users */
    const user = users.find((u) => u.id === selectedUser);
    if (!user) {
      setApiError("Selected user was not found.");
      return;
    }

    setSubmitting(true);

    try {
      const response = await fetch("http://localhost:8000/api/moniter/react/assign-role/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_id: user.id,
          user_name: user.display_name || user.user_principal_name || "Unknown User",
          user_email: user.mail || user.user_principal_name || "",
          role: selectedRole,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || "Role assignment failed.");
      }

      setApiMessage(data.message || "Role assignment completed.");
      setSelectedUser("");
      setSelectedRole("");
    } catch (error) {
      setApiError(error.message || "Unable to assign role.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="assign-roles-container">
      <div className="assign-roles-header">
        <button className="back-button" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Assign Roles</h1>
      </div>

      <div className="assign-roles-form-wrapper">
        <form onSubmit={handleSubmit} className="assign-roles-form">
          <div className="form-group">
            <label htmlFor="user-select">Select User:</label>
            <select
              id="user-select"
              value={selectedUser}
              onChange={(e) => setSelectedUser(e.target.value)}
              className="form-select"
              disabled={submitting || loadingUsers}
            >
              <option value="">
                {loadingUsers ? "Loading Azure users..." : "-- Choose a user --"}
              </option>
              {users.map((user) => {
                const labelName = user.display_name || user.user_principal_name || user.id;
                const emailText = user.mail || user.user_principal_name || "no-email";
                return (
                  <option key={user.id} value={user.id}>
                    {labelName} ({emailText})
                  </option>
                );
              })}
            </select>
            {usersError && <p style={{ color: "red", marginTop: "8px" }}>{usersError}</p>}
            {!loadingUsers && !usersError && users.length === 0 && (
              <p style={{ color: "red", marginTop: "8px" }}>
                No Azure AD users found for this tenant.
              </p>
            )}
            <button
              type="button"
              className="reset-button"
              onClick={fetchAzureUsers}
              disabled={submitting || loadingUsers}
              style={{ marginTop: "10px" }}
            >
              {loadingUsers ? "Refreshing..." : "Refresh Users"}
            </button>
          </div>

          <div className="form-group">
            <label>Select Role:</label>
            <div className="role-options">
              {roles.map((role) => (
                <div key={role.id} className="role-option">
                  <input
                    type="radio"
                    id={`role-${role.id}`}
                    name="role"
                    value={role.id}
                    checked={selectedRole === role.id}
                    onChange={(e) => setSelectedRole(e.target.value)}
                    disabled={submitting}
                  />
                  <label htmlFor={`role-${role.id}`} className="role-label">
                    <span className="role-title">{role.label}</span>
                    <span className="role-description">{role.description}</span>
                  </label>
                </div>
              ))}
            </div>
          </div>

          <div className="form-actions">
            <button
              type="submit"
              className="submit-button"
              disabled={submitting || loadingUsers || users.length === 0}
            >
              {submitting ? "Submitting..." : "Submit"}
            </button>
            <button
              type="button"
              className="reset-button"
              disabled={submitting}
              onClick={() => {
                setSelectedUser("");
                setSelectedRole("");
                setApiError("");
                setApiMessage("");
              }}
            >
              Reset
            </button>
          </div>

          {apiError && <p style={{ color: "red", marginTop: "12px" }}>{apiError}</p>}
          {apiMessage && <p style={{ color: "green", marginTop: "12px" }}>{apiMessage}</p>}
        </form>

        <div className="assign-roles-preview">
          <h3>Payload Preview</h3>
          <p style={{ marginTop: 0 }}>
            This is the JSON shape we are sending today. We can wire an editable JSON mode later.
          </p>
          <pre className="assign-roles-json">
            {JSON.stringify(payloadPreview, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
