import { useEffect, useMemo, useState } from "react";

import { api } from "../../api";

const APP_TIME_ZONE = "Asia/Calcutta";
const PLACED = new Set(["PENDING", "PLACEMENT_PENDING", "WAITING_TRIGGER", "DEFERRED_MARKET_OPEN"]);
const IN_POSITION = new Set(["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]);

function parseTimestamp(value) {
  if (!value) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const text = String(value).trim();
  if (!text) return null;
  const hasExplicitZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(text);
  const parsed = new Date(hasExplicitZone ? text : `${text}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function appDayKey(value) {
  const date = value instanceof Date ? value : parseTimestamp(value);
  if (!date) return "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: APP_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function isAppLocalToday(value) {
  return Boolean(value) && appDayKey(value) === appDayKey(new Date());
}

export function trackerStatusLabel(status) {
  const normalized = String(status || "").toUpperCase();
  if (PLACED.has(normalized)) return "Placed";
  if (IN_POSITION.has(normalized)) return "In Position";
  if (normalized === "CLOSED") return "Closed";
  return normalized
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function trackerPl(row) {
  const label = trackerStatusLabel(row?.status);
  if (label === "In Position") return row?.unrealized_pl;
  if (label === "Closed") return row?.realized_pl;
  return null;
}

function formatPl(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(2)}`;
}

function formatLevel(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? String(number) : "—";
}

function canEdit(row) {
  const label = trackerStatusLabel(row?.status);
  return label === "Placed" || label === "In Position";
}

function TrackerTable({ rows, onEdit }) {
  if (!rows.length) {
    return <p className="px-3 py-6 text-center text-xs text-slate-500">No orders in this view.</p>;
  }
  return (
    <table className="min-w-full text-left text-[11px]">
      <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500 dark:bg-slate-950">
        <tr>
          <th className="px-2 py-2 font-semibold">Symbol</th>
          <th className="px-2 py-2 font-semibold">Side</th>
          <th className="px-2 py-2 font-semibold">Status</th>
          <th className="px-2 py-2 font-semibold">Qty</th>
          <th className="px-2 py-2 font-semibold">Entry</th>
          <th className="px-2 py-2 font-semibold">SL</th>
          <th className="px-2 py-2 font-semibold">Target</th>
          <th className="px-2 py-2 font-semibold">P/L</th>
          <th className="px-2 py-2 font-semibold" />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const label = trackerStatusLabel(row.status);
          const pl = trackerPl(row);
          const plNumber = Number(pl);
          return (
            <tr key={row.id} className="border-t border-slate-100 dark:border-slate-800">
              <td className="px-2 py-1.5 font-semibold">{row.symbol}</td>
              <td className="px-2 py-1.5">{row.side}</td>
              <td className="px-2 py-1.5">{label}</td>
              <td className="px-2 py-1.5">{formatLevel(row.position_quantity ?? row.quantity)}</td>
              <td className="px-2 py-1.5">{formatLevel(row.entry)}</td>
              <td className="px-2 py-1.5">{formatLevel(row.stop_loss)}</td>
              <td className="px-2 py-1.5">{formatLevel(row.target)}</td>
              <td className={`px-2 py-1.5 font-semibold ${Number.isFinite(plNumber) && plNumber < 0 ? "text-rose-600" : Number.isFinite(plNumber) && plNumber > 0 ? "text-emerald-600" : "text-slate-500"}`}>
                {formatPl(pl)}
              </td>
              <td className="px-2 py-1.5 text-right">
                {canEdit(row) ? (
                  <button
                    type="button"
                    onClick={() => onEdit?.(row)}
                    className="rounded-md border border-slate-200 px-2 py-1 text-[10px] font-semibold text-indigo-700 hover:bg-indigo-50 dark:border-slate-700"
                  >
                    Edit
                  </button>
                ) : null}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function OrderTracker({ token, liveOrders = [], onEdit }) {
  const [tab, setTab] = useState("recent");
  const [historyRows, setHistoryRows] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const recentRows = useMemo(
    () => (liveOrders || []).filter((row) => isAppLocalToday(row.created_at)),
    [liveOrders]
  );

  useEffect(() => {
    if (tab !== "history" || !token) return undefined;
    let cancelled = false;
    const load = async () => {
      setHistoryLoading(true);
      setHistoryError("");
      try {
        const page = await api("/orders/history?limit=20", "GET", undefined, token);
        if (cancelled) return;
        setHistoryRows(page?.records || []);
        setNextCursor(page?.next_cursor || null);
      } catch (error) {
        if (cancelled) return;
        setHistoryRows([]);
        setNextCursor(null);
        setHistoryError(error?.message || "History is unavailable.");
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [tab, token]);

  const loadMore = async () => {
    if (!nextCursor || historyLoading) return;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const page = await api(`/orders/history?limit=20&cursor=${encodeURIComponent(nextCursor)}`, "GET", undefined, token);
      setHistoryRows((current) => [...current, ...(page?.records || [])]);
      setNextCursor(page?.next_cursor || null);
    } catch (error) {
      setHistoryError(error?.message || "Could not load more history.");
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">Orders</p>
        <div className="grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
          <button
            type="button"
            onClick={() => setTab("recent")}
            className={`rounded-md px-2 py-1 text-[10px] font-bold ${tab === "recent" ? "bg-white text-slate-900 shadow dark:bg-slate-950 dark:text-slate-100" : "text-slate-500"}`}
          >
            Recent
          </button>
          <button
            type="button"
            onClick={() => setTab("history")}
            className={`rounded-md px-2 py-1 text-[10px] font-bold ${tab === "history" ? "bg-white text-slate-900 shadow dark:bg-slate-950 dark:text-slate-100" : "text-slate-500"}`}
          >
            History
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "recent" ? (
          <TrackerTable rows={recentRows} onEdit={onEdit} />
        ) : (
          <>
            {historyError ? <p className="px-3 py-2 text-xs text-rose-600">{historyError}</p> : null}
            <TrackerTable rows={historyRows} onEdit={onEdit} />
            {nextCursor ? (
              <div className="px-3 py-2">
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={historyLoading}
                  className="rounded-md border border-slate-200 px-3 py-1.5 text-[11px] font-semibold text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200"
                >
                  {historyLoading ? "Loading…" : "Load more"}
                </button>
              </div>
            ) : historyLoading ? (
              <p className="px-3 py-2 text-xs text-slate-500">Loading history…</p>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
