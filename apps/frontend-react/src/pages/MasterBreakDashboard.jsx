import { useEffect, useRef, useState } from "react";
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Crosshair, Settings } from "lucide-react";

import { api } from "../api";
import MasterBreakSettingsModal from "../components/master-break/MasterBreakSettingsModal";
import BacktestResultsPagination from "../components/shared/BacktestResultsPagination";
import { fetchBacktestCursorPage } from "../utils/backtestCursorPagination";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 2_000 } },
});

const DEFAULT_BACKTEST_PAGE_SIZE = 10;
const TABS = [
  { id: "live", label: "Live" },
  { id: "backtest", label: "Backtest" },
  { id: "history", label: "History" },
];

function defaultFromDate() {
  const date = new Date();
  date.setDate(date.getDate() - 7);
  return date.toISOString().slice(0, 10);
}

function defaultToDate() {
  return new Date().toISOString().slice(0, 10);
}

function formatPnl(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const tone =
    number > 0 ? "text-emerald-700 dark:text-emerald-400" : number < 0 ? "text-rose-700 dark:text-rose-400" : "text-slate-700";
  const prefix = number > 0 ? "+" : "";
  return (
    <span className={tone}>
      {prefix}
      {number.toFixed(2)}
    </span>
  );
}

function formatTs(value) {
  if (value == null || value === "") return "-";
  if (typeof value === "number" && Number.isFinite(value)) {
    const ms = value > 1e12 ? value : value * 1000;
    const date = new Date(ms);
    if (!Number.isNaN(date.getTime())) {
      const iso = date.toISOString().replace("Z", "");
      const [datePart, timePart = ""] = iso.split("T");
      return { date: datePart, time: timePart.slice(0, 8) || "-" };
    }
  }
  const text = String(value).trim();
  if (/^\d{10,13}$/.test(text)) {
    return formatTs(Number(text));
  }
  if (text.includes("T")) {
    const [datePart, timePart = ""] = text.replace("Z", "").replace(/\+00:00$/, "").split("T");
    return { date: datePart, time: (timePart || "").slice(0, 8) || "-" };
  }
  if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/.test(text)) {
    const [datePart, timePart = ""] = text.split(/\s+/);
    return { date: datePart, time: timePart.slice(0, 8) || "-" };
  }
  return { date: text.slice(0, 10), time: "-" };
}

function formatDateTimeLabel(value) {
  if (value == null || value === "") return "?";
  const ts = formatTs(value);
  if (ts === "-") return "?";
  if (ts.time && ts.time !== "-") return `${ts.date} ${ts.time}`;
  return ts.date;
}

function SummaryGrid({ summary }) {
  if (!summary) return null;
  const ddPeriod = summary.max_dd_period || {};
  const ddLabel =
    ddPeriod.from || ddPeriod.to
      ? `${formatDateTimeLabel(ddPeriod.from)} → ${formatDateTimeLabel(ddPeriod.to)}`
      : ddPeriod.duration_trades
        ? `${ddPeriod.duration_trades} trades`
        : "-";
  const cells = [
    ["Total PnL", formatPnl(summary.total_pnl)],
    ["Total Trades", summary.total_trades ?? summary.closed_trades ?? 0],
    ["Wins %", `${summary.win_pct ?? 0}%`],
    ["Losses %", `${summary.loss_pct ?? 0}%`],
    ["Avg Profit", formatPnl(summary.avg_profit)],
    ["Avg Loss", formatPnl(summary.avg_loss)],
    ["Max Drawdown", formatPnl(-Math.abs(Number(summary.max_drawdown ?? 0)))],
    ["Max DD Period", ddLabel],
    ["Max Profit", formatPnl(summary.max_profit)],
    ["Max Loss", formatPnl(summary.max_loss)],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
      {cells.map(([label, value]) => (
        <div key={label}>
          <p className="text-[10px] uppercase text-slate-500">{label}</p>
          <p className="truncate font-semibold text-slate-900 dark:text-slate-100">{value}</p>
        </div>
      ))}
    </div>
  );
}

function formatPrice(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(2);
}

function openDatePicker(event) {
  const input = event.currentTarget;
  if (typeof input.showPicker !== "function") return;
  try {
    input.showPicker();
  } catch {
    // Browser may reject if not a trusted gesture; native focus still works.
  }
}

function DateField({ id, label, value, onChange }) {
  return (
    <div className="relative z-10 text-xs font-semibold text-slate-600 dark:text-slate-300">
      <label htmlFor={id} className="block">
        {label}
      </label>
      <input
        id={id}
        type="date"
        className="mt-1 w-full cursor-pointer rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onClick={openDatePicker}
        onFocus={openDatePicker}
      />
    </div>
  );
}

