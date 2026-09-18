import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";

const TIMEFRAMES = ["M1", "M5", "M15"];

const CANCELLABLE = new Set([
  "INITIATED",
  "ARMED",
  "ORDER_PLACED",
  "RETRY_INITIATED",
  "RETRY_ARMED",
  "RETRY_ORDER_PLACED",
]);

function isGoldSymbol(symbol) {
  const letters = String(symbol || "").toUpperCase().replace(/[^A-Z]/g, "");
  return letters.includes("XAU") || letters.includes("GOLD");
}

function defaultMaxSignalCandlePips(symbol) {
  return isGoldSymbol(symbol) ? 100 : 10;
}

function midFromTick(tick) {
  if (!tick) return null;
  const bid = Number(tick.bid);
  const ask = Number(tick.ask);
  if (Number.isFinite(bid) && bid > 0 && Number.isFinite(ask) && ask > 0) {
    return (bid + ask) / 2;
  }
  const price = Number(tick.price);
  if (Number.isFinite(price) && price > 0) return price;
  if (Number.isFinite(bid) && bid > 0) return bid;
  if (Number.isFinite(ask) && ask > 0) return ask;
  return null;
}

function ltpForSymbol(symbol, livePrices = {}) {
  const key = String(symbol || "").trim().toUpperCase();
  if (!key) return null;
  const direct = livePrices[key] || livePrices[symbol];
  if (direct) return midFromTick(direct);
  const matchKey = Object.keys(livePrices || {}).find((candidate) => {
    const upper = candidate.toUpperCase();
    return upper === key || upper.includes(key) || key.includes(upper);
  });
  return matchKey ? midFromTick(livePrices[matchKey]) : null;
}

function deriveSide(level, mid) {
  const levelN = Number(level);
  const midN = Number(mid);
  if (!Number.isFinite(levelN) || !Number.isFinite(midN) || midN <= 0) return null;
  if (Math.abs(levelN - midN) < 1e-12) return null;
  return levelN > midN ? "SELL" : "BUY";
}

function statusTone(status) {
  const value = String(status || "").toUpperCase();
  if (value.includes("EXIT") || value.includes("CANCELLED")) {
    return "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200";
  }
  if (value.includes("FILLED") || value === "ARMED" || value === "RETRY_ARMED") {
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300";
  }
  if (value.includes("PLACED") || value.includes("INITIATED")) {
    return "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300";
  }
  return "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-300";
}

function formatPrice(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toFixed(Math.abs(number) >= 100 ? 2 : 5);
}

