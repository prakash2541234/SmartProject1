import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./CreateUser.css";
import { API_BASE_URL, readBackendJson, formatApiError } from "./api/apiHelpers";

export default function DeleteUser() {
  const navigate = useNavigate();

  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState("");

  const [loadingUsers, setLoadingUsers] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  // ✅ Fetch Users
  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setLoadingUsers(true);
    setError("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/moniter/azure/ad-users/`
      );

      const data = await readBackendJson(response);

      if (!response.ok) {
        throw new Error(formatApiError(data, "Failed to fetch users"));
      }

      setUsers(data.users || []);
    } catch (err) {
      setUsers([]);
      setError(err.message || "Unable to load users");
    } finally {
      setLoadingUsers(false);
    }
  };

  // ✅ Handle Delete
  const handleDelete = async () => {
    setError("");
    setMessage("");

    if (!selectedUser) {
      setError("Please select a user");
      return;
    }

    setSubmitting(true);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/moniter/azure/delete-user/${selectedUser}/`,
        {
          method: "DELETE",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      const data = await readBackendJson(response);

      if (!response.ok) {
        throw new Error(
          formatApiError(data, `Delete failed (${response.status})`)
        );
      }

      if (data.status === "error") {
        throw new Error(formatApiError(data, "Delete failed"));
      }

      // ✅ SUCCESS FLOW
      setMessage(data.message || "User deleted successfully");

      // ✅ Navigate to Dashboard
      if (data.request_id) {
        const dashboardState = {
          requestId: data.request_id,
          processName: "Delete User",
          status: data.status || "success",
          inputPayload: { userId: selectedUser },
          outputPayload: data,
        };

        navigate("/dashboard", { state: dashboardState });
        return;
      }

      // fallback (if no request_id)
      fetchUsers();

    } catch (err) {
      setError(err.message || "Error deleting user");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="user-page">
      <div className="user-header">
        <button className="user-back" onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
        <h1>Delete User</h1>
      </div>

      <div className="user-form">
        <section className="user-section">
          <h2>Select User</h2>

          <div className="user-grid">
            <select
              value={selectedUser}
              onChange={(e) => setSelectedUser(e.target.value)}
              disabled={loadingUsers}
            >
              <option value="">-- Select User --</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.displayName || u.display_name || u.userPrincipalName}
                </option>
              ))}
            </select>
          </div>
        </section>

        <div className="user-actions">
          <button
            onClick={handleDelete}
            disabled={!selectedUser || submitting}
          >
            {submitting ? "Deleting..." : "Delete"}
          </button>

          <button onClick={fetchUsers} disabled={loadingUsers}>
            Refresh Users
          </button>
        </div>

        {/* ✅ Messages */}
        {error && <p className="user-error">{error}</p>}
        {message && <p className="user-message">{message}</p>}
      </div>
    </div>
  );    
}