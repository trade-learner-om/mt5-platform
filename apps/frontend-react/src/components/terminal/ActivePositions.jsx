import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import PriceCell from "./PriceCell";
import { formatPriceWithDigits } from "../../utils/pricePrecision";

function formatPrice(value, digits = null) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return formatPriceWithDigits(numeric, digits, [], 0);
}

function formatPnl(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(2)}`;
}

export default function ActivePositions({
  rows = [],
  actionLoadingId = "",
  onFullClose,
  onPartialClose,
}) {
  const [menuRowId, setMenuRowId] = useState("");
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuRowId) return undefined;
    const onPointerDown = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuRowId("");
      }
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setMenuRowId("");
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuRowId]);

  return (
    <section className="flex h-full min-h-0 flex-col rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
          Active Positions
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-50 dark:bg-slate-950">
            <tr className="text-left text-slate-500 dark:text-slate-400">
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Size</th>
              <th className="px-3 py-2">Open</th>
              <th className="px-3 py-2 text-right">Live PnL</th>
            </tr>
          </thead>
          <motion.tbody layout>
            <AnimatePresence initial={false}>
              {rows.length ? rows.map((row) => {
                const loading = actionLoadingId === row.id;
                const menuOpen = menuRowId === row.id;
                return (
                  <motion.tr
                    key={row.id}
                    layout
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    className={`relative cursor-pointer border-t border-slate-100 dark:border-slate-800 ${menuOpen ? "bg-slate-50 dark:bg-slate-800/60" : "hover:bg-slate-50 dark:hover:bg-slate-800/40"}`}
                    onClick={() => setMenuRowId((current) => (current === row.id ? "" : row.id))}
                  >
                    <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{row.symbol}</td>
                    <td className={`px-3 py-2 ${row.type === "Long" ? "text-emerald-500 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"}`}>
                      {row.type}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums">{row.size}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{formatPrice(row.openPrice, row.priceDigits)}</td>
                    <td className="relative px-3 py-2 text-right">
                      <PriceCell value={row.pnl} formatter={formatPnl} tone="pnl" />
                      {menuOpen ? (
                        <div
                          ref={menuRef}
                          className="absolute right-2 top-full z-20 mt-1 w-44 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <button
                            type="button"
                            disabled={loading || !onFullClose}
                            onClick={() => {
                              setMenuRowId("");
                              onFullClose?.(row.raw || row);
                            }}
                            className="w-full rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-800 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-100 dark:hover:bg-slate-800"
                          >
                            {loading ? "Closing..." : "Close Position"}
                          </button>
                          <button
                            type="button"
                            disabled={loading || !onPartialClose}
                            onClick={() => {
                              setMenuRowId("");
                              onPartialClose?.(row.raw || row, row.currentPrice);
                            }}
                            className="w-full rounded-lg px-3 py-2 text-left text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 dark:text-indigo-300 dark:hover:bg-indigo-950/40"
                          >
                            Partial Exit
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </motion.tr>
                );
              }) : (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
                    No active positions.
                  </td>
                </tr>
              )}
            </AnimatePresence>
          </motion.tbody>
        </table>
      </div>
    </section>
  );
}
