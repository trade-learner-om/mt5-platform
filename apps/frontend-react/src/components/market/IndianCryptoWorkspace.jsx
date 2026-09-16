function FeatureCard({ title, body }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
      <p className="text-sm font-semibold text-slate-900">{title}</p>
      <p className="mt-2 text-sm text-slate-600">{body}</p>
    </div>
  );
}

export default function IndianCryptoWorkspace() {
  return (
    <main className="min-h-0 flex-1 overflow-auto">
      <section className="rounded-3xl border border-cyan-200 bg-gradient-to-br from-slate-950 via-cyan-950 to-slate-900 p-6 text-white shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-300">Indian Crypto</p>
        <h2 className="mt-2 text-3xl font-black tracking-tight">Delta Exchange India workspace</h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-cyan-50/88">
          This market is now reserved inside the current SignalBridge UI as a separate workspace for Delta Exchange India.
          The workspace is intentionally isolated from MT5 international flows and from the current Indian equities setup.
        </p>
        <div className="mt-5 inline-flex items-center gap-2 rounded-full border border-cyan-300/30 bg-white/10 px-3 py-1.5 text-xs font-semibold text-cyan-100">
          <span className="inline-flex h-2.5 w-2.5 rounded-full bg-cyan-300" />
          Workspace prepared
        </div>
      </section>

      <section className="mt-4 grid gap-3 lg:grid-cols-3">
        <FeatureCard
          title="Market shell ready"
          body="The current UI can now switch into a dedicated Indian Crypto market without falling back to the MT5 or Indian equities workspaces."
        />
        <FeatureCard
          title="Delta integration pending"
          body="No Delta Exchange India authentication, market data, orders, or account onboarding has been connected yet."
        />
        <FeatureCard
          title="Safe next step"
          body="We can now define the exact Delta account model, workspace sections, and backend routes without disturbing the existing two markets."
        />
      </section>
    </main>
  );
}
