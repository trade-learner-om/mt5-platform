import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { api } from "../../api";
import PriceCell from "./PriceCell";
import { formatPriceWithDigits } from "../../utils/pricePrecision";

function formatWatchPrice(value, digits) {
  if (value == null || value === "") return "--";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return formatPriceWithDigits(numeric, digits, [], 0);
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path
        d="M7.5 4.5h5M4.5 6h11M8 8.5v6M12 8.5v6M6.2 6.2l.6 10.1c.1.7.6 1.2 1.3 1.2h3.8c.7 0 1.2-.5 1.3-1.2l.6-10.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function LiveWatchlist({
  rows = [],
  selectedInstrument = "",
  onSelectInstrument,
  token = "",
  selectedAccountExists = false,
  selectedAccountId = "",
  onNotify,
  onSymbolDigits,
}) {
  const [symbol, setSymbol] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [adding, setAdding] = useState(false);
  const [pendingRemove, setPendingRemove] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  useEffect(() => {
    if (!selectedAccountExists || symbol.trim().length < 1) {
      setSuggestions([]);
      setHighlightedIndex(-1);
      return undefined;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await api(`/instruments/suggest?q=${encodeURIComponent(symbol)}&limit=8`, "GET", undefined, token);
        setSuggestions(data.symbols || []);
        setHighlightedIndex((data.symbols || []).length ? 0 : -1);
      } catch {
        setSuggestions([]);
        setHighlightedIndex(-1);
      }
    }, 180);
    return () => clearTimeout(timer);
  }, [symbol, token, selectedAccountExists]);

  const add = async () => {
    if (!selectedAccountExists) {
      onNotify?.("error", "Select an account before adding watchlist symbols.");
      return;
    }
    if (!symbol.trim()) return;
    setAdding(true);
    try {
      const result = await api("/watchlist", "POST", { symbol }, token);
      const brokerSymbol = result?.broker_symbol || symbol.trim().toUpperCase();
      setSymbol("");
      setSuggestions([]);
      setHighlightedIndex(-1);
      onSelectInstrument?.(brokerSymbol);
      if (result?.price_digits !== null && result?.price_digits !== undefined) {
        onSymbolDigits?.(brokerSymbol, result.price_digits);
      }
      onNotify?.(
        "success",
        result?.display_symbol && result.display_symbol !== brokerSymbol
          ? `${result.display_symbol} added to watchlist.`
          : `${brokerSymbol} added to watchlist.`,
      );
    } catch (err) {
      onNotify?.("error", err.message);
    } finally {
      setAdding(false);
    }
  };

  const selectSuggestion = (value) => {
    setSymbol(value);
    setSuggestions([]);
    setHighlightedIndex(-1);
  };

  const handleKeyDown = (event) => {
    if (!suggestions.length) {
      if (event.key === "Enter") {
        event.preventDefault();
        add();
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (highlightedIndex >= 0 && suggestions[highlightedIndex]) {
        selectSuggestion(suggestions[highlightedIndex]);
      } else {
        add();
      }
    }
  };

  const remove = async (value, event) => {
    event?.stopPropagation?.();
    setPendingRemove(value);
    try {
      await api(`/watchlist?symbol=${encodeURIComponent(value)}`, "DELETE", undefined, token);
      onNotify?.("success", `${value} removed from watchlist.`);
      if (selectedInstrument === value) {
        onSelectInstrument?.("");
      }
    } catch (err) {
      onNotify?.("error", err.message);
    } finally {
      setPendingRemove("");
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
          Live Watchlist
        </p>
        <div className="relative mt-2">
          <div className="flex gap-2">
            <input
              className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
              disabled={!selectedAccountExists}
              value={symbol}
              onChange={(event) => setSymbol(event.target.value.toUpperCase())}
              onKeyDown={handleKeyDown}
              placeholder={selectedAccountExists ? "Type symbol..." : "Select an account first"}
            />
            <button
              type="button"
              onClick={add}
              disabled={adding || !selectedAccountExists}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {adding ? "..." : "Add"}
            </button>
          </div>
          {suggestions.length > 0 && symbol ? (
            <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
              {suggestions.map((suggestion, index) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => selectSuggestion(suggestion)}
                  className={`block w-full px-3 py-2 text-left text-sm ${
                    index === highlightedIndex
                      ? "bg-indigo-50 text-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-200"
                      : "text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
                  }`}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-sm">
          <tbody>
            {rows.map((row) => {
              const active = selectedInstrument === row.symbol;
              return (
                <motion.tr
                  key={row.symbol}
                  layout
                  onClick={() => onSelectInstrument?.(row.symbol)}
                  className={`cursor-pointer border-b border-slate-100 dark:border-slate-800 ${
                    active ? "bg-slate-100 dark:bg-slate-800" : "hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  }`}
                >
                  <td className="px-3 py-2 text-xs font-medium text-slate-900 dark:text-slate-100">
                    {row.symbol}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <PriceCell
                      value={row.price}
                      formatter={(value) => formatWatchPrice(value, row.price_digits ?? 2)}
                    />
                  </td>
                  <td className="w-10 px-2 py-2 text-right">
                    <button
                      type="button"
                      aria-label={`Remove ${row.symbol}`}
                      disabled={pendingRemove === row.symbol}
                      onClick={(event) => remove(row.symbol, event)}
                      className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-50 dark:hover:bg-rose-950/40 dark:hover:text-rose-300"
                    >
                      <TrashIcon />
                    </button>
                  </td>
                </motion.tr>
              );
            })}
            {!rows.length ? (
              <tr>
                <td colSpan={3} className="px-3 py-6 text-center text-xs text-slate-400">
                  Search and add symbols to watch.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
