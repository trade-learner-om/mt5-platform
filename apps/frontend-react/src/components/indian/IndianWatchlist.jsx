import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import SymbolIcon from "../SymbolIcon";
import IndianInstrumentSearch from "./IndianInstrumentSearch";

function formatIndianPrice(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M7.5 4.5h5M4.5 6h11M8 8.5v6M12 8.5v6M6.2 6.2l.6 10.1c.1.7.6 1.2 1.3 1.2h3.8c.7 0 1.2-.5 1.3-1.2l.6-10.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function IndianWatchlist({ token, selectedAccountExists, items = [], onNotify, showHeader = true }) {
  const [pendingRemove, setPendingRemove] = useState("");
  const visibleItems = useMemo(() => items.filter((item) => item?.symbol), [items]);
  const priceDirections = useRef({});
  const previousPrices = useRef({});
  const [rowDirections, setRowDirections] = useState({});

  useEffect(() => {
    const nextDirections = {};
    const nextPrevious = { ...previousPrices.current };
    visibleItems.forEach((item) => {
      const currentPrice = item.price;
      const previousPrice = previousPrices.current[`${item.symbol}:${item.instrument_token || ""}`];
      const key = `${item.symbol}:${item.instrument_token || ""}`;
      if (typeof currentPrice === "number" && typeof previousPrice === "number") {
        if (currentPrice > previousPrice) nextDirections[key] = "up";
        else if (currentPrice < previousPrice) nextDirections[key] = "down";
        else nextDirections[key] = priceDirections.current[key] || "flat";
      } else {
        nextDirections[key] = priceDirections.current[key] || "flat";
      }
      nextPrevious[key] = currentPrice;
    });
    previousPrices.current = nextPrevious;
    priceDirections.current = nextDirections;
    setRowDirections(nextDirections);
  }, [visibleItems]);

  const add = async (instrument) => {
    if (!selectedAccountExists) {
      onNotify?.("error", "Select an Indian account before adding watchlist instruments.");
      return;
    }
    try {
      await api("/indian/watchlist", "POST", { symbol: instrument }, token);
      onNotify?.("success", `${instrument.symbol} added to watchlist.`);
    } catch (err) {
      onNotify?.("error", err.message);
      throw err;
    }
  };

  const remove = async (item) => {
    setPendingRemove(`${item.symbol}:${item.instrument_token || ""}`);
    try {
      await api(`/indian/watchlist?symbol=${encodeURIComponent(item.symbol)}&instrument_token=${encodeURIComponent(item.instrument_token)}`, "DELETE", undefined, token);
      onNotify?.("success", `${item.symbol} removed from watchlist.`);
    } catch (err) {
      onNotify?.("error", err.message);
    } finally {
      setPendingRemove("");
    }
  };

  return (
    <section className="h-full rounded-2xl border border-indigo-100 bg-gradient-to-b from-white to-indigo-50 p-4 shadow-sm">
      {showHeader && (
        <div className="mb-4 hidden lg:block">
          <h3 className="text-lg font-semibold text-slate-900">Watchlist</h3>
        </div>
      )}
      <div className="mb-4">
        <IndianInstrumentSearch
          token={token}
          disabled={!selectedAccountExists}
          placeholder={selectedAccountExists ? "Search cash, futures, options..." : "Select an Indian account first"}
          onSelect={add}
          onError={() => undefined}
        />
      </div>
      <div className="space-y-2">
        {visibleItems.length ? (
          visibleItems.map((item) => {
            const key = `${item.symbol}:${item.instrument_token || ""}`;
            return (
              <div key={key} className="group rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 transition hover:bg-indigo-50">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <SymbolIcon symbol={item.symbol} />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">{item.symbol}</p>
                      <p className="mt-0.5 truncate text-xs text-slate-500">{item.display_name || item.symbol}</p>
                      <p className="mt-0.5 text-[11px] uppercase tracking-[0.18em] text-slate-400">{item.exchange || "INDIA"}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className={`flex items-center justify-end gap-1 text-sm font-semibold ${rowDirections[key] === "up" ? "text-emerald-600" : rowDirections[key] === "down" ? "text-rose-600" : "text-slate-900"}`}>
                        <span>{formatIndianPrice(item.price)}</span>
                        <span className="inline-flex w-4 items-center justify-center text-[11px] leading-none">
                          {rowDirections[key] === "up" ? "▲" : rowDirections[key] === "down" ? "▼" : ""}
                        </span>
                      </div>
                      <p className={`mt-0.5 text-xs font-semibold ${typeof item.change === "number" ? item.change >= 0 ? "text-emerald-600" : "text-rose-600" : "text-slate-500"}`}>
                        {typeof item.change === "number" ? `${item.change >= 0 ? "+" : ""}${formatIndianPrice(item.change)}` : "--"}
                      </p>
                    </div>
                    <button
                      onClick={() => remove(item)}
                      disabled={pendingRemove === key}
                      aria-label={`Remove ${item.symbol}`}
                      title={`Remove ${item.symbol}`}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full text-rose-600 opacity-0 transition hover:bg-rose-50 group-hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-100"
                    >
                      {pendingRemove === key ? "..." : <TrashIcon />}
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="rounded-xl border border-dashed border-indigo-200 bg-white/70 px-3 py-6 text-center text-sm text-slate-500">
            No instruments yet. Start typing to add anything from cash, futures, or options.
          </div>
        )}
      </div>
    </section>
  );
}
