import IndianStrategyBuilder from "../indian/IndianStrategyBuilder";
import IndianPeCycleBacktestPanel from "../indian/IndianPeCycleBacktestPanel";
import IndianWatchlist from "../indian/IndianWatchlist";

function formatInr(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(value);
}

function MstockBadge() {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-sm">
      <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-black text-white">m</span>
      m.Stock
    </span>
  );
}

export default function IndianMarketWorkspace({
  me,
  token,
  onOpenAddAccount,
  onOpenConnectSession,
  indianMarketOverview,
  mobileWatchlistOpen,
  setMobileWatchlistOpen,
  onNotify,
}) {
  const accounts = (me?.accounts || []).filter(
    (account) => String(account.market_type || "INTERNATIONAL").toUpperCase() === "INDIAN"
  );
  const selectedAccount = accounts.find((account) => account.id === me?.selected_indian_account_id) || accounts[0] || null;
  const streamConnected = Boolean(indianMarketOverview?.stream_connected);

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[320px_1fr]">
      <aside className={`${mobileWatchlistOpen ? "block" : "hidden"} min-h-0 overflow-auto lg:block`}>
        <div className="mb-3 flex items-center justify-between rounded-2xl border border-indigo-100 bg-white px-4 py-3 shadow-sm lg:hidden">
          <p className="text-sm font-semibold text-slate-900">Watchlist</p>
          <button
            type="button"
            onClick={() => setMobileWatchlistOpen(false)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-lg text-slate-600"
            aria-label="Hide watchlist"
          >
            ×
          </button>
        </div>
        <IndianWatchlist token={token} selectedAccountExists={Boolean(selectedAccount)} items={indianMarketOverview?.watchlist || []} onNotify={onNotify} showHeader />
      </aside>
      <main className="min-h-0 space-y-3 overflow-auto">
        {!selectedAccount ? (
          <section className="rounded-3xl border border-amber-200 bg-amber-50 p-5 shadow-sm">
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-amber-700">Indian Market</p>
            <h2 className="mt-2 text-2xl font-bold text-slate-900">Add an Indian broker account to get started</h2>
            <button
              type="button"
              onClick={onOpenAddAccount}
              className="mt-4 inline-flex items-center rounded-2xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
            >
              Add Indian Broker
            </button>
          </section>
        ) : (
          <>
            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Indian Market</p>
                  <h2 className="mt-2 text-2xl font-bold text-slate-900">{selectedAccount.account_name}</h2>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-600">
                    <MstockBadge />
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${streamConnected ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-700"}`}>
                      Feed {streamConnected ? "Connected" : "Waiting"}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                      String(selectedAccount.session_status || "").toUpperCase() === "CONNECTED"
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : String(selectedAccount.session_status || "").toUpperCase() === "OTP_PENDING"
                          ? "border-amber-200 bg-amber-50 text-amber-700"
                          : "border-slate-200 bg-slate-50 text-slate-700"
                    }`}>
                      Session: {selectedAccount.session_status || "DISCONNECTED"}
                    </span>
                    <button
                      type="button"
                      onClick={() => onOpenConnectSession(selectedAccount)}
                      className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
                    >
                      {String(selectedAccount.session_status || "").toUpperCase() === "CONNECTED" ? "Reconnect Session" : "Connect Session"}
                    </button>
                    {selectedAccount.broker_user_id ? (
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700">
                        User {selectedAccount.broker_user_id}
                      </span>
                    ) : null}
                    {selectedAccount.account_id ? (
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700">
                        Account {selectedAccount.account_id}
                      </span>
                    ) : null}
                    {selectedAccount.currency_code ? (
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700">
                        {selectedAccount.currency_code}
                      </span>
                    ) : null}
                    {typeof selectedAccount.available_margin === "number" ? (
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700">
                        Available Margin {formatInr(selectedAccount.available_margin)}
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>
              <div className="mt-5 grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Market</p>
                  <p className="mt-2 text-lg font-semibold text-slate-900">Indian</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Broker</p>
                  <div className="mt-2"><MstockBadge /></div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Risk Per Trade</p>
                  <p className="mt-2 text-lg font-semibold text-slate-900">{formatInr(Number(selectedAccount.risk_amount))}</p>
                </div>
              </div>
              <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                {String(selectedAccount.session_status || "").toUpperCase() === "CONNECTED"
                  ? (streamConnected ? "Session connected. Live market data is flowing." : "Session connected. Waiting for market data feed.")
                  : "Connect the session to start live market data."}
              </div>
            </section>
            <IndianPeCycleBacktestPanel
              token={token}
              selectedAccount={selectedAccount}
              onNotify={onNotify}
            />
            <IndianStrategyBuilder token={token} selectedAccount={selectedAccount} />
          </>
        )}
      </main>
    </div>
  );
}
