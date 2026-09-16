import { useEffect, useState } from "react";

export default function AddIndianAccountModal({ open, onClose, onSubmit, embedded = false }) {
  const [form, setForm] = useState({ account_name: "", api_key: "", username: "", password: "", risk_amount: "100" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({ account_name: "", api_key: "", username: "", password: "", risk_amount: "100" });
    setError("");
    setSaving(false);
  }, [open]);

  if (!open) return null;

  const submit = async () => {
    if (!form.account_name.trim() || !form.api_key.trim() || !form.username.trim() || !form.password.trim() || Number(form.risk_amount) <= 0) {
      setError("Fill all fields with a valid risk amount.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSubmit({
        market_type: "INDIAN",
        broker_type: "MSTOCK",
        account_name: form.account_name.trim(),
        credentials: {
          api_key: form.api_key.trim(),
          username: form.username.trim(),
          password: form.password,
        },
        risk_amount: Number(form.risk_amount),
      });
      setSaving(false);
    } catch (err) {
      setError(err.message || "Unable to add Indian account.");
      setSaving(false);
    }
  };

  const content = (
      <div className={`${embedded ? "" : "w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"}`}>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Add Indian Broker</h3>

          </div>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-sm font-semibold text-slate-500 hover:bg-slate-100">Close</button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Market</span>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-medium text-slate-800">Indian Market</div>
          </div>
          <div className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Broker</span>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-medium text-slate-800">Mstock</div>
          </div>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Account Label</span>
            <input className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.account_name} onChange={(e) => setForm((c) => ({ ...c, account_name: e.target.value }))} placeholder="Primary Mstock" />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Risk Amount (INR)</span>
            <input type="number" min="1" className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.risk_amount} onChange={(e) => setForm((c) => ({ ...c, risk_amount: e.target.value }))} />
          </label>
          <label className="space-y-1 text-sm sm:col-span-2">
            <span className="font-medium text-slate-600">API Key</span>
            <input className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.api_key} onChange={(e) => setForm((c) => ({ ...c, api_key: e.target.value }))} placeholder="API key" />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">User ID</span>
            <input className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.username} onChange={(e) => setForm((c) => ({ ...c, username: e.target.value }))} placeholder="User ID" />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-600">Password</span>
            <input type="password" className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" value={form.password} onChange={(e) => setForm((c) => ({ ...c, password: e.target.value }))} placeholder="Password" />
          </label>
        </div>
        {error ? <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div> : null}
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700">Cancel</button>
          <button onClick={submit} disabled={saving} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400">{saving ? "Saving..." : "Save Account"}</button>
        </div>
      </div>
  );

  if (embedded) {
    return content;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
      {content}
    </div>
  );
}
