import { useState } from "react";

function ConnectionBadge({ liveStatus }) {
  const labelMap = {
    connected: "Live connected",
    reconnecting: "Reconnecting",
    disconnected: "Offline"
  };
  const classMap = {
    connected: "border-emerald-200 bg-emerald-50 text-emerald-700",
    reconnecting: "border-amber-200 bg-amber-50 text-amber-700",
    disconnected: "border-slate-200 bg-slate-100 text-slate-600"
  };
  const dotClassMap = {
    connected: "bg-emerald-500",
    reconnecting: "bg-amber-400",
    disconnected: "bg-slate-400"
  };

  return (
    <>
      <span
        className={`inline-flex h-2.5 w-2.5 rounded-full lg:hidden ${dotClassMap[liveStatus] || dotClassMap.disconnected}`}
        aria-label={labelMap[liveStatus] || labelMap.disconnected}
        title={labelMap[liveStatus] || labelMap.disconnected}
      />
      <span className={`hidden rounded-full border px-3 py-1 text-xs font-semibold lg:inline-flex ${classMap[liveStatus] || classMap.disconnected}`}>
        {labelMap[liveStatus] || labelMap.disconnected}
      </span>
    </>
  );
}

export default function Header({
  me,
  liveStatus,
  runningPl,
  indianMarketOverview,
  selectedMarket,
  onMarketChange,
  onLogout,
  onAccountChange,
  onOpenAddAccount,
  switchingAccount,
  notifications,
  onOpenNotificationDetails,
  currentPage,
  onPageChange,
  mobileWatchlistOpen = false,
  onToggleMobileWatchlist,
  formatNotificationTimestamp,
}) {
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [mobileAccountMenuOpen, setMobileAccountMenuOpen] = useState(false);
  const [mobileNavMenuOpen, setMobileNavMenuOpen] = useState(false);
  const recentNotifications = notifications.slice(0, 6);
  const filteredAccounts = (me?.accounts || []).filter(
    (account) => String(account.market_type || "INTERNATIONAL").toUpperCase() === String(selectedMarket || "INTERNATIONAL").toUpperCase()
  );
  const selectedMarketAccount = filteredAccounts.find((account) => account.id === me?.selected_account_id) || filteredAccounts[0] || null;
  const hasSelectedMarketAccount = filteredAccounts.length > 0;
  const indianStatusOpen = String(indianMarketOverview?.status || "").toUpperCase() === "OPEN";
  const indianIndices = Array.isArray(indianMarketOverview?.indices) ? indianMarketOverview.indices : [];
  const navItems = [
    { id: "trading", label: "Trading" },
    { id: "trade-planner", label: "Trade Planner" },
    { id: "automation", label: "Automation" },
    ...(me?.is_admin ? [{ id: "admin", label: "Admin" }] : []),
  ];

  return (
    <header className="flex flex-col gap-0.5 rounded-2xl border border-indigo-700 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 px-2 py-0 text-white shadow-lg lg:flex-row lg:items-center lg:justify-between lg:px-2.5 lg:py-0">
      <div className="flex min-h-[2rem] items-center justify-between gap-1 lg:min-h-0">
        <div className="relative lg:hidden">
          <button
            type="button"
            onClick={() => {
              setMobileAccountMenuOpen((current) => !current);
              setMobileNavMenuOpen(false);
            }}
            className="inline-flex h-7 w-7 items-center justify-center rounded-xl border border-indigo-400/30 bg-white/10 text-base"
            aria-label="Open account menu"
          >
            ☰
          </button>
          {mobileAccountMenuOpen && me && (
            <div className="absolute left-0 top-12 z-30 w-[min(18rem,calc(100vw-2rem))] rounded-2xl border border-indigo-200 bg-white p-3 text-slate-900 shadow-2xl">
              <div className="space-y-3">
                <div className="rounded-xl bg-slate-100 px-3 py-2">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">SignalBridge</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">{`Welcome, ${me.full_name}`}</p>
                </div>
                {currentPage === "trading" && (
                  <button
                    type="button"
                    onClick={() => {
                      onToggleMobileWatchlist?.();
                      setMobileAccountMenuOpen(false);
                    }}
                    className="w-full rounded-xl bg-slate-100 px-3 py-2 text-left text-sm font-semibold text-slate-800"
                  >
                    {mobileWatchlistOpen ? "Hide Watchlist" : "Show Watchlist"}
                  </button>
                )}
                <select
                  value={selectedMarket || "INTERNATIONAL"}
                  onChange={(e) => {
                    onMarketChange(e.target.value);
                    setMobileAccountMenuOpen(false);
                  }}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none"
                >
                  <option value="INTERNATIONAL">International Market</option>
                  <option value="INDIAN">Indian Market</option>
                </select>
                <select
                  value={me.selected_account_id || ""}
                  disabled={switchingAccount}
                  onChange={(e) => {
                    onAccountChange(e.target.value);
                    setMobileAccountMenuOpen(false);
                  }}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none"
                >
                  <option value="" disabled>
                    Select account
                  </option>
                  {filteredAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.account_name}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => {
                    setMobileAccountMenuOpen(false);
                    onOpenAddAccount();
                  }}
                  className="w-full rounded-xl bg-indigo-600 px-3 py-2 text-sm font-semibold text-white"
                >
                  Add Account
                </button>
                <button
                  onClick={() => {
                    setMobileAccountMenuOpen(false);
                    setNotificationsOpen(false);
                    onOpenNotificationDetails();
                  }}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800"
                >
                  Notifications ({notifications.length})
                </button>
                <button
                  onClick={() => {
                    setMobileAccountMenuOpen(false);
                    onLogout();
                  }}
                  className="w-full rounded-xl border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-700"
                >
                  Logout
                </button>
              </div>
            </div>
          )}
        </div>
        <div className="flex flex-1 items-center justify-center lg:flex-none lg:justify-start">
          <div className="flex items-center gap-1">
            <img
              src="/signalbridge-logo-light.png"
              alt="SignalBridge"
              className="-my-2 h-[3.85rem] w-auto max-w-none object-contain lg:my-0 lg:h-[4.5rem]"
            />
            <div className="hidden lg:block">
              <p className="text-[11px] uppercase tracking-wide text-indigo-200">SignalBridge</p>
              <p className="hidden text-xs font-semibold lg:block">{me ? `Welcome, ${me.full_name}` : "Dashboard"}</p>
            </div>
            <div className="hidden lg:block">
              <ConnectionBadge liveStatus={liveStatus} />
            </div>
            {String(selectedMarket).toUpperCase() === "INDIAN" && hasSelectedMarketAccount ? (
              <div className="hidden items-center gap-2 lg:flex">
                <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold ${indianStatusOpen ? "border-emerald-300 bg-emerald-500/15 text-emerald-200" : "border-rose-300 bg-rose-500/15 text-rose-200"}`}>
                  <span className={`inline-flex h-2 w-2 rounded-full ${indianStatusOpen ? "bg-emerald-400" : "bg-rose-400"}`} />
                  Market {indianStatusOpen ? "Open" : "Closed"}
                </span>
                {typeof selectedMarketAccount?.available_margin === "number" ? (
                  <span className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold text-indigo-50">
                    Available Margin: {selectedMarketAccount.available_margin.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                ) : null}
                {indianIndices.map((item) => (
                  <span key={item.symbol} className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold text-indigo-50">
                    {item.display_name}: {typeof item.price === "number" ? item.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "--"}
                  </span>
                ))}
              </div>
            ) : null}
            {String(selectedMarket).toUpperCase() === "INTERNATIONAL" && Number.isFinite(Number(runningPl)) && Math.abs(Number(runningPl)) > 0 ? (
              <div className={`hidden rounded-full px-2.5 py-1 text-xs font-semibold lg:block ${Number(runningPl) >= 0 ? "bg-emerald-500/15 text-emerald-200" : "bg-rose-500/15 text-rose-200"}`}>
                Open P/L {Number(runningPl) >= 0 ? "+" : ""}{Number(runningPl).toFixed(2)}
              </div>
            ) : null}
          </div>
          <div className="hidden flex-wrap rounded-xl bg-white/10 p-0.5 lg:flex">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => onPageChange(item.id)}
                className={`rounded-lg px-3 py-0.5 text-sm font-semibold transition ${currentPage === item.id ? "bg-white text-slate-900" : "text-indigo-100"}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="relative lg:hidden">
          <button
            type="button"
            onClick={() => {
              setMobileNavMenuOpen((current) => !current);
              setMobileAccountMenuOpen(false);
            }}
            className="inline-flex h-7 w-7 items-center justify-center rounded-xl border border-indigo-400/30 bg-white/10 text-base"
            aria-label="Open navigation menu"
          >
            ☰
          </button>
          {mobileNavMenuOpen && (
            <div className="absolute right-0 top-12 z-30 w-[min(18rem,calc(100vw-2rem))] rounded-2xl border border-indigo-200 bg-white p-3 text-slate-900 shadow-2xl">
              <div className="space-y-2">
                {navItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      onPageChange(item.id);
                      setMobileNavMenuOpen(false);
                    }}
                    className={`w-full rounded-xl px-3 py-2 text-left text-sm font-semibold ${currentPage === item.id ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"}`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      {me && (
        <div className="hidden flex-col gap-1 sm:flex-row sm:items-center lg:flex">
          <select
            value={selectedMarket || "INTERNATIONAL"}
            disabled={switchingAccount}
            onChange={(e) => onMarketChange(e.target.value)}
            className="rounded-xl border border-indigo-400/30 bg-slate-900 px-3 py-1 text-sm outline-none"
          >
            <option value="INTERNATIONAL">International Market</option>
            <option value="INDIAN">Indian Market</option>
          </select>
          <select
            value={me.selected_account_id || ""}
            disabled={switchingAccount}
            onChange={(e) => onAccountChange(e.target.value)}
            className="rounded-xl border border-indigo-400/30 bg-slate-900 px-3 py-1 text-sm outline-none"
          >
            <option value="" disabled>
              Select account
            </option>
            {filteredAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.account_name}
              </option>
            ))}
          </select>
          <button onClick={onOpenAddAccount} className="rounded-xl bg-indigo-500 px-3 py-1 text-sm font-semibold hover:bg-indigo-600">
            Add Account
          </button>
          <div className="relative">
            <button
              onClick={() => setNotificationsOpen((current) => !current)}
              className="relative inline-flex h-8 w-8 items-center justify-center rounded-xl border border-indigo-400/30 hover:bg-indigo-900/40"
              aria-label="Notifications"
            >
              <span className="text-lg leading-none">🔔</span>
              {notifications.length > 0 && (
                <span className="absolute -right-1 -top-1 inline-flex min-h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1.5 text-[10px] font-bold text-white">
                  {notifications.length > 99 ? "99+" : notifications.length}
                </span>
              )}
            </button>
            {notificationsOpen && (
              <div className="absolute right-0 z-20 mt-2 w-[min(24rem,calc(100vw-2rem))] rounded-2xl border border-indigo-100 bg-white p-3 text-slate-900 shadow-2xl">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <p className="text-xs text-slate-500">Latest activity from your orders</p>
                  <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-[11px] font-semibold text-indigo-700">
                    {notifications.length}
                  </span>
                </div>
                {recentNotifications.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-indigo-200 bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">
                    No notifications yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {recentNotifications.map((notification) => (
                      <div key={notification.id} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                        <div className="mb-1 flex items-center justify-between gap-3">
                          <span className="truncate text-xs font-semibold uppercase tracking-wide text-slate-500">
                            {notification.symbol || notification.category}
                          </span>
                          <span className="shrink-0 text-[11px] text-slate-400">
                            {formatNotificationTimestamp(notification.timestamp)}
                          </span>
                        </div>
                        <p className="line-clamp-2 text-sm font-medium text-slate-800">{notification.activity}</p>
                      </div>
                    ))}
                  </div>
                )}
                <button
                  onClick={() => {
                    setNotificationsOpen(false);
                    onOpenNotificationDetails();
                  }}
                  className="mt-3 w-full rounded-xl bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
                >
                  View Details
                </button>
              </div>
            )}
          </div>
          <button onClick={onLogout} className="rounded-xl border border-indigo-400/30 px-3 py-1.5 text-sm font-semibold hover:bg-indigo-900/40">
            Logout
          </button>
        </div>
      )}
    </header>
  );
}
