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

export function getActiveUnmitigatedSwingsSession(token, accountId) {
  return api(
    `/structure/unmitigated-swings/active?account_id=${encodeURIComponent(accountId)}`,
    "GET",
    null,
    token,
  );
}

export function listUnmitigatedSwingsSessions(token, accountId, limit = 20) {
  const params = new URLSearchParams();
  if (accountId) params.set("account_id", accountId);
  params.set("limit", String(limit));
  return api(`/structure/unmitigated-swings/sessions?${params.toString()}`, "GET", null, token);
}
