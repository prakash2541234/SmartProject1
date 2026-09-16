// src/utils/Naming.jsx

/* ========================== Config ========================== */
const NAMING_BASE =
  (typeof window !== "undefined" && window.__NAMING_BASE) ||
  "http://localhost:8100/api/naming"; // remote counter (Option C)

const AZURE_BASE =
  (typeof window !== "undefined" && window.__AZURE_API_BASE) ||
  "http://localhost:8000/api/moniter/azure"; // your Azure proxy backend

/* ======================= Small Utilities ===================== */
function sanitize(value) {
  return (value || "").toLowerCase().replace(/[^a-z0-9-]/g, "");
}
function pad(n) {
  return String(n).padStart(3, "0");
}
function stellantis(prefix, tags, counter) {
  const loc = sanitize(tags.location).replace(/-/g, "");
  const env = sanitize(tags.environment).replace(/-/g, "");
  return `${prefix}-stellantis-${loc}-${env}-${pad(counter)}`;
}
function withTimeout(promise, ms = 2000) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("Timeout")), ms);
    promise.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

/* =================== Local Counter Fallback ================== */
const LOCAL_KEY = "nameCountersV1";
function loadLocal() {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveLocal(obj) {
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(obj));
  } catch {}
}

function localKey(type, tags) {
  return `${type}|${sanitize(tags.location)}|${sanitize(tags.environment)}`;
}

function nextLocalCounter(type, tags) {
  const store = loadLocal();
  const k = localKey(type, tags);
  const next = (store[k] || 0) + 1;
  store[k] = next;
  saveLocal(store);
  return next;
}

/* ============== Session guard to avoid duplicates ============ */
const sessionLastName = new Map(); // key: `${type}|loc|env` -> name string
function markAndEnsureUnique(type, tags, name, bumpIfSame) {
  const k = localKey(type, tags);
  if (sessionLastName.get(k) === name) {
    // last emitted was same; bump counter locally once
    const bumped = bumpIfSame();
    sessionLastName.set(k, bumped);
    return bumped;
  }
  sessionLastName.set(k, name);
  return name;
}

/* =================== Remote Counter (Option C) ================== */
async function getNextCounterRemote(type, tags) {
  const qs = new URLSearchParams({
    type,
    location: sanitize(tags.location),
    environment: sanitize(tags.environment),
  }).toString();

  const url = `${NAMING_BASE}/next-counter?${qs}`;
  const res = await withTimeout(fetch(url), 2000);
  let data = {};
  try { data = await res.json(); } catch {}
  if (!res.ok || typeof data?.next !== "number") {
    throw new Error(data?.message || `Failed to fetch next counter for ${type}`);
  }
  return data.next;
}

/* ================ RG Listing to compute highest+1 ================ */
async function listResourceGroups(subscriptionId) {
  const url = `${AZURE_BASE}/resource-groups/?subscription_id=${encodeURIComponent(subscriptionId)}`;
  const res = await withTimeout(fetch(url), 4000);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !Array.isArray(data?.resource_groups)) return [];
  return data.resource_groups.map((rg) => rg?.name).filter(Boolean);
}

function extractRgCounter(name, loc, env) {
  const safeLoc = sanitize(loc);
  const safeEnv = sanitize(env);
  const re = new RegExp(`^rg-stellantis-${safeLoc}-${safeEnv}-(\\d{3})$`);
  const m = name.match(re);
  if (!m) return 0;
  const n = parseInt(m[1], 10);
  return Number.isFinite(n) ? n : 0;
}

async function computeNextRgCounterFromList(subscriptionId, tags) {
  const existing = await listResourceGroups(subscriptionId);
  let highest = 0;
  for (const name of existing) {
    highest = Math.max(highest, extractRgCounter(name, tags.location, tags.environment));
  }
  return highest + 1;
}

