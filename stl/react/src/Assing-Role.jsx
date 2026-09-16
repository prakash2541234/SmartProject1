import React, { useEffect, useState } from "react";
import { useNavigate} from "react-router-dom";

export default function AssignRole() {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);

  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]);
  const [resources, setResources] = useState([]);

  const [selectedUser, setSelectedUser] = useState("");
  const [selectedSubscription, setSelectedSubscription] = useState("");
  const [scopeType, setScopeType] = useState("");
  const [selectedRG, setSelectedRG] = useState("");
  const [selectedResource, setSelectedResource] = useState("");
  const [role, setRole] = useState("");

  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    fetchUsers();
    fetchSubscriptions();
  }, []);

  const fetchUsers = async () => {
    const res = await fetch("http://localhost:8000/api/moniter/azure/ad-users/");
    const data = await res.json();
    setUsers(data.users || []);
  };

  const fetchSubscriptions = async () => {
    const res = await fetch("http://localhost:8000/api/moniter/azure/subscriptions/");
    const data = await res.json();
    setSubscriptions(data.subscriptions || []);
  };

  const fetchRG = async (subId) => {
    const res = await fetch(
      `http://localhost:8000/api/moniter/azure/resource-groups/?subscription_id=${subId}`
    );
    const data = await res.json();
    setResourceGroups(data.resource_groups || []);
  };

  const fetchResources = async (subId, rg) => {
    const res = await fetch(
      `http://localhost:8000/api/moniter/azure/resources/?subscription_id=${subId}&resource_group=${rg}`
    );
    const data = await res.json();
    setResources(data.resources || []);
  };

  const buildScope = () => {
    if (scopeType === "none") {
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

  const selectedUserRecord = users.find((user) => user.id === selectedUser) || null;
  const payloadPreview = {
    user_id: selectedUser || "",
    role: role || "",
    scope: buildScope(),
    user_name: selectedUserRecord?.display_name || "",
    user_email: selectedUserRecord?.mail || selectedUserRecord?.user_principal_name || "",
  };

  const handleSubmit = async () => {
    setError("");
    setMessage("");
    setErrors({});

    // ✅ VALIDATIONS (FIXED)
    if (!selectedSubscription) return setError("Subscription is required");
    if (!selectedUser) return setError("User is required");
    if (!scopeType) return setError("Please select scope type");
    if (!role) return setError("Please select role");

    if (scopeType === "rg" && !selectedRG) {
      return setError("Please select Resource Group");
    }

    if (scopeType === "resource" && !selectedResource) {
      return setError("Please select Resource");
    }

    const scope = buildScope();

    if (!scope) return setError("Scope is invalid");

    const payload = {
      user_id: selectedUser,
      role: role,
      scope: scope,
      user_name: selectedUserRecord?.display_name || selectedUserRecord?.user_principal_name || "",
      user_email: selectedUserRecord?.mail || selectedUserRecord?.user_principal_name || "",
    };

    console.log("FINAL PAYLOAD:", payload);

    try {
      const response = await fetch(
        "http://localhost:8000/api/moniter/react/assign-role/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const data = await response.json();
      console.log("API RESPONSE:", data);

      if (!response.ok) {
        if (data.errors) {
          setErrors(data.errors);
        } else {
          setError(data.message || JSON.stringify(data));
        }
        return;
      }

      setMessage("✅ Role assigned successfully");

    } catch (err) {
      setError("Server error: " + err.message);
    }
  };

  return (
    <div style={{ padding: "20px", maxWidth: "500px" }}>
      <button onClick={() => navigate("/")}>⬅ Back</button>
      <h2>Assign Role</h2>

      {/* SUBSCRIPTION */}
      <div>
        <label>Subscription</label>
        <select
          value={selectedSubscription}
          onChange={(e) => {
            setSelectedSubscription(e.target.value);
            fetchRG(e.target.value);
          }}
        >
          <option value="">--Select--</option>
          {subscriptions.map((s) => (
            <option key={s.subscription_id} value={s.subscription_id}>
              {s.display_name}
            </option>
          ))}
        </select>
      </div>

      {/* USER */}
      <div>
        <label>User</label>
        <select
          value={selectedUser}
          onChange={(e) => setSelectedUser(e.target.value)}
        >
          <option value="">--Select--</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.display_name || u.user_principal_name || u.id}
            </option>
          ))}
        </select>
        {errors.user_id && <p style={{ color: "red" }}>{errors.user_id[0]}</p>}
      </div>
      
      {/* SCOPE */}
      <div>
        <label>Scope</label>
        <label><input type="radio" value="none" onChange={(e) => setScopeType(e.target.value)} /> Subscription</label>
        <label><input type="radio" value="rg" onChange={(e) => setScopeType(e.target.value)} /> RG</label>
        <label><input type="radio" value="resource" onChange={(e) => setScopeType(e.target.value)} /> Resource</label>
      </div>

      {/* RG */}
      {(scopeType === "rg" || scopeType === "resource") && (
        <select onChange={(e) => {
          setSelectedRG(e.target.value);
          if (scopeType === "resource") {
            fetchResources(selectedSubscription, e.target.value);
          }
        }}>
          <option value="">--Select RG--</option>
          {resourceGroups.map((rg) => (
            <option key={rg.name} value={rg.name}>{rg.name}</option>
          ))}
        </select>
      )}

      {/* RESOURCE */}
      {scopeType === "resource" && (
        <select onChange={(e) => setSelectedResource(e.target.value)}>
          <option value="">--Select Resource--</option>
          {resources.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      )}

      {/* ROLE */}
      <div>
        <label>Role</label>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">--Select--</option>
          <option value="reader">Reader</option>
          <option value="contributor">Contributor</option>
        </select>
        {errors.role && <p style={{ color: "red" }}>{errors.role[0]}</p>}
      </div>

      <button onClick={handleSubmit}>Submit</button>

      {error && <p style={{ color: "red" }}>{error}</p>}
      {message && <p style={{ color: "green" }}>{message}</p>}

      <div style={{ marginTop: "24px", padding: "16px", border: "1px solid #dbe3ee", borderRadius: "8px" }}>
        <h3 style={{ marginTop: 0 }}>Payload Preview</h3>
        <p style={{ marginTop: 0 }}>This is the JSON payload view we can keep for review before making it editable later.</p>
        <pre style={{
          margin: 0,
          padding: "16px",
          background: "#0f172a",
          color: "#dbeafe",
          borderRadius: "6px",
          overflow: "auto",
          fontSize: "13px",
          lineHeight: 1.5,
        }}>
          {JSON.stringify(payloadPreview, null, 2)}
        </pre>
      </div>
    </div>
  );
}