export default function ScheduledTradePanel({
  token,
  accounts = [],
  activeAccountId = "",
  livePrices = {},
  liveScheduledTrades = null,
  subscribeLiveSymbol,
  onNotify,
}) {
  const activeAccount = useMemo(
    () => (accounts || []).find((account) => account.id === activeAccountId) || accounts[0] || null,
    [accounts, activeAccountId],
  );

  const [form, setForm] = useState({
    symbol: "XAUUSD",
    level: "",
    timeframe: "M5",
    risk_amount: "",
    target: "",
    max_signal_candle_pips: "100",
    retryable_order: false,
  });
  const [maxPipsTouched, setMaxPipsTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [cancellingId, setCancellingId] = useState("");
  const [error, setError] = useState("");
  const [schedules, setSchedules] = useState([]);
  const [loadingList, setLoadingList] = useState(false);

  useEffect(() => {
    const risk = activeAccount?.risk_amount;
    if (risk === undefined || risk === null) return;
    setForm((current) => ({
      ...current,
      risk_amount: current.risk_amount === "" ? String(risk) : current.risk_amount,
    }));
  }, [activeAccount?.id, activeAccount?.risk_amount]);

  useEffect(() => {
    if (maxPipsTouched) return;
    setForm((current) => ({
      ...current,
      max_signal_candle_pips: String(defaultMaxSignalCandlePips(current.symbol)),
    }));
  }, [form.symbol, maxPipsTouched]);

  useEffect(() => {
    if (Array.isArray(liveScheduledTrades)) {
      setSchedules(liveScheduledTrades);
    }
  }, [liveScheduledTrades]);

  useEffect(() => {
    if (!token || Array.isArray(liveScheduledTrades)) return undefined;
    let cancelled = false;
    const load = async () => {
      setLoadingList(true);
      try {
        const rows = await api("/scheduled-trades", "GET", null, token);
        if (!cancelled) setSchedules(Array.isArray(rows) ? rows : []);
      } catch (err) {
        if (!cancelled) setError(err.message || "Could not load scheduled trades");
      } finally {
        if (!cancelled) setLoadingList(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [token, liveScheduledTrades]);

  useEffect(() => {
    if (!subscribeLiveSymbol) return undefined;
    const symbols = [];
    const formSymbol = String(form.symbol || "").trim().toUpperCase();
    if (formSymbol) symbols.push(formSymbol);
    for (const row of schedules) {
      const symbol = String(row?.symbol || "").trim().toUpperCase();
      if (symbol && !symbols.includes(symbol)) symbols.push(symbol);
    }
    if (symbols.length === 0) {
      subscribeLiveSymbol("", "scheduled-trade");
      return () => subscribeLiveSymbol("", "scheduled-trade");
    }
    symbols.forEach((symbol, index) => {
      subscribeLiveSymbol(symbol, `scheduled-trade-${index}`);
    });
    return () => {
      symbols.forEach((_, index) => subscribeLiveSymbol("", `scheduled-trade-${index}`));
    };
  }, [form.symbol, schedules, subscribeLiveSymbol]);

  const liveMid = useMemo(() => ltpForSymbol(form.symbol, livePrices), [form.symbol, livePrices]);

  const derivedSide = deriveSide(form.level, liveMid);
  const defaultMaxPips = defaultMaxSignalCandlePips(form.symbol);

  const onSubmit = async (event) => {
    event.preventDefault();
    setError("");
    if (!token) {
      setError("Sign in required");
      return;
    }
    const level = Number(form.level);
    const risk = Number(form.risk_amount);
    const maxPips = Number(form.max_signal_candle_pips);
    if (!String(form.symbol || "").trim()) {
      setError("Symbol is required");
      return;
    }
    if (!Number.isFinite(level)) {
      setError("Level must be a number");
      return;
    }
    if (!Number.isFinite(risk) || risk <= 0) {
      setError("Risk amount must be positive");
      return;
    }
    if (!Number.isFinite(maxPips) || maxPips <= 0) {
      setError("Max signal candle pips must be positive");
      return;
    }
    if (liveMid != null && Math.abs(level - liveMid) < 1e-12) {
      setError("Level cannot equal the live mid price");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        symbol: String(form.symbol).trim().toUpperCase(),
        level,
        timeframe: form.timeframe,
        risk_amount: risk,
        max_signal_candle_pips: maxPips,
        retryable_order: Boolean(form.retryable_order),
      };
      if (form.target !== "" && form.target != null) {
        payload.target = Number(form.target);
      }
      const created = await api("/scheduled-trades", "POST", payload, token);
      setSchedules((current) => [created, ...(current || []).filter((row) => row.id !== created.id)]);
      setMaxPipsTouched(false);
      setForm((current) => ({
        ...current,
        level: "",
        target: "",
        max_signal_candle_pips: String(defaultMaxSignalCandlePips(current.symbol)),
        retryable_order: false,
      }));
      onNotify?.({ type: "success", message: `Scheduled ${created.side} ${created.symbol} on ${created.timeframe}` });
    } catch (err) {
      setError(err.message || "Could not create scheduled trade");
    } finally {
      setSubmitting(false);
    }
  };

  const onCancel = async (scheduleId) => {
    setError("");
    setCancellingId(scheduleId);
    try {
      const updated = await api(`/scheduled-trades/${scheduleId}/cancel`, "POST", null, token);
      setSchedules((current) => (current || []).map((row) => (row.id === updated.id ? updated : row)));
      onNotify?.({ type: "success", message: `Cancelled schedule ${scheduleId.slice(-6)}` });
    } catch (err) {
      setError(err.message || "Could not cancel schedule");
    } finally {
      setCancellingId("");
    }
  };

  return (
    <div className="space-y-4">
      <form onSubmit={onSubmit} className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Create Scheduled Trade</h4>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Break level on {activeAccount?.account_name || "selected account"} · direction from live mid
            </p>
          </div>
          <div className="text-right text-xs text-slate-500 dark:text-slate-400">
            <div>Live mid: {liveMid != null ? formatPrice(liveMid) : "—"}</div>
            <div>
              Direction:{" "}
              <span className={derivedSide === "SELL" ? "font-semibold text-rose-600" : derivedSide === "BUY" ? "font-semibold text-emerald-600" : ""}>
                {derivedSide || "—"}
              </span>
            </div>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-xs font-semibold text-slate-500">
            Symbol
            <input
              value={form.symbol}
              onChange={(event) => {
                setMaxPipsTouched(false);
                setForm((current) => ({ ...current, symbol: event.target.value.toUpperCase() }));
              }}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </label>
          <label className="text-xs font-semibold text-slate-500">
            Level
            <input
              value={form.level}
              onChange={(event) => setForm((current) => ({ ...current, level: event.target.value }))}
              inputMode="decimal"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </label>
          <label className="text-xs font-semibold text-slate-500">
            Timeframe
            <select
              value={form.timeframe}
              onChange={(event) => setForm((current) => ({ ...current, timeframe: event.target.value }))}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-semibold text-slate-500">
            Risk amount
            <input
              value={form.risk_amount}
              onChange={(event) => setForm((current) => ({ ...current, risk_amount: event.target.value }))}
              inputMode="decimal"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </label>
          <label className="text-xs font-semibold text-slate-500">
            Target (optional, ≥4R)
            <input
              value={form.target}
              onChange={(event) => setForm((current) => ({ ...current, target: event.target.value }))}
              inputMode="decimal"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </label>
          <label className="text-xs font-semibold text-slate-500">
            Max signal candle (pips)
            <input
              value={form.max_signal_candle_pips}
              onChange={(event) => {
                setMaxPipsTouched(true);
                setForm((current) => ({ ...current, max_signal_candle_pips: event.target.value }));
              }}
              inputMode="decimal"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
            <span className="mt-1 block font-normal text-[11px] text-slate-500 dark:text-slate-400">
              Skip signal candles wider than this (default {defaultMaxPips} for {isGoldSymbol(form.symbol) ? "XAU/GOLD" : "FX"}).
            </span>
          </label>
          <label className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
            <input
              type="checkbox"
              checked={Boolean(form.retryable_order)}
              onChange={(event) => setForm((current) => ({ ...current, retryable_order: event.target.checked }))}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span>
              Retryable order
              <span className="mt-0.5 block font-normal text-slate-500 dark:text-slate-400">Off by default · one SL re-place after stop-out</span>
            </span>
          </label>
        </div>
        {error ? (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">
            {error}
          </div>
        ) : null}
        <div className="mt-3 flex justify-end">
          <button
            type="submit"
            disabled={submitting || !activeAccount}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400 dark:bg-slate-100 dark:text-slate-950"
          >
            {submitting ? "Scheduling…" : "Schedule break trade"}
          </button>
        </div>
      </form>

      <div className="rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Lifecycle</h4>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
            {schedules.length}
          </span>
        </div>
        {loadingList ? (
          <div className="px-4 py-8 text-center text-sm text-slate-500">Loading schedules…</div>
        ) : schedules.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-slate-500">No scheduled trades yet.</div>
        ) : (
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">LTP</th>
                  <th className="px-3 py-2">Side</th>
                  <th className="px-3 py-2">TF</th>
                  <th className="px-3 py-2">Level</th>
                  <th className="px-3 py-2">Max pips</th>
                  <th className="px-3 py-2">Entry / SL</th>
                  <th className="px-3 py-2">Notes</th>
                  <th className="px-3 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map((row) => {
                  const ltp = ltpForSymbol(row.symbol, livePrices);
                  return (
                  <tr key={row.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${statusTone(row.status)}`}>
                        {row.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-semibold">{row.symbol}</td>
                    <td className="px-3 py-2 font-semibold tabular-nums text-slate-800 dark:text-slate-100">
                      {ltp != null ? formatPrice(ltp) : "—"}
                    </td>
                    <td className={`px-3 py-2 font-semibold ${row.side === "SELL" ? "text-rose-600" : "text-emerald-600"}`}>{row.side}</td>
                    <td className="px-3 py-2">{row.timeframe}</td>
                    <td className="px-3 py-2">{formatPrice(row.level)}</td>
                    <td className="px-3 py-2">{row.max_signal_candle_pips ?? "—"}</td>
                    <td className="px-3 py-2">
                      {row.entry != null ? `${formatPrice(row.entry)} / ${formatPrice(row.stop_loss)}` : "—"}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {row.placement_order_type === "LIMIT" || row.placement_fallback_reason
                        ? "LIMIT fallback"
                        : row.retryable_order
                          ? row.retry_used
                            ? "Retry used"
                            : "Retryable"
                          : row.last_error || "—"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {CANCELLABLE.has(String(row.status || "").toUpperCase()) ? (
                        <button
                          type="button"
                          disabled={cancellingId === row.id}
                          onClick={() => onCancel(row.id)}
                          className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                        >
                          {cancellingId === row.id ? "…" : "Cancel"}
                        </button>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
