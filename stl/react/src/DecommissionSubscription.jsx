import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const BASE_URL = "http://localhost:8000";

export default function DecommissionSubscription() {
  const [subscriptions, setSubscriptions] = useState([]);
  const [resourceGroups, setResourceGroups] = useState([]);
  const [resources, setResources] = useState([]);

  const [selectedSubscription, setSelectedSubscription] = useState("");
  const [selectedResourceGroup, setSelectedResourceGroup] = useState("");

  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [detachingResourceId, setDetachingResourceId] = useState("");

  const navigate = useNavigate();

  // 🔹 Load Subscriptions
  useEffect(() => {
    fetch(`${BASE_URL}/api/moniter/azure/subscriptions/`)
      .then(res => res.json())
      .then(data => setSubscriptions(data.subscriptions || []))
      .catch(() => alert("Error loading subscriptions"));
  }, []);

  // 🔹 Load Resource Groups
  const loadResourceGroups = (subId) => {
    setSelectedSubscription(subId);
    setSelectedResourceGroup("");
    setResources([]);

    fetch(`${BASE_URL}/api/moniter/azure/resource-groups/?subscription_id=${subId}`)
      .then(res => res.json())
      .then(data => setResourceGroups(data.resource_groups || []))
      .catch(() => alert("Error loading resource groups"));
  };

  // 🔹 Load Resources
  const loadResources = (rg) => {
    setSelectedResourceGroup(rg);
    setLoading(true);

    fetch(`${BASE_URL}/api/moniter/azure/resources/?subscription_id=${selectedSubscription}&resource_group=${rg}`)
      .then(res => res.json())
      .then(data => setResources(data.resources || []))
      .catch(() => alert("Error loading resources"))
      .finally(() => setLoading(false));
  };

  // 🔹 Delete Resource (FIXED)
  const handleDeleteResource = async (resourceId) => {
    if (!selectedSubscription || !selectedResourceGroup) {
      alert("Please select subscription and resource group first");
      return;
    }

    if (!window.confirm("Are you sure you want to delete this resource?")) return;

    setDeleting(true);

    try {
      const response = await fetch(
        `${BASE_URL}/api/moniter/azure/delete-resource/?subscription_id=${selectedSubscription}&resource_group=${selectedResourceGroup}&resource_id=${encodeURIComponent(resourceId)}`,
        {
          method: "DELETE",
        }
      );

      const data = await response.json();
      if (!response.ok) {
        console.error("Backend error:", data);
        alert(data.error || data.message || "Delete failed");
        return;
      }

      alert(data.message || "Resource deleted successfully");

      // 🔄 Refresh resources list
      loadResources(selectedResourceGroup);

    } catch (error) {
      console.error(error);
      alert("Error deleting resource");
    } finally {
      setDeleting(false);
    }
  };

  const handleDetachPublicIp = async (resourceId) => {
    if (!selectedSubscription || !selectedResourceGroup) {
      alert("Please select subscription and resource group first");
      return;
    }

    if (!window.confirm("Detach this public IP from its attached resource?")) return;

    setDetachingResourceId(resourceId);

    try {
      const response = await fetch(
        `${BASE_URL}/api/moniter/azure/detach-public-ip/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            subscription_id: selectedSubscription,
            resource_group: selectedResourceGroup,
            resource_id: resourceId,
          }),
        }
      );

      const data = await response.json();
      if (!response.ok) {
        console.error("Detach error:", data);
        alert(data.error || data.message || "Unable to detach public IP");
        return;
      }

      alert(data.message || "Public IP detached successfully");
      loadResources(selectedResourceGroup);
    } catch (error) {
      console.error(error);
      alert("Error detaching public IP");
    } finally {
      setDetachingResourceId("");
    }
  };

  // 🔹 Delete Resource Group
  const deleteResourceGroup = async () => {
    if (!window.confirm("Delete this resource group?")) return;

    try {
      await fetch(
        `${BASE_URL}/api/moniter/azure/delete-resource-group/?subscription_id=${selectedSubscription}&resource_group=${selectedResourceGroup}`,
        { method: "DELETE" }
      );

      alert("Resource Group Deleted");
      setResources([]);
      setSelectedResourceGroup("");
    } catch {
      alert("Error deleting resource group");
    }
  };

  return (
    <div style={{ padding: "20px" }}>
      {/* 🔹 Back Button */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: "20px" }}>
        <button onClick={() => navigate("/")}>
          {"<- Back"}
        </button>
      </div>

      <h1>Decommission Subscription</h1>

      {/* 🔹 Subscription Dropdown */}
      <div>
        <label>Select Subscription:</label>
        <br />
        <select onChange={(e) => loadResourceGroups(e.target.value)}>
          <option value="">-- Select Subscription --</option>
          {subscriptions.map(sub => (
            <option key={sub.subscription_id} value={sub.subscription_id}>
              {sub.display_name}
            </option>
          ))}
        </select>
      </div>

      {/* 🔹 Resource Group Dropdown */}
      {resourceGroups.length > 0 && (
        <div style={{ marginTop: "15px" }}>
          <label>Select Resource Group:</label>
          <br />
          <select onChange={(e) => loadResources(e.target.value)}>
            <option value="">-- Select Resource Group --</option>
            {resourceGroups.map(rg => (
              <option key={rg.name} value={rg.name}>
                {rg.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* 🔹 Delete Resource Group Button */}
      {selectedResourceGroup && (
        <div style={{ marginTop: "15px" }}>
          <button
            onClick={deleteResourceGroup}
            style={{ background: "red", color: "white", padding: "8px" }}
          >
            Delete Resource Group
          </button>
        </div>
      )}

      {/* 🔹 Resources Table */}
      <div style={{ marginTop: "20px" }}>
        {loading ? (
          <p>Loading resources...</p>
        ) : (
          <table border="1" cellPadding="10" width="100%">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Location</th>
                <th>ID</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {resources.length > 0 ? (
                resources.map((res, index) => (
                  <tr key={index}>
                    <td>{res.name}</td>
                    <td>{res.type}</td>
                    <td>{res.location}</td>
                    <td style={{ fontSize: "12px" }}>{res.id}</td>
                    <td>
                      <button
                        onClick={() => handleDeleteResource(res.id)}
                        disabled={deleting}
                        style={{ background: "red", color: "white", padding: "8px" }}
                      >
                        {deleting ? "Deleting..." : "Delete Resource"}
                      </button>
                      {res.type === "Microsoft.Network/publicIPAddresses" && (
                        <button
                          onClick={() => handleDetachPublicIp(res.id)}
                          disabled={detachingResourceId === res.id}
                          style={{
                            marginLeft: "8px",
                            background: "#444",
                            color: "white",
                            padding: "8px",
                          }}
                        >
                          {detachingResourceId === res.id
                            ? "Detaching..."
                            : "Detach Public IP"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="5" align="center">
                    No resources found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
