import React, { useEffect, useRef, useState } from "react";
import { API_BASE_URL, formatApiError, readBackendJson } from "./api/apiHelpers";

const START_PROCESS_URL = `${API_BASE_URL}/api/start-process/`;
const PROCESS_STATUS_URL = `${API_BASE_URL}/api/process-status/`;
const POLL_INTERVAL_MS = 4000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

const LOCATION_OPTIONS = [
  { label: "Central India", value: "centralindia" },
  { label: "East US", value: "eastus" },
  { label: "West US 2", value: "westus2" },
  { label: "West Europe", value: "westeurope" },
  { label: "Southeast Asia", value: "southeastasia" },
];

const SKU_OPTIONS = [
  { label: "Standard LRS", value: "Standard_LRS" },
  { label: "Standard GRS", value: "Standard_GRS" },
  { label: "Premium LRS", value: "Premium_LRS" },
];

const KIND_OPTIONS = [
  { label: "StorageV2", value: "StorageV2" },
  { label: "Storage", value: "Storage" },
  { label: "BlobStorage", value: "BlobStorage" },
];

const ROLE_OPTIONS = [
  { label: "Contributor", value: "Contributor" },
  { label: "Storage Account Contributor", value: "Storage Account Contributor" },
  { label: "Reader", value: "Reader" },
];

const DEFAULT_FORM = {
  projectName: "",
  location: LOCATION_OPTIONS[0].value,
  sku: SKU_OPTIONS[0].value,
  kind: KIND_OPTIONS[0].value,
  subscriptionRole: ROLE_OPTIONS[0].value,
};

const createUiTaskId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
};

