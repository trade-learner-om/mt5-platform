import { useEffect, useMemo, useState } from "react";
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api";
import IndianStockPicker from "./IndianStockPicker";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: false,
    },
  },
});

function formatInr(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function defaultFromDate() {
  const date = new Date();
  date.setMonth(date.getMonth() - 3);
  return date.toISOString().slice(0, 10);
}

function defaultToDate() {
  return new Date().toISOString().slice(0, 10);
}

function eventTone(eventType) {
  const type = String(eventType || "").toUpperCase();
  if (type.includes("DATA_GAP")) return "text-amber-700";
  if (type.includes("SOLD") || type.includes("BOUGHT")) return "text-indigo-700";
  if (type.includes("SQUARE") || type.includes("CLOSED") || type.includes("FLAT")) return "text-rose-700";
  if (type.includes("EXIT")) return "text-slate-500";
  return "text-slate-800";
}

export default function IndianPeCycleBacktestPanel(props) {
  return (
    <QueryClientProvider client={queryClient}>
      <IndianPeCycleBacktestPanelContent {...props} />
    </QueryClientProvider>
  );
}

function IndianPeCycleBacktestPanelContent({ token, selectedAccount, onNotify }) {
  const client = useQueryClient();
  const [selectedStock, setSelectedStock] = useState(null);
  const [fromDate, setFromDate] = useState(defaultFromDate);
  const [toDate, setToDate] = useState(defaultToDate);
  const [expandedId, setExpandedId] = useState("");

  const sessionReady = String(selectedAccount?.session_status || "").toUpperCase() === "CONNECTED";

  const listQuery = useQuery({
    queryKey: ["indian-pe-cycle", "backtests"],
    enabled: Boolean(token && selectedAccount),
    queryFn: () => api("/indian/pe-cycle/backtests?limit=20", "GET", undefined, token),
    refetchOnWindowFocus: false,
  });

  const detailQuery = useQuery({
    queryKey: ["indian-pe-cycle", "backtest", expandedId],
    enabled: Boolean(token && expandedId),
    queryFn: () => api(`/indian/pe-cycle/backtest/${encodeURIComponent(expandedId)}`, "GET", undefined, token),
  });

  const runMutation = useMutation({
    mutationFn: () =>
      api(
        "/indian/pe-cycle/backtest",
        "POST",
        {
          underlying: selectedStock?.underlying || selectedStock?.symbol,
          from_date: fromDate,
          to_date: toDate,
        },
        token,
      ),
    onSuccess: (result) => {
      onNotify?.("success", "PE→Stock→CE backtest completed.");
      client.invalidateQueries({ queryKey: ["indian-pe-cycle", "backtests"] });
      if (result?.backtest_id) {
        setExpandedId(result.backtest_id);
      }
    },
    onError: (error) => onNotify?.("error", error?.message || "Backtest failed."),
  });

  const deleteMutation = useMutation({
    mutationFn: (backtestId) =>
      api(`/indian/pe-cycle/backtest/${encodeURIComponent(backtestId)}`, "DELETE", undefined, token),
    onSuccess: (_result, backtestId) => {
      onNotify?.("success", "Backtest deleted.");
      if (expandedId === backtestId) setExpandedId("");
      client.invalidateQueries({ queryKey: ["indian-pe-cycle", "backtests"] });
    },
    onError: (error) => onNotify?.("error", error?.message || "Delete failed."),
  });

  useEffect(() => {
    if (!listQuery.data?.results?.length) return;
    if (!expandedId) {
      setExpandedId(String(listQuery.data.results[0].backtest_id || ""));
    }
  }, [listQuery.data, expandedId]);

  const results = listQuery.data?.results || [];
  const detail = detailQuery.data;
  const events = useMemo(() => detail?.events || [], [detail]);

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">PE → Stock → CE</p>
          <h3 className="mt-1 text-xl font-bold text-slate-900">Monthly cycle backtest</h3>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Sell monthly PE at −10% of spot. On strike hit, square PE, buy 1 lot stock, sell CE at +10%.
            On expiry: CE ITM closes stock+CE and restarts; CE OTM keeps stock and sells next monthly CE.
            Option fills use historical candles.
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-[1.2fr_0.8fr_0.8fr_auto]">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Stock</label>
          <IndianStockPicker
            token={token}
            disabled={!sessionReady || runMutation.isPending}
            value={selectedStock}
            onChange={setSelectedStock}
            onError={(err) => onNotify?.("error", err?.message || "Stock search failed.")}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">From</label>
          <input
            type="date"
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">To</label>
          <input
            type="date"
            value={toDate}
            onChange={(event) => setToDate(event.target.value)}
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
          />
        </div>
        <div className="flex items-end">
          <button
            type="button"
            disabled={!sessionReady || !selectedStock || runMutation.isPending}
            onClick={() => runMutation.mutate()}
            className="w-full rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {runMutation.isPending ? "Running..." : "Run backtest"}
          </button>
        </div>
      </div>

      {!sessionReady ? (
        <p className="mt-3 text-sm text-amber-700">Connect the Indian broker session to search stocks and run backtests.</p>
      ) : null}

      <div className="mt-6 grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Recent runs</p>
          {listQuery.isLoading ? <p className="text-sm text-slate-500">Loading...</p> : null}
          {!listQuery.isLoading && !results.length ? (
            <p className="text-sm text-slate-500">No backtests yet.</p>
          ) : null}
          {results.map((row) => {
            const active = expandedId === row.backtest_id;
            return (
              <button
                key={row.backtest_id}
                type="button"
                onClick={() => setExpandedId(row.backtest_id)}
                className={`w-full rounded-2xl border px-3 py-3 text-left ${
                  active ? "border-indigo-300 bg-indigo-50" : "border-slate-200 bg-slate-50 hover:bg-white"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold text-slate-900">{row.underlying}</p>
                    <p className="text-xs text-slate-500">
                      {row.from_date} → {row.to_date}
                    </p>
                  </div>
                  <p className={`font-mono text-sm font-semibold ${Number(row.cumulative_pnl) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                    {formatInr(Number(row.cumulative_pnl || 0))}
                  </p>
                </div>
                <p className="mt-1 text-[11px] text-slate-400">{row.event_count || 0} events · {row.final_state || "-"}</p>
              </button>
            );
          })}
        </div>

        <div className="min-h-[240px] rounded-2xl border border-slate-200 bg-slate-50 p-4">
          {!expandedId ? (
            <p className="text-sm text-slate-500">Select a backtest to view the event timeline.</p>
          ) : detailQuery.isLoading ? (
            <p className="text-sm text-slate-500">Loading details...</p>
          ) : !detail ? (
            <p className="text-sm text-slate-500">Backtest not found.</p>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-lg font-bold text-slate-900">{detail.underlying}</p>
                  <p className="text-sm text-slate-600">
                    {detail.from_date} → {detail.to_date} · PnL {formatInr(Number(detail.summary?.cumulative_pnl ?? detail.cumulative_pnl ?? 0))}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(detail.backtest_id)}
                  className="rounded-xl border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                >
                  Delete
                </button>
              </div>
              <div className="mt-4 max-h-[420px] space-y-2 overflow-auto">
                {events.map((event, index) => (
                  <div key={`${event.event_type}-${event.event_time}-${index}`} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className={`text-xs font-bold uppercase tracking-wide ${eventTone(event.event_type)}`}>
                        {event.event_type}
                      </p>
                      <p className="font-mono text-xs text-slate-500">{event.event_time}</p>
                    </div>
                    <p className="mt-1 text-sm text-slate-800">{event.message}</p>
                    <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-slate-500">
                      {event.symbol ? <span>{event.symbol}</span> : null}
                      {event.strike != null ? <span>Strike {event.strike}</span> : null}
                      {event.premium != null ? <span>Prem {event.premium}</span> : null}
                      {event.price != null ? <span>Price {event.price}</span> : null}
                      {event.quantity != null ? <span>Qty {event.quantity}</span> : null}
                      {event.pnl_update ? <span>Δ {formatInr(Number(event.pnl_update))}</span> : null}
                      <span>Cum {formatInr(Number(event.cumulative_pnl || 0))}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
