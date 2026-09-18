function envFlagEnabled(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}

/** Restorable production API (also used by `.env.production` builds). */
export const PRODUCTION_API_BASE = "https://api.signalbridge.in";

/** Default local backend when UI is opened on localhost / LAN. */
export const LOCAL_API_BASE = "http://localhost:8000";

const PRODUCTION_APP_HOSTS = new Set([
  "signalbridge.in",
  "www.signalbridge.in",
  "app.signalbridge.in",
]);

function useProductionApi() {
  // Restore production from a local UI session:
  //   VITE_USE_PRODUCTION_API=true
  // Production builds still load https://api.signalbridge.in from `.env.production`.
  return envFlagEnabled(import.meta.env.VITE_USE_PRODUCTION_API);
}

function defaultApiBase() {
  if (useProductionApi()) return PRODUCTION_API_BASE;
  return LOCAL_API_BASE;
}

function isLocalDevHost(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

function isPrivateLanHost(hostname) {
  if (!hostname) return false;
  return (
    /^10\./.test(hostname) ||
    /^192\.168\./.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(hostname)
  );
}

function isProductionApiHost(hostname) {
  return hostname === "api.signalbridge.in" || PRODUCTION_APP_HOSTS.has(hostname);
}

function localApiBaseForBrowser(hostname) {
  const host = hostname || "localhost";
  return `http://${host}:8000`;
}

function resolveBrowserBase(value) {
  const configured = (value || defaultApiBase()).replace(/\/$/, "");
  if (typeof window === "undefined") return configured;

  const browserHost = window.location.hostname;
  if (PRODUCTION_APP_HOSTS.has(browserHost)) {
    return PRODUCTION_API_BASE;
  }

  if (isLocalDevHost(browserHost) || isPrivateLanHost(browserHost)) {
    if (useProductionApi()) {
      return PRODUCTION_API_BASE;
    }

    try {
      const url = new URL(configured);
      // Local UI must talk to the local backend unless production is explicitly opted in.
      if (isProductionApiHost(url.hostname)) {
        return localApiBaseForBrowser(browserHost);
      }
      if (isLocalDevHost(url.hostname) || isPrivateLanHost(url.hostname)) {
        url.hostname = browserHost;
        if (!url.port) url.port = "8000";
        return url.toString().replace(/\/$/, "");
      }
      return configured;
    } catch {
      return localApiBaseForBrowser(browserHost);
    }
  }

  if (window.location.protocol === "https:") {
    try {
      const url = new URL(configured);
      if (url.protocol === "http:") {
        return PRODUCTION_API_BASE;
      }
    } catch {
      return PRODUCTION_API_BASE;
    }
  }

  return configured;
}

export const API_BASE = resolveBrowserBase(import.meta.env.VITE_API_BASE || import.meta.env.VITE_API_BASE_URL);
export const WS_LIVE_HEARTBEAT_MS = 20000;
export const WS_LIVE_STALE_MS = 45000;

export async function pingBackendHealth(timeoutMs = 20000) {
  const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const res = await fetch(`${API_BASE}/health`, {
      method: "GET",
      cache: "no-store",
      signal: controller?.signal,
      headers: { Accept: "application/json,text/plain,*/*" }
    });
    return {
      ok: res.ok,
      status: res.status,
      error: res.ok ? "" : `Backend health returned HTTP ${res.status}.`
    };
  } catch (error) {
    const message = error?.name === "AbortError" ? "Backend health check timed out." : (error?.message || "Could not reach backend.");
    return { ok: false, status: null, error: message };
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

function liveTickTimeMs(tick) {
  const candidates = [tick?.time, tick?.updated_at, tick?.last_tick_at, tick?.price_time];
  for (const value of candidates) {
    const parsed = Date.parse(value || "");
    if (!Number.isNaN(parsed)) return parsed;
  }
  return NaN;
}

export function liveSnapshotHasFreshPrices(payload, staleMs = WS_LIVE_STALE_MS) {
  if (!payload || typeof payload !== "object") return false;
  const now = Date.now();
  const prices = payload.prices || {};
  for (const tick of Object.values(prices)) {
    const time = liveTickTimeMs(tick);
    if (!Number.isNaN(time) && now - time < staleMs) return true;
  }
  for (const item of payload.watchlist || []) {
    const time = liveTickTimeMs(item);
    if (!Number.isNaN(time) && now - time < staleMs) return true;
  }
  return false;
}

function formatApiErrorDetail(detail) {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const location = Array.isArray(item.loc) ? item.loc.join(" > ") : "";
          const message = item.msg || item.message || JSON.stringify(item);
          return location ? `${location}: ${message}` : message;
        }
        return String(item);
      })
      .join("; ");
  }
  if (typeof detail === "object") {
    return detail.message || detail.error || JSON.stringify(detail);
  }
  return String(detail);
}

function socketBaseUrl() {
  if (import.meta.env.VITE_WS_BASE) {
    return resolveBrowserBase(import.meta.env.VITE_WS_BASE).replace(/^http/, "ws");
  }
  return API_BASE.replace(/^http/, "ws");
}

export async function api(path, method = "GET", body, token) {
  const headers = {
    ...(body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(formatApiErrorDetail(data.detail || data));
  }
  return res.json();
}

function isLiveSocketControlPayload(payload) {
  const type = String(payload?.type || "").toLowerCase();
  return type === "ping" || type === "pong";
}

export function openLiveSocket(token, onMessage, callbacks = {}) {
  const ws = new WebSocket(`${socketBaseUrl()}/ws/live?token=${token}`);
  let heartbeatTimer = null;

  const stopHeartbeat = () => {
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  };

  const startHeartbeat = () => {
    stopHeartbeat();
    heartbeatTimer = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, WS_LIVE_HEARTBEAT_MS);
  };

  ws.addEventListener("message", (ev) => {
    let payload;
    try {
      payload = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (payload?.type === "ping") {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "pong" }));
      }
      return;
    }
    if (isLiveSocketControlPayload(payload)) return;
    onMessage(payload);
  });

  ws.addEventListener("open", () => {
    ws.send("ready");
    startHeartbeat();
    callbacks.onOpen?.();
  });

  ws.addEventListener("close", (event) => {
    stopHeartbeat();
    callbacks.onClose?.(event);
  });

  ws.addEventListener("error", (event) => {
    callbacks.onError?.(event);
  });

  ws.stopHeartbeat = stopHeartbeat;
  ws.sendPing = () => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  };

  return ws;
}
