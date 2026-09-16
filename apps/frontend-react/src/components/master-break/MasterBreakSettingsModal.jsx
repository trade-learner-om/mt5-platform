import { useEffect, useState } from "react";

import { api } from "../../api";

const MASTER_TFS = ["H4", "H6", "H12", "D1"];
const EXEC_TFS = ["M1", "M5", "M15"];

const DEFAULT_SETTINGS = {
  risk_amount: 100,
  master_timeframe: "H6",
  exec_timeframe: "M5",
  breakeven_r: 1,
  targets: [
    { r: 2, qty_pct: 50 },
    { r: 4, qty_pct: 50 },
  ],
};

function cloneTargets(targets) {
  const rows = Array.isArray(targets) && targets.length ? targets : DEFAULT_SETTINGS.targets;
  return rows.map((item) => ({
    r: Number(item.r) || 0,
    qty_pct: Number(item.qty_pct) || 0,
  }));
}

export default function MasterBreakSettingsModal({
  open,
  onClose,
  token,
  initialSettings,
  onSaved,
  onNotify,
}) {
  const [riskAmount, setRiskAmount] = useState("100");
  const [masterTimeframe, setMasterTimeframe] = useState("H6");
  const [execTimeframe, setExecTimeframe] = useState("M5");
  const [breakevenR, setBreakevenR] = useState("1");
  const [targets, setTargets] = useState(cloneTargets(DEFAULT_SETTINGS.targets));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    const settings = initialSettings || DEFAULT_SETTINGS;
    setRiskAmount(String(settings.risk_amount ?? 100));
    setMasterTimeframe(String(settings.master_timeframe || "H6").toUpperCase());
    setExecTimeframe(String(settings.exec_timeframe || "M5").toUpperCase());
    setBreakevenR(String(settings.breakeven_r ?? 1));
    setTargets(cloneTargets(settings.targets));
  }, [open, initialSettings]);

  if (!open) return null;

  function updateTarget(index, key, value) {
    setTargets((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row))
    );
  }

  function addTarget() {
    setTargets((current) => [...current, { r: 2, qty_pct: 0 }]);
  }

  function removeTarget(index) {
    setTargets((current) => (current.length <= 1 ? current : current.filter((_, i) => i !== index)));
  }

  async function handleSave() {
    const payload = {
      risk_amount: Number(riskAmount) || 100,
      master_timeframe: masterTimeframe,
      exec_timeframe: execTimeframe,
      breakeven_r: Number(breakevenR) || 0,
      targets: targets.map((row) => ({
        r: Number(row.r) || 0,
        qty_pct: Number(row.qty_pct) || 0,
      })),
    };
    setSaving(true);
    try {
      const saved = await api("/master-break/settings", "PUT", payload, token);
      onSaved?.(saved);
      onNotify?.("success", "Master Break settings saved");
      onClose?.();
    } catch (err) {
      onNotify?.("error", err?.message || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Master Break settings</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-2 py-1 text-sm dark:border-slate-700"
          >
            Close
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Risk $
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
              value={riskAmount}
              onChange={(e) => setRiskAmount(e.target.value)}
            />
          </label>
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Breakeven R
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
              value={breakevenR}
              onChange={(e) => setBreakevenR(e.target.value)}
            />
          </label>
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Master TF
            <select
              className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
              value={masterTimeframe}
              onChange={(e) => setMasterTimeframe(e.target.value)}
            >
              {MASTER_TFS.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Exec TF
            <select
              className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
              value={execTimeframe}
              onChange={(e) => setExecTimeframe(e.target.value)}
            >
              {EXEC_TFS.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Targets</p>
            <button type="button" onClick={addTarget} className="text-xs font-semibold text-indigo-600">
              Add
            </button>
          </div>
          {targets.map((row, index) => (
            <div key={`target-${index}`} className="grid grid-cols-[1fr_1fr_auto] gap-2">
              <input
                className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
                value={row.r}
                onChange={(e) => updateTarget(index, "r", e.target.value)}
                placeholder="R"
              />
              <input
                className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
                value={row.qty_pct}
                onChange={(e) => updateTarget(index, "qty_pct", e.target.value)}
                placeholder="Qty %"
              />
              <button
                type="button"
                onClick={() => removeTarget(index)}
                className="rounded-lg border border-rose-200 px-2 text-xs font-semibold text-rose-700"
              >
                Del
              </button>
            </div>
          ))}
          <p className="text-[11px] text-slate-500">qty_pct must sum to 100</p>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold dark:border-slate-700"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={handleSave}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
