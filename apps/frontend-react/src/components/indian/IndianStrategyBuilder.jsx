import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import SymbolIcon from "../SymbolIcon";
import IndianInstrumentSearch from "./IndianInstrumentSearch";

function formatInr(value) {
  if (value === "Unlimited") return "Unlimited";
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function buildPayoffPoint(price, leg) {
  const actionSign = String(leg.action || "BUY").toUpperCase() === "BUY" ? 1 : -1;
  const quantity = Math.max(Number(leg.lots || 1), 1) * Math.max(Number(leg.lot_size || 1), 1);
  const premium = Number(leg.price || 0);
  const strike = Number(leg.strike || 0);
  const type = String(leg.instrument_type || "").toUpperCase();
  const optionType = String(leg.option_type || "").toUpperCase();
  if (type === "OPTION" || optionType === "CE" || optionType === "PE") {
    const intrinsic = optionType === "PE" ? Math.max(strike - price, 0) : Math.max(price - strike, 0);
    return actionSign * (intrinsic - premium) * quantity;
  }
  return actionSign * (price - premium) * quantity;
}

function summarizeExtremes(series) {
  if (!series.length) {
    return { maxProfit: null, maxLoss: null, rr: null };
  }
  const values = series.map((point) => point.payoff);
  const maxValue = Math.max(...values);
  const minValue = Math.min(...values);
  const lastSlope = values.length > 2 ? values[values.length - 1] - values[values.length - 3] : 0;
  const firstSlope = values.length > 2 ? values[2] - values[0] : 0;
  const maxAtEdge = maxValue === values[0] || maxValue === values[values.length - 1];
  const minAtEdge = minValue === values[0] || minValue === values[values.length - 1];

  const maxProfit = maxAtEdge && ((maxValue === values[values.length - 1] && lastSlope > 0) || (maxValue === values[0] && firstSlope < 0))
    ? "Unlimited"
    : maxValue;
  const maxLoss = minAtEdge && ((minValue === values[values.length - 1] && lastSlope < 0) || (minValue === values[0] && firstSlope > 0))
    ? "Unlimited"
    : Math.abs(minValue);

  const rr = typeof maxProfit === "number" && typeof maxLoss === "number" && maxLoss > 0 ? maxProfit / maxLoss : null;
  return { maxProfit, maxLoss, rr };
}

function payoffLine(series, width, height) {
  if (!series.length) return "";
  const values = series.map((point) => point.payoff);
  const maxY = Math.max(...values, 0);
  const minY = Math.min(...values, 0);
  const rangeY = Math.max(maxY - minY, 1);
  const rangeX = Math.max(series[series.length - 1].price - series[0].price, 1);
  return series
    .map((point) => {
      const x = ((point.price - series[0].price) / rangeX) * width;
      const y = height - ((point.payoff - minY) / rangeY) * height;
      return `${x},${y}`;
    })
    .join(" ");
}

export default function IndianStrategyBuilder({ token, selectedAccount }) {
  const [legs, setLegs] = useState([]);
  const [marginPreview, setMarginPreview] = useState({ legs: [], required_margin: 0 });
  const [marginLoading, setMarginLoading] = useState(false);
  const [marginError, setMarginError] = useState("");

  const canSearch = Boolean(selectedAccount) && String(selectedAccount.session_status || "").toUpperCase() === "CONNECTED";

  const addLeg = async (instrument) => {
    setLegs((current) => [
      ...current,
      {
        symbol: instrument.symbol,
        exchange: instrument.exchange,
        instrument_token: instrument.instrument_token,
        instrument_type: instrument.instrument_type,
        option_type: instrument.option_type,
        strike: instrument.strike,
        expiry: instrument.expiry,
        lot_size: Number(instrument.lot_size || 1),
        underlying: instrument.underlying,
        action: "BUY",
        lots: 1,
        price: 0,
      },
    ]);
  };

  const updateLeg = (index, patch) => {
    setLegs((current) => current.map((leg, legIndex) => (legIndex === index ? { ...leg, ...patch } : leg)));
  };

  const removeLeg = (index) => {
    setLegs((current) => current.filter((_, legIndex) => legIndex !== index));
  };

  useEffect(() => {
    if (!canSearch || !legs.length) {
      setMarginPreview({ legs: [], required_margin: 0 });
      setMarginError("");
      return;
    }
    const payload = {
      legs: legs.map((leg) => ({
        symbol: leg.symbol,
        exchange: leg.exchange,
        instrument_token: leg.instrument_token,
        instrument_type: leg.instrument_type,
        option_type: leg.option_type,
        strike: leg.strike,
        expiry: leg.expiry,
        lot_size: Number(leg.lot_size || 1),
        action: leg.action,
        lots: Number(leg.lots || 1),
        price: Number(leg.price || 0),
      })),
    };
    const timer = setTimeout(async () => {
      setMarginLoading(true);
      setMarginError("");
      try {
        const data = await api("/indian/strategy/preview", "POST", payload, token);
        setMarginPreview(data || { legs: [], required_margin: 0 });
      } catch (err) {
        setMarginError(err.message || "Unable to calculate margin.");
      } finally {
        setMarginLoading(false);
      }
    }, 240);
    return () => clearTimeout(timer);
  }, [canSearch, legs, token]);

  const payoffSeries = useMemo(() => {
    if (!legs.length) return [];
    const strikes = legs.map((leg) => Number(leg.strike)).filter((value) => Number.isFinite(value) && value > 0);
    const prices = legs.map((leg) => Number(leg.price)).filter((value) => Number.isFinite(value) && value > 0);
    const anchor = strikes.length ? strikes : prices;
    const center = anchor.length ? anchor.reduce((sum, value) => sum + value, 0) / anchor.length : 100;
    const spread = Math.max(...anchor, center) - Math.min(...anchor, center);
    const range = Math.max(spread * 1.8, center * 0.15, 50);
    const start = Math.max(center - range, 1);
    const end = center + range;
    const steps = 120;
    const series = [];
    for (let index = 0; index <= steps; index += 1) {
      const price = start + ((end - start) * index) / steps;
      const payoff = legs.reduce((sum, leg) => sum + buildPayoffPoint(price, leg), 0);
      series.push({ price, payoff });
    }
    return series;
  }, [legs]);

  const summary = useMemo(() => summarizeExtremes(payoffSeries), [payoffSeries]);
  const graphPoints = useMemo(() => payoffLine(payoffSeries, 680, 260), [payoffSeries]);

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">FnO Strategy Builder</p>
          <h3 className="mt-1 text-2xl font-bold text-slate-900">Build the trade, see the payoff</h3>
        </div>
        <div className="w-full max-w-xl">
          <IndianInstrumentSearch
            token={token}
            disabled={!canSearch}
            placeholder={canSearch ? "Type NIFTY 25000, BANKNIFTY, RELIANCE..." : "Connect the Indian session first"}
            onSelect={addLeg}
            onError={() => undefined}
          />
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Max Profit</p>
          <p className="mt-2 text-lg font-semibold text-emerald-700">{formatInr(summary.maxProfit)}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Max Loss</p>
          <p className="mt-2 text-lg font-semibold text-rose-700">{formatInr(summary.maxLoss)}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Risk / Reward</p>
          <p className="mt-2 text-lg font-semibold text-slate-900">{typeof summary.rr === "number" ? summary.rr.toFixed(2) : "--"}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Required Margin</p>
          <p className="mt-2 text-lg font-semibold text-slate-900">{marginLoading ? "Calculating..." : formatInr(marginPreview.required_margin)}</p>
        </div>
      </div>

      <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <p className="text-sm font-semibold text-slate-900">Strategy Legs</p>
          <p className="text-xs text-slate-500">Use the search box above, then fine-tune side, lots, and premium.</p>
        </div>
        {legs.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-white text-left text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-semibold">Instrument</th>
                  <th className="px-4 py-3 font-semibold">Side</th>
                  <th className="px-4 py-3 font-semibold">Lots</th>
                  <th className="px-4 py-3 font-semibold">Premium</th>
                  <th className="px-4 py-3 font-semibold">Lot Size</th>
                  <th className="px-4 py-3 font-semibold">Margin</th>
                  <th className="px-4 py-3 font-semibold"></th>
                </tr>
              </thead>
              <tbody>
                {legs.map((leg, index) => {
                  const marginLeg = marginPreview.legs?.[index] || {};
                  return (
                    <tr key={`${leg.symbol}-${leg.instrument_token}-${index}`} className="border-t border-slate-200">
                      <td className="px-4 py-3 align-top">
                        <div className="flex items-start gap-3">
                          <SymbolIcon symbol={leg.symbol} />
                          <div>
                            <p className="font-semibold text-slate-900">{leg.symbol}</p>
                            <p className="text-xs text-slate-500">{[leg.exchange, leg.instrument_type, leg.expiry, leg.strike, leg.option_type].filter(Boolean).join(" · ")}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <select
                          value={leg.action}
                          onChange={(event) => updateLeg(index, { action: event.target.value })}
                          className="rounded-xl border border-slate-300 bg-white px-3 py-2 font-semibold outline-none"
                        >
                          <option value="BUY">Buy</option>
                          <option value="SELL">Sell</option>
                        </select>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <input
                          type="number"
                          min="1"
                          value={leg.lots}
                          onChange={(event) => updateLeg(index, { lots: Math.max(Number(event.target.value || 1), 1) })}
                          className="w-24 rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
                        />
                      </td>
                      <td className="px-4 py-3 align-top">
                        <input
                          type="number"
                          min="0"
                          step="0.05"
                          value={leg.price}
                          onChange={(event) => updateLeg(index, { price: Number(event.target.value || 0) })}
                          className="w-28 rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
                        />
                      </td>
                      <td className="px-4 py-3 align-top text-slate-700">{leg.lot_size || "--"}</td>
                      <td className="px-4 py-3 align-top text-slate-700">{marginLeg.margin_error ? <span className="text-rose-600">{marginLeg.margin_error}</span> : formatInr(marginLeg.required_margin)}</td>
                      <td className="px-4 py-3 align-top text-right">
                        <button type="button" onClick={() => removeLeg(index)} className="rounded-lg px-2 py-1 text-xs font-semibold text-rose-600 hover:bg-rose-50">Remove</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-4 py-8 text-sm text-slate-500">Start with the search box and add the first leg. Typing something like NIFTY 25000 will surface matching options.</div>
        )}
      </div>

      <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-900">Payoff Graph</p>
          {marginError ? <p className="text-xs font-semibold text-rose-600">{marginError}</p> : null}
        </div>
        {payoffSeries.length ? (
          <div className="overflow-x-auto">
            <svg viewBox="0 0 680 260" className="h-[260px] w-full min-w-[680px] rounded-xl bg-white">
              <line x1="0" y1="130" x2="680" y2="130" stroke="#cbd5e1" strokeDasharray="5 5" />
              <polyline fill="none" stroke="#4f46e5" strokeWidth="3" points={graphPoints} />
            </svg>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-sm text-slate-500">
            Add at least one leg to render the payoff.
          </div>
        )}
      </div>
    </section>
  );
}
