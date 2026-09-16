import { useEffect, useState } from "react";

import { API_BASE } from "../../api";

export default function AddInternationalAccountModal({ open, onClose, onSubmit, embedded = false, token = "" }) {
  const [form, setForm] = useState({ account_name: "", account_id: "", api_token: "", mt5_server: "", mt5_terminal_path: "", risk_amount: "100" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [terminalOptions, setTerminalOptions] = useState([]);
  const [loadingTerminals, setLoadingTerminals] = useState(false);
  const [browsingTerminal, setBrowsingTerminal] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({ account_name: "", account_id: "", api_token: "", mt5_server: "", mt5_terminal_path: "", risk_amount: "100" });
    setError("");
    setSaving(false);
    setTerminalOptions([]);
    setLoadingTerminals(false);
    setBrowsingTerminal(false);
  }, [open]);

  if (!open) return null;

  const submit = async () => {
    if (!form.account_name.trim() || !form.account_id.trim() || !form.api_token.trim() || !form.mt5_server.trim() || !form.mt5_terminal_path.trim() || Number(form.risk_amount) <= 0) {
      setError("Fill all fields with a valid risk amount.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSubmit({
        market_type: "INTERNATIONAL",
        broker_type: "MT5",
        account_name: form.account_name.trim(),
        account_id: form.account_id.trim(),
        api_token: form.api_token.trim(),
        credentials: {
          mt5_login: form.account_id.trim(),
          mt5_password: form.api_token.trim(),
          mt5_server: form.mt5_server.trim(),
          mt5_terminal_path: form.mt5_terminal_path.trim(),
        },
        risk_amount: Number(form.risk_amount),
      });
      setSaving(false);
    } catch (err) {
      setError(err.message || "Unable to add international account.");
      setSaving(false);
    }
  };

  const browseTerminalFile = async () => {
    setBrowsingTerminal(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/mt5/browse-terminal`, {
        method: "POST",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail || payload?.message || "Unable to browse MT5 terminal.");
      }
      if (payload.path) {
        setForm((current) => ({ ...current, mt5_terminal_path: payload.path }));
      }
    } catch (err) {
      setError(err.message || "Unable to browse MT5 terminal.");
    } finally {
      setBrowsingTerminal(false);
    }
  };

  const detectRunningTerminals = async () => {
    setLoadingTerminals(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/mt5/terminals`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail || payload?.message || "Unable to detect MT5 terminals.");
      }
      const options = Array.from(new Set((payload.unique_paths || []).filter(Boolean)));
      setTerminalOptions(options);
      if (options.length === 1) {
        setForm((current) => ({ ...current, mt5_terminal_path: options[0] }));
      }
      if (!options.length) {
        setError("No running MT5 terminals found. Start the MT5 instance for this account, then click Detect running.");
      } else if (payload.requires_unique_install_paths) {
        setError("Some MT5 windows are running from the same terminal64.exe path. Use separate MT5 folders per account before adding them.");
      }
    } catch (err) {
      setError(err.message || "Unable to detect MT5 terminals.");
    } finally {
      setLoadingTerminals(false);
    }
  };

  const content = (
      <div className={`${embedded ? "" : "w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"}`}>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Add Local MT5 Account</h3>
            <p className="mt-1 text-sm text-slate-600">Detect the MT5 terminal path on the machine running the backend. Do not reuse the same terminal64.exe for multiple accounts.</p>
          </div>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-sm font-semibold text-slate-500 hover:bg-slate-100">Close</button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Market</span>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-medium text-slate-800">International Market</div>
          </div>
          <div className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Broker</span>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-medium text-slate-800">Local MT5</div>
          </div>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Account Label</span>
            <input className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.account_name} onChange={(e) => setForm((c) => ({ ...c, account_name: e.target.value }))} placeholder="Primary MT5" />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">MT5 Account Number</span>
            <input className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.account_id} onChange={(e) => setForm((c) => ({ ...c, account_id: e.target.value }))} placeholder="28205674" />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">MT5 Server</span>
            <input className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.mt5_server} onChange={(e) => setForm((c) => ({ ...c, mt5_server: e.target.value }))} placeholder="VantageMarkets-Live" />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">MT5 Password</span>
            <input type="password" className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.api_token} onChange={(e) => setForm((c) => ({ ...c, api_token: e.target.value }))} placeholder="MT5 password" />
          </label>
          <label className="space-y-1 text-sm sm:col-span-2">
            <span className="font-medium text-slate-600">MT5 Terminal Path</span>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input className="min-w-0 flex-1 rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.mt5_terminal_path} onChange={(e) => setForm((c) => ({ ...c, mt5_terminal_path: e.target.value }))} placeholder="Path to this account's MT5 terminal executable" />
              <button type="button" onClick={browseTerminalFile} disabled={browsingTerminal || loadingTerminals} className="rounded-xl border border-indigo-200 px-3 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:text-slate-400">
                {browsingTerminal ? "Browsing..." : "Browse"}
              </button>
              <button type="button" onClick={detectRunningTerminals} disabled={loadingTerminals || browsingTerminal} className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400">
                {loadingTerminals ? "Detecting..." : "Detect running"}
              </button>
            </div>
            {terminalOptions.length ? (
              <select
                value={form.mt5_terminal_path}
                onChange={(e) => setForm((c) => ({ ...c, mt5_terminal_path: e.target.value }))}
                className="mt-2 w-full rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm outline-none focus:border-indigo-500"
              >
                <option value="">Select a running MT5 terminal...</option>
                {terminalOptions.map((path) => (
                  <option key={path} value={path}>{path}</option>
                ))}
              </select>
            ) : null}
            <span className="block text-xs text-slate-500">Use Detect running after starting the MT5 instance for this account on the backend machine. If the backend moves to another machine, re-detect and save the terminal path there.</span>
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Risk Amount</span>
            <input type="number" min="1" className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.risk_amount} onChange={(e) => setForm((c) => ({ ...c, risk_amount: e.target.value }))} />
          </label>
        </div>
        {error ? <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div> : null}
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700">Cancel</button>
          <button onClick={submit} disabled={saving} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400">{saving ? "Saving..." : "Save Account"}</button>
        </div>
      </div>
  );

  if (embedded) {
    return content;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
      {content}
    </div>
  );
}
