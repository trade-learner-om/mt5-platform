import { AnimatePresence, motion } from "framer-motion";
import { Play, Square } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../../api";
import { formatPriceWithDigits, livePriceFromTick, lookupLiveTick, resolveSymbolPriceDigits } from "../../utils/pricePrecision";

function formatPrice(value, digits = null, relatedValues = []) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return formatPriceWithDigits(numeric, digits, relatedValues, 0);
}

function normalizeLevelRows(levels) {
  const supports = (levels?.active_h1_supports || [])
    .map((price) => ({ id: `support-${price}`, price }))
    .sort((left, right) => Number(right.price || 0) - Number(left.price || 0));
  const resistances = (levels?.active_h1_resistances || [])
    .map((price) => ({ id: `resistance-${price}`, price }))
    .sort((left, right) => Number(right.price || 0) - Number(left.price || 0));
  return { supports, resistances };
}

function LevelList({ rows, tone, digits }) {
  return (
    <ul className="space-y-1.5">
      <AnimatePresence initial={false}>
        {rows.map((row) => (
          <motion.li
            key={row.id}
            layout
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className={`rounded-md border px-2 py-1 font-mono text-xs tabular-nums ${
              tone === "support"
                ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-500 dark:text-emerald-400"
                : "border-rose-500/20 bg-rose-500/10 text-rose-500 dark:text-rose-400"
            }`}
          >
            {formatPrice(row.price, digits)}
          </motion.li>
        ))}
      </AnimatePresence>
    </ul>
  );
}

