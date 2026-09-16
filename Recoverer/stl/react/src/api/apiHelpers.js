const API_BASE_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

const readBackendJson = async (response) => {
  const text = await response.text();
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch (error) {
    console.error("Backend returned invalid JSON:", text, error);
    throw new Error("Server error: Invalid JSON response");
  }
};

const formatApiError = (payload, fallback = "Request failed") => {
  if (!payload) return fallback;
  if (typeof payload.message === "string" && payload.message.trim()) {
    return payload.message;
  }

  if (Array.isArray(payload.errors)) {
    return payload.errors
      .map((entry) => (typeof entry === "string" ? entry : JSON.stringify(entry)))
      .filter(Boolean)
      .join("; ");
  }

  if (payload.errors && typeof payload.errors === "object") {
    return Object.entries(payload.errors)
      .map(([field, value]) => {
        if (typeof value === "string") {
          return `${field}: ${value}`;
        }
        if (Array.isArray(value)) {
          return value.join("; ");
        }
        return JSON.stringify(value);
      })
      .filter(Boolean)
      .join("; ") || fallback;
  }

  return fallback;
};

export { API_BASE_URL, readBackendJson, formatApiError };
