import { useEffect, useState } from "react";

export default function IndianSessionModal({ open, accountName, onClose, onRequestOtp, onVerifyOtp }) {
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [requesting, setRequesting] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [requested, setRequested] = useState(false);

  useEffect(() => {
    if (!open) return;
    setOtp("");
    setError("");
    setRequesting(false);
    setVerifying(false);
    setRequested(false);
  }, [open]);

  if (!open) return null;

  const handleRequestOtp = async () => {
    setRequesting(true);
    setError("");
    try {
      await onRequestOtp();
      setRequested(true);
    } catch (err) {
      setError(err.message || "Unable to request OTP.");
    } finally {
      setRequesting(false);
    }
  };

  const handleVerify = async () => {
    if (!otp.trim()) {
      setError("Enter the OTP received from Mstock.");
      return;
    }
    setVerifying(true);
    setError("");
    try {
      await onVerifyOtp(otp.trim());
    } catch (err) {
      setError(err.message || "Unable to verify OTP.");
      setVerifying(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Connect Indian Broker Session</h3>
            <p className="mt-1 text-sm text-slate-600">{accountName ? `${accountName} · ` : ""}Enter the OTP to connect today's session.</p>
          </div>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-sm font-semibold text-slate-500 hover:bg-slate-100">Close</button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button onClick={handleRequestOtp} disabled={requesting || verifying} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400">
            {requesting ? "Requesting..." : "Request OTP"}
          </button>
          {requested ? <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-2 text-xs font-semibold text-emerald-700">OTP requested</span> : null}
        </div>

        <label className="mt-4 block space-y-1 text-sm">
          <span className="font-medium text-slate-600">OTP</span>
          <input
            className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            placeholder="Enter OTP"
          />
        </label>

        {error ? <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div> : null}

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700">Cancel</button>
          <button onClick={handleVerify} disabled={verifying} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-400">
            {verifying ? "Connecting..." : "Connect"}
          </button>
        </div>
      </div>
    </div>
  );
}
