import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./RoleAssignment.css";

export default function ViewRoles() {
  const navigate = useNavigate();

  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]);
  const [resources, setResources] = useState([]);

  const [selectedSubscription, setSelectedSubscription] = useState("");
  const [scopeType, setScopeType] = useState("");
  const [selectedRG, setSelectedRG] = useState("");
  const [selectedResource, setSelectedResource] = useState("");

  const [roles, setRoles] = useState([]);
  const [viewMode, setViewMode] = useState(false);

  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // 🔥 ROLE PRIORITY
  const rolePriority = {
    "Owner": 1,
    "Contributor": 2,
    "Reader": 3,
    "User Access Administrator": 4
  };

  // ---------------- SAFE FETCH ----------------
  const safeFetch = async (url, options = {}) => {
    const res = await fetch(url, options);
    const contentType = res.headers.get("content-type");

    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || "API Error");
    }

    if (!contentType || !contentType.includes("application/json")) {
      const text = await res.text();
      throw new Error("Expected JSON but got: " + text);
    }

    return res.json();
  };

  // ---------------- FETCH DATA ----------------
  useEffect(() => {
    fetchSubscriptions();
  }, []);

  const fetchSubscriptions = async () => {
    try {
      const data = await safeFetch(
        "http://localhost:8000/api/moniter/azure/subscriptions/"
      );
      setSubscriptions(data.subscriptions || []);
    } catch (err) {
      setError("Failed to load subscriptions: " + err.message);
    }
  };

  const fetchRG = async (subId) => {
    try {
      const data = await safeFetch(
        `http://localhost:8000/api/moniter/azure/resource-groups/?subscription_id=${subId}`
      );
      setResourceGroups(data.resource_groups || []);
    } catch (err) {
      setError("Failed to load resource groups");
    }
  };

  const fetchResources = async (subId, rg) => {
    try {
      const data = await safeFetch(
        `http://localhost:8000/api/moniter/azure/resources/?subscription_id=${subId}&resource_group=${rg}`
      );
      setResources(data.resources || []);
    } catch (err) {
      setError("Failed to load resources");
    }
  };

  // ---------------- BUILD SCOPE ----------------
  const buildScope = () => {
    if (scopeType === "subscription") {
      return `/subscriptions/${selectedSubscription}`;
    }
    if (scopeType === "rg") {
      return `/subscriptions/${selectedSubscription}/resourceGroups/${selectedRG}`;
    }
    if (scopeType === "resource") {
      return selectedResource;
    }
    return "";
  };

  // ---------------- VIEW ROLES ----------------
  const handleView = async () => {
    setError("");
    setLoading(true);
    const scope = buildScope();
    if (!scope) {
      setError("Invalid scope");
      setLoading(false);
      return;
    }

    try {
      const data = await safeFetch(
        `http://localhost:8000/api/moniter/azure/view-roles/?scope=${encodeURIComponent(scope)}`
      );

      setRoles(data.roles || []);
      setViewMode(true);

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // ---------------- DELETE ROLE ----------------
  const handleDelete = async (assignmentId, scope) => {
    if (!window.confirm("Are you sure you want to delete this role?")) return;

    try {
      await safeFetch(
        "http://localhost:8000/api/moniter/azure/delete-role/",
        {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            assignment_name: assignmentId,
            scope: scope,
          }),
        }
      );

      handleView();

    } catch (err) {
      alert("Delete failed: " + err.message);
    }
  };

  // ---------------- FILTER + SORT ----------------
  const processedRoles = roles
    .filter((r) => {
      const name = r.principal_name || r.principal_id;
      return name.toLowerCase().includes(search.toLowerCase());
    })
    .sort((a, b) => {
      return (rolePriority[a.role_name] || 99) - (rolePriority[b.role_name] || 99);
    });

  // ---------------- UI ----------------
  return (
    <div className="container">

      {/* HEADER */}
      <div className="header">
        <button onClick={() => navigate("/")}>⬅ Back</button>
        <button onClick={() => navigate("/assign-roles-with-scope")}>Assign Role</button>
      </div>

      {/* ---------------- SELECTION ---------------- */}
      {!viewMode && (
        <div className="card">
          <h2>Select Scope</h2>

          <div className="form-group">
            <label>Subscription</label>
            <select
              value={selectedSubscription}
              onChange={(e) => {
                setSelectedSubscription(e.target.value);
                fetchRG(e.target.value);
              }}
            >
              <option value="">--Select Subscription--</option>
              {subscriptions.map((s) => (
                <option key={s.subscription_id} value={s.subscription_id}>
                  {s.display_name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Scope Type</label>
            <div className="radio-group">
              <label>
                <input type="radio" value="subscription" onChange={(e) => setScopeType(e.target.value)} />
                Subscription
              </label>
              <label>
                <input type="radio" value="rg" onChange={(e) => setScopeType(e.target.value)} />
                Resource Group
              </label>
              <label>
                <input type="radio" value="resource" onChange={(e) => setScopeType(e.target.value)} />
                Resource
              </label>
            </div>
          </div>

          {(scopeType === "rg" || scopeType === "resource") && (
            <div className="form-group">
              <label>Resource Group</label>
              <select
                onChange={(e) => {
                  setSelectedRG(e.target.value);
                  if (scopeType === "resource") {
                    fetchResources(selectedSubscription, e.target.value);
                  }
                }}
              >
                <option value="">--Select RG--</option>
                {resourceGroups.map((rg) => (
                  <option key={rg.name} value={rg.name}>{rg.name}</option>
                ))}
              </select>
            </div>
          )}

          {scopeType === "resource" && (
            <div className="form-group">
              <label>Resource</label>
              <select onChange={(e) => setSelectedResource(e.target.value)}>
                <option value="">--Select Resource--</option>
                {resources.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
            </div>
          )}

          <button className="primary-btn" onClick={handleView}>
            {loading ? "Loading..." : "View Roles"}
          </button>

          {error && <p className="error">{error}</p>}
        </div>
      )}

      {/* ---------------- TABLE ---------------- */}
      {viewMode && (
        <div className="table-container">
          <h2>Role Assignments</h2>

          {/* 🔍 SEARCH */}
          <input
            type="text"
            placeholder="Search user..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="search-input"
          />

          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Scope</th>
                <th>Action</th>
              </tr>
            </thead>

            <tbody>
              {processedRoles.length === 0 ? (
                <tr>
                  <td colSpan="4">No roles found</td>
                </tr>
              ) : (
                processedRoles.map((r) => (
                  <tr key={r.assignment_id}>
                    <td>{r.principal_name || r.principal_id}</td>
                    <td>{r.role_name}</td>
                    <td>{r.scope}</td>
                    <td>
                      <button
                        className="delete-btn"
                        onClick={() => handleDelete(r.assignment_id, r.scope)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}