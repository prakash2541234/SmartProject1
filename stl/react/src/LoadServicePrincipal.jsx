import React, { useEffect, useState } from "react";
import Dashboard from "./DashBoard";
import "./DashboardStatus.css";

const API_BASE = "http://localhost:8000/api/moniter/azure/service-principals";
const SERVICE_PRINCIPALS_URL = `${API_BASE}/`;
const IN_USE_URL = `${API_BASE}/in-use/`;
const deleteUrl = (id) => `${API_BASE}/${id}/delete/`;

const stripHtml = (input) =>
  input.replace(/<[^>]*>/g, "").trim();

const ServicePrincipals = () => {
  const [servicePrincipals, setServicePrincipals] = useState([]);
  const [inUsePrincipals, setInUsePrincipals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // 🔥 Track request ID for dashboard
  const [requestId, setRequestId] = useState(null);
  const [dashboardVisible, setDashboardVisible] = useState(false);
  const [deleteRequestState, setDeleteRequestState] = useState(null);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    const fetchData = async () => {
      try {
        const spResponse = await fetch(SERVICE_PRINCIPALS_URL);

        if (!spResponse.ok) {
          throw new Error(`SP API failed: ${spResponse.status}`);
        }

        const spData = await spResponse.json();

        const usedResponse = await fetch(IN_USE_URL);

        if (!usedResponse.ok) {
          throw new Error(`In-use API failed: ${usedResponse.status}`);
        }

        const usedData = await usedResponse.json();

        setServicePrincipals(spData);
        setInUsePrincipals(usedData);

      } catch (err) {
        console.error("ERROR:", err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const handleDelete = async (id) => {
    if (inUsePrincipals.includes(id)) {
      alert("❌ This service principal is used by APIs.");
      return;
    }

    const confirmDelete = window.confirm(
      "Are you sure you want to delete?"
    );

    if (!confirmDelete) return;

    setDashboardVisible(true);
    setRequestId(null);
    setDeleteRequestState("pending");
    setDeleteError("");

    try {
      const response = await fetch(deleteUrl(id), {
        method: "DELETE",
      });

      if (!response.ok) {
        const text = await response.text();
        const cleaned = stripHtml(text);
        const message =
          cleaned ||
          response.statusText ||
          `Delete failed with status ${response.status}`;

        setDeleteRequestState("failed");
        setDeleteError(message);
        throw new Error(message);
      }

      const data = await response.json(); // 🔥 IMPORTANT

      // 🔥 Set request ID (this triggers Dashboard)
      setRequestId(data.request_id);

      if (!response.ok) {
        setDeleteRequestState("failed");
        throw new Error(data.error || "Delete failed");
      }

      setDeleteRequestState("success");

      // ✅ Update UI after delete
      setServicePrincipals((prev) =>
        prev.filter((sp) => sp.id !== id)
      );

      alert("✅ Service Principal deleted successfully");

    } catch (err) {
      console.error(err);
      setDeleteRequestState("failed");
      const message = err?.message?.toString() ?? "Delete failed";
      setDeleteError(message);
      alert("❌ Failed to delete service principal");
    }
  };

  if (loading) return <div className="p-4">Loading...</div>;
  if (error) return <div className="p-4 text-red-500">{error}</div>;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">
        Service Principals
      </h1>

      <table className="min-w-full border border-gray-300">
        <thead className="bg-gray-100">
          <tr>
            <th className="p-2 border">Display Name</th>
            <th className="p-2 border">App ID</th>
            <th className="p-2 border">Tenant ID</th>
            <th className="p-2 border">Status</th>
            <th className="p-2 border">Action</th>
          </tr>
        </thead>

        <tbody>
          {servicePrincipals.map((sp) => {
            const isInUse = inUsePrincipals.includes(sp.id);
            const isManaged = sp.isManaged;
            const canDelete = !isInUse;

            return (
              <tr key={sp.id} className="text-center">
                <td className="p-2 border">{sp.displayName}</td>
                <td className="p-2 border">{sp.appId}</td>
                <td className="p-2 border">{sp.tenantId}</td>

                <td className="p-2 border">
                  {isInUse ? (
                    <span className="text-red-600 font-semibold">
                      In Use
                    </span>
                  ) : (
                    <span className="text-green-600">
                      Not Used
                    </span>
                  )}
                  <div className="text-xs text-gray-500 mt-1">
                    {isManaged ? "Managed" : "Unmanaged (cannot delete)"}
                  </div>
                </td>

                <td className="p-2 border">
                  <button
                    onClick={() => handleDelete(sp.id)}
                    disabled={!canDelete}
                    title={
                      isInUse
                        ? "This principal is currently in use"
                        : isManaged
                        ? "This principal is managed by the system"
                        : "This principal was created manually (will be auto-registered before delete)"
                    }
                    className={`px-3 py-1 rounded text-white ${
                      canDelete
                        ? "bg-red-500 hover:bg-red-600"
                        : "bg-gray-400 cursor-not-allowed"
                    }`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* 🔥 DASHBOARD ONLY AFTER DELETE */}
      {dashboardVisible && (
        <div className="mt-6">
          <Dashboard
            requestId={requestId}
            stage={deleteRequestState}
            error={deleteError}
          />
        </div>
      )}
    </div>
  );
};

export default ServicePrincipals;
