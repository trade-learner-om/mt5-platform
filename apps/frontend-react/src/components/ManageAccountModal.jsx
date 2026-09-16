import { useEffect, useMemo, useState } from "react";
import { API_BASE, api } from "../api";
import AddIndianAccountModal from "./indian/AddIndianAccountModal";
import AddInternationalAccountModal from "./international/AddInternationalAccountModal";

function normalizeMarket(value) {
  const normalized = String(value || "INTERNATIONAL").toUpperCase();
  if (normalized === "INDIAN") return "INDIAN";
  return "INTERNATIONAL";
}

function marketLabel(value) {
  const normalized = normalizeMarket(value);
  if (normalized === "INDIAN") return "Indian Market";
  return "International Market";
}

function brokerLabel(account) {
  const broker = String(account?.broker_type || "").toUpperCase();
  if (broker === "MSTOCK") return "Mstock";
  if (broker === "METAAPI" || broker === "MT5") return "Local MT5";
  return broker || "Broker";
}

function backendWsBaseUrl() {
  return API_BASE.replace(/^http/, "ws");
}

function mt5TickBridgeUrl(account) {
  if (!account?.mt5_tick_ingest_secret) return "";
  const params = new URLSearchParams({
    secret: account.mt5_tick_ingest_secret,
    account_id: account.account_id || account.id,
  });
  return `${backendWsBaseUrl()}/ws/mt5/ticks?${params.toString()}`;
}