const formatTimestamp = (value) => {
  if (!value) return "Waiting";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

export default function DashBoardAPI() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState("");
  const [tasks, setTasks] = useState([]);
  const [formError, setFormError] = useState("");
  const [usersError, setUsersError] = useState("");
  const [usersLoading, setUsersLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [latestRun, setLatestRun] = useState(null);

  const tasksRef = useRef(tasks);
  const activeRequestsRef = useRef(new Set());

  useEffect(() => {
    tasksRef.current = tasks;
  }, [tasks]);

  useEffect(() => {
    const fetchUsers = async () => {
      setUsersLoading(true);
      setUsersError("");
      try {
        const response = await fetch(`${API_BASE_URL}/api/moniter/azure/ad-users/?limit=200`);
        const data = await readBackendJson(response);
        if (!response.ok) {
          throw new Error(formatApiError(data, "Unable to fetch Azure users."));
        }
        setUsers(data.users || []);
      } catch (error) {
        setUsers([]);
        setUsersError(error.message || "Unable to fetch Azure users.");
      } finally {
        setUsersLoading(false);
      }
    };

    fetchUsers();
  }, []);

  const updateTask = (taskId, updater) => {
    setTasks((current) => current.map((task) => (task.task_id === taskId ? updater(task) : task)));
  };

  const pollTaskStatus = async (task) => {
    if (!task.polling || task.state !== "ON") return;
    if (activeRequestsRef.current.has(task.task_id)) return;

    const startedAt = new Date(task.started_at).getTime();
    if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
      updateTask(task.task_id, (current) => ({
        ...current,
        state: "OFF",
        result: "TIMEOUT",
        polling: false,
        loading: false,
        status_message: "Polling timed out after 5 minutes.",
        error: "Process status polling timed out.",
        updated_at: new Date().toISOString(),
      }));
      return;
    }

    activeRequestsRef.current.add(task.task_id);

    try {
      const response = await fetch(`${PROCESS_STATUS_URL}${encodeURIComponent(task.ritm_number)}/`);
      const data = await readBackendJson(response);

      if (!response.ok) {
        throw new Error(formatApiError(data, "Failed to fetch process status."));
      }

      const nextStatus = (data.status || "PENDING").toUpperCase();

      if (nextStatus === "PENDING") {
        updateTask(task.task_id, (current) => ({
          ...current,
          loading: true,
          status_message: "Waiting for the Azure Logic App to complete...",
          last_checked_at: new Date().toISOString(),
        }));
        return;
      }

      if (nextStatus === "SUCCESS" || nextStatus === "FAILED") {
        updateTask(task.task_id, (current) => ({
          ...current,
          state: "OFF",
          result: nextStatus,
          polling: false,
          loading: false,
          project_name: data.project_name || current.project_name,
          u_state: data.u_state || "",
          u_result: data.u_result || "",
          updated_at: data.updated_at || new Date().toISOString(),
          last_checked_at: new Date().toISOString(),
          status_message: nextStatus === "SUCCESS" ? "Process completed successfully." : "Process failed.",
          error: "",
        }));
      }
    } catch (error) {
      updateTask(task.task_id, (current) => ({
        ...current,
        loading: true,
        error: error.message,
        status_message: "Retrying status check.",
        last_checked_at: new Date().toISOString(),
      }));
    } finally {
      activeRequestsRef.current.delete(task.task_id);
    }
  };

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      tasksRef.current.filter((task) => task.polling && task.state === "ON").forEach((task) => {
        pollTaskStatus(task);
      });
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, []);

  const handleStartProcess = async () => {
    const trimmedProjectName = form.projectName.trim();
    if (!trimmedProjectName) {
      setFormError("Project Name is required.");
      return;
    }
    if (!selectedUser) {
      setFormError("Please select a user.");
      return;
    }

    setFormError("");
    setSubmitting(true);

    try {
      const response = await fetch(START_PROCESS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requester_user_id: selectedUser,
          project_name: trimmedProjectName,
          location: form.location,
          sku: form.sku,
          kind: form.kind,
          subscription_role: form.subscriptionRole,
        }),
      });

      const data = await readBackendJson(response);
      if (!response.ok) {
        throw new Error(formatApiError(data, "Failed to start process."));
      }

      const task = {
        task_id: createUiTaskId(),
        ritm_number: data.ritm_number,
        catalog_task_sysid: data.catalog_task_sysid || "",
        project_name: trimmedProjectName,
        location: form.location,
        sku: form.sku,
        kind: form.kind,
        subscription_role: form.subscriptionRole,
        requester_user_id: selectedUser,
        state: "ON",
        result: "PENDING",
        polling: true,
        loading: true,
        started_at: new Date().toISOString(),
        last_checked_at: "",
        updated_at: "",
        u_state: "",
        u_result: "",
        status_message: "Process Started",
        error: "",
      };

      setTasks((current) => [task, ...current]);
      setLatestRun({
        ritm_number: data.ritm_number,
        status: "Process Started",
        started_at: new Date().toISOString(),
      });
      setForm((current) => ({ ...current, projectName: "" }));
      pollTaskStatus(task);
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSubmitting(false);
    }
  };

  const activeCount = tasks.filter((task) => task.state === "ON").length;

  return (
    <div style={styles.page}>
      <div style={styles.heroGlow} />
      <div style={styles.card}>
        <div style={styles.headerRow}>
          <div>
            <p style={styles.kicker}>Process Control</p>
            <h1 style={styles.title}>Azure Storage Process Starter</h1>
          </div>
          <div style={styles.counter}>
            <span style={styles.counterLabel}>Active</span>
            <span style={styles.counterValue}>{activeCount}</span>
          </div>
        </div>

        {latestRun && (
          <div style={styles.summaryCard}>
            <div>
              <div style={styles.summaryLabel}>Latest Run</div>
              <div style={styles.summaryValue}>{latestRun.ritm_number}</div>
            </div>
            <div>
              <div style={styles.summaryLabel}>Status</div>
              <div style={styles.summaryStatus}>{latestRun.status}</div>
            </div>
            <div>
              <div style={styles.summaryLabel}>Started</div>
              <div style={styles.summaryTime}>{formatTimestamp(latestRun.started_at)}</div>
            </div>
          </div>
        )}

        <div style={styles.formGrid}>
          <label style={styles.field}>
            <span style={styles.fieldLabel}>User</span>
            <select
              value={selectedUser}
              onChange={(event) => setSelectedUser(event.target.value)}
              style={styles.input}
              disabled={usersLoading}
            >
              <option value="">
                {usersLoading ? "Loading users..." : "Select a user"}
              </option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name || user.user_principal_name || user.id}
                </option>
              ))}
            </select>
          </label>

          <label style={styles.field}>
            <span style={styles.fieldLabel}>Project Name</span>
            <input
              type="text"
              value={form.projectName}
              onChange={(event) => setForm((current) => ({ ...current, projectName: event.target.value }))}
              placeholder="Project ABC"
              style={styles.input}
            />
          </label>

          <label style={styles.field}>
            <span style={styles.fieldLabel}>Location</span>
            <select
              value={form.location}
              onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))}
              style={styles.input}
            >
              {LOCATION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label style={styles.field}>
            <span style={styles.fieldLabel}>SKU</span>
            <select
              value={form.sku}
              onChange={(event) => setForm((current) => ({ ...current, sku: event.target.value }))}
              style={styles.input}
            >
              {SKU_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label style={styles.field}>
            <span style={styles.fieldLabel}>Kind</span>
            <select
              value={form.kind}
              onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value }))}
              style={styles.input}
            >
              {KIND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label style={styles.field}>
            <span style={styles.fieldLabel}>Subscription Role</span>
            <select
              value={form.subscriptionRole}
              onChange={(event) => setForm((current) => ({ ...current, subscriptionRole: event.target.value }))}
              style={styles.input}
            >
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <br />
          <div style={styles.formGrid}>
            <button
              type="button"
              onClick={handleStartProcess}
              disabled={submitting}
              style={{ ...styles.button, ...(submitting ? styles.buttonDisabled : {}) }}
            >
              {submitting ? "Starting..." : "Start Process"}
            </button>
          </div>
        </div>

        {formError && <p style={styles.formError}>{formError}</p>}
        {usersError && <p style={styles.formError}>{usersError}</p>}

        <div style={styles.tableWrap}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Project</th>
                <th style={styles.th}>RITM</th>
                <th style={styles.th}>Location</th>
                <th style={styles.th}>SKU</th>
                <th style={styles.th}>Kind</th>
                <th style={styles.th}>Role</th>
                <th style={styles.th}>State</th>
                <th style={styles.th}>Final Details</th>
                <th style={styles.th}>Updated</th>
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 ? (
                <tr>
                  <td colSpan="9" style={styles.emptyCell}>
                    No runs yet. Start one to begin polling.
                  </td>
                </tr>
              ) : (
                tasks.map((task) => (
                  <tr key={task.task_id}>
                    <td style={styles.td}>{task.project_name}</td>
                    <td style={styles.tdMono}>{task.ritm_number}</td>
                    <td style={styles.td}>{task.location}</td>
                    <td style={styles.td}>{task.sku}</td>
                    <td style={styles.td}>{task.kind}</td>
                    <td style={styles.td}>{task.subscription_role}</td>
                    <td style={styles.td}>
                      <span
                        style={{
                          ...styles.badge,
                          ...(task.state === "ON" ? styles.badgeOn : styles.badgeOff),
                        }}
                      >
                        {task.loading ? "ON" : task.state}
                      </span>
                      <div style={styles.subText}>{task.status_message}</div>
                      {task.error && <div style={styles.errorText}>{task.error}</div>}
                    </td>
                    <td style={styles.td}>
                      <span
                        style={{
                          ...styles.badge,
                          ...(task.result === "SUCCESS"
                            ? styles.badgeSuccess
                            : task.result === "FAILED" || task.result === "TIMEOUT"
                              ? styles.badgeFailed
                              : styles.badgePending),
                        }}
                      >
                        {task.result}
                      </span>
                      <div style={styles.subText}>
                        <div>State: {task.u_state || "Waiting"}</div>
                        <div>Result: {task.u_result || "Waiting"}</div>
                      </div>
                    </td>
                    <td style={styles.td}>
                      <div style={styles.subText}>{formatTimestamp(task.updated_at || task.last_checked_at)}</div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    padding: "32px 20px",
    background:
      "radial-gradient(circle at top left, rgba(18, 95, 255, 0.18), transparent 30%), radial-gradient(circle at bottom right, rgba(15, 118, 110, 0.18), transparent 28%), linear-gradient(180deg, #eef4ff 0%, #f8fbff 100%)",
    color: "#10203a",
  },
  heroGlow: {
    position: "fixed",
    inset: "auto -140px 60px auto",
    width: "280px",
    height: "280px",
    borderRadius: "999px",
    background: "rgba(29, 78, 216, 0.10)",
    filter: "blur(24px)",
    pointerEvents: "none",
  },
  card: {
    position: "relative",
    zIndex: 1,
    width: "100%",
    maxWidth: "1320px",
    margin: "0 auto",
    borderRadius: "24px",
    border: "1px solid rgba(16, 32, 58, 0.08)",
    background: "rgba(255, 255, 255, 0.9)",
    backdropFilter: "blur(10px)",
    boxShadow: "0 24px 60px rgba(16, 32, 58, 0.12)",
    padding: "28px",
  },
  headerRow: {
    display: "flex",
    gap: "16px",
    justifyContent: "space-between",
    alignItems: "flex-start",
    flexWrap: "wrap",
  },
  kicker: {
    margin: 0,
    textTransform: "uppercase",
    letterSpacing: "0.16em",
    fontSize: "12px",
    fontWeight: 800,
    color: "#4762d6",
  },
  title: {
    margin: "10px 0 12px",
    fontSize: "clamp(30px, 4vw, 46px)",
    lineHeight: 1.05,
  },
  description: {
    margin: 0,
    maxWidth: "72ch",
    color: "#52627a",
    fontSize: "16px",
  },
  counter: {
    minWidth: "140px",
    borderRadius: "18px",
    padding: "16px 18px",
    background: "linear-gradient(135deg, rgba(29, 78, 216, 0.10), rgba(15, 118, 110, 0.10))",
    border: "1px solid rgba(29, 78, 216, 0.14)",
  },
  counterLabel: {
    display: "block",
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    fontSize: "11px",
    fontWeight: 800,
    color: "#5f6f8a",
    marginBottom: "4px",
  },
  counterValue: {
    fontSize: "34px",
    fontWeight: 800,
    color: "#10203a",
  },
  summaryCard: {
    marginTop: "22px",
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: "16px",
    borderRadius: "18px",
    padding: "18px 20px",
    background: "linear-gradient(135deg, rgba(29, 78, 216, 0.08), rgba(15, 118, 110, 0.08))",
    border: "1px solid rgba(29, 78, 216, 0.12)",
  },
  summaryLabel: {
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    fontSize: "11px",
    fontWeight: 800,
    color: "#71819c",
    marginBottom: "6px",
  },
  summaryValue: {
    fontSize: "20px",
    fontWeight: 800,
    color: "#10203a",
    wordBreak: "break-word",
  },
  summaryStatus: {
    fontSize: "18px",
    fontWeight: 800,
    color: "#0f766e",
  },
  summaryTime: {
    fontSize: "14px",
    color: "#52627a",
  },
  formGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: "14px",
    alignItems: "end",
    marginTop: "24px",
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  fieldLabel: {
    fontSize: "12px",
    fontWeight: 800,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "#71819c",
  },
  input: {
    width: "100%",
    borderRadius: "14px",
    border: "1px solid #dce4f2",
    background: "#fff",
    padding: "14px 16px",
    fontSize: "15px",
    color: "#10203a",
    outline: "none",
    boxShadow: "0 1px 0 rgba(16, 32, 58, 0.03)",
  },
  button: {
    border: "none",
    borderRadius: "999px",
    padding: "14px 22px",
    background: "linear-gradient(135deg, #1d4ed8 0%, #0f766e 100%)",
    color: "#fff",
    fontSize: "15px",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: "0 14px 28px rgba(29, 78, 216, 0.24)",
  },
  buttonDisabled: {
    opacity: 0.75,
    cursor: "not-allowed",
  },
  formError: {
    marginTop: "14px",
    marginBottom: 0,
    color: "#b42318",
    fontWeight: 700,
  },
  tableWrap: {
    marginTop: "24px",
    borderRadius: "18px",
    overflowX: "auto",
    border: "1px solid #e4eaf4",
    background: "#fff",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    minWidth: "1180px",
  },
  th: {
    textAlign: "left",
    fontSize: "12px",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "#71819c",
    padding: "14px 16px",
    borderBottom: "1px solid #e7edf6",
    background: "#f8fbff",
  },
  td: {
    verticalAlign: "top",
    padding: "14px 16px",
    borderBottom: "1px solid #edf2f7",
    color: "#10203a",
    fontSize: "14px",
  },
  tdMono: {
    verticalAlign: "top",
    padding: "14px 16px",
    borderBottom: "1px solid #edf2f7",
    color: "#10203a",
    fontSize: "13px",
    fontFamily:
      "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace",
    wordBreak: "break-word",
  },
  emptyCell: {
    padding: "24px 16px",
    textAlign: "center",
    color: "#52627a",
  },
  badge: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    borderRadius: "999px",
    padding: "6px 10px",
    fontSize: "12px",
    fontWeight: 800,
    letterSpacing: "0.04em",
  },
  badgeOn: {
    background: "#e8f5ff",
    color: "#0f4c81",
  },
  badgeOff: {
    background: "#edf2f7",
    color: "#334155",
  },
  badgeSuccess: {
    background: "#e7f8ee",
    color: "#146c43",
  },
  badgeFailed: {
    background: "#fff1f2",
    color: "#b42318",
  },
  badgePending: {
    background: "#f8fafc",
    color: "#52627a",
  },
  subText: {
    marginTop: "8px",
    color: "#5f6f8a",
    fontSize: "12px",
    lineHeight: 1.5,
  },
  errorText: {
    marginTop: "8px",
    color: "#b42318",
    fontSize: "12px",
    fontWeight: 700,
  },
};