function colorBadge(color) {
  const tone =
    color === "green"
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
      : color === "red"
        ? "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300"
        : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${tone}`}>{color || "doji"}</span>;
}

function biasBadges(sides) {
  const badges = [];
  const pushSide = (key, sideKey, tone) => {
    const slot = sides?.[sideKey];
    if (!slot?.bias_formed) return;
    const filled = slot.entry_filled === "yes";
    const pnl =
      filled && slot.result_pnl != null && Number.isFinite(Number(slot.result_pnl)) ? (
        formatPnl(slot.result_pnl)
      ) : (
        <span className="text-slate-400">-</span>
      );
    badges.push({ key, label: slot.bias_formed, tone, pnl });
  };
  pushSide("S", "SHORT", "text-rose-700 dark:text-rose-400");
  pushSide("L", "LONG", "text-emerald-700 dark:text-emerald-400");
  if (!badges.length) return <span className="text-slate-400">—</span>;
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
      {badges.map((item) => (
        <span key={item.key} className="inline-flex items-center gap-1">
          <span className={`text-[10px] font-semibold uppercase ${item.tone}`}>{item.label}</span>
          <span className="text-[10px] font-medium tabular-nums">{item.pnl}</span>
        </span>
      ))}
    </span>
  );
}

function SideAuditGrid({ sideKey, slot, execLabel }) {
  if (!slot) return null;
  const filled = slot.entry_filled === "yes";
  const cells = [
    ["Level", formatPrice(slot.level)],
    [`${execLabel} beyond`, slot.exec_closed_beyond || "no"],
    [`${execLabel} close time`, (() => {
      const ts = formatTs(slot.exec_close_time);
      return slot.exec_close_time ? `${ts.date} ${ts.time}` : "-";
    })()],
    ["Side breached", slot.side_breached || "-"],
    ["Bias formed", slot.bias_formed || "-"],
    ["Signal color", slot.signal_candle_color || "-"],
    ["Signal high", formatPrice(slot.signal_high)],
    ["Signal low", formatPrice(slot.signal_low)],
    ["Planned entry", formatPrice(slot.planned_entry)],
    ["Planned SL", formatPrice(slot.planned_sl)],
    ["Quantity", slot.quantity != null ? Number(slot.quantity).toFixed(2) : "-"],
    ["Entry filled", slot.entry_filled || "no"],
    [
      "Entry fill time",
      (() => {
        const ts = formatTs(slot.entry_fill_time);
        return filled && slot.entry_fill_time ? `${ts.date} ${ts.time}` : "-";
      })(),
    ],
    [
      "Exit time",
      (() => {
        const ts = formatTs(slot.exit_time);
        return filled && slot.exit_time ? `${ts.date} ${ts.time}` : "-";
      })(),
    ],
    ["Result PnL", filled ? formatPnl(slot.result_pnl) : "-"],
  ];
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{sideKey}</p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 md:grid-cols-3">
        {cells.map(([label, value]) => (
          <div key={`${sideKey}-${label}`}>
            <p className="text-[10px] uppercase text-slate-500">{label}</p>
            <p className="truncate text-xs font-medium text-slate-900 dark:text-slate-100">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

async function copyJson(payload, onNotify) {
  try {
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    onNotify?.("success", "Copied raw JSON");
  } catch {
    onNotify?.("error", "Could not copy JSON");
  }
}

function MasterCandleRow({ row, execLabel, onNotify }) {
  const [open, setOpen] = useState(false);
  const when = formatTs(row.time);
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700">
      <div className="flex items-stretch gap-1">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="grid min-w-0 flex-1 grid-cols-2 gap-1 px-2 py-2 text-left text-xs md:grid-cols-6"
        >
          <span>{when.date}</span>
          <span>{when.time}</span>
          <span>H {formatPrice(row.high)}</span>
          <span>L {formatPrice(row.low)}</span>
          <span>{colorBadge(row.color)}</span>
          <span className="flex items-center justify-between gap-2">
            {biasBadges(row.sides)}
            <span className="text-slate-400">{open ? "▾" : "▸"}</span>
          </span>
        </button>
        <button
          type="button"
          onClick={() => copyJson(row, onNotify)}
          className="shrink-0 border-l border-slate-200 px-2 text-[10px] font-semibold uppercase text-slate-600 dark:border-slate-700 dark:text-slate-300"
        >
          Copy raw JSON
        </button>
      </div>
      {open ? (
        <div className="space-y-3 border-t border-slate-100 px-2 py-2 dark:border-slate-800">
          <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-5">
            <div>
              <p className="text-[10px] uppercase text-slate-500">Open</p>
              <p>{formatPrice(row.open)}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-slate-500">High</p>
              <p>{formatPrice(row.high)}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-slate-500">Low</p>
              <p>{formatPrice(row.low)}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-slate-500">Close</p>
              <p>{formatPrice(row.close)}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-slate-500">Color</p>
              <p>{colorBadge(row.color)}</p>
            </div>
          </div>
          <SideAuditGrid sideKey="SHORT" slot={row.sides?.SHORT} execLabel={execLabel} />
          <SideAuditGrid sideKey="LONG" slot={row.sides?.LONG} execLabel={execLabel} />
        </div>
      ) : null}
    </div>
  );
}

function MasterCandleList({ rows, execTimeframe, onNotify }) {
  const execLabel = String(execTimeframe || "M5").toUpperCase();
  if (!rows?.length) {
    return <p className="text-xs text-slate-500">No master candles in range.</p>;
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="hidden grid-cols-6 gap-1 px-2 text-[10px] uppercase text-slate-500 md:grid md:flex-1">
          <span>Date</span>
          <span>Time</span>
          <span>High</span>
          <span>Low</span>
          <span>Color</span>
          <span>Bias / PnL</span>
        </div>
        <button
          type="button"
          onClick={() => copyJson(rows, onNotify)}
          className="rounded border border-slate-200 px-2 py-1 text-[10px] font-semibold uppercase text-slate-600 dark:border-slate-700 dark:text-slate-300"
        >
          Copy all master rows
        </button>
      </div>
      {rows.map((row, index) => (
        <MasterCandleRow
          key={row.time || index}
          row={row}
          execLabel={execLabel}
          onNotify={onNotify}
        />
      ))}
    </div>
  );
}

function MasterBreakDashboardContent({ token, selectedAccountExists, onNotify }) {
  const client = useQueryClient();
  const [tab, setTab] = useState("live");
  const [symbol, setSymbol] = useState("XAUUSD");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [fromDate, setFromDate] = useState(defaultFromDate);
  const [toDate, setToDate] = useState(defaultToDate);
  const [expandedId, setExpandedId] = useState("");
  const [backtestPage, setBacktestPage] = useState(1);
  const [backtestPageSize, setBacktestPageSize] = useState(DEFAULT_BACKTEST_PAGE_SIZE);
  const [latestBacktest, setLatestBacktest] = useState(null);
  const backtestPageCursorsRef = useRef({});

  const settingsQuery = useQuery({
    queryKey: ["master-break", "settings", token],
    enabled: Boolean(token),
    queryFn: () => api("/master-break/settings", "GET", undefined, token),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const activeQuery = useQuery({
    queryKey: ["master-break", "active", token],
    enabled: Boolean(token && selectedAccountExists && tab === "live"),
    queryFn: () => api("/master-break/active", "GET", undefined, token),
    refetchInterval: 3_000,
  });

  const historyQuery = useQuery({
    queryKey: ["master-break", "backtests", token, backtestPage, backtestPageSize],
    enabled: Boolean(token && (tab === "history" || tab === "backtest")),
    queryFn: async () => {
      const { data, cursors } = await fetchBacktestCursorPage(api, token, {
        targetPage: backtestPage,
        pageSize: backtestPageSize,
        cursors: backtestPageCursorsRef.current,
        endpoint: "/master-break/backtests",
      });
      backtestPageCursorsRef.current = cursors;
      return data;
    },
    placeholderData: (previous) => previous,
    refetchOnWindowFocus: false,
    staleTime: 5_000,
  });

  const detailQuery = useQuery({
    queryKey: ["master-break", "backtest", token, expandedId],
    enabled: Boolean(token && expandedId),
    queryFn: () => api(`/master-break/backtest/${encodeURIComponent(expandedId)}`, "GET", undefined, token),
    staleTime: 30_000,
  });

  useEffect(() => {
    backtestPageCursorsRef.current = {};
    setBacktestPage(1);
  }, [backtestPageSize]);

  const startMutation = useMutation({
    mutationFn: (payload) => api("/master-break/start", "POST", payload, token),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["master-break", "active"] });
      onNotify?.("success", "Master Break started");
    },
    onError: (err) => onNotify?.("error", err?.message || "Start failed"),
  });

  const stopMutation = useMutation({
    mutationFn: (payload) => api("/master-break/stop", "POST", payload, token),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["master-break", "active"] });
      onNotify?.("success", "Master Break stopped");
    },
    onError: (err) => onNotify?.("error", err?.message || "Stop failed"),
  });

  const runBacktestMutation = useMutation({
    mutationFn: (payload) => api("/master-break/backtest", "POST", payload, token),
    onSuccess: (data) => {
      backtestPageCursorsRef.current = {};
      setBacktestPage(1);
      setLatestBacktest(data);
      setExpandedId(data.id || data.backtest_id || "");
      client.invalidateQueries({ queryKey: ["master-break", "backtests"] });
      onNotify?.("success", "Backtest complete");
    },
    onError: (err) => onNotify?.("error", err?.message || "Backtest failed"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => api(`/master-break/backtest/${id}`, "DELETE", undefined, token),
    onSuccess: (_data, id) => {
      if (expandedId === id) setExpandedId("");
      if ((latestBacktest?.id || latestBacktest?.backtest_id) === id) setLatestBacktest(null);
      backtestPageCursorsRef.current = {};
      client.invalidateQueries({ queryKey: ["master-break", "backtests"] });
    },
  });

  const settings = settingsQuery.data || {};
  const activeRuns = activeQuery.data?.runs || [];
  const historyRows = historyQuery.data?.results || [];
  const pageInfo = historyQuery.data?.page_info || {};
  const totalCount = Number(pageInfo.total_count || 0);
  const totalPages = Math.max(1, Number(pageInfo.total_pages || 1));

  function handleStart() {
    startMutation.mutate({
      symbol: symbol.trim().toUpperCase() || "XAUUSD",
      risk_amount: Number(settings.risk_amount) || 100,
      master_timeframe: settings.master_timeframe,
      exec_timeframe: settings.exec_timeframe,
      breakeven_r: settings.breakeven_r,
      targets: settings.targets,
    });
  }

  function handleRunBacktest() {
    runBacktestMutation.mutate({
      symbol: symbol.trim().toUpperCase() || "XAUUSD",
      from_date: fromDate,
      to_date: toDate,
      risk_amount: Number(settings.risk_amount) || 100,
      master_timeframe: settings.master_timeframe,
      exec_timeframe: settings.exec_timeframe,
      breakeven_r: settings.breakeven_r,
      targets: settings.targets,
    });
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3">
      <section className="terminal-panel">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Master Break</p>
            <h2 className="mt-1 flex items-center gap-2 text-2xl font-bold text-[color:var(--text-strong)]">
              <Crosshair className="h-5 w-5" />
              XAUUSD dual-side breakout
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-[color:var(--text-muted)]">
              Master TF levels arm exec-TF entries with partial targets and breakeven. International MT5 / GOLD only.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold dark:border-slate-700"
          >
            <Settings className="h-4 w-4" />
            Settings
          </button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${
                tab === item.id
                  ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                  : "border border-slate-200 text-slate-700 dark:border-slate-700 dark:text-slate-200"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      {tab === "live" ? (
        <section className="terminal-panel min-h-0 flex-1 overflow-auto">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
              Symbol
              <input
                className="mt-1 w-36 rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              />
            </label>
            <button
              type="button"
              disabled={!selectedAccountExists || startMutation.isPending}
              onClick={handleStart}
              className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
            >
              Start
            </button>
            <button
              type="button"
              disabled={!activeRuns.length || stopMutation.isPending}
              onClick={() => stopMutation.mutate({ symbol: symbol.trim().toUpperCase() || "XAUUSD" })}
              className="rounded-lg border border-rose-200 px-3 py-1.5 text-sm font-semibold text-rose-700 disabled:opacity-50"
            >
              Stop
            </button>
          </div>
          <div className="mt-4 space-y-3">
            {activeRuns.length === 0 ? (
              <p className="text-sm text-slate-500">No active Master Break runs.</p>
            ) : (
              activeRuns.map((run) => (
                <div key={run.run_id || run.symbol} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold text-slate-900 dark:text-slate-100">
                      {run.display_symbol || run.symbol}
                    </p>
                    <p className="text-xs text-slate-500">
                      {run.settings?.master_timeframe}/{run.settings?.exec_timeframe} · bid {run.live_bid ?? "-"}
                    </p>
                  </div>
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    {["short", "long"].map((side) => {
                      const snap = run[side] || {};
                      return (
                        <div key={side} className="rounded-lg bg-slate-50 px-2 py-2 text-xs dark:bg-slate-800/60">
                          <p className="font-semibold uppercase">{side}</p>
                          <p className="mt-1 text-slate-600 dark:text-slate-300">
                            {snap.state || "-"}
                            {snap.entry != null ? ` · entry ${Number(snap.entry).toFixed(2)}` : ""}
                            {snap.stop_loss != null ? ` · SL ${Number(snap.stop_loss).toFixed(2)}` : ""}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                  {run.last_error ? <p className="mt-2 text-xs text-rose-600">{run.last_error}</p> : null}
                </div>
              ))
            )}
          </div>
        </section>
      ) : null}

      {tab === "backtest" ? (
        <section className="terminal-panel min-h-0 flex-1 overflow-auto">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
              Symbol
              <input
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              />
            </label>
            <DateField id="master-break-from" label="From" value={fromDate} onChange={setFromDate} />
            <DateField id="master-break-to" label="To" value={toDate} onChange={setToDate} />
            <div className="flex items-end">
              <button
                type="button"
                disabled={!selectedAccountExists || runBacktestMutation.isPending}
                onClick={handleRunBacktest}
                className="w-full rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
              >
                {runBacktestMutation.isPending ? "Running…" : "Run backtest"}
              </button>
            </div>
          </div>
          {latestBacktest ? (
            <div className="mt-4 space-y-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
              <SummaryGrid summary={latestBacktest.summary} />
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Details · master candles ({latestBacktest.master_rows?.length ?? latestBacktest.master_row_count ?? 0})
                </p>
                <MasterCandleList
                  rows={latestBacktest.master_rows || []}
                  execTimeframe={latestBacktest.settings?.exec_timeframe}
                  onNotify={onNotify}
                />
              </div>
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-500">Run a backtest to see summary and master-candle details.</p>
          )}
        </section>
      ) : null}

      {tab === "history" ? (
        <section className="terminal-panel flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="min-h-0 flex-1 space-y-2 overflow-auto">
            {historyRows.length === 0 ? (
              <p className="text-sm text-slate-500">No saved Master Break backtests.</p>
            ) : (
              historyRows.map((row) => {
                const id = row.id || row.backtest_id;
                const expanded = expandedId === id;
                const detail = expanded ? detailQuery.data : null;
                return (
                  <div key={id} className="rounded-xl border border-slate-200 dark:border-slate-700">
                    <div className="flex items-stretch gap-2 px-3 py-3">
                      <button
                        type="button"
                        onClick={() => setExpandedId(expanded ? "" : id)}
                        className="flex min-w-0 flex-1 items-center justify-between gap-3 text-left text-sm"
                      >
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-900 dark:text-slate-100">
                            {row.display_symbol || row.symbol}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            {row.from_date} → {row.to_date} · {row.master_row_count ?? "—"} masters ·{" "}
                            {row.trade_count ?? row.summary?.total_trades ?? 0} trades
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-semibold">{formatPnl(row.summary?.total_pnl)}</p>
                          <p className="text-xs text-slate-500">{expanded ? "Hide" : "Details"}</p>
                        </div>
                      </button>
                      <button
                        type="button"
                        disabled={deleteMutation.isPending}
                        onClick={() => deleteMutation.mutate(id)}
                        className="rounded-lg border border-rose-200 px-2 text-xs font-semibold text-rose-700"
                      >
                        Delete
                      </button>
                    </div>
                    {expanded ? (
                      <div className="border-t border-slate-100 px-3 py-3 dark:border-slate-800">
                        {detailQuery.isLoading ? (
                          <p className="text-xs text-slate-500">Loading…</p>
                        ) : (
                          <div className="space-y-3">
                            <SummaryGrid summary={detail?.summary || row.summary} />
                            <div>
                              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                                Details · master candles (
                                {detail?.master_rows?.length ?? detail?.master_row_count ?? row.master_row_count ?? 0})
                              </p>
                              <MasterCandleList
                                rows={detail?.master_rows || []}
                                execTimeframe={detail?.settings?.exec_timeframe || row.settings?.exec_timeframe}
                                onNotify={onNotify}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </div>
          <BacktestResultsPagination
            page={backtestPage}
            pageSize={backtestPageSize}
            totalCount={totalCount}
            totalPages={totalPages}
            onPageChange={setBacktestPage}
            onPageSizeChange={setBacktestPageSize}
            disabled={historyQuery.isFetching}
          />
        </section>
      ) : null}

      <MasterBreakSettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        token={token}
        initialSettings={settingsQuery.data}
        onSaved={(saved) => {
          client.setQueryData(["master-break", "settings", token], saved);
        }}
        onNotify={onNotify}
      />
    </div>
  );
}

export default function MasterBreakDashboard(props) {
  return (
    <QueryClientProvider client={queryClient}>
      <MasterBreakDashboardContent {...props} />
    </QueryClientProvider>
  );
}
