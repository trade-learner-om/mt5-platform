import { AnimatePresence, motion } from "framer-motion";
import { Activity, Bell, List, Menu, Moon, Settings, Sun, Workflow } from "lucide-react";
import { useMemo, useState } from "react";

import { cn } from "../../lib/cn";
import { useTheme } from "../theme/ThemeProvider";
import TerminalStatusFooter from "./TerminalStatusFooter";

function formatUsd(value) {
  if (value == null || value === "") return "--";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric);
}

const DEFAULT_NAV = [
  { id: "trading", label: "Watchlist", shortLabel: "Watch", icon: List },
  { id: "trap-reversal", label: "FSM Engines", shortLabel: "FSM", icon: Workflow },
  { id: "positions", label: "Positions", shortLabel: "Pos", icon: Activity },
  { id: "settings", label: "Settings", shortLabel: "Set", icon: Settings },
];

export default function AppShell({
  currentPage,
  onPageChange,
  navItems = DEFAULT_NAV,
  serverConnected = true,
  lastServerStateLogAt = null,
  totalEquity = null,
  selectedAccountLabel = "",
  notificationsCount = 0,
  onOpenNotifications,
  children,
}) {
  const { resolvedTheme, toggleTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const current = useMemo(
    () => navItems.find((item) => item.id === currentPage) || navItems[0],
    [currentPage, navItems]
  );

  const Sidebar = (
    <div className="flex h-full flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="flex h-16 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        {!collapsed ? (
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">
              SignalBridge
            </p>
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
              Execution Terminal
            </p>
          </div>
        ) : <div className="h-8 w-8 rounded-lg bg-slate-900 dark:bg-slate-100" />}
        <button
          type="button"
          onClick={() => setCollapsed((currentValue) => !currentValue)}
          className="hidden rounded-lg p-2 hover:bg-slate-100 dark:hover:bg-slate-800 lg:inline-flex"
        >
          <Menu className="h-4 w-4" />
        </button>
      </div>

      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = currentPage === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                onPageChange(item.id);
                setMobileSidebarOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                active
                  ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-950"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                collapsed ? "justify-center" : ""
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed ? <span>{item.label}</span> : null}
            </button>
          );
        })}
      </nav>

      {!collapsed ? (
        <div className="border-t border-slate-200 px-3 py-3 dark:border-slate-800">
          <p className="truncate text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
            Active Account
          </p>
          <p className="mt-1 truncate text-sm font-medium text-slate-900 dark:text-slate-100">
            {selectedAccountLabel || "No account selected"}
          </p>
        </div>
      ) : null}
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 text-slate-700 dark:bg-slate-950 dark:text-slate-300">
      <div className="flex h-screen overflow-hidden">
        <aside className={cn("hidden border-r border-slate-200 dark:border-slate-800 lg:block", collapsed ? "w-16" : "w-60")}>
          {Sidebar}
        </aside>

        <AnimatePresence>
          {mobileSidebarOpen ? (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-40 bg-slate-950/60 lg:hidden"
                onClick={() => setMobileSidebarOpen(false)}
              />
              <motion.aside
                initial={{ x: -24, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: -24, opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="fixed inset-y-0 left-0 z-50 w-64 border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 lg:hidden"
              >
                {Sidebar}
              </motion.aside>
            </>
          ) : null}
        </AnimatePresence>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setMobileSidebarOpen(true)}
                className="rounded-lg p-2 hover:bg-slate-100 dark:hover:bg-slate-800 lg:hidden"
              >
                <Menu className="h-4 w-4" />
              </button>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
                  {current?.label || "Terminal"}
                </p>
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                  Pure Execution and Data Terminal
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="hidden items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs dark:border-slate-800 md:inline-flex">
                <span className={cn("h-2 w-2 rounded-full", serverConnected ? "bg-emerald-500 animate-pulse" : "bg-rose-500")} />
                <span className="font-medium">{serverConnected ? "Server Ping" : "Server Offline"}</span>
              </div>
              <div className="hidden items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800 md:inline-flex">
                <span className="text-xs text-slate-500 dark:text-slate-400">Total Equity</span>
                <span className="font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                  {formatUsd(totalEquity)}
                </span>
              </div>
              <button
                type="button"
                onClick={onOpenNotifications}
                className="relative rounded-lg border border-slate-200 p-2 hover:bg-slate-100 dark:border-slate-800 dark:hover:bg-slate-800"
              >
                <Bell className="h-4 w-4" />
                {notificationsCount > 0 ? (
                  <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-rose-500" />
                ) : null}
              </button>
              <button
                type="button"
                onClick={toggleTheme}
                className="rounded-lg border border-slate-200 p-2 hover:bg-slate-100 dark:border-slate-800 dark:hover:bg-slate-800"
              >
                {resolvedTheme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
            </div>
          </header>

          <main className="min-h-0 flex-1 overflow-hidden p-4 pb-2">
            {children}
          </main>

          <TerminalStatusFooter
            serverConnected={serverConnected}
            lastServerStateLogAt={lastServerStateLogAt}
          />
        </div>
      </div>
    </div>
  );
}
