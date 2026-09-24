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
                key={`${row.kind || title}-${row.price}-${row.time || ""}`}
                className={`flex items-center justify-between gap-3 px-3 py-2 text-sm ${
                  mitigated ? "opacity-50" : ""
                }`}
              >
                <div>
                  <div className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">
                    {formatPrice(row.price)}
                  </div>
                  <div className="text-[11px] text-slate-500">{formatTime(row.time)}</div>
                </div>
                <span
                  className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                    mitigated
                      ? "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
                  }`}
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

export default function UnmitigatedSwingsPanel({
  token,
  accounts = [],
  activeAccountId = "",
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
    const timer = window.setInterval(poll, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [token, sessionId]);

  const displayHighs = useMemo(() => {
    if (session?.highs?.length) return session.highs;
    return (result?.highs || []).map((row) => ({ ...row, kind: "high" }));
  }, [session, result]);

  const displayLows = useMemo(() => {
    if (session?.lows?.length) return session.lows;
    return (result?.lows || []).map((row) => ({ ...row, kind: "low" }));
  }, [session, result]);

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
        <div className="grid gap-3 lg:grid-cols-2">
          <LevelColumn title="Highs" rows={displayHighs} tone="high" />
          <LevelColumn title="Lows" rows={displayLows} tone="low" />
        </div>
      )}

      {sessionId ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Session {sessionId.slice(0, 8)}… · M1 schedules are live under Scheduled Trade. Levels flip to Mitigated when
          taken out.
        </p>
      ) : null}
    </div>
  );
}
