export default function SettingsTerminalPage({
  selectedMarket,
  onMarketChange,
  selectedAccountId,
  marketAccounts = [],
  onAccountChange,
  switchingAccount,
  onOpenManageAccount,
  onOpenNotifications,
  onOpenPlanner,
  onOpenAdmin,
  onLogout,
  isAdmin = false,
}) {
  return (
    <div className="grid h-full min-h-0 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Session Settings</p>
        <div className="mt-4 space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Market</span>
            <select
              value={selectedMarket}
              onChange={(event) => onMarketChange(event.target.value)}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none dark:border-slate-800 dark:bg-slate-950"
            >
              <option value="INTERNATIONAL">International Market</option>
              <option value="INDIAN">Indian Market</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Active Account</span>
            <select
              value={selectedAccountId || ""}
              onChange={(event) => onAccountChange(event.target.value)}
              disabled={switchingAccount}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none disabled:opacity-60 dark:border-slate-800 dark:bg-slate-950"
            >
              <option value="" disabled>Select account</option>
              {marketAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.account_name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Workspace Actions</p>
        <div className="mt-4 grid gap-2">
          <button type="button" onClick={onOpenManageAccount} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white dark:bg-slate-100 dark:text-slate-950">
            Manage Accounts
          </button>
          <button type="button" onClick={onOpenNotifications} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold dark:border-slate-800">
            Open Notifications
          </button>
          <button type="button" onClick={onOpenPlanner} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold dark:border-slate-800">
            Open Planner Workspace
          </button>
          {isAdmin ? (
            <button type="button" onClick={onOpenAdmin} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold dark:border-slate-800">
              Open Admin Console
            </button>
          ) : null}
          <button type="button" onClick={onLogout} className="rounded-lg border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-600 dark:border-rose-900/60 dark:text-rose-400">
            Logout
          </button>
        </div>
      </section>
    </div>
  );
}