export default function FSMCommandCenter({
  token,
  selectedAccountExists,
  onNotify,
  livePrices = {},
  symbolPriceDigits = {},
  selectedInstrument = "",
  className = "",
}) {
  const [symbol, setSymbol] = useState(selectedInstrument || "GOLD");
  const [riskAmount, setRiskAmount] = useState("100");
  const [levels, setLevels] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loadingLevels, setLoadingLevels] = useState(false);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    if (selectedInstrument) {
      setSymbol(selectedInstrument);
    }
  }, [selectedInstrument]);

  const normalizedSymbol = String(symbol || "").trim().toUpperCase();
  const levelRows = useMemo(() => normalizeLevelRows(levels), [levels]);
  const liveTick = lookupLiveTick(livePrices, normalizedSymbol);
  const livePrice = livePriceFromTick(liveTick);
  const priceDigits = resolveSymbolPriceDigits(normalizedSymbol, livePrices, symbolPriceDigits) ?? levels?.price_digits ?? null;

  const loadLevels = async (symbolValue = normalizedSymbol, silent = false) => {
    if (!selectedAccountExists || !symbolValue) {
      setLevels(null);
      return;
    }
    if (!silent) setLoadingLevels(true);
    try {
      const data = await api(`/trap-reversal/levels/${encodeURIComponent(symbolValue)}`, "GET", undefined, token);
      setLevels(data);
    } catch (error) {
      if (!silent) onNotify?.("error", error?.message || "Could not load H1 levels.");
    } finally {
      if (!silent) setLoadingLevels(false);
    }
  };

  const loadRuns = async (silent = false) => {
    if (!selectedAccountExists) {
      setRuns([]);
      return;
    }
    if (!silent) setLoadingRuns(true);
    try {
      const data = await api("/trap-reversal/active", "GET", undefined, token);
      setRuns(Array.isArray(data?.runs) ? data.runs : []);
    } catch (error) {
      if (!silent) onNotify?.("error", error?.message || "Could not load active engines.");
    } finally {
      if (!silent) setLoadingRuns(false);
    }
  };

  useEffect(() => {
    loadLevels(normalizedSymbol, true);
  }, [normalizedSymbol]);

  useEffect(() => {
    loadRuns(true);
    const timer = window.setInterval(() => loadRuns(true), 3000);
    return () => window.clearInterval(timer);
  }, [token, selectedAccountExists]);

  const onStart = async () => {
    const risk = Number(riskAmount);
    if (!selectedAccountExists) {
      onNotify?.("error", "Select an international account before starting an engine.");
      return;
    }
    if (!normalizedSymbol) {
      onNotify?.("error", "Symbol is required.");
      return;
    }
    if (!Number.isFinite(risk) || risk <= 0) {
      onNotify?.("error", "Risk amount must be greater than 0.");
      return;
    }
    setActionLoading(true);
    try {
      const data = await api("/trap-reversal/start", "POST", { symbol: normalizedSymbol, risk_amount: risk }, token);
      setLevels((current) => ({
        ...(current || {}),
        ...data,
        active_h1_supports: data.supports || current?.active_h1_supports || [],
        active_h1_resistances: data.resistances || current?.active_h1_resistances || [],
      }));
      await loadRuns(true);
      onNotify?.("success", `${data.display_symbol || normalizedSymbol} engine started.`);
    } catch (error) {
      onNotify?.("error", error?.message || "Could not start the engine.");
    } finally {
      setActionLoading(false);
    }
  };

  const onStop = async () => {
    if (!normalizedSymbol) {
      onNotify?.("error", "Symbol is required.");
      return;
    }
    setActionLoading(true);
    try {
      await api("/trap-reversal/stop", "POST", { symbol: normalizedSymbol }, token);
      await loadRuns(true);
      onNotify?.("success", `${normalizedSymbol} engine stopped.`);
    } catch (error) {
      onNotify?.("error", error?.message || "Could not stop the engine.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <section className={`grid h-full min-h-0 grid-rows-[auto_1fr_1fr] gap-3 rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      <div className="flex flex-wrap items-end gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
        <label className="flex min-w-[10rem] flex-1 flex-col gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Symbol</span>
          <input
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none dark:border-slate-800 dark:bg-slate-950"
            placeholder="GOLD"
          />
        </label>
        <label className="flex min-w-[10rem] flex-1 flex-col gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Risk Amount</span>
          <input
            value={riskAmount}
            onChange={(event) => setRiskAmount(event.target.value)}
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm outline-none dark:border-slate-800 dark:bg-slate-950"
            placeholder="100"
          />
        </label>
        <button
          type="button"
          onClick={onStart}
          disabled={actionLoading}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
        >
          <Play className="h-4 w-4" />
          Start Engine
        </button>
        <button
          type="button"
          onClick={onStop}
          disabled={actionLoading}
          className="inline-flex items-center gap-2 rounded-lg bg-rose-600 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-60"
        >
          <Square className="h-4 w-4" />
          Stop Engine
        </button>
      </div>

      <div className="grid min-h-0 grid-cols-2 gap-3">
        <div className="min-h-0 overflow-auto rounded-lg border border-slate-200 p-3 dark:border-slate-800">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-500 dark:text-emerald-400">H1 Supports</p>
            <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
              {livePrice == null ? "--" : formatPrice(livePrice, priceDigits)}
            </span>
          </div>
          <LevelList rows={levelRows.supports} tone="support" digits={priceDigits} />
        </div>
        <div className="min-h-0 overflow-auto rounded-lg border border-slate-200 p-3 dark:border-slate-800">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-rose-500 dark:text-rose-400">H1 Resistances</p>
            <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
              {loadingLevels ? "..." : `${levelRows.supports.length + levelRows.resistances.length} lvls`}
            </span>
          </div>
          <LevelList rows={levelRows.resistances} tone="resistance" digits={priceDigits} />
        </div>
      </div>

      <div className="min-h-0 overflow-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-50 dark:bg-slate-950">
            <tr className="text-left text-slate-500 dark:text-slate-400">
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">State</th>
              <th className="px-3 py-2">Entry</th>
              <th className="px-3 py-2">SL</th>
              <th className="px-3 py-2">Target</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.symbol} className="border-t border-slate-100 dark:border-slate-800">
                <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{run.display_symbol || run.symbol}</td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    {run.state}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono tabular-nums">{formatPrice(run.entry, run.price_digits)}</td>
                <td className="px-3 py-2 font-mono tabular-nums">{formatPrice(run.stop_loss, run.price_digits)}</td>
                <td className="px-3 py-2 font-mono tabular-nums">{formatPrice(run.target, run.price_digits)}</td>
              </tr>
            ))}
            {!runs.length && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                  {loadingRuns ? "Loading active engines..." : "No active engines listening to ticks right now."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