/* ======================= Key Vault helpers ======================= */
function kvCandidate(tags, counter = 1) {
  const loc = sanitize(tags?.location).replace(/-/g, "");
  const env = sanitize(tags?.environment).replace(/-/g, "");
  const padded = pad(counter);

  // 1) kv-<loc>-<env>-<###>
  let name = `kv-${loc}-${env}-${padded}`;
  if (name.length <= 24) return name;

  // 2) kv-<loc>-<e>-<###>
  name = `kv-${loc}-${(env || "")[0] || ""}-${padded}`;
  if (name.length <= 24 && /^[a-z]/.test(name)) return name;

  // 3) kv-<loc>-<###>
  name = `kv-${loc}-${padded}`;
  if (name.length <= 24 && /^[a-z]/.test(name)) return name;

  // 4) fallback trim
  name = name.replace(/[^a-z0-9-]/g, "");
  if (!/^[a-z]/.test(name)) name = `kv${name}`;
  if (name.length > 24) name = name.slice(0, 24);
  if (name.endsWith("-")) name = name.slice(0, -1);
  return name;
}

function kvNameValid(name) {
  return /^[a-z][a-z0-9-]{1,22}[a-z0-9]$/.test(name) && name.length >= 3 && name.length <= 24;
}

/* ====================== Public API (async) ====================== */
/**
 * RESOURCE GROUP name
 * 1) Try listing RGs -> highest+1
 * 2) Else try remote counter 'rg'
 * 3) Else local counter
 */
export async function buildResourceGroupName(subscriptionId, tags) {
  // 1) Azure list
  try {
    const counter = await computeNextRgCounterFromList(subscriptionId, tags);
    const name = stellantis("rg", tags, counter);
    return markAndEnsureUnique("rg", tags, name, () => stellantis("rg", tags, counter + 1));
  } catch {
    // fall through
  }
  // 2) Remote counter
  try {
    const counter = await getNextCounterRemote("rg", tags);
    const name = stellantis("rg", tags, counter);
    return markAndEnsureUnique("rg", tags, name, () => stellantis("rg", tags, counter + 1));
  } catch {
    // fall through
  }
  // 3) Local
  const counter = nextLocalCounter("rg", tags);
  const name = stellantis("rg", tags, counter);
  return markAndEnsureUnique("rg", tags, name, () => {
    const c2 = nextLocalCounter("rg", tags);
    return stellantis("rg", tags, c2);
  });
}

/**
 * SERVICE PRINCIPAL name
 * 1) Remote counter 'spn'
 * 2) Local counter
 */
export async function buildServicePrincipalName(tags) {
  try {
    const counter = await getNextCounterRemote("spn", tags);
    const name = stellantis("spn", tags, counter);
    return markAndEnsureUnique("spn", tags, name, () => stellantis("spn", tags, counter + 1));
  } catch {
    // local fallback
    const counter = nextLocalCounter("spn", tags);
    const name = stellantis("spn", tags, counter);
    return markAndEnsureUnique("spn", tags, name, () => {
      const c2 = nextLocalCounter("spn", tags);
      return stellantis("spn", tags, c2);
    });
  }
}

/**
 * VNET name
 * 1) Remote counter 'vnet'
 * 2) Local counter
 */
export async function buildVNetName(tags) {
  try {
    const counter = await getNextCounterRemote("vnet", tags);
    const name = stellantis("vnet", tags, counter);
    return markAndEnsureUnique("vnet", tags, name, () => stellantis("vnet", tags, counter + 1));
  } catch {
    const counter = nextLocalCounter("vnet", tags);
    const name = stellantis("vnet", tags, counter);
    return markAndEnsureUnique("vnet", tags, name, () => {
      const c2 = nextLocalCounter("vnet", tags);
      return stellantis("vnet", tags, c2);
    });
  }
}

export async function buildKeyVaultName(tags) {
  // Remote first
  try {
    const counter = await getNextCounterRemote("kv", tags);
    let name = kvCandidate(tags, counter);
    if (!kvNameValid(name)) {
      // Try single bump if rules cause overflow/truncation issues
      name = kvCandidate(tags, counter + 1);
    }
    return markAndEnsureUnique("kv", tags, name, () => kvCandidate(tags, counter + 1));
  } catch {
    // Local
    const counter = nextLocalCounter("kv", tags);
    let name = kvCandidate(tags, counter);
    if (!kvNameValid(name)) {
      const c2 = nextLocalCounter("kv", tags);
      name = kvCandidate(tags, c2);
    }
    return markAndEnsureUnique("kv", tags, name, () => {
      const c3 = nextLocalCounter("kv", tags);
      return kvCandidate(tags, c3);
    });
  }
}

/* Region helper (unchanged) */
export function normalizeRegion(region) {
  return (region || "").toLowerCase().replace(/\s+/g, "");
}