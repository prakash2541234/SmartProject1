import { useEffect, useState } from "react";
import ApiButtons from "../ApiButtons.jsx";
import "./open.css";

export default function One() {
  const [statusMessage, setStatusMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [adUserCount, setAdUserCount] = useState(null);
  const [adError, setAdError] = useState("");

  useEffect(() => {
    checkDjangoHealth();
    fetchMessages();
  }, []);

  const checkDjangoHealth = async () => {
    try {
      const response = await fetch("http://localhost:8000/api/moniter/react/health/");
      if (response.ok) setStatusMessage("running");
    } catch (err) {
      console.error("Django is not running", err);
    }
  };

  const fetchAdUserCount = async () => {
    setAdError("");
    try {
      const res = await fetch("http://localhost:8000/api/moniter/azure/ad-users-count/");
      const data = await res.json().catch(() => ({}));

      if (data.status === "success" || data.status === "degraded") {
        const nextCount = data.count ?? data["@odata.count"] ?? null;
        if (nextCount !== null) setAdUserCount(nextCount);
        if (data.status === "degraded" && data.message) setAdError(data.message);
        return;
      }

      const errorMessage = data.message || "Failed to fetch AD users count";
      setAdError(errorMessage);
    } catch (err) {
      setAdError(`Unable to connect: ${err.message}`);
    }
  };

  const fetchMessages = async () => {
    try {
      const response = await fetch("http://localhost:8000/api/moniter/react/messages/");
      if (!response.ok) return;
      const data = await response.json();
      setMessages(data || []);
    } catch (err) {
      console.error("Error fetching messages:", err);
    }
  };

  return (
    <div className="container">
      <div className="content">
        <h1>Hello React</h1>
        <p>This is a default JSX component.</p>
        <p>Welcome to here</p>

        <ApiButtons />

        <hr />

        {statusMessage && (
          <p>
            <strong>Django:</strong> {statusMessage}
          </p>
        )}

        {messages.length > 0 && (
          <div className="section">
            <h3>Messages</h3>
            <ul>
              {messages.map((m) => (
                <li key={m.id}>
                  <strong>{m.title}:</strong> {m.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        <hr />

        <div className="section">
          <h2>Azure AD</h2>

          <button onClick={fetchAdUserCount}>
            Get Azure AD Users Count
          </button>

          {adError && <div className="error">{adError}</div>}

          {adUserCount !== null && (
            <div className="success">
              Azure AD Users: {adUserCount}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}