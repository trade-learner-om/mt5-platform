import { api } from "../api";

export function analyzeUnmitigatedSwings(token, payload) {
  return api("/structure/unmitigated-swings", "POST", payload, token);
}

export function executeUnmitigatedSwings(token, payload) {
  return api("/structure/unmitigated-swings/execute", "POST", payload, token);
}

export function getUnmitigatedSwingsSession(token, sessionId) {
  return api(`/structure/unmitigated-swings/session/${encodeURIComponent(sessionId)}`, "GET", null, token);
}
