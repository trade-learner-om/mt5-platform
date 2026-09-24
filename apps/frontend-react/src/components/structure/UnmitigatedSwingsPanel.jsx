import { useEffect, useMemo, useState } from "react";
import {
  analyzeUnmitigatedSwings,
  executeUnmitigatedSwings,
  getUnmitigatedSwingsSession,
} from "../../services/structureSwings";

const TIMEFRAMES = ["H4", "H1", "M15"];

function formatPrice(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toFixed(Math.abs(number) >= 100 ? 2 : 5);
}

function formatTime(value) {
  if (!value) return "—";
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  } catch {
    return String(value);
  }
}

function levelStatusTone(status) {
  if (String(status || "") === "Mitigated") {
    return "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  }
  return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300";
}

function tradeStatusTone(status) {
  const value = String(status || "").toUpperCase();
  if (!value) return "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  if (value.includes("EXIT") || value.includes("CANCELLED")) {
    return "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200";
  }
  if (value.includes("FILLED") || value === "ARMED") {
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300";
  }
  if (value.includes("PLACED") || value.includes("INITIATED")) {
    return "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300";
  }
  return "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-300";
}

function LevelColumn({ title, rows, tone }) {
  const headerTone =
    tone === "high"
      ? "text-rose-600 dark:text-rose-400"
      : "text-emerald-600 dark:text-emerald-400";
  return (
    <div className="rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <p className={`text-xs font-semibold uppercase tracking-[0.18em] ${headerTone}`}>
          {title} · {rows.length}
        </p>
      </div>
      <div className="divide-y divide-slate-100 dark:divide-slate-900">
        {rows.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs text-slate-500">No levels</p>
        ) : (
          rows.map((row) => {
            const mitigated = String(row.status || "Active") === "Mitigated";
            return (
              <div
                key={`${row.kind || title}-${row.price}-${row.schedule_id || row.time || ""}`}
                className={`flex items-center justify-between gap-3 px-3 py-2 text-sm ${
                  mitigated ? "opacity-50" : ""
                }`}
              >
                <div>
                  <div className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">
                    {formatPrice(row.price)}
                  </div>
                  <div className="text-[11px] text-slate-500">
                    {row.trade_status || formatTime(row.time)}
                  </div>
                </div>
                <span
                  className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${levelStatusTone(
                    row.status,
                  )}`}
                >
                  {row.status || "Active"}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function AutomationTracker({ rows }) {
  if (!rows.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div>
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Automation tracking
          </h4>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Per swing level status and linked M1 schedule / trade lifecycle
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
          {rows.length}
        </span>
      </div>
      <div className="overflow-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-3 py-2">Level</th>
              <th className="px-3 py-2">Kind</th>
              <th className="px-3 py-2">Level status</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2">Trade status</th>
              <th className="px-3 py-2">Entry / SL / TP</th>
              <th className="px-3 py-2">Qty</th>
              <th className="px-3 py-2">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={`${row.kind}-${row.price}-${row.schedule_id || "none"}`}
                className="border-t border-slate-100 dark:border-slate-800"
              >
                <td className="px-3 py-2 font-semibold tabular-nums">{formatPrice(row.price)}</td>
                <td className="px-3 py-2 uppercase text-xs font-semibold text-slate-500">{row.kind}</td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${levelStatusTone(
                      row.status,
                    )}`}
                  >
                    {row.status || "Active"}
                  </span>
                </td>
                <td
                  className={`px-3 py-2 font-semibold ${
                    row.side === "SELL" ? "text-rose-600" : row.side === "BUY" ? "text-emerald-600" : ""
                  }`}
                >
                  {row.side || "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${tradeStatusTone(
                      row.trade_status,
                    )}`}
                  >
                    {row.trade_status || "—"}
                  </span>
                </td>
                <td className="px-3 py-2 tabular-nums text-xs">
                  {row.entry != null
                    ? `${formatPrice(row.entry)} / ${formatPrice(row.stop_loss)}${
                        row.target != null ? ` / ${formatPrice(row.target)}` : ""
                      }`
                    : "—"}
                </td>
                <td className="px-3 py-2 tabular-nums">{row.quantity != null ? row.quantity : "—"}</td>
                <td className="px-3 py-2 text-xs text-slate-500">
                  {row.last_error || row.error || (row.order_id ? `order ${String(row.order_id).slice(0, 8)}…` : "—")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function UnmitigatedSwingsPanel({
  token,
  accounts = [],
  activeAccountId = "",
  liveScheduledTrades = null,
  onNotify,
}) {
  const activeAccount = useMemo(
    () => (accounts || []).find((account) => account.id === activeAccountId) || accounts[0] || null,
    [accounts, activeAccountId],
  );

  const [form, setForm] = useState({
    symbol: "XAUUSD",
    timeframe: "H1",
    swing_count: "5",
    risk_amount: "",
  });
  const [analyzing, setAnalyzing] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState(null);
  const [sessionId, setSessionId] = useState("");
  const [session, setSession] = useState(null);

  useEffect(() => {
    if (!activeAccount) return;
    setForm((current) => ({
      ...current,
      risk_amount: current.risk_amount || String(activeAccount.risk_amount || ""),
    }));
  }, [activeAccount]);

  useEffect(() => {
    if (!token || !sessionId) return undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await getUnmitigatedSwingsSession(token, sessionId);
        if (!cancelled) setSession(data);
      } catch {
        /* ignore transient poll errors */
      }
    };
    poll();
    const timer = window.setInterval(poll, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [token, sessionId]);

  const liveById = useMemo(() => {
    const map = new Map();
    (liveScheduledTrades || []).forEach((row) => {
      if (row?.id) map.set(String(row.id), row);
    });
    return map;
  }, [liveScheduledTrades]);

  const trackedLevels = useMemo(() => {
    const base = session?.levels || [];
    if (!base.length) return [];
    return base.map((row) => {
      const live = row.schedule_id ? liveById.get(String(row.schedule_id)) : null;
      if (!live) return row;
      return {
        ...row,
        trade_status: live.status || row.trade_status,
        side: live.side || row.side,
        entry: live.entry ?? row.entry,
        stop_loss: live.stop_loss ?? row.stop_loss,
        target: live.target ?? row.target,
        quantity: live.quantity ?? row.quantity,
        order_id: live.order_id || row.order_id,
        last_error: live.last_error || row.last_error,
      };
    });
  }, [session, liveById]);

  const displayHighs = useMemo(() => {
    if (trackedLevels.length) return trackedLevels.filter((row) => row.kind === "high");
    return (result?.highs || []).map((row) => ({ ...row, kind: "high" }));
  }, [trackedLevels, result]);

  const displayLows = useMemo(() => {
    if (trackedLevels.length) return trackedLevels.filter((row) => row.kind === "low");
    return (result?.lows || []).map((row) => ({ ...row, kind: "low" }));
  }, [trackedLevels, result]);

  const canExecute =
    Boolean(activeAccount?.id) &&
    (displayHighs.length > 0 || displayLows.length > 0) &&
    Number(form.risk_amount) > 0 &&
    !executing;

  const onAnalyze = async (event) => {
    event.preventDefault();
    if (!token || !activeAccount?.id) {
      onNotify?.("error", "Select an international account first.");
      return;
    }
    setAnalyzing(true);
    setSessionId("");
    setSession(null);
    try {
      const payload = {
        account_id: activeAccount.id,
        symbol: String(form.symbol || "").trim().toUpperCase(),
        timeframe: form.timeframe,
        swing_count: Math.max(1, Math.min(50, Number(form.swing_count) || 5)),
      };
      const data = await analyzeUnmitigatedSwings(token, payload);
      setResult(data);
      onNotify?.(
        "success",
        `Found ${(data.highs || []).length} highs / ${(data.lows || []).length} lows on ${data.timeframe}.`,
      );
    } catch (error) {
      onNotify?.("error", error?.message || "Analyze failed.");
    } finally {
      setAnalyzing(false);
    }
  };

  const onExecute = async () => {
    if (!canExecute || !activeAccount?.id) return;
    setExecuting(true);
    try {
      const payload = {
        account_id: activeAccount.id,
        symbol: String(form.symbol || result?.requested_symbol || "").trim().toUpperCase(),
        structure_timeframe: result?.timeframe || form.timeframe,
        highs: displayHighs
          .filter((row) => String(row.status || "Active") !== "Mitigated")
          .map((row) => Number(row.price)),
        lows: displayLows
          .filter((row) => String(row.status || "Active") !== "Mitigated")
          .map((row) => Number(row.price)),
        risk_amount: Number(form.risk_amount),
      };
      const data = await executeUnmitigatedSwings(token, payload);
      setSession(data.session || null);
      setSessionId(data.session?.id || "");
      const createdCount = (data.created || []).length;
      const errorCount = (data.errors || []).length;
      if (createdCount) {
        onNotify?.(
          "success",
          `Armed ${createdCount} M1 schedule${createdCount === 1 ? "" : "s"}${
            errorCount ? ` (${errorCount} skipped)` : ""
          }.`,
        );
      } else {
        onNotify?.("error", errorCount ? data.errors[0]?.detail || "Execute failed." : "No schedules created.");
      }
    } catch (error) {
      onNotify?.("error", error?.message || "Execute Automation failed.");
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="space-y-4">
      <form
        onSubmit={onAnalyze}
        className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950"
      >
        <div className="mb-3">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Unmitigated Swings
          </h4>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Analyze structure on {activeAccount?.account_name || "selected account"}, then arm one-shot M1 break
            schedules. Target = 4R or prior {form.timeframe} candle extreme, whichever is farther. No retry.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs font-semibold text-slate-500">
            Instrument
            <input
              value={form.symbol}
              onChange={(event) =>
                setForm((current) => ({ ...current, symbol: event.target.value.toUpperCase() }))
              }
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
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-semibold text-slate-500">
            Number of swings
            <input
              value={form.swing_count}
              onChange={(event) => setForm((current) => ({ ...current, swing_count: event.target.value }))}
              inputMode="numeric"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
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
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={analyzing || !activeAccount?.id}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {analyzing ? "Analyzing…" : "Analyze"}
          </button>
          <button
            type="button"
            onClick={onExecute}
            disabled={!canExecute}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {executing ? "Arming…" : "Execute Automation"}
          </button>
        </div>
      </form>

      {(result || session) && (
        <>
          {result?.lookback_exhausted ? (
            <p className="text-xs text-amber-700 dark:text-amber-300">
              Only {displayHighs.length} high{displayHighs.length === 1 ? "" : "s"} / {displayLows.length} low
              {displayLows.length === 1 ? "" : "s"} found after merging levels within 1% and expanding lookback
              {result?.bar_count ? ` (${result.bar_count} bars)` : ""}.
            </p>
          ) : null}
          <div className="grid gap-3 lg:grid-cols-2">
            <LevelColumn title="Highs" rows={displayHighs} tone="high" />
            <LevelColumn title="Lows" rows={displayLows} tone="low" />
          </div>
        </>
      )}

      <AutomationTracker rows={trackedLevels} />

      {sessionId ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Session {sessionId.slice(0, 8)}… · tracking refreshes every few seconds. Levels flip to Mitigated when taken
          out; trade status follows the linked M1 schedule.
        </p>
      ) : null}
    </div>
  );
}