function AccountSymbolAliases({ account, token, onUpdated }) {
  const [editing, setEditing] = useState(false);
  const [goldAlias, setGoldAlias] = useState(account?.symbol_aliases?.GOLD || "");
  const [suggestions, setSuggestions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setGoldAlias(account?.symbol_aliases?.GOLD || "");
    setEditing(false);
    setError("");
  }, [account?.id, account?.symbol_aliases?.GOLD]);

  useEffect(() => {
    if (!editing || !token || goldAlias.trim().length < 1) {
      setSuggestions([]);
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      try {
        const data = await api(`/instruments/suggest?q=${encodeURIComponent(goldAlias)}&limit=8`, "GET", undefined, token);
        setSuggestions(data.symbols || []);
      } catch {
        setSuggestions([]);
      }
    }, 180);
    return () => window.clearTimeout(timer);
  }, [editing, goldAlias, token]);

  async function saveAliases() {
    setSaving(true);
    setError("");
    try {
      const payload = goldAlias.trim() ? { GOLD: goldAlias.trim().toUpperCase() } : {};
      const updated = await api(`/accounts/${account.id}/symbol-aliases`, "PATCH", { aliases: payload }, token);
      onUpdated?.(updated);
      setEditing(false);
    } catch (err) {
      setError(err.message || "Could not save symbol aliases.");
    } finally {
      setSaving(false);
    }
  }

  const currentGold = account?.symbol_aliases?.GOLD || "Auto-detected";

  return (
    <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Symbol Aliases</p>
          <p className="text-xs text-slate-700">GOLD → {currentGold}</p>
        </div>
        <button
          type="button"
          onClick={() => setEditing((current) => !current)}
          className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700"
        >
          {editing ? "Cancel" : "Edit"}
        </button>
      </div>
      {editing ? (
        <div className="mt-2 space-y-2">
          <input
            value={goldAlias}
            onChange={(event) => setGoldAlias(event.target.value.toUpperCase())}
            className="w-full rounded-lg border border-slate-300 px-2 py-1 text-xs outline-none focus:border-indigo-500"
            placeholder="Broker GOLD symbol, e.g. XAUUSD+"
          />
          {suggestions.length ? (
            <div className="flex flex-wrap gap-1">
              {suggestions.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setGoldAlias(String(item).toUpperCase())}
                  className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-indigo-700 ring-1 ring-indigo-100"
                >
                  {item}
                </button>
              ))}
            </div>
          ) : null}
          {error ? <p className="text-xs text-rose-600">{error}</p> : null}
          <button
            type="button"
            disabled={saving}
            onClick={saveAliases}
            className="rounded-lg bg-indigo-600 px-3 py-1 text-[11px] font-semibold text-white disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save GOLD Alias"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function ManageAccountModal({
  open,
  token,
  accounts = [],
  selectedMarket = "INTERNATIONAL",
  selectedAccountId = "",
  switchingAccount = false,
  onClose,
  onSubmitAdd,
  onDeleteAccount,
  onSelectAccount,
  onAccountUpdated,
}) {
  const [view, setView] = useState("accounts");
  const [addMarket, setAddMarket] = useState(normalizeMarket(selectedMarket));
  const [deletingId, setDeletingId] = useState("");
  const [localAccounts, setLocalAccounts] = useState(accounts);

  useEffect(() => {
    setLocalAccounts(accounts);
  }, [accounts]);

  useEffect(() => {
    if (!open) return;
    setView("accounts");
    setAddMarket(normalizeMarket(selectedMarket));
    setDeletingId("");
  }, [open, selectedMarket]);

  const groupedAccounts = useMemo(() => {
    const groups = { INTERNATIONAL: [], INDIAN: [] };
    localAccounts.forEach((account) => {
      groups[normalizeMarket(account.market_type)].push(account);
    });
    return groups;
  }, [localAccounts]);

  const handleAccountUpdated = (updated) => {
    if (!updated?.id) return;
    setLocalAccounts((current) => current.map((account) => (account.id === updated.id ? { ...account, ...updated } : account)));
    onAccountUpdated?.(updated);
  };

  if (!open) return null;

  const submitAdd = async (payload) => {
    await onSubmitAdd(payload);
    setView("accounts");
    setAddMarket(normalizeMarket(payload.market_type));
  };

  const deleteAccount = async (account) => {
    const confirmed = window.confirm(`Delete ${account.account_name}? This removes the broker account from SignalBridge.`);
    if (!confirmed) return;
    setDeletingId(account.id);
    try {
      await onDeleteAccount(account.id);
    } finally {
      setDeletingId("");
    }
  };

  const renderAccounts = (market) => {
    const marketAccounts = groupedAccounts[market] || [];
    if (!marketAccounts.length) {
      return (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-500">
          No {marketLabel(market).toLowerCase()} accounts yet.
        </div>
      );
    }

    return (
      <div className="space-y-2">
        {marketAccounts.map((account) => {
          const isSelected = account.id === selectedAccountId;
          const bridgeUrl = normalizeMarket(account.market_type) === "INTERNATIONAL" ? mt5TickBridgeUrl(account) : "";
          return (
            <div key={account.id} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-bold text-slate-900">{account.account_name}</p>
                    {isSelected ? (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                        Active
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {brokerLabel(account)} · {account.account_id || account.broker_user_id || "No broker ID"} · Risk {account.risk_amount}
                  </p>
                  {bridgeUrl ? (
                    <div className="mt-2 rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700">MT5 EA Tick URL</p>
                      <div className="mt-1 flex gap-2">
                        <code className="min-w-0 flex-1 truncate rounded-lg bg-white px-2 py-1 text-[11px] text-slate-700" title={bridgeUrl}>
                          {bridgeUrl}
                        </code>
                        <button
                          type="button"
                          onClick={() => navigator.clipboard?.writeText(bridgeUrl)}
                          className="rounded-lg bg-indigo-600 px-2 py-1 text-[11px] font-semibold text-white"
                        >
                          Copy
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {normalizeMarket(account.market_type) === "INTERNATIONAL" ? (
                    <AccountSymbolAliases account={account} token={token} onUpdated={handleAccountUpdated} />
                  ) : null}
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={isSelected || switchingAccount}
                    onClick={() => onSelectAccount(account.id)}
                    className="rounded-xl border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
                  >
                    {isSelected ? "Selected" : "Set Active"}
                  </button>
                  <button
                    type="button"
                    disabled={deletingId === account.id}
                    onClick={() => deleteAccount(account)}
                    className="rounded-xl border border-rose-200 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:text-rose-300"
                  >
                    {deletingId === account.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
      <div className="max-h-[92vh] w-full max-w-3xl overflow-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">Accounts</p>
            <h3 className="mt-1 text-xl font-bold text-slate-900">Manage Accounts</h3>
            <p className="mt-1 text-sm text-slate-600">Add broker accounts or remove accounts you no longer use.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-1 text-sm font-semibold text-slate-500 hover:bg-slate-100">
            Close
          </button>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setView("accounts")}
            className={`rounded-xl px-3 py-2 text-sm font-semibold ${view === "accounts" ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-700"}`}
          >
            Existing Accounts
          </button>
          <button
            type="button"
            onClick={() => {
              setAddMarket(normalizeMarket(selectedMarket));
              setView("add");
            }}
            className={`rounded-xl px-3 py-2 text-sm font-semibold ${view === "add" ? "bg-indigo-600 text-white" : "border border-indigo-200 text-indigo-700"}`}
          >
            Add New Account
          </button>
        </div>

        {view === "accounts" ? (
          <div className="space-y-5">
            <section>
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-sm font-bold text-slate-900">International Market</h4>
                <button type="button" onClick={() => { setAddMarket("INTERNATIONAL"); setView("add"); }} className="text-xs font-semibold text-indigo-700">
                  Add International
                </button>
              </div>
              {renderAccounts("INTERNATIONAL")}
            </section>
            <section>
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-sm font-bold text-slate-900">Indian Market</h4>
                <button type="button" onClick={() => { setAddMarket("INDIAN"); setView("add"); }} className="text-xs font-semibold text-indigo-700">
                  Add Indian
                </button>
              </div>
              {renderAccounts("INDIAN")}
            </section>
          </div>
        ) : (
          <div>
            <div className="mb-4 flex flex-wrap gap-2 rounded-2xl bg-slate-50 p-2">
              {["INTERNATIONAL", "INDIAN"].map((market) => (
                <button
                  key={market}
                  type="button"
                  onClick={() => setAddMarket(market)}
                  className={`rounded-xl px-3 py-2 text-sm font-semibold ${addMarket === market ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}
                >
                  {marketLabel(market)}
                </button>
              ))}
            </div>
            {addMarket === "INDIAN" ? (
              <AddIndianAccountModal open embedded onClose={() => setView("accounts")} onSubmit={submitAdd} />
            ) : (
              <AddInternationalAccountModal open embedded token={token} onClose={() => setView("accounts")} onSubmit={submitAdd} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
