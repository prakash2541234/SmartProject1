import React, { useState } from 'react';
import './Tracker.css';
import { API_BASE_URL } from "./api/apiHelpers";

const TRIGGER_LOGIC_APP_URL = `${API_BASE_URL}/api/moniter/react/trigger-logic-app/`;
const PROCESS_DETAILS_URL = `${API_BASE_URL}/api/moniter/react/process-details/`;
const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 60000;

const isPlainObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const NAME_FIELDS = ["Name", "name", "SubName", "subName", "VNetName", "vnetName", "SPName", "spName", "RoleName", "roleName", "KVName", "kvName", "BackupType", "backupType"];

const extractCatalogSysid = (rowKey) => {
  if (!rowKey) return "-";
  const value = String(rowKey);
  const marker = "_storelogs_";
  if (value.includes(marker)) {
    return value.split(marker)[0] || value;
  }
  return value;
};

const mergeNameValues = (row) => {
  if (!row || typeof row !== "object") return "-";

  const values = NAME_FIELDS
    .map((field) => row[field])
    .filter((value) => value !== null && value !== undefined && String(value).trim() !== "")
    .map((value) => String(value).trim());

  const uniqueValues = Array.from(new Set(values));
  return uniqueValues.length ? uniqueValues.join(" | ") : "-";
};

const formatListValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  if (Array.isArray(value)) {
    return value.length ? value.map((item) => String(item)).join(", ") : "-";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
};

const buildDisplayRows = (rows) =>
  rows.map((row) => ({
    ritmNum: row?.PartitionKey || row?.partitionKey || "-",
    catalogSysid: extractCatalogSysid(row?.RowKey || row?.rowKey),
    stepName: row?.StepName || row?.stepName || "-",
    state: row?.State || row?.state || row?.u_state || "-",
    name: mergeNameValues(row),
    result: row?.Result || row?.result || row?.u_result || "-",
    error: row?.Error || row?.error || "-",
    errorField: formatListValue(
      row?.ErrorField || row?.error_field || row?.MissingFields || row?.missing_fields
    ),
  }));

const Tracker = () => {
  const [jsonPayload, setJsonPayload] = useState('');
  const [responseData, setResponseData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleInputChange = (e) => {
    setJsonPayload(e.target.value);
  };

  const fetchStoredPayload = async (payload) => {
    const ritmNumber = payload?.u_ritm_number || payload?.ritm_number;
    const catalogTaskSysid = payload?.u_catalog_task_sysid || payload?.catalog_task_sysid;

    if (!ritmNumber || !catalogTaskSysid) {
      throw new Error("Stored payload lookup requires u_ritm_number and u_catalog_task_sysid.");
    }

    const startedAt = Date.now();
    while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
      const url = new URL(PROCESS_DETAILS_URL);
      url.searchParams.set("ritm_number", ritmNumber);
      url.searchParams.set("catalog_task_sysid", catalogTaskSysid);

      const response = await fetch(url.toString(), {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      });

      let data = {};
      try {
        data = await response.json();
      } catch {
        data = {};
      }

      if (response.ok && data?.payload) {
        return data.payload;
      }

      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }

    throw new Error("Timed out waiting for the stored Logic App output in Azure Table Storage.");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResponseData(null);

    try {
      const parsedPayload = JSON.parse(jsonPayload);
      if (parsedPayload === null || typeof parsedPayload !== "object" || Array.isArray(parsedPayload)) {
        throw new Error("Payload must be a JSON object.");
      }

      const response = await fetch(TRIGGER_LOGIC_APP_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(parsedPayload),
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(errorBody || 'Failed to trigger Logic App');
      }

      const ackData = await response.json();
      const storedPayload = await fetchStoredPayload(parsedPayload);
      setResponseData({
        trigger_acknowledgement: ackData,
        stored_output: storedPayload?.rows || storedPayload,
        table_name: storedPayload?.table_name || null,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const storedRows = Array.isArray(responseData?.stored_output)
    ? responseData.stored_output
    : responseData?.stored_output && isPlainObject(responseData.stored_output)
      ? [responseData.stored_output]
      : [];

  const displayRows = buildDisplayRows(storedRows);

  const formatCellValue = (value) => {
    if (value === null || value === undefined || value === "") {
      return "-";
    }

    if (typeof value === "object") {
      return JSON.stringify(value);
    }

    return String(value);
  };

  return (
    <div className="tracker">
      <div className="tracker-shell">
        <div className="tracker-hero">
          <p className="eyebrow">Azure Logic App Monitor</p>
          <h1>Logic App Tracker</h1>
          <p className="subtitle">
            Submit your JSON payload, trigger the workflow, and review the stored Azure Table output below.
          </p>
        </div>

        <form className="tracker-form" onSubmit={handleSubmit}>
          <label htmlFor="jsonPayload">JSON Payload</label>
          <textarea
            id="jsonPayload"
            value={jsonPayload}
            onChange={handleInputChange}
            placeholder='{"u_ritm_number":"RITM1001","u_catalog_task_sysid":"abc123","u_state":"success","u_result":"done"}'
            rows="10"
          ></textarea>
          <div className="form-actions">
            <button type="submit" disabled={loading}>
              {loading ? 'Submitting...' : 'Submit Payload'}
            </button>
          </div>
        </form>

        {error && <div className="status-banner error">Error: {error}</div>}

        {responseData && (
          <div className="results-panel">
            <div className="results-header">
              <div>
                <h2>Stored Output</h2>
                <p>{responseData.table_name ? `Table: ${responseData.table_name}` : "Stored Azure Table rows returned from the backend"}</p>
              </div>
              <div className="result-meta">
                <span>{displayRows.length} row{displayRows.length === 1 ? "" : "s"}</span>
              </div>
            </div>

            <div className="table-wrap">
              <table className="output-table">
                <thead>
                  <tr>
                    <th>Ritm Num</th>
                    <th>Catalog Sysid</th>
                    <th>StepName</th>
                    <th>State</th>
                    <th>Name</th>
                    <th>Result</th>
                    <th>Error</th>
                    <th>ErrorField</th>
                  </tr>
                </thead>
                <tbody>
                  {displayRows.map((row, index) => (
                    <tr key={`${index}-${row.catalogSysid}-${row.ritmNum}`}>
                      <td>{formatCellValue(row.ritmNum)}</td>
                      <td>{formatCellValue(row.catalogSysid)}</td>
                      <td>{formatCellValue(row.stepName)}</td>
                      <td>
                        <span className={`state-pill state-${String(row.state).toLowerCase()}`}>
                          {formatCellValue(row.state)}
                        </span>
                      </td>
                      <td>{formatCellValue(row.name)}</td>
                      <td>{formatCellValue(row.result)}</td>
                      <td>{formatCellValue(row.error)}</td>
                      <td>{formatCellValue(row.errorField)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Tracker;
