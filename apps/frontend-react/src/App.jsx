import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlarmClock, Crosshair, Layers, List, Settings, Workflow } from "lucide-react";
import { api, openLiveSocket, liveSnapshotHasFreshPrices, pingBackendHealth, WS_LIVE_STALE_MS } from "./api";
import AppShell from "./components/layout/AppShell";
import ManageAccountModal from "./components/ManageAccountModal";
import SymbolIcon from "./components/SymbolIcon";
import TrapReversalDashboard from "./pages/TrapReversalDashboard";
import MasterBreakDashboard from "./pages/MasterBreakDashboard";
import InternationalMarketWorkspace from "./components/market/InternationalMarketWorkspace";
import IndianMarketWorkspace from "./components/market/IndianMarketWorkspace";
import IndianSessionModal from "./components/indian/IndianSessionModal";
import SettingsTerminalPage from "./components/terminal/SettingsTerminalPage";
import ScheduledTradePanel from "./components/scheduled-trade/ScheduledTradePanel";
import UnmitigatedSwingsPanel from "./components/structure/UnmitigatedSwingsPanel";
import {
  decimalPlaces,
  formatPriceWithDigits,
  livePriceFromTick,
  livePriceKey,
  lookupLiveTick,
  priceStepForDigits,
  resolveSymbolPriceDigits,
  roundPriceToDigits,
} from "./utils/pricePrecision";

const APP_TIME_ZONE = "Asia/Calcutta";

function parseAppTimestamp(value) {
  if (!value) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const text = String(value).trim();
  if (!text) return null;
  const hasExplicitZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(text);
  const normalized = hasExplicitZone ? text : `${text}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function hasVisibleFieldError(fieldName, touchedFields, submitAttempted) {
  return Boolean(submitAttempted || touchedFields[fieldName]);
}

function inputTone(hasError) {
  return hasError ? "border-rose-300 focus:border-rose-500" : "border-slate-300 focus:border-indigo-500";
}

function formatPrice(value, relatedValues = [], minimumPrecision = 0, maxDigits = null) {
  return formatPriceWithDigits(value, maxDigits, relatedValues, minimumPrecision);
}

function formatQty(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toFixed(2);
}

function isEditablePendingOrder(status) {
  return ["PENDING", "PLACEMENT_PENDING", "WAITING_TRIGGER", "DEFERRED_MARKET_OPEN"].includes(String(status || "").toUpperCase());
}

function isDeferredMarketOpenOrder(row) {
  return String(row?.status || "").toUpperCase() === "DEFERRED_MARKET_OPEN";
}

function isMarketClosedOfferOrder(row) {
  return Boolean(row?.manual_context?.market_closed_offer) && String(row?.status || "").toUpperCase() === "PLACEMENT_PENDING";
}

function formatNotificationTimestamp(value) {
  if (!value) return "-";
  const date = parseAppTimestamp(value);
  if (!date) return value;
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: APP_TIME_ZONE
  }) + " IST";
}

function formatTimeOnly(value) {
  if (!value) return "-";
  const date = parseAppTimestamp(value);
  if (!date) return String(value);
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: APP_TIME_ZONE,
  });
}

function formatDisplayTimestamp(value) {
  if (!value) return "-";
  const date = parseAppTimestamp(value);
  if (!date) return String(value);
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: APP_TIME_ZONE,
  });
}

function formatDateTimeLocalInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function formatBacktestDateTimeRange(backtest, fallbackFrom, fallbackTo) {
  const fromValue = backtest?.fromDateTime || fallbackFrom || "";
  const toValue = backtest?.toDateTime || fallbackTo || "";
  const formatOne = (value) => {
    if (!value) return "-";
    const date = parseAppTimestamp(value);
    if (!date) return String(value);
    return date.toLocaleString([], {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: APP_TIME_ZONE,
    });
  };
  return `${formatOne(fromValue)} to ${formatOne(toValue)}`;
}

function formatBacktestTimestamp(value) {
  if (!value) return "-";
  const date = parseAppTimestamp(value);
  if (!date) return value;
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: APP_TIME_ZONE
  }).formatToParts(date);
  const get = (type) => parts.find((part) => part.type === type)?.value || "";
  return `${get("day")}-${get("month")}, ${get("hour")}:${get("minute")}`;
}

function formatTargetPrices(values) {
  const normalized = Array.isArray(values) ? values.filter((value) => value !== null && value !== undefined && value !== "") : [];
  if (!normalized.length) return "-";
  return normalized.map((value) => formatPrice(Number(value))).join(", ");
}

function formatTradeDirection(direction) {
  return String(direction || "").toUpperCase() === "SHORT" ? "SHORT" : "LONG";
}

function formatActivationMode(mode) {
  return String(mode || "").toUpperCase() === "CONDITIONAL" ? "CONDITIONAL" : "IMMEDIATE";
}

function isLiquidityReversalStrategy(value) {
  return String(value || "").toUpperCase() === "LIQUIDITY_REVERSAL";
}

function normalizeAutomationTimeframe(value) {
  const normalized = String(value || "5m").trim().toLowerCase();
  if (["1m", "m1", "1", "1min", "1minute"].includes(normalized)) return "1m";
  return "5m";
}

function formatAutomationTimeframe(value) {
  return normalizeAutomationTimeframe(value) === "1m" ? "1 minute" : "5 minutes";
}

function parseBooleanFlag(value, fallback = false) {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  const normalized = String(value).trim().toLowerCase();
  if (["true", "1", "yes", "y", "on"].includes(normalized)) return true;
  if (["false", "0", "no", "n", "off", ""].includes(normalized)) return false;
  return fallback;
}

function formatCurrencyValue(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numericValue);
}

/** Possible profit/loss at target vs SL, e.g. "200/80". Requires known SL + Target + risk. */
function expectedRewardRiskLabel(order) {
  const stop = Number(order?.stop_loss);
  const target = Number(order?.target);
  const entry = Number(order?.entry);
  const risk = Number(order?.risk_amount);
  if (!Number.isFinite(stop) || stop <= 0) return null;
  if (!Number.isFinite(target) || target <= 0) return null;
  if (!Number.isFinite(risk) || risk <= 0) return null;
  let rr = Number(order?.rr_ratio);
  if (!Number.isFinite(rr) || rr <= 0) {
    if (!Number.isFinite(entry) || entry <= 0) return null;
    const riskDist = Math.abs(entry - stop);
    const rewardDist = Math.abs(target - entry);
    if (riskDist <= 0) return null;
    rr = rewardDist / riskDist;
  }
  const reward = risk * rr;
  if (!Number.isFinite(reward) || reward <= 0) return null;
  return `${Math.round(reward)}/${Math.round(risk)}`;
}

function renderExpectedRewardRisk(order) {
  const label = expectedRewardRiskLabel(order);
  if (!label) return <span className="text-slate-400">—</span>;
  const [reward, risk] = label.split("/");
  return (
    <span className="font-semibold tabular-nums" title="Possible profit / loss (target / SL)">
      <span className="text-emerald-700 dark:text-emerald-400">{reward}</span>
      <span className="text-slate-400">/</span>
      <span className="text-rose-700 dark:text-rose-400">{risk}</span>
    </span>
  );
}

function formatPartialExits(value) {
  if (!Array.isArray(value) || value.length === 0) return "-";
  return value
    .map((item) => `${formatPrice(item.price)}(${item.closeQuantity ?? "-"})`)
    .join(" | ");
}

function instrumentDirectionBadge(direction) {
  return String(direction || "").toUpperCase() === "SHORT"
    ? { label: "S", tone: "bg-rose-100 text-rose-700 ring-rose-200" }
    : { label: "L", tone: "bg-emerald-100 text-emerald-700 ring-emerald-200" };
}

function tradePlannerSwingTypeDisplay(strongSwingType) {
  const normalized = String(strongSwingType || "").toUpperCase();
  if (normalized === "STRONG_HIGH") {
    return {
      label: "Short Bias",
      detail: "Strong High",
      icon: "▼",
      tone: "border-rose-200 bg-rose-50 text-rose-800",
      iconTone: "bg-rose-100 text-rose-700",
    };
  }
  if (normalized === "STRONG_LOW") {
    return {
      label: "Long Bias",
      detail: "Strong Low",
      icon: "▲",
      tone: "border-emerald-200 bg-emerald-50 text-emerald-800",
      iconTone: "bg-emerald-100 text-emerald-700",
    };
  }
  return null;
}

function formatCandleAnalysisSummary(analysis, direction) {
  if (!analysis?.candle) return { label: "No completed candle yet", ohlc: "-" };
  const candle = analysis.candle;
  const ohlc = `O ${formatPrice(candle.open)}  H ${formatPrice(candle.high)}  L ${formatPrice(candle.low)}  C ${formatPrice(candle.close)}`;
  const directionUpper = String(direction || "").toUpperCase();
  const label = directionUpper === "SHORT"
    ? (analysis.hammer ? "Hammer" : "Not Hammer")
    : (analysis.shootingStar ? "Shooting Star" : "Not Shooting Star");
  return { label, ohlc };
}

function isDesiredCandle(analysis, direction) {
  const directionUpper = String(direction || "").toUpperCase();
  if (!analysis?.candle) return false;
  return directionUpper === "SHORT" ? Boolean(analysis.hammer) : Boolean(analysis.shootingStar);
}

const STATUS_LABELS = {
  IDLE: "Idle",
  WAITING_FOR_PIVOT: "Waiting For Pivot",
  WAITING_FOR_C0_CLOSE: "Waiting For C0 Close",
  WAITING_FOR_C1_CLOSE: "Waiting For C1 Close",
  WAITING_FOR_REENTRY_C1_CLOSE: "Waiting For Re-entry C1 Close",
  LIQUIDITY_REVERSAL_ACTIVATED: "Liquidity Reversal Activated",
  EXECUTION_STARTED: "Execution Started",
  WAITING_FOR_ACTIVATION: "Waiting For Activation",
  ORDER_PLACED: "Order Placed",
  POSITION_OPEN: "Position Open",
  EXECUTION_STOPPED: "Execution Stopped",
  EXECUTION_COMPLETED: "Execution Completed",
  EXECUTION_FAILED: "Execution Failed",
  REENTRY_WAIT: "Re-entry Wait",
  SETUP_VALIDATED: "Setup Validated",
  INVALIDATED: "Invalidated",
  TARGET: "Target Hit",
  STOP_LOSS: "Stop Loss Hit",
  SL_TARGET_1: "Stop Loss Hit After Target 1",
  SL_TARGET_2: "Stop Loss Hit After Target 2",
  SL_TARGET_3: "Stop Loss Hit After Target 3",
  ENTRY_NOT_TRIGGERED_WITHIN_C1_C2: "Entry did not trigger within two candles",
  REENTRY_NOT_TRIGGERED_WITHIN_2_CANDLES: "Re-entry did not trigger within two candles",
  PLACEMENT_PENDING: "Placement Pending",
  WAITING_TRIGGER: "Waiting Trigger",
  PENDING: "Pending",
  DEFERRED_MARKET_OPEN: "Pending (Mon 4:30 IST)",
  FILLED: "Filled",
  PARTIALLY_CLOSED: "Partially Closed",
  CLOSED: "Closed",
  CANCELLED: "Cancelled",
  FAILED: "Failed",
  LONG_SETUP_ACTIVE: "Long Setup Active",
  SHORT_SETUP_ACTIVE: "Short Setup Active",
  WAITING: "Waiting",
  ACTIVE: "Active",
};

function humanizeStatus(value) {
  const upper = String(value || "").toUpperCase();
  if (!upper) return "-";
  if (STATUS_LABELS[upper]) return STATUS_LABELS[upper];
  return upper
    .split("_")
    .map((part) => titleCaseWord(part))
    .join(" ");
}

function formatSetupTypeLabel(value, strategyOptions = []) {
  const matched = strategyOptions.find((item) => item.id === String(value || "").toUpperCase());
  if (matched?.label) return matched.label;
  return humanizeStatus(value);
}

function formatRetryCount(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? String(Math.floor(numeric)) : "1";
}

function ensureBacktestTargetRows(values, minimumRows = 1) {
  const normalized = Array.isArray(values) ? values.map((value) => value === null || value === undefined ? "" : String(value)) : [];
  while (normalized.length > 1 && normalized[normalized.length - 1] === "") {
    normalized.pop();
  }
  if (normalized.every((value) => value === "")) {
    normalized.splice(0, normalized.length, "");
  }
  while (normalized.length < minimumRows) {
    normalized.push("");
  }
  return normalized;
}

function finalExitQuantity(result) {
  const entryQuantity = Number(result?.quantity || 0);
  if (!Number.isFinite(entryQuantity) || entryQuantity <= 0) return null;
  const partialClosed = Array.isArray(result?.partialExits)
    ? result.partialExits.reduce((sum, item) => sum + Number(item?.closeQuantity || 0), 0)
    : 0;
  const remaining = Math.max(entryQuantity - partialClosed, 0);
  return Number(remaining.toFixed(2));
}

function formatFinalExit(result) {
  if (result?.exitPrice === null || result?.exitPrice === undefined || result?.exitPrice === "") return "-";
  const quantity = finalExitQuantity(result);
  return `${formatPrice(result.exitPrice, [result.entryPrice, result.stopLoss, result.partialExitPrice])}(${quantity == null ? "-" : formatQty(quantity)})`;
}

function rrAtPrice(entryPrice, stopLoss, exitPrice, side) {
  const normalizedEntry = Number(entryPrice);
  const normalizedStop = Number(stopLoss);
  const normalizedExit = Number(exitPrice);
  if (!Number.isFinite(normalizedEntry) || !Number.isFinite(normalizedStop) || !Number.isFinite(normalizedExit)) return null;
  const risk = Math.abs(normalizedEntry - normalizedStop);
  if (!risk) return 0;
  return String(side || "").toUpperCase() === "SHORT"
    ? (normalizedEntry - normalizedExit) / risk
    : (normalizedExit - normalizedEntry) / risk;
}

function pipSizeForSymbol(symbol) {
  const upper = String(symbol || "").toUpperCase();
  if (upper.includes("XAU") || upper.includes("GOLD")) return 0.01;
  return upper.includes("JPY") ? 0.01 : 0.0001;
}

const KNOWN_CURRENCY_CODES = new Set([
  "USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "SGD", "HKD",
  "NOK", "SEK", "DKK", "ZAR", "MXN", "CNH", "PLN", "TRY", "HUF", "CZK",
]);

function symbolUsesPips(symbol) {
  const letters = String(symbol || "").toUpperCase().replace(/[^A-Z]/g, "");
  if (letters.includes("XAU") || letters.includes("GOLD")) return true;
  if (letters.length < 6) return false;
  for (let index = 0; index <= letters.length - 6; index += 1) {
    const base = letters.slice(index, index + 3);
    const quote = letters.slice(index + 3, index + 6);
    if (KNOWN_CURRENCY_CODES.has(base) && KNOWN_CURRENCY_CODES.has(quote)) {
      return true;
    }
  }
  return false;
}

function formatDistanceValue(symbol, distance) {
  const numericDistance = Number(distance);
  if (!Number.isFinite(numericDistance)) return "-";
  if (symbolUsesPips(symbol)) {
    return `${numericDistance >= 10 ? numericDistance.toFixed(1) : numericDistance.toFixed(2)} pips`;
  }
  return formatPrice(numericDistance, [numericDistance]);
}

function canonicalLabelForBrokerSymbol(brokerSymbol, aliases = {}) {
  const normalized = String(brokerSymbol || "").trim().toUpperCase();
  if (!normalized) return null;
  for (const [canonical, alias] of Object.entries(aliases || {})) {
    if (String(alias).trim().toUpperCase() === normalized) return canonical;
  }
  if (normalized.includes("XAU") || normalized === "GOLD") return "GOLD";
  return null;
}

function SymbolResolveHint({ info, className = "" }) {
  if (!info?.broker_symbol || !info?.display_symbol) return null;
  if (String(info.display_symbol).toUpperCase() === String(info.broker_symbol).toUpperCase()) return null;
  return (
    <p className={`text-xs text-slate-500 ${className}`}>
      {info.display_symbol}
    </p>
  );
}

function profitPipsAtPrice(symbol, entryPrice, exitPrice, side) {
  const normalizedEntry = Number(entryPrice);
  const normalizedExit = Number(exitPrice);
  if (!Number.isFinite(normalizedEntry) || !Number.isFinite(normalizedExit)) return null;
  const pipSize = pipSizeForSymbol(symbol);
  if (!pipSize) return null;
  const move = String(side || "").toUpperCase() === "SHORT"
    ? (normalizedEntry - normalizedExit)
    : (normalizedExit - normalizedEntry);
  return Number((move / pipSize).toFixed(2));
}

function distancePipsToPrice(symbol, currentPrice, referencePrice) {
  const normalizedCurrent = Number(currentPrice);
  const normalizedReference = Number(referencePrice);
  if (!Number.isFinite(normalizedCurrent) || !Number.isFinite(normalizedReference)) return null;
  if (!symbolUsesPips(symbol)) {
    return Number(Math.abs(normalizedCurrent - normalizedReference).toFixed(4));
  }
  const pipSize = pipSizeForSymbol(symbol);
  if (!pipSize) return null;
  return Number((Math.abs(normalizedCurrent - normalizedReference) / pipSize).toFixed(1));
}

function normalizeLiveOrders(rows = []) {
  const positionGroups = new Map();
  const sequence = [];
  (rows || []).forEach((row) => {
    const status = String(row?.status || "").toUpperCase();
    const positionId = String(row?.meta_position_id || "").trim();
    if (!positionId || !["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].includes(status)) {
      sequence.push({ type: "row", row });
      return;
    }
    const key = `${row?.account_id || row?.broker_info?.account_id || ""}:${positionId}`;
    if (!positionGroups.has(key)) {
      positionGroups.set(key, []);
      sequence.push({ type: "position", key });
    }
    positionGroups.get(key).push(row);
  });

  const isPresentNumber = (value) => Number.isFinite(Number(value)) && Number(value) > 0;
  const pickPrimary = (duplicates) => {
    const tracked = duplicates.filter((item) => String(item.external_source || "").toUpperCase() !== "BROKER_IMPORT");
    const pool = tracked.length ? tracked : duplicates;
    return pool
      .slice()
      .sort((left, right) => String(left.id || "").localeCompare(String(right.id || "")))[0];
  };

  return sequence.map((entry) => {
    if (entry.type === "row") return entry.row;
    const duplicates = positionGroups.get(entry.key);
    if (duplicates.length === 1) return duplicates[0];
    const primary = { ...pickPrimary(duplicates) };
    ["target", "stop_loss", "entry", "rr_ratio"].forEach((field) => {
      if (!isPresentNumber(primary[field])) {
        const donor = duplicates.find((item) => isPresentNumber(item[field]));
        if (donor) primary[field] = donor[field];
      }
    });
    if (!String(primary.side || "").trim()) {
      const donor = duplicates.find((item) => String(item.side || "").trim());
      if (donor) primary.side = donor.side;
    }
    return primary;
  });
}

function hasValidLivePrice(tick) {
  if (!tick || typeof tick !== "object") return false;
  return [tick.price, tick.bid, tick.ask].some((value) => typeof value === "number" && Number.isFinite(value) && value > 0);
}

function mergeLivePrices(previous = {}, incoming = {}) {
  const next = { ...previous };
  Object.entries(incoming || {}).forEach(([symbol, tick]) => {
    if (hasValidLivePrice(tick)) {
      next[livePriceKey(symbol)] = tick;
    }
  });
  return next;
}

function mergeSymbolPriceDigits(previous = {}, livePrices = {}, watchlist = [], resolveInfo = null) {
  const next = { ...previous };
  Object.entries(livePrices || {}).forEach(([symbol, tick]) => {
    if (tick?.price_digits !== null && tick?.price_digits !== undefined) {
      next[livePriceKey(symbol)] = Number(tick.price_digits);
    }
  });
  (watchlist || []).forEach((item) => {
    if (item?.price_digits !== null && item?.price_digits !== undefined) {
      next[livePriceKey(item.symbol)] = Number(item.price_digits);
    }
  });
  if (resolveInfo?.broker_symbol && resolveInfo?.price_digits !== null && resolveInfo?.price_digits !== undefined) {
    next[livePriceKey(resolveInfo.broker_symbol)] = Number(resolveInfo.price_digits);
  }
  return next;
}

function mergeWatchlistPrices(previous = [], incoming = []) {
  const previousBySymbol = new Map((previous || []).map((item) => [livePriceKey(item.symbol), item]));
  return (incoming || []).map((item) => {
    const symbol = livePriceKey(item.symbol);
    const previousItem = previousBySymbol.get(symbol);
    if (hasValidLivePrice(item) || !previousItem) return item;
    return {
      ...item,
      bid: previousItem.bid,
      ask: previousItem.ask,
      price: previousItem.price,
      time: previousItem.time,
    };
  });
}

function pivotDistanceTone(distancePips) {
  const value = Number(distancePips);
  if (!Number.isFinite(value)) {
    return "bg-slate-100 text-slate-600";
  }
  if (value <= 5) {
    return "bg-emerald-100 text-emerald-700";
  }
  if (value <= 15) {
    return "bg-amber-100 text-amber-700";
  }
  return "bg-rose-100 text-rose-700";
}

function impliedRiskAmount(result) {
  const explicit = Number(result?.riskAmount);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  const pnl = Number(result?.pnl);
  const realizedR = Number(result?.realizedR);
  if (Number.isFinite(pnl) && Number.isFinite(realizedR) && realizedR !== 0) {
    return Math.abs(pnl / realizedR);
  }
  return null;
}

function backtestExecutionBreakdown(result) {
  const entryPrice = Number(result?.entryPrice);
  const stopLoss = Number(result?.stopLoss);
  const symbol = String(result?.symbol || "");
  const side = String(result?.type || "").toUpperCase() === "SHORT" ? "SHORT" : "LONG";
  const entryQuantity = Number(result?.quantity || 0);
  const riskAmount = impliedRiskAmount(result);
  const relatedPrices = [result?.stopLoss, result?.partialExitPrice, result?.exitPrice, ...(result?.targetPrices || [])];
  const executions = [];

  if (Array.isArray(result?.partialExits)) {
    result.partialExits.forEach((item, index) => {
      const quantity = Number(item?.closeQuantity || 0);
      const price = Number(item?.price);
      const closeFraction = entryQuantity > 0 ? quantity / entryQuantity : 0;
      const rr = rrAtPrice(entryPrice, stopLoss, price, side);
      executions.push({
        id: `partial-${index}`,
        kind: item?.type || "PARTIAL",
        price,
        quantity,
        profitPips: profitPipsAtPrice(symbol, entryPrice, price, side),
        pnl: Number.isFinite(Number(item?.pnl)) ? Number(item?.pnl) : (Number.isFinite(rr) && Number.isFinite(riskAmount) ? Number((rr * closeFraction * riskAmount).toFixed(2)) : null),
        relatedPrices,
      });
    });
  }

  if (result?.exitPrice !== null && result?.exitPrice !== undefined && result?.exitPrice !== "") {
    const quantity = finalExitQuantity(result);
    if (quantity && quantity > 0) {
      const closeFraction = entryQuantity > 0 ? quantity / entryQuantity : 0;
      const rr = rrAtPrice(entryPrice, stopLoss, result.exitPrice, side);
      executions.push({
        id: "final",
        kind: result?.exitType || "FINAL",
        price: Number(result.exitPrice),
        quantity,
        profitPips: profitPipsAtPrice(symbol, entryPrice, result.exitPrice, side),
        pnl: Number.isFinite(rr) && Number.isFinite(riskAmount) ? Number((rr * closeFraction * riskAmount).toFixed(2)) : null,
        relatedPrices,
      });
    }
  }

  const totalPnl = Number(result?.pnl);
  if (Number.isFinite(totalPnl) && executions.length) {
    const subtotal = executions.slice(0, -1).reduce((sum, item) => sum + Number(item?.pnl || 0), 0);
    const finalExecution = executions[executions.length - 1];
    finalExecution.pnl = Number((totalPnl - subtotal).toFixed(2));
  }

  return executions;
}

function notificationToastType(notification) {
  const upperStatus = String(notification?.status || "").toUpperCase();
  const upperEvent = String(notification?.event_type || "").toUpperCase();
  if (upperStatus === "FAILED" || upperEvent.includes("FAILED")) return "error";
  return "success";
}

function summarizePlacement(result) {
  if (!result) return "Order submission finished.";
  const waiting = (result.results || []).filter((item) => String(item.status || "").toUpperCase() === "WAITING_TRIGGER").length;
  const marketClosed = (result.results || []).filter((item) => item.market_closed).length;
  if (result.success_count && result.failed_count) {
    return waiting
      ? `Armed/placed on ${result.success_count} account(s). ${result.failed_count} account(s) failed.`
      : `Placed on ${result.success_count} account(s). ${result.failed_count} account(s) failed.`;
  }
  if (result.success_count) {
    return waiting === result.success_count
      ? `Conditional SL armed on ${result.success_count} account(s). Waiting for trigger.`
      : waiting
        ? `Submitted on ${result.success_count} account(s) (${waiting} waiting for trigger).`
        : `Placed successfully on ${result.success_count} account(s).`;
  }
  if (marketClosed && !result.failed_count) {
    return null;
  }
  return `Order placement failed on ${result.failed_count || 0} account(s).`;
}

function accountBrokerScope(account) {
  return String(account?.broker_scope_key || account?.broker_server || account?.broker_type || "").toUpperCase();
}

function normalizeExecutionSelection(currentIds, nextIds, accounts, activeAccountId) {
  const validIds = new Set((accounts || []).map((account) => account.id));
  const activeAccount = (accounts || []).find((account) => account.id === activeAccountId);
  const activeScope = accountBrokerScope(activeAccount);
  // Feed may be omitted: prices still come from the header account, but orders
  // can target only a secondary account on the same broker/server.
  const ordered = [...(nextIds || [])];
  const normalized = [];
  ordered.forEach((id) => {
    if (!validIds.has(id) || normalized.includes(id)) return;
    const account = accounts.find((item) => item.id === id);
    if (activeScope && accountBrokerScope(account) !== activeScope) return;
    if (normalized.length >= 2) return;
    normalized.push(id);
  });
  return normalized;
}

function isExecutionAccountDisabled(account, selectedIds, accounts, activeAccountId) {
  const activeAccount = (accounts || []).find((item) => item.id === activeAccountId);
  const activeScope = accountBrokerScope(activeAccount);
  if (activeScope && accountBrokerScope(account) !== activeScope) return true;
  return !selectedIds.includes(account.id) && selectedIds.length >= 2;
}

function titleCaseWord(value) {
  const text = String(value || "").toLowerCase();
  return text ? `${text[0].toUpperCase()}${text.slice(1)}` : "";
}

function statusTone(status) {
  const upper = String(status || "").toUpperCase();
  if (upper === "FAILED") return "bg-rose-100 text-rose-700";
  if (["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED", "CLOSED"].includes(upper)) return "bg-emerald-100 text-emerald-700";
  if (["PLACEMENT_PENDING", "PENDING", "WAITING_TRIGGER", "DEFERRED_MARKET_OPEN"].includes(upper)) return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-700";
}

function DirectionSwitch({ value, onChange, disabled = false, compact = false }) {
  const normalized = String(value || "").toUpperCase() === "SHORT" ? "SHORT" : "LONG";
  return (
    <div className="grid w-full min-w-0 grid-cols-2 overflow-hidden rounded-xl border border-slate-300 bg-white">
      {[
        { id: "LONG", label: "Long", activeTone: "bg-emerald-600 text-white", idleTone: "text-emerald-700" },
        { id: "SHORT", label: "Short", activeTone: "bg-rose-600 text-white", idleTone: "text-rose-700" },
      ].map((option) => {
        const active = normalized === option.id;
        return (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            onClick={() => onChange(option.id)}
            className={`min-w-0 text-center font-semibold whitespace-nowrap transition disabled:cursor-not-allowed disabled:opacity-50 ${
              compact ? "px-2.5 py-1.5 text-xs" : "px-3 py-2 text-sm"
            } ${
              active ? option.activeTone : `bg-white ${option.idleTone}`
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function ToggleSwitch({ checked, onChange, disabled = false, onLabel = "On", offLabel = "Off" }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
        checked
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : "border-slate-300 bg-white text-slate-600"
      }`}
    >
      <span
        className={`relative h-5 w-9 rounded-full transition ${
          checked ? "bg-emerald-500" : "bg-slate-300"
        }`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
            checked ? "left-[18px]" : "left-0.5"
          }`}
        />
      </span>
      <span>{checked ? onLabel : offLabel}</span>
    </button>
  );
}

function ActivationModeSwitch({ value, onChange, disabled = false, compact = false }) {
  const normalized = String(value || "").toUpperCase() === "CONDITIONAL" ? "CONDITIONAL" : "IMMEDIATE";
  return (
    <div className="grid w-full min-w-0 grid-cols-2 overflow-hidden rounded-xl border border-slate-300 bg-white">
      {[
        { id: "IMMEDIATE", label: "Immediate" },
        { id: "CONDITIONAL", label: "Conditional" },
      ].map((option) => {
        const active = normalized === option.id;
        return (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            onClick={() => onChange(option.id)}
            className={`min-w-0 text-center font-semibold whitespace-nowrap transition disabled:cursor-not-allowed disabled:opacity-50 ${
              compact ? "px-2.5 py-1.5 text-xs" : "px-3 py-2 text-sm"
            } ${
              active ? "bg-slate-900 text-white" : "bg-white text-slate-600"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function brokerLabel(brokerInfo) {
  if (!brokerInfo) return "Broker Account";
  return brokerInfo.account_name || brokerInfo.login || brokerInfo.account_id || "Broker Account";
}

function currentHostname() {
  if (typeof window === "undefined") return "";
  return String(window.location.hostname || "").toLowerCase();
}

function isMarketingHostname(hostname) {
  return hostname === "www.aureliusmarketsystems.com" || hostname === "aureliusmarketsystems.com";
}

function appBaseUrlForHostname(hostname) {
  if (hostname.endsWith(".amplifyapp.com")) {
    return `${window.location.origin.replace(/\/$/, "")}`;
  }
  return "https://app.aureliusmarketsystems.com";
}

function createInstrumentLiveDraft(instrument) {
  const normalizedTargets = Array.isArray(instrument?.targetPrices)
    ? instrument.targetPrices
      .map((value) => String(value ?? "").trim())
      .filter((value) => value !== "")
    : [];
  return {
    direction: instrument?.direction || "LONG",
    activationMode: instrument?.activationMode || "IMMEDIATE",
    activationPrice: instrument?.activationPrice === null || instrument?.activationPrice === undefined ? "" : String(instrument.activationPrice),
    targetPrices: normalizedTargets.length ? normalizedTargets : [""],
    allowReentry: parseBooleanFlag(instrument?.allowReentry, false),
    timeframe: normalizeAutomationTimeframe(instrument?.timeframe),
    slMarkPrice: instrument?.slMarkPrice === null || instrument?.slMarkPrice === undefined ? "" : String(instrument.slMarkPrice),
    forwardTestOnly: parseBooleanFlag(instrument?.forwardTestOnly, false),
    pivotPrice: instrument?.pivotPrice === null || instrument?.pivotPrice === undefined ? "" : String(instrument.pivotPrice),
    retryCount: formatRetryCount(instrument?.retryCount),
  };
}

function createInstrumentEditDraft(instrument, position) {
  const baseDraft = createInstrumentLiveDraft(instrument);
  const targetPlan = position?.automation_context?.targetPlan || null;
  if (!targetPlan) return baseDraft;
  const achievedTargets = new Set((targetPlan.hitTargetPrices || []).map((value) => Number(value)));
  const editableTargets = (targetPlan.targetPrices || [])
    .filter((value) => !achievedTargets.has(Number(value)))
    .map((value) => String(value))
    .filter((value) => value.trim() !== "");
  return {
    ...baseDraft,
    targetPrices: editableTargets.length ? editableTargets : [""],
  };
}

function deriveLiquidityReversalDirection(pivotPrice, currentPrice, fallback = "LONG") {
  const pivot = Number(pivotPrice);
  const current = Number(currentPrice);
  if (!Number.isFinite(pivot) || !Number.isFinite(current) || pivot === current) {
    return formatTradeDirection(fallback);
  }
  return pivot > current ? "SHORT" : "LONG";
}

function getTokenExpiryMs(token) {
  try {
    const [, payloadPart] = token.split(".");
    const normalized = payloadPart.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    const payload = JSON.parse(window.atob(padded));
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

function InstrumentIcon({ symbol }) {
  return <SymbolIcon symbol={symbol} />;
}

function BinarySwitch({
  label,
  leftLabel,
  rightLabel,
  value,
  onChange,
  leftValue,
  rightValue,
  leftActiveClass = "bg-indigo-600 text-white shadow",
  rightActiveClass = "bg-indigo-600 text-white shadow",
  disabled = false
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(leftValue)}
          className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${
            value === leftValue ? leftActiveClass : "text-slate-500"
          } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
        >
          {leftLabel}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(rightValue)}
          className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${
            value === rightValue ? rightActiveClass : "text-slate-500"
          } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
        >
          {rightLabel}
        </button>
      </div>
    </div>
  );
}

function FlashMessage({ flash, onDismiss }) {
  const dismissRef = useRef(onDismiss);

  useEffect(() => {
    dismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    if (!flash?.id) return undefined;
    const timer = window.setTimeout(() => dismissRef.current?.(), 5000);
    return () => window.clearTimeout(timer);
  }, [flash?.id]);

  useEffect(() => {
    if (!flash?.id) return;
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.type = flash.type === "error" ? "sawtooth" : "sine";
    oscillator.frequency.setValueAtTime(flash.type === "error" ? 420 : 780, audioContext.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(
      flash.type === "error" ? 280 : 980,
      audioContext.currentTime + 0.14
    );

    gainNode.gain.setValueAtTime(0.0001, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.08, audioContext.currentTime + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.18);

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.2);

    oscillator.onended = () => {
      audioContext.close().catch(() => {});
    };

    return () => {
      try {
        oscillator.stop();
      } catch {}
      audioContext.close().catch(() => {});
    };
  }, [flash?.id, flash?.type]);

  if (!flash) return null;

  const toneClasses =
    flash.type === "error"
      ? "border-rose-200 bg-rose-50 text-rose-700"
      : flash.type === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-emerald-200 bg-emerald-50 text-emerald-700";

  return (
    <div className={`pointer-events-auto w-[min(24rem,calc(100vw-2.5rem))] rounded-2xl border px-4 py-3 text-sm font-medium shadow-xl ${toneClasses}`}>
      <div className="flex items-start justify-between gap-3">
        <p>{flash.message}</p>
        <button onClick={onDismiss} className="rounded-lg px-2 py-1 text-xs font-semibold hover:bg-white/50">
          Dismiss
        </button>
      </div>
    </div>
  );
}

function FlashMessages({ flashes, onDismiss }) {
  if (!flashes?.length) return null;

  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-[70] flex max-w-[calc(100vw-2.5rem)] flex-col-reverse gap-3">
      {flashes.map((flash) => (
        <FlashMessage key={flash.id} flash={flash} onDismiss={() => onDismiss(flash.id)} />
      ))}
    </div>
  );
}

function hasBlankTargetValue(values) {
  return (values || []).some((value) => `${value ?? ""}`.trim() === "");
}

function hasInvalidTargetOrder(values, direction = "LONG") {
  const numericTargets = (values || []).map((value) => {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  });
  return numericTargets.some((value, index) => {
    if (value === null || index === 0) return false;
    const previous = numericTargets[index - 1];
    if (previous === null) return false;
    return direction === "SHORT" ? value >= previous : value <= previous;
  });
}

function isTargetStepValid(value, previousValue, direction = "LONG") {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return false;
  if (previousValue === null || previousValue === undefined) return true;
  const previousParsed = Number.parseFloat(previousValue);
  if (!Number.isFinite(previousParsed)) return false;
  return direction === "SHORT" ? parsed < previousParsed : parsed > previousParsed;
}

function TargetPriceInputList({ values, onChange, direction = "LONG", disabled = false, compact = false }) {
  const normalizedValues = values || [];
  const hasBlankValue = hasBlankTargetValue(normalizedValues);
  const hasOrderingError = hasInvalidTargetOrder(normalizedValues, direction);
  const canAppendTarget = normalizedValues.length > 0
    && isTargetStepValid(normalizedValues[normalizedValues.length - 1], normalizedValues.length > 1 ? normalizedValues[normalizedValues.length - 2] : null, direction)
    && !hasBlankValue
    && !hasOrderingError;

  const updateAt = (index, nextValue) => {
    onChange(values.map((value, valueIndex) => (valueIndex === index ? nextValue : value)));
  };

  const removeAt = (index) => {
    onChange(values.filter((_, valueIndex) => valueIndex !== index));
  };

  const addTarget = () => {
    onChange([...(values || []), ""]);
  };

  return (
    <div className="space-y-2">
      <div className="space-y-2">
        {normalizedValues.map((value, index) => (
          <div key={index} className="flex min-w-0 items-center gap-2">
            {(() => {
              const previousValue = index > 0 ? normalizedValues[index - 1] : null;
              const isValid = `${value ?? ""}`.trim() === "" || isTargetStepValid(value, previousValue, direction);
              return (
                <input
                  type="number"
                  step="any"
                  value={value}
                  disabled={disabled}
                  onChange={(e) => updateAt(index, e.target.value)}
                  className={`${compact ? "w-full max-w-[11rem] px-2.5 py-1.5 text-xs" : "w-full px-3 py-2 text-sm"} min-w-0 rounded-xl border outline-none focus:border-indigo-500 disabled:bg-slate-100 ${isValid ? "border-slate-300" : "border-rose-300 bg-rose-50/60"}`}
                  placeholder={`T${index + 1}`}
                />
              );
            })()}
            {index === normalizedValues.length - 1 && (
              <button
                type="button"
                disabled={disabled || !canAppendTarget}
                onClick={addTarget}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-300 text-sm font-semibold leading-none text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Add target"
              >
                +
              </button>
            )}
            <button
              type="button"
              disabled={disabled || normalizedValues.length <= 1}
              onClick={() => removeAt(index)}
              className="rounded-lg bg-rose-100 px-2 py-1.5 text-[11px] font-semibold text-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function NotificationsPanel({ notifications, filters, onFiltersChange, hideHeader = false }) {
  const filteredNotifications = useMemo(() => {
    return notifications.filter((notification) => {
      const categoryMatch = filters.category === "ALL" || notification.category === filters.category;
      const statusMatch = filters.status === "ALL" || notification.status === filters.status;
      const query = filters.query.trim().toLowerCase();
      const queryMatch = !query
        || notification.activity.toLowerCase().includes(query)
        || (notification.symbol || "").toLowerCase().includes(query)
        || (notification.event_type || "").toLowerCase().includes(query)
        || brokerLabel(notification.broker_info).toLowerCase().includes(query)
        || (notification.failure_reason || "").toLowerCase().includes(query);
      return categoryMatch && statusMatch && queryMatch;
    });
  }, [filters, notifications]);

  const categories = useMemo(() => {
    return ["ALL", ...new Set(notifications.map((notification) => notification.category).filter(Boolean))];
  }, [notifications]);

  const statuses = useMemo(() => {
    return ["ALL", ...new Set(notifications.map((notification) => notification.status).filter(Boolean))];
  }, [notifications]);

  return (
    <section className="overflow-x-hidden rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:[&_input]:border-slate-700 dark:[&_input]:bg-slate-950 dark:[&_input]:text-slate-100 dark:[&_select]:border-slate-700 dark:[&_select]:bg-slate-950 dark:[&_select]:text-slate-100 dark:[&_.bg-white]:!bg-slate-900 dark:[&_.bg-slate-50]:!bg-slate-950 dark:[&_.text-slate-900]:!text-slate-100 dark:[&_.text-slate-700]:!text-slate-200 dark:[&_.text-slate-600]:!text-slate-300 dark:[&_.text-slate-500]:!text-slate-400 dark:[&_.border-slate-200]:!border-slate-800 dark:[&_.border-slate-300]:!border-slate-700">
      {!hideHeader && (
        <div className="mb-4">
          <div>
            <h3 className="text-xl font-bold text-slate-900">Notifications</h3>
            <p className="text-sm text-slate-500">Track every order update with saved timestamps, categories, and activity.</p>
          </div>
        </div>
      )}

      <div className="mb-4 grid gap-3 lg:grid-cols-[1.4fr_180px_180px]">
        <label className="space-y-1 text-sm">
          <span className="font-medium text-slate-600">Search activity</span>
          <input
            className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
            value={filters.query}
            onChange={(e) => onFiltersChange({ ...filters, query: e.target.value })}
            placeholder="Search by symbol, event, or activity..."
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium text-slate-600">Category</span>
          <select
            className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
            value={filters.category}
            onChange={(e) => onFiltersChange({ ...filters, category: e.target.value })}
          >
            {categories.map((category) => (
              <option key={category} value={category}>{category}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium text-slate-600">Status</span>
          <select
            className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
            value={filters.status}
            onChange={(e) => onFiltersChange({ ...filters, status: e.target.value })}
          >
            {statuses.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
        </label>
      </div>

      {filteredNotifications.length === 0 ? (
        <div className="rounded-xl border border-dashed border-indigo-200 bg-white/70 px-3 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400">
          No notifications match the current filters yet.
        </div>
      ) : (
        <div className="space-y-3">
          {filteredNotifications.map((notification) => (
            <article key={notification.id} className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-indigo-700">
                      {notification.category}
                    </span>
                    {notification.status && (
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-700">
                        {notification.status}
                      </span>
                    )}
                    {notification.symbol && (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                        <SymbolIcon symbol={notification.symbol} size="sm" />
                        {notification.symbol}
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-semibold text-slate-900">{notification.activity}</p>
                  <div className="space-y-1">
                    <p className="text-xs uppercase tracking-wide text-slate-400">{notification.event_type || "UPDATE"}</p>
                    <p className="text-xs font-medium text-slate-500">{brokerLabel(notification.broker_info)}</p>
                    {notification.failure_reason && (
                      <p className="text-xs text-rose-600">Failure: {notification.failure_reason}</p>
                    )}
                    {notification.placement_fallback_reason && (
                      <p className="text-xs text-amber-700">Placement: {notification.placement_fallback_reason}</p>
                    )}
                  </div>
                </div>
                <p className="shrink-0 text-xs font-medium text-slate-500">{formatNotificationTimestamp(notification.timestamp)}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function NotificationDetailsModal({ open, notifications, filters, onFiltersChange, onClose }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[85] flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[2px]">
      <div className="flex max-h-[88vh] w-[min(72rem,100%)] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div>
            <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">Notification Details</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">Review saved order activity with filters and timestamps.</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Close
          </button>
        </div>
        <div className="overflow-auto p-6">
          <NotificationsPanel
            notifications={notifications}
            filters={filters}
            onFiltersChange={onFiltersChange}
            hideHeader
          />
        </div>
      </div>
    </div>
  );
}

function ProfileLoader({ open, message }) {
  if (!open) return null;

  const isWelcomeMessage = message.startsWith("Welcome, ");
  const welcomeName = isWelcomeMessage ? message.replace("Welcome, ", "").replace(/\s*🙂$/, "") : "";

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/25 backdrop-blur-[2px]">
      <div className="flex min-h-[20vh] w-[min(34rem,calc(100vw-2rem))] items-center rounded-[2rem] border border-indigo-100 bg-white/95 px-6 py-6 shadow-2xl">
        <div className="flex w-full flex-col items-center justify-center gap-4 text-center">
          <span className="relative inline-flex h-16 w-16 items-center justify-center rounded-full bg-indigo-100/90 text-indigo-700">
            <span className="absolute inset-0 animate-spin rounded-full border-[3px] border-indigo-200 border-t-indigo-700 border-r-violet-500" />
            <span className="absolute inset-[10px] rounded-full bg-white/80" />
            <span className="absolute h-2.5 w-2.5 rounded-full bg-indigo-600" />
          </span>
          <div className="min-w-0 text-center">
            {isWelcomeMessage ? (
              <div className="space-y-1">
                <p className="text-base font-medium tracking-[0.02em] text-slate-500">Welcome,</p>
                <p className="text-3xl font-semibold leading-none text-slate-900">{welcomeName}</p>
              </div>
            ) : (
              <p className="whitespace-nowrap text-lg font-semibold tracking-[0.01em] text-slate-900">
                {message}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Auth({ onAuth, initialMode = "login" }) {
  const normalizedInitialMode = initialMode === "register" ? "register" : "login";
  const [mode, setMode] = useState(normalizedInitialMode);
  const [form, setForm] = useState({ username: "", password: "", full_name: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [touchedFields, setTouchedFields] = useState({});
  const [submitAttempted, setSubmitAttempted] = useState(false);

  const fieldErrors = {
    username: form.username.trim() ? "" : "Username is required.",
    password: form.password.trim() ? "" : "Password is required.",
    full_name: mode === "register" && !form.full_name.trim() ? "Full name is required." : ""
  };
  const hasFieldErrors = Object.values(fieldErrors).some(Boolean);

  const submit = async (event) => {
    event?.preventDefault();
    setSubmitAttempted(true);
    if (hasFieldErrors) {
      setTouchedFields((current) => ({
        ...current,
        username: true,
        password: true,
        ...(mode === "register" ? { full_name: true } : {})
      }));
      return;
    }
    const path = mode === "login" ? "/auth/login" : "/auth/register";
    setSubmitting(true);
    setError("");
    try {
      const authData = await api(path, "POST", form);
      onAuth(authData);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const markTouched = (fieldName) => setTouchedFields((current) => ({ ...current, [fieldName]: true }));

  useEffect(() => {
    setMode(normalizedInitialMode);
  }, [normalizedInitialMode]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-950 via-indigo-950 to-violet-900 p-4">
      <div className="w-full max-w-md space-y-4 rounded-2xl border border-indigo-800/50 bg-slate-900/90 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-white">{mode === "login" ? "Login" : "Register"}</h2>
        <BinarySwitch
          label="Mode"
          leftLabel="Login"
          rightLabel="Register"
          value={mode}
          onChange={setMode}
          leftValue="login"
          rightValue="register"
          leftActiveClass="bg-indigo-600 text-white shadow"
          rightActiveClass="bg-violet-600 text-white shadow"
          disabled={submitting}
        />
        <form onSubmit={submit} className="space-y-4">
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-indigo-100">Username</span>
            <input
              className={`w-full rounded-xl border bg-slate-800 px-3 py-2 text-white outline-none ${hasVisibleFieldError("username", touchedFields, submitAttempted) && fieldErrors.username ? "border-rose-500/70 focus:border-rose-400" : "border-indigo-900/60 focus:border-indigo-400"}`}
              placeholder="Username"
              autoComplete="username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              onBlur={() => markTouched("username")}
            />
            {hasVisibleFieldError("username", touchedFields, submitAttempted) && fieldErrors.username && (
              <p className="text-xs text-rose-300">{fieldErrors.username}</p>
            )}
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-indigo-100">Password</span>
            <input
              className={`w-full rounded-xl border bg-slate-800 px-3 py-2 text-white outline-none ${hasVisibleFieldError("password", touchedFields, submitAttempted) && fieldErrors.password ? "border-rose-500/70 focus:border-rose-400" : "border-indigo-900/60 focus:border-indigo-400"}`}
              placeholder="Password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              onBlur={() => markTouched("password")}
            />
            {hasVisibleFieldError("password", touchedFields, submitAttempted) && fieldErrors.password && (
              <p className="text-xs text-rose-300">{fieldErrors.password}</p>
            )}
          </label>
          {mode === "register" && (
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-indigo-100">Full name</span>
            <input
              className={`w-full rounded-xl border bg-slate-800 px-3 py-2 text-white outline-none ${hasVisibleFieldError("full_name", touchedFields, submitAttempted) && fieldErrors.full_name ? "border-rose-500/70 focus:border-rose-400" : "border-indigo-900/60 focus:border-indigo-400"}`}
              placeholder="Full name"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              onBlur={() => markTouched("full_name")}
            />
            {hasVisibleFieldError("full_name", touchedFields, submitAttempted) && fieldErrors.full_name && (
              <p className="text-xs text-rose-300">{fieldErrors.full_name}</p>
            )}
          </label>
          )}
          {error && <div className="rounded-xl border border-rose-700/40 bg-rose-950/40 px-3 py-2 text-sm text-rose-100">{error}</div>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-xl bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-600"
          >
            {submitting ? "Please wait..." : mode === "login" ? "Login" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}

function MaintenancePage({ message, checking = false, onRetry }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(99,102,241,0.24),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(14,165,233,0.18),_transparent_28%),linear-gradient(145deg,_#020617_0%,_#111827_45%,_#1e1b4b_100%)] px-4 py-10 text-slate-100">
      <div className="w-full max-w-xl rounded-[32px] border border-white/10 bg-slate-950/55 p-8 shadow-[0_30px_90px_rgba(15,23,42,0.55)] backdrop-blur">
        <div className="mx-auto flex w-full max-w-sm flex-col items-center text-center">
          <div className="relative mb-6">
            <div className="absolute inset-0 rounded-full bg-indigo-500/30 blur-2xl" />
            <div className="relative flex h-28 w-28 items-center justify-center rounded-full border border-indigo-300/20 bg-gradient-to-br from-slate-900 via-indigo-950 to-sky-900 shadow-[0_0_0_10px_rgba(15,23,42,0.35)]">
              <img src="/signalbridge-logo-light.svg" alt="SignalBridge" className="h-16 w-16 object-contain drop-shadow-[0_8px_24px_rgba(129,140,248,0.45)]" />
            </div>
          </div>
          <p className="text-xs font-semibold uppercase tracking-[0.34em] text-sky-200/80">Maintenance Mode</p>
          <h1 className="mt-3 text-3xl font-black tracking-tight text-white">SignalBridge Cloud is temporarily unavailable</h1>
          <p className="mt-4 text-sm leading-6 text-slate-300">
            {message || "We’re waiting for the backend to come back online. Once service is restored, the app will be available again."}
          </p>
          <div className="mt-6 flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">
            <span className={`h-2.5 w-2.5 rounded-full ${checking ? "animate-pulse bg-amber-300" : "bg-rose-300"}`} />
            <span>{checking ? "Checking backend status..." : "Waiting for backend recovery"}</span>
          </div>
          <button
            type="button"
            onClick={onRetry}
            className="mt-8 inline-flex items-center rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-indigo-950/40 transition hover:-translate-y-0.5 hover:bg-sky-50"
          >
            Retry connection
          </button>
        </div>
      </div>
    </div>
  );
}

function MarketingLandingPage() {
  const hostname = currentHostname();
  const appBaseUrl = appBaseUrlForHostname(hostname);
  const signInUrl = `${appBaseUrl}?mode=login`;
  const registerUrl = `${appBaseUrl}?mode=register`;

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.18),_transparent_32%),radial-gradient(circle_at_bottom_right,_rgba(14,165,233,0.14),_transparent_28%),linear-gradient(135deg,_#f8fafc_0%,_#e2e8f0_48%,_#dbeafe_100%)] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-6 py-8">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <img
              src="/signalbridge-logo-light.svg"
              alt="SignalBridge"
              className="h-24 w-auto object-contain sm:h-28 lg:h-32"
            />
            <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-indigo-600">Aurelius Market Systems</p>
            <h1 className="mt-2 text-2xl font-black tracking-tight text-slate-950">SignalBridge Trade Automation</h1>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <a
              href={signInUrl}
              className="rounded-xl border border-slate-300 bg-white/80 px-5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm backdrop-blur hover:bg-white"
            >
              Sign in
            </a>
            <a
              href={registerUrl}
              className="rounded-xl bg-slate-950 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-slate-900/15 hover:bg-slate-800"
            >
              Register
            </a>
          </div>
        </header>

        <main className="grid flex-1 items-center gap-12 py-12 lg:grid-cols-[1.15fr_0.85fr]">
          <section>
            <div className="inline-flex rounded-full border border-indigo-200 bg-white/70 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.24em] text-indigo-700 shadow-sm backdrop-blur">
              Systematic execution for discretionary traders
            </div>
            <h2 className="mt-6 max-w-4xl text-5xl font-black leading-[1.02] tracking-tight text-slate-950 sm:text-6xl">
              Turn price-action rules into a disciplined execution desk.
            </h2>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
              SignalBridge gives professional traders a focused workspace for structured order execution, live automation,
              backtesting, AI-assisted market analysis, and broker-synced trade oversight in one platform.
            </p>

            <div className="mt-10 flex flex-wrap gap-3">
              <a
                href={registerUrl}
                className="rounded-2xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/20 hover:bg-indigo-500"
              >
                Create trading workspace
              </a>
              <a
                href={signInUrl}
                className="rounded-2xl border border-slate-300 bg-white/80 px-6 py-3 text-sm font-semibold text-slate-800 shadow-sm backdrop-blur hover:bg-white"
              >
                Access existing account
              </a>
            </div>

            <div className="mt-12 grid gap-4 sm:grid-cols-3">
              <div className="rounded-3xl border border-white/70 bg-white/70 p-5 shadow-sm backdrop-blur">
                <p className="text-sm font-semibold text-slate-950">Execution discipline</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">Structured live automation with price-gated activation, risk-aware order sizing, and target management.</p>
              </div>
              <div className="rounded-3xl border border-white/70 bg-white/70 p-5 shadow-sm backdrop-blur">
                <p className="text-sm font-semibold text-slate-950">Backtest transparency</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">Live engine visibility with structural level proof, trapped-liquidity state tracking, and broker-aware precision.</p>
              </div>
              <div className="rounded-3xl border border-white/70 bg-white/70 p-5 shadow-sm backdrop-blur">
                <p className="text-sm font-semibold text-slate-950">AI market context</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">Live automation, execution oversight, and account-aware risk control for structured trading workflows.</p>
              </div>
            </div>
          </section>

          <section className="rounded-[2rem] border border-slate-200 bg-slate-950 p-6 text-white shadow-2xl shadow-slate-900/15">
            <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Inside the platform</p>
              <div className="mt-5 space-y-4">
                {[
                  {
                    title: "Broker-synced execution hub",
                    body: "Track live positions, pending orders, risk exposure, and instrument watchlists against connected broker accounts."
                  },
                  {
                    title: "Continuation Failure automation",
                    body: "Run shared live/backtest strategy logic with consistent validation, conditional activation, and target-based management."
                  },
                  {
                    title: "Research and model tooling",
                    body: "Explore H1 AI candle prediction, scoring, documentation helpers, and structured analytics from the same interface."
                  }
                ].map((item) => (
                  <div key={item.title} className="rounded-2xl border border-white/10 bg-slate-900/70 p-4">
                    <p className="text-sm font-semibold text-white">{item.title}</p>
                    <p className="mt-2 text-sm leading-6 text-slate-300">{item.body}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-6 rounded-[1.5rem] border border-emerald-400/20 bg-emerald-400/10 p-5">
              <p className="text-sm font-semibold text-emerald-200">Who this is for</p>
              <p className="mt-2 text-sm leading-6 text-emerald-50/90">
                Traders who already have a ruleset and want tighter execution, clearer feedback loops, and a cleaner bridge between manual judgment and automation.
              </p>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

function Watchlist({ token, selectedAccountExists, selectedAccountId = "", symbolAliases = {}, onSymbolDigits, items, onNotify, selectedInstrument, onSelectInstrument, showHeader = true }) {
  const [symbol, setSymbol] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [adding, setAdding] = useState(false);
  const [pendingRemove, setPendingRemove] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [priceDirections, setPriceDirections] = useState({});
  const [pricePrecisions, setPricePrecisions] = useState({});
  const [symbolResolve, setSymbolResolve] = useState(null);
  const previousPricesRef = useRef({});
  const visibleItems = useMemo(() => items.filter((item) => item?.symbol), [items]);

  useEffect(() => {
    if (!selectedAccountExists || symbol.trim().length < 1) {
      setSuggestions([]);
      setHighlightedIndex(-1);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await api(`/instruments/suggest?q=${encodeURIComponent(symbol)}&limit=8`, "GET", undefined, token);
        setSuggestions(data.symbols || []);
        setHighlightedIndex((data.symbols || []).length ? 0 : -1);
      } catch {
        setSuggestions([]);
        setHighlightedIndex(-1);
      }
    }, 180);
    return () => clearTimeout(timer);
  }, [symbol, token, selectedAccountExists]);

  useEffect(() => {
    if (!selectedAccountExists || !selectedAccountId || symbol.trim().length < 1) {
      setSymbolResolve(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await api(
          `/accounts/${selectedAccountId}/symbols/resolve?symbol=${encodeURIComponent(symbol)}`,
          "GET",
          undefined,
          token
        );
        setSymbolResolve(data);
        if (data?.broker_symbol && data?.price_digits !== null && data?.price_digits !== undefined) {
          onSymbolDigits?.(data.broker_symbol, data.price_digits);
        }
      } catch {
        setSymbolResolve(null);
      }
    }, 220);
    return () => clearTimeout(timer);
  }, [symbol, token, selectedAccountExists, selectedAccountId, onSymbolDigits]);

  useEffect(() => {
    const nextDirections = {};
    const nextPreviousPrices = { ...previousPricesRef.current };

    visibleItems.forEach((item) => {
      const currentPrice = item.price;
      const previousPrice = previousPricesRef.current[item.symbol];

      if (typeof currentPrice === "number" && typeof previousPrice === "number") {
        if (currentPrice > previousPrice) {
          nextDirections[item.symbol] = "up";
        } else if (currentPrice < previousPrice) {
          nextDirections[item.symbol] = "down";
        } else {
          nextDirections[item.symbol] = priceDirections[item.symbol] || "flat";
        }
      } else {
        nextDirections[item.symbol] = priceDirections[item.symbol] || "flat";
      }

      nextPreviousPrices[item.symbol] = currentPrice;
    });

    previousPricesRef.current = nextPreviousPrices;
    setPriceDirections(nextDirections);
  }, [visibleItems]);

  useEffect(() => {
    setPricePrecisions((current) => {
      const next = { ...current };
      visibleItems.forEach((item) => {
        if (item.price_digits !== null && item.price_digits !== undefined) {
          next[item.symbol] = Number(item.price_digits);
          return;
        }
        const observedPrecision = Math.max(
          decimalPlaces(item.price),
          decimalPlaces(item.bid),
          decimalPlaces(item.ask),
          current[item.symbol] || 0
        );
        if (observedPrecision > 0) {
          next[item.symbol] = observedPrecision;
        }
      });
      return next;
    });
  }, [visibleItems]);

  const add = async () => {
    if (!selectedAccountExists) {
      onNotify("error", "Select an account before adding watchlist symbols.");
      return;
    }
    if (!symbol.trim()) return;
    setAdding(true);
    try {
      const result = await api("/watchlist", "POST", { symbol }, token);
      const brokerSymbol = result?.broker_symbol || symbol.trim().toUpperCase();
      setSymbol("");
      setSuggestions([]);
      setHighlightedIndex(-1);
      setSymbolResolve(null);
      onSelectInstrument(brokerSymbol);
      if (result?.price_digits !== null && result?.price_digits !== undefined) {
        onSymbolDigits?.(brokerSymbol, result.price_digits);
      }
      onNotify(
        "success",
        result?.display_symbol && result.display_symbol !== brokerSymbol
          ? `${result.display_symbol} added to watchlist.`
          : `${brokerSymbol} added to watchlist.`
      );
    } catch (err) {
      onNotify("error", err.message);
    } finally {
      setAdding(false);
    }
  };

  const selectSuggestion = (value) => {
    setSymbol(value);
    setSuggestions([]);
    setHighlightedIndex(-1);
  };

  const handleKeyDown = (e) => {
    if (!suggestions.length) {
      if (e.key === "Enter") {
        e.preventDefault();
        add();
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((current) => (current + 1) % suggestions.length);
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIndex >= 0 && suggestions[highlightedIndex]) {
        selectSuggestion(suggestions[highlightedIndex]);
      } else {
        add();
      }
    }
  };

  const remove = async (value) => {
    setPendingRemove(value);
    try {
      await api(`/watchlist?symbol=${encodeURIComponent(value)}`, "DELETE", undefined, token);
      onNotify("success", `${value} removed from watchlist.`);
    } catch (err) {
      onNotify("error", err.message);
    } finally {
      setPendingRemove("");
    }
  };

  const TrashIcon = () => (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M7.5 4.5h5M4.5 6h11M8 8.5v6M12 8.5v6M6.2 6.2l.6 10.1c.1.7.6 1.2 1.3 1.2h3.8c.7 0 1.2-.5 1.3-1.2l.6-10.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );

  return (
    <section className="h-full rounded-[1.75rem] border border-[color:var(--shell-border)] bg-[color:var(--panel)] p-4 text-[color:var(--text-strong)] shadow-[var(--shadow-soft)]">
      {showHeader && (
        <div className="mb-4 hidden lg:block">
          <h3 className="text-lg font-semibold text-[color:var(--text-strong)]">Watchlist</h3>
        </div>
      )}
      <>
          <div className="relative mb-4">
            <div className="flex gap-2">
              <input
                className="w-full rounded-xl border border-[color:var(--shell-border)] bg-[color:var(--panel-muted)] px-3 py-2 outline-none focus:border-indigo-500 disabled:opacity-60"
                disabled={!selectedAccountExists}
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                onKeyDown={handleKeyDown}
                placeholder={selectedAccountExists ? "Type symbol..." : "Select an account first"}
              />
              <button
                onClick={add}
                disabled={adding || !selectedAccountExists}
                className="rounded-xl bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {adding ? "Adding..." : "Add"}
              </button>
            </div>
            {suggestions.length > 0 && symbol && (
              <div className="absolute z-10 mt-1 w-full rounded-xl border border-[color:var(--shell-border)] bg-[color:var(--panel)] shadow-[var(--shadow-pop)]">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => selectSuggestion(suggestion)}
                    onMouseEnter={() => setHighlightedIndex(suggestions.indexOf(suggestion))}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${highlightedIndex === suggestions.indexOf(suggestion) ? "bg-indigo-500/15 text-indigo-300" : "hover:bg-[color:var(--panel-muted)]"}`}
                  >
                    <SymbolIcon symbol={suggestion} size="sm" />
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
            <SymbolResolveHint info={symbolResolve} className="mt-1 px-1" />
          </div>
          {visibleItems.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[color:var(--shell-border)] bg-[color:var(--panel-muted)] px-3 py-6 text-center text-sm text-[color:var(--text-muted)]">
              No symbols yet. Add a pair to start the live stream.
            </div>
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <tbody>
                  {visibleItems.map((item) => (
                    <tr
                      key={item.symbol}
                      onClick={() => onSelectInstrument(item.symbol)}
                      className={`group border-b border-indigo-50 transition ${
                        selectedInstrument === item.symbol ? "bg-indigo-500/12" : "hover:bg-[color:var(--panel-muted)]"
                      } cursor-pointer`}
                    >
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <InstrumentIcon symbol={item.symbol} />
                          <div>
                            <span className="font-semibold text-[color:var(--text-strong)]">{item.symbol}</span>
                            {(() => {
                              const label = canonicalLabelForBrokerSymbol(item.symbol, symbolAliases);
                              return label && label !== item.symbol ? (
                                <p className="text-[11px] text-[color:var(--text-muted)]">{label}</p>
                              ) : null;
                            })()}
                          </div>
                        </div>
                      </td>
                      <td className="py-2 text-right">
                        <div
                          className={`flex items-center justify-end gap-1 font-semibold ${
                            priceDirections[item.symbol] === "up"
                              ? "text-emerald-600"
                              : priceDirections[item.symbol] === "down"
                                ? "text-rose-600"
                              : "text-[color:var(--text-strong)]"
                          }`}
                        >
                          <span>{formatPrice(item.price, [item.bid, item.ask], 0, item.price_digits ?? pricePrecisions[item.symbol] ?? null)}</span>
                          <span className="inline-flex w-4 shrink-0 items-center justify-center text-[11px] leading-none">
                            <span className={priceDirections[item.symbol] === "flat" ? "invisible" : ""}>
                              {priceDirections[item.symbol] === "up" ? "▲" : "▼"}
                            </span>
                          </span>
                        </div>
                      </td>
                      <td className="py-2 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            remove(item.symbol);
                          }}
                          disabled={pendingRemove === item.symbol}
                          aria-label={`Remove ${item.symbol}`}
                          className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-sm font-semibold text-rose-600 transition ${
                            pendingRemove === item.symbol
                              ? "bg-rose-100 opacity-100"
                              : "opacity-0 group-hover:opacity-100 hover:bg-rose-100"
                          } disabled:cursor-not-allowed`}
                          title={`Remove ${item.symbol}`}
                        >
                          {pendingRemove === item.symbol ? "…" : <TrashIcon />}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </>
    </section>
  );
}

function OrderScreen({
  token,
  accounts,
  activeAccountId,
  selectedAccountExists,
  onNotify,
  livePrices,
  symbolPriceDigits = {},
  onSymbolDigits,
  subscribeLiveSymbol,
  selectedInstrument,
  onAccountRiskSaved,
  me,
  onMeUpdated,
}) {
  const savedOrderDefaults = me?.ui_settings?.order_defaults || {};
  const defaultAtm = savedOrderDefaults.automatic_trade_management !== false;
  const defaultRetryable = savedOrderDefaults.retryable_order !== false;
  const [orderMode, setOrderMode] = useState("quick");
  const [quickTimeframe, setQuickTimeframe] = useState("M1");
  const [quickQuote, setQuickQuote] = useState(null);
  const [quickQuoteError, setQuickQuoteError] = useState("");
  const quickQuoteRequestRef = useRef(0);
  const [form, setForm] = useState({
    symbol: "EURUSD",
    order_type: "SL",
    side: "BUY",
    entry: "",
    stop_loss: "",
    target: "",
    cancel_at: "",
    comment: "",
    retryable_order: defaultRetryable,
    automatic_trade_management: defaultAtm,
    conditional_order: false,
    trigger_price: "",
  });
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [marketPrice, setMarketPrice] = useState(null);
  const [marketDirection, setMarketDirection] = useState("flat");
  const [placingOrder, setPlacingOrder] = useState(false);
  const [marketClosedOffer, setMarketClosedOffer] = useState(null);
  const [deferBusy, setDeferBusy] = useState(false);
  const [touchedFields, setTouchedFields] = useState({});
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [selectedTargetIds, setSelectedTargetIds] = useState([]);
  const [riskInputs, setRiskInputs] = useState({});
  const [savingRiskIds, setSavingRiskIds] = useState({});
  const [detectorOpen, setDetectorOpen] = useState(false);
  const [detectorForm, setDetectorForm] = useState({ timeframe: "M1", candle_type: "HAMMER" });
  const [detectorLoading, setDetectorLoading] = useState(false);
  const [detectorError, setDetectorError] = useState("");
  const [detectorResult, setDetectorResult] = useState(null);
  const [symbolResolve, setSymbolResolve] = useState(null);

  const entry = Number(form.entry);
  const sl = Number(form.stop_loss);
  const target = form.target ? Number(form.target) : null;
  const cancelAt = form.cancel_at ? Number(form.cancel_at) : null;
  const triggerPrice = form.trigger_price ? Number(form.trigger_price) : null;
  const disabled = !selectedAccountExists || placingOrder;
  const isQuickOrder = orderMode === "quick";
  const effectiveOrderType = isQuickOrder ? "MARKET" : form.order_type;
  const isMarketOrder = effectiveOrderType === "MARKET";
  const isConditionalSl = !isQuickOrder && effectiveOrderType === "SL" && Boolean(form.conditional_order);
  const effectiveEntry = isMarketOrder ? Number(marketPrice || entry || 0) : entry;

  useEffect(() => {
    const defaults = me?.ui_settings?.order_defaults;
    if (!defaults || typeof defaults !== "object") return;
    setForm((current) => ({
      ...current,
      automatic_trade_management:
        defaults.automatic_trade_management !== undefined && defaults.automatic_trade_management !== null
          ? Boolean(defaults.automatic_trade_management)
          : current.automatic_trade_management,
      retryable_order:
        defaults.retryable_order !== undefined && defaults.retryable_order !== null
          ? Boolean(defaults.retryable_order)
          : current.retryable_order,
    }));
  }, [me?.ui_settings?.order_defaults]);

  const persistOrderDefaults = async (nextDefaults) => {
    try {
      const snapshot = await api("/auth/ui-settings", "POST", { order_defaults: nextDefaults }, token);
      if (snapshot) onMeUpdated?.(snapshot);
    } catch (err) {
      onNotify?.("error", err?.message || "Failed to save order defaults.");
      throw err;
    }
  };

  useEffect(() => {
    setRiskInputs((current) => {
      const next = { ...current };
      accounts.forEach((account) => {
        if (!next[account.id]) {
          next[account.id] = String(account.risk_amount ?? "");
        }
      });
      return next;
    });
  }, [accounts]);

  useEffect(() => {
    setSelectedTargetIds((current) => {
      const next = normalizeExecutionSelection(current, current, accounts, activeAccountId);
      if (next.length) return next;
      if (activeAccountId && accounts.some((account) => account.id === activeAccountId)) {
        return [activeAccountId];
      }
      return accounts[0]?.id ? [accounts[0].id] : [];
    });
  }, [accounts, activeAccountId]);

  useEffect(() => {
    if (!selectedInstrument) return;
    setForm((current) => ({ ...current, symbol: selectedInstrument }));
  }, [selectedInstrument]);

  useEffect(() => {
    if (!selectedAccountExists || !activeAccountId || !form.symbol.trim()) {
      setSymbolResolve(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await api(
          `/accounts/${activeAccountId}/symbols/resolve?symbol=${encodeURIComponent(form.symbol)}`,
          "GET",
          undefined,
          token
        );
        setSymbolResolve(data);
        if (data?.broker_symbol && data?.price_digits !== null && data?.price_digits !== undefined) {
          onSymbolDigits?.(data.broker_symbol, data.price_digits);
        }
      } catch {
        setSymbolResolve(null);
      }
    }, 220);
    return () => clearTimeout(timer);
  }, [form.symbol, activeAccountId, selectedAccountExists, token, onSymbolDigits]);

  const liveSymbol = useMemo(
    () => String(symbolResolve?.broker_symbol || form.symbol || "").trim().toUpperCase(),
    [form.symbol, symbolResolve]
  );
  const priceDigits = useMemo(
    () => symbolResolve?.price_digits ?? preview?.price_digits ?? resolveSymbolPriceDigits(liveSymbol, livePrices, symbolPriceDigits),
    [symbolResolve, preview, liveSymbol, livePrices, symbolPriceDigits]
  );

  const roundPriceField = (fieldName) => {
    if (priceDigits === null || priceDigits === undefined) return;
    setForm((current) => {
      const raw = current[fieldName];
      if (raw === "" || raw === null || raw === undefined) return current;
      const rounded = roundPriceToDigits(Number(raw), priceDigits);
      if (!Number.isFinite(rounded)) return current;
      return { ...current, [fieldName]: String(rounded) };
    });
  };

  useEffect(() => {
    if (!isMarketOrder) return;
    const livePrice = livePrices[liveSymbol];
    const nextEntry =
      form.side === "BUY"
        ? livePrice?.ask ?? livePrice?.price ?? ""
        : livePrice?.bid ?? livePrice?.price ?? "";
    const normalizedEntry = nextEntry === "" || nextEntry === undefined || nextEntry === null
      ? ""
      : priceDigits !== null && priceDigits !== undefined
        ? String(roundPriceToDigits(Number(nextEntry), priceDigits))
        : String(nextEntry);
    setForm((current) => ({
      ...current,
      entry: normalizedEntry
    }));
  }, [form.side, form.symbol, isMarketOrder, livePrices, liveSymbol, priceDigits]);

  useEffect(() => {
    if (!selectedAccountExists || !form.symbol.trim()) {
      setMarketPrice(null);
      subscribeLiveSymbol("", "order-screen");
      return;
    }
    subscribeLiveSymbol(liveSymbol, "order-screen");
  }, [form.symbol, liveSymbol, selectedAccountExists, subscribeLiveSymbol]);

  useEffect(() => {
    if (!selectedAccountExists || !form.symbol.trim()) {
      setMarketPrice(null);
      setMarketDirection("flat");
      return;
    }
    const livePrice = livePrices[liveSymbol];
    const nextPrice = livePrice?.price ?? null;
    setMarketPrice((current) => {
      if (typeof current === "number" && typeof nextPrice === "number") {
        if (nextPrice > current) {
          setMarketDirection("up");
        } else if (nextPrice < current) {
          setMarketDirection("down");
        }
      }
      return nextPrice;
    });
  }, [form.symbol, livePrices, liveSymbol, selectedAccountExists]);

  useEffect(() => {
    if (!isQuickOrder || !selectedAccountExists || !form.symbol.trim()) {
      setQuickQuote(null);
      setQuickQuoteError("");
      return;
    }
    const requestId = ++quickQuoteRequestRef.current;
    const loadQuickQuote = async () => {
      try {
        const quote = await api("/orders/quick/preview", "POST", {
          symbol: form.symbol.trim().toUpperCase(),
          timeframe: quickTimeframe,
          side: form.side,
          targets: selectedTargetIds.flatMap((accountId) => {
            const riskAmount = Number(riskInputs[accountId]);
            return Number.isFinite(riskAmount) && riskAmount > 0
              ? [{ account_db_id: accountId, risk_amount: riskAmount }]
              : [];
          }),
        }, token);
        if (requestId !== quickQuoteRequestRef.current) return;
        setQuickQuote(quote);
        setQuickQuoteError("");
        setForm((current) => ({
          ...current,
          entry: String(quote.entry),
          stop_loss: String(quote.stop_loss),
          target: "",
        }));
      } catch (error) {
        if (requestId !== quickQuoteRequestRef.current) return;
        setQuickQuote(null);
        setQuickQuoteError(error?.message || "Quick Order quote is unavailable.");
      }
    };
    loadQuickQuote();
    return () => {
      quickQuoteRequestRef.current += 1;
    };
  }, [isQuickOrder, selectedAccountExists, form.symbol, form.side, quickTimeframe, token, activeAccountId, accounts, riskInputs, selectedTargetIds]);

  const selectedTargets = useMemo(() => {
    return selectedTargetIds
      .map((accountId) => {
        const account = accounts.find((item) => item.id === accountId);
        if (!account) return null;
        const riskAmount = Number(riskInputs[accountId]);
        return {
          account_db_id: account.id,
          account_name: account.account_name,
          risk_amount: riskAmount,
          saved_risk_amount: account.risk_amount
        };
      })
      .filter(Boolean);
  }, [accounts, riskInputs, selectedTargetIds]);

  useEffect(() => {
    const run = async () => {
      if (!selectedAccountExists || (!isMarketOrder && !entry) || !sl || selectedTargets.length === 0) {
        setPreview(null);
        setPreviewError("");
        return;
      }
      const data = await api("/risk-preview/multi", "POST", {
        symbol: form.symbol,
        order_type: effectiveOrderType,
        side: form.side,
        entry: effectiveEntry,
        stop_loss: sl,
        target,
        conditional_order: isConditionalSl,
        trigger_price: isConditionalSl && Number.isFinite(triggerPrice) ? triggerPrice : null,
        targets: selectedTargets.map((item) => ({
          account_db_id: item.account_db_id,
          risk_amount: item.risk_amount
        }))
      }, token);
      setPreview(data);
      setPreviewError("");
    };
    run().catch((err) => {
      setPreview(null);
      setPreviewError(err.message);
    });
  }, [form.symbol, effectiveOrderType, form.side, form.entry, form.stop_loss, form.target, form.conditional_order, form.trigger_price, token, entry, sl, target, triggerPrice, isConditionalSl, selectedAccountExists, selectedTargets, isMarketOrder, marketPrice, effectiveEntry]);

  const fieldErrors = {
    symbol: form.symbol.trim() ? "" : "Symbol is required.",
    entry: isMarketOrder
      ? ""
      : !Number.isFinite(entry) || entry <= 0
      ? "Entry must be a valid positive number."
      : isConditionalSl && form.side === "SELL" && Number.isFinite(triggerPrice) && entry >= triggerPrice
        ? "Conditional SELL entry must be below trigger price."
      : isConditionalSl && form.side === "BUY" && Number.isFinite(triggerPrice) && entry <= triggerPrice
          ? "Conditional BUY entry must be above trigger price."
      : !isConditionalSl && marketPrice !== null && effectiveOrderType === "SL" && form.side === "BUY" && entry <= marketPrice
        ? "SL BUY entry must be above current price."
      : !isConditionalSl && marketPrice !== null && effectiveOrderType === "SL" && form.side === "SELL" && entry >= marketPrice
          ? "SL SELL entry must be below current price."
      : marketPrice !== null && effectiveOrderType === "LIMIT" && form.side === "BUY" && entry >= marketPrice
            ? "LIMIT BUY entry must be below current price."
      : marketPrice !== null && effectiveOrderType === "LIMIT" && form.side === "SELL" && entry <= marketPrice
              ? "LIMIT SELL entry must be above current price."
              : "",
    stop_loss: !Number.isFinite(sl) || sl <= 0
      ? "Stop Loss must be a valid positive number."
      : Number.isFinite(effectiveEntry) && form.side === "BUY" && sl >= effectiveEntry
        ? "For BUY, Stop Loss must be below entry."
        : Number.isFinite(effectiveEntry) && form.side === "SELL" && sl <= effectiveEntry
          ? "For SELL, Stop Loss must be above entry."
          : "",
    target: form.target && target === null
      ? "Target must be a valid number."
      : target !== null && form.side === "BUY" && target <= effectiveEntry
        ? "For BUY, target should be above entry."
        : target !== null && form.side === "SELL" && target >= effectiveEntry
          ? "For SELL, target should be below entry."
          : "",
    targets: selectedTargets.length === 0
      ? "Select at least one account for copy trading."
      : selectedTargets.some((item) => !Number.isFinite(item.risk_amount) || item.risk_amount <= 0)
        ? "Each selected account needs a valid positive risk amount."
        : "",
    cancel_at: !form.cancel_at
      ? ""
      : effectiveOrderType !== "LIMIT"
        ? "Cancel At is only for LIMIT orders."
        : !Number.isFinite(cancelAt)
          ? "Cancel At must be a valid number."
          : form.side === "BUY" && Number.isFinite(effectiveEntry) && cancelAt <= effectiveEntry
            ? "For BUY, Cancel At must be above entry."
            : form.side === "SELL" && Number.isFinite(effectiveEntry) && cancelAt >= effectiveEntry
              ? "For SELL, Cancel At must be below entry."
              : "",
    trigger_price: !isConditionalSl
      ? ""
      : !form.trigger_price || !Number.isFinite(triggerPrice) || triggerPrice <= 0
        ? "Trigger price is required."
        : marketPrice !== null && form.side === "SELL" && triggerPrice <= marketPrice
          ? "For SELL, trigger must be above current price."
          : marketPrice !== null && form.side === "BUY" && triggerPrice >= marketPrice
            ? "For BUY, trigger must be below current price."
            : "",
  };
  const formError = !selectedAccountExists ? "Select a local MT5 account before placing orders." : "";
  const hasValidationErrors = Boolean(formError || Object.values(fieldErrors).some(Boolean) || (isQuickOrder && !quickQuote));

  const saveAccountRisk = async (accountId) => {
    const riskAmount = Number(riskInputs[accountId]);
    if (!Number.isFinite(riskAmount) || riskAmount <= 0) {
      onNotify("error", "Risk amount must be greater than 0.");
      return;
    }
    const account = accounts.find((item) => item.id === accountId);
    if (!account || Number(account.risk_amount) === riskAmount) return;

    setSavingRiskIds((current) => ({ ...current, [accountId]: true }));
    try {
      const updatedAccount = await api(`/accounts/${accountId}/risk`, "PATCH", { risk_amount: riskAmount }, token);
      onAccountRiskSaved(updatedAccount);
      onNotify("success", `Saved risk for ${updatedAccount.account_name}.`);
    } catch (err) {
      onNotify("error", err.message);
    } finally {
      setSavingRiskIds((current) => ({ ...current, [accountId]: false }));
    }
  };

  const placeOrder = async () => {
    setSubmitAttempted(true);
    setTouchedFields({
      symbol: true,
      entry: true,
      stop_loss: true,
      target: true,
      cancel_at: true,
      trigger_price: true,
      targets: true
    });
    if (hasValidationErrors) return;

    setPlacingOrder(true);
    try {
      const payload = {
        symbol: form.symbol.trim().toUpperCase(),
        side: form.side,
        comment: form.comment.trim() || null,
        automatic_trade_management: form.automatic_trade_management,
        targets: selectedTargets.map((item) => ({
          account_db_id: item.account_db_id,
          risk_amount: item.risk_amount
        }))
      };
      const result = isQuickOrder
        ? await api("/orders/quick", "POST", { ...payload, timeframe: quickTimeframe }, token)
        : await api("/orders", "POST", {
            ...form,
            ...payload,
            order_type: effectiveOrderType,
            entry: effectiveEntry,
            stop_loss: sl,
            target,
            cancel_at: effectiveOrderType === "LIMIT" && form.cancel_at ? cancelAt : null,
            conditional_order: isConditionalSl,
            trigger_price: isConditionalSl ? triggerPrice : null,
            retryable_order: (effectiveOrderType === "LIMIT" || effectiveOrderType === "SL") ? form.retryable_order : false,
          }, token);
      const closedOffers = (result.results || []).filter((item) => item.market_closed && item.order_id);
      if (closedOffers.length) {
        setMarketClosedOffer({ results: closedOffers, placement: result });
      }
      const summary = summarizePlacement(result);
      if (summary) {
        onNotify(result.failed_count > 0 ? "error" : "success", summary);
      }
      if (result.failed_count === 0 && !closedOffers.length) {
        const defaults = me?.ui_settings?.order_defaults || {};
        setForm((current) => ({
          ...current,
          entry: "",
          stop_loss: "",
          target: "",
          cancel_at: "",
          trigger_price: "",
          conditional_order: false,
          comment: "",
          retryable_order: defaults.retryable_order !== false,
          automatic_trade_management: defaults.automatic_trade_management !== false,
        }));
        setSubmitAttempted(false);
        setTouchedFields({});
      }
    } catch (err) {
      onNotify("error", err.message);
    } finally {
      setPlacingOrder(false);
    }
  };

  const confirmMarketClosedDefer = async () => {
    if (!marketClosedOffer?.results?.length) return;
    setDeferBusy(true);
    try {
      for (const item of marketClosedOffer.results) {
        await api(`/orders/${item.order_id}/defer-market-open`, "POST", undefined, token);
      }
      onNotify("success", `Pending order saved. It will be sent to the broker after Monday 04:30 IST.`);
      setMarketClosedOffer(null);
      const defaults = me?.ui_settings?.order_defaults || {};
      setForm((current) => ({
        ...current,
        entry: "",
        stop_loss: "",
        target: "",
        cancel_at: "",
        trigger_price: "",
        conditional_order: false,
        comment: "",
        retryable_order: defaults.retryable_order !== false,
        automatic_trade_management: defaults.automatic_trade_management !== false,
      }));
      setSubmitAttempted(false);
      setTouchedFields({});
    } catch (err) {
      onNotify("error", err.message || "Could not save pending order.");
    } finally {
      setDeferBusy(false);
    }
  };

  const declineMarketClosedDefer = async () => {
    if (!marketClosedOffer?.results?.length) {
      setMarketClosedOffer(null);
      return;
    }
    setDeferBusy(true);
    try {
      for (const item of marketClosedOffer.results) {
        await api(`/orders/${item.order_id}/decline-defer`, "POST", undefined, token);
      }
      onNotify("info", "Pending order not saved.");
      setMarketClosedOffer(null);
    } catch (err) {
      onNotify("error", err.message || "Could not decline pending order.");
    } finally {
      setDeferBusy(false);
    }
  };

  const markTouched = (fieldName) => setTouchedFields((current) => ({ ...current, [fieldName]: true }));
  const previewMap = Object.fromEntries((preview?.targets || []).map((item) => [item.account_db_id, item]));

  const runCandleDetector = async () => {
    const symbol = form.symbol.trim().toUpperCase();
    if (!symbol) {
      setDetectorError("Enter a symbol before running the detector.");
      return;
    }
    setDetectorLoading(true);
    setDetectorError("");
    setDetectorResult(null);
    try {
      const result = await api("/orders/candle-detector/preview", "POST", {
        symbol,
        timeframe: detectorForm.timeframe,
        candle_type: detectorForm.candle_type,
        account_id: activeAccountId || undefined,
      }, token);
      setDetectorResult(result);
      if (!result?.found) {
        setDetectorError(result?.message || "No matching candle found.");
        return;
      }
      setForm((current) => ({
        ...current,
        symbol,
        order_type: "SL",
        side: result.side || current.side,
        entry: result.entry === null || result.entry === undefined ? current.entry : String(result.entry),
        stop_loss: result.stop_loss === null || result.stop_loss === undefined ? current.stop_loss : String(result.stop_loss),
        comment: current.comment || `Candle Detector ${String(result.candle_type || "").replace("_", " ")}`,
      }));
      setTouchedFields((current) => ({
        ...current,
        symbol: true,
        entry: true,
        stop_loss: true,
      }));
      onNotify("success", `Detected ${String(result.candle_type || "").replace("_", " ")} on ${symbol}.`);
    } catch (err) {
      setDetectorError(err.message || "Unable to run candle detector.");
    } finally {
      setDetectorLoading(false);
    }
  };

  return (
    <section className="h-full overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:[&_input]:border-slate-700 dark:[&_input]:bg-slate-950 dark:[&_input]:text-slate-100 dark:[&_select]:border-slate-700 dark:[&_select]:bg-slate-950 dark:[&_select]:text-slate-100 dark:[&_.bg-white]:!bg-slate-900 dark:[&_.bg-slate-50]:!bg-slate-950 dark:[&_.bg-indigo-50]:!bg-slate-900 dark:[&_.text-slate-950]:!text-slate-100 dark:[&_.text-slate-900]:!text-slate-100 dark:[&_.text-slate-800]:!text-slate-100 dark:[&_.text-slate-700]:!text-slate-200 dark:[&_.text-slate-600]:!text-slate-300 dark:[&_.text-slate-500]:!text-slate-400 dark:[&_.border-slate-200]:!border-slate-800 dark:[&_.border-slate-300]:!border-slate-700">
      <div className="mb-3 space-y-2">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-indigo-500">Trade Ticket</p>
            <h3 className="text-xl font-bold leading-tight text-slate-950">Place Order</h3>
          </div>
          <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
            <button type="button" onClick={() => setOrderMode("quick")} className={`rounded-lg px-2 py-1 text-[10px] font-bold ${isQuickOrder ? "bg-indigo-600 text-white shadow" : "text-slate-500"}`}>Quick</button>
            <button type="button" onClick={() => setOrderMode("manual")} className={`rounded-lg px-2 py-1 text-[10px] font-bold ${!isQuickOrder ? "bg-indigo-600 text-white shadow" : "text-slate-500"}`}>Manual</button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700">
          <span className="inline-flex items-center gap-2">
            {form.symbol.trim() ? <SymbolIcon symbol={form.symbol} size="sm" /> : null}
            {form.symbol.trim() || "Select Instrument"}
          </span>
        </span>
        <span
          className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
            marketDirection === "up"
              ? "bg-emerald-100 text-emerald-700"
              : marketDirection === "down"
                ? "bg-rose-100 text-rose-700"
                : "bg-slate-100 text-slate-700"
          }`}
        >
          <span className="inline-flex items-center gap-1">
            <span className="inline-flex w-3 items-center justify-center">
              <span className={marketDirection === "flat" ? "invisible" : ""}>
                {marketDirection === "up" ? "▲" : "▼"}
              </span>
            </span>
            <span>
              {formatPrice(marketPrice, [
                livePrices[liveSymbol]?.bid,
                livePrices[liveSymbol]?.ask
              ], 0, priceDigits)}
            </span>
          </span>
        </span>
        </div>
        <SymbolResolveHint info={symbolResolve} />
      </div>
      <div className="grid gap-2">
        <label className="space-y-0.5 text-xs">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Symbol</span>
          <input
            className={`w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none disabled:bg-slate-100 ${inputTone(hasVisibleFieldError("symbol", touchedFields, submitAttempted) && fieldErrors.symbol)}`}
            value={form.symbol}
            disabled={disabled}
            onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
            onBlur={() => markTouched("symbol")}
            placeholder="Symbol"
          />
          {hasVisibleFieldError("symbol", touchedFields, submitAttempted) && fieldErrors.symbol && (
            <p className="text-xs text-rose-600">{fieldErrors.symbol}</p>
          )}
        </label>
        {isQuickOrder ? (
          <div className="grid grid-cols-2 gap-2 rounded-xl border border-emerald-200 bg-emerald-50/70 p-2.5">
            <label className="space-y-0.5 text-xs">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Candle timeframe</span>
              <select value={quickTimeframe} disabled={disabled} onChange={(event) => setQuickTimeframe(event.target.value)} className="w-full rounded-lg border border-emerald-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800 outline-none">
                <option value="M1">1 minute</option>
                <option value="M3">3 minutes</option>
                <option value="M5">5 minutes</option>
              </select>
            </label>
            <div className="space-y-0.5 text-xs">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Live stop rule</span>
              <p className="rounded-lg border border-emerald-200 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-800">{form.side === "BUY" ? "Low - 1 tick" : "High + 1 tick"}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Order Type</p>
            <div className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1">
              {["SL", "LIMIT", "MARKET"].map((orderType) => (
                <button
                  key={orderType}
                  type="button"
                  disabled={disabled}
                  onClick={() => setForm({
                    ...form,
                    order_type: orderType,
                    cancel_at: orderType === "LIMIT" ? form.cancel_at : "",
                    conditional_order: orderType === "SL" ? form.conditional_order : false,
                    trigger_price: orderType === "SL" ? form.trigger_price : "",
                  })}
                  className={`rounded-lg px-2 py-1.5 text-[11px] font-semibold transition ${form.order_type === orderType ? "bg-indigo-600 text-white shadow" : "text-slate-500"} ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
                >
                  {orderType}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="space-y-2 rounded-xl border border-slate-200 bg-white/90 p-2.5 dark:bg-slate-900">
          <label className="flex items-start gap-2 text-xs text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={form.automatic_trade_management}
              disabled={disabled}
              onChange={async (event) => {
                const checked = event.target.checked;
                setForm((current) => ({ ...current, automatic_trade_management: checked }));
                try {
                  await persistOrderDefaults({
                    automatic_trade_management: checked,
                    retryable_order: form.retryable_order,
                  });
                } catch {
                  setForm((current) => ({ ...current, automatic_trade_management: !checked }));
                }
              }}
            />
            <span>
              <span className="font-semibold text-slate-900">Automatic trade management</span>
              <span className="mt-0.5 block text-[11px] text-slate-500">Book 50% at 4R; close the rest at target, or let it run if no target is set.</span>
            </span>
          </label>
          {!isQuickOrder && (form.order_type === "LIMIT" || form.order_type === "SL") ? (
            <label className="flex items-start gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={form.retryable_order}
                disabled={disabled}
                onChange={async (event) => {
                  const checked = event.target.checked;
                  setForm((current) => ({ ...current, retryable_order: checked }));
                  try {
                    await persistOrderDefaults({
                      automatic_trade_management: form.automatic_trade_management,
                      retryable_order: checked,
                    });
                  } catch {
                    setForm((current) => ({ ...current, retryable_order: !checked }));
                  }
                }}
              />
              <span>
                <span className="font-semibold text-slate-900">Retryable order</span>
                <span className="mt-0.5 block text-[11px] text-slate-500">After one clean stop-loss hit, re-place once as an SL order with the same entry, stop, and quantity.</span>
              </span>
            </label>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <BinarySwitch
            label="Direction"
            leftLabel="BUY"
            rightLabel="SELL"
            value={form.side}
            onChange={(value) => setForm({ ...form, side: value })}
            leftValue="BUY"
            rightValue="SELL"
            leftActiveClass="bg-emerald-600 text-white shadow"
            rightActiveClass="bg-rose-600 text-white shadow"
            disabled={disabled}
          />
          {!isQuickOrder && form.order_type === "SL" ? (
            <BinarySwitch
              label="Conditional order"
              leftLabel="Off"
              rightLabel="On"
              value={form.conditional_order ? "ON" : "OFF"}
              onChange={(value) =>
                setForm({
                  ...form,
                  conditional_order: value === "ON",
                  trigger_price: value === "ON" ? form.trigger_price : "",
                })
              }
              leftValue="OFF"
              rightValue="ON"
              leftActiveClass="bg-slate-600 text-white shadow"
              rightActiveClass="bg-indigo-600 text-white shadow"
              disabled={disabled}
            />
          ) : (
            <label className="space-y-0.5 text-xs">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Entry</span>
              <input
                className={`w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none disabled:bg-slate-100 ${inputTone(hasVisibleFieldError("entry", touchedFields, submitAttempted) && fieldErrors.entry)}`}
                placeholder={isMarketOrder ? "Market" : "Entry"}
                disabled={disabled || isMarketOrder}
                value={form.entry}
                step={priceDigits !== null && priceDigits !== undefined ? priceStepForDigits(priceDigits) : "any"}
                onChange={(e) => setForm({ ...form, entry: e.target.value })}
                onBlur={() => {
                  markTouched("entry");
                  roundPriceField("entry");
                }}
              />
            </label>
          )}
        </div>
        {!isQuickOrder && form.order_type === "SL" && form.conditional_order ? (
          <label className="space-y-0.5 text-xs">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">When price crosses</span>
            <input
              className={`w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none disabled:bg-slate-100 ${inputTone(hasVisibleFieldError("trigger_price", touchedFields, submitAttempted) && fieldErrors.trigger_price)}`}
              placeholder={form.side === "SELL" ? "Above current price" : "Below current price"}
              disabled={disabled}
              value={form.trigger_price}
              step={priceDigits !== null && priceDigits !== undefined ? priceStepForDigits(priceDigits) : "any"}
              onChange={(e) => setForm({ ...form, trigger_price: e.target.value })}
              onBlur={() => {
                markTouched("trigger_price");
                roundPriceField("trigger_price");
              }}
            />
            <p className="text-[11px] text-slate-500">
              {form.side === "SELL"
                ? "Arms after price trades up through this level, then places the SELL stop (entry must be below trigger)."
                : "Arms after price trades down through this level, then places the BUY stop (entry must be above trigger)."}
            </p>
            {(hasVisibleFieldError("trigger_price", touchedFields, submitAttempted) && fieldErrors.trigger_price) ? (
              <p className="text-[11px] text-rose-600">{fieldErrors.trigger_price}</p>
            ) : null}
          </label>
        ) : null}
        {!isQuickOrder && form.order_type === "SL" ? (
          <label className="space-y-0.5 text-xs">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Entry</span>
            <input
              className={`w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none disabled:bg-slate-100 ${inputTone(hasVisibleFieldError("entry", touchedFields, submitAttempted) && fieldErrors.entry)}`}
              placeholder="Entry"
              disabled={disabled}
              value={form.entry}
              step={priceDigits !== null && priceDigits !== undefined ? priceStepForDigits(priceDigits) : "any"}
              onChange={(e) => setForm({ ...form, entry: e.target.value })}
              onBlur={() => {
                markTouched("entry");
                roundPriceField("entry");
              }}
            />
          </label>
        ) : null}
        {(hasVisibleFieldError("entry", touchedFields, submitAttempted) && fieldErrors.entry) && (
          <p className="text-[11px] text-rose-600">{fieldErrors.entry}</p>
        )}
        <div className={`grid gap-2 ${isQuickOrder ? "grid-cols-1" : "grid-cols-2"}`}>
          <label className="space-y-0.5 text-xs">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{isQuickOrder ? "Live Stop Loss" : "Stop Loss"}</span>
            <input
              className={`w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none disabled:bg-slate-100 ${inputTone(hasVisibleFieldError("stop_loss", touchedFields, submitAttempted) && fieldErrors.stop_loss)}`}
              placeholder="Stop"
              disabled={disabled || isQuickOrder}
              value={form.stop_loss}
              step={priceDigits !== null && priceDigits !== undefined ? priceStepForDigits(priceDigits) : "any"}
              onChange={(e) => setForm({ ...form, stop_loss: e.target.value })}
              onBlur={() => {
                markTouched("stop_loss");
                roundPriceField("stop_loss");
              }}
            />
          </label>
          {!isQuickOrder && <label className="space-y-0.5 text-xs">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Target</span>
            <input
              className={`w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none disabled:bg-slate-100 ${inputTone(hasVisibleFieldError("target", touchedFields, submitAttempted) && fieldErrors.target)}`}
              placeholder="Optional"
              disabled={disabled}
              value={form.target}
              step={priceDigits !== null && priceDigits !== undefined ? priceStepForDigits(priceDigits) : "any"}
              onChange={(e) => setForm({ ...form, target: e.target.value })}
              onBlur={() => {
                markTouched("target");
                roundPriceField("target");
              }}
            />
          </label>}
        </div>
        {!isQuickOrder && form.order_type === "LIMIT" ? (
          <label className="space-y-0.5 text-xs">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Cancel At</span>
            <input
              className={`w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none disabled:bg-slate-100 ${inputTone(hasVisibleFieldError("cancel_at", touchedFields, submitAttempted) && fieldErrors.cancel_at)}`}
              placeholder={form.side === "BUY" ? "Above entry (optional)" : "Below entry (optional)"}
              disabled={disabled}
              value={form.cancel_at}
              step={priceDigits !== null && priceDigits !== undefined ? priceStepForDigits(priceDigits) : "any"}
              onChange={(e) => setForm({ ...form, cancel_at: e.target.value })}
              onBlur={() => {
                markTouched("cancel_at");
                roundPriceField("cancel_at");
              }}
            />
            {(hasVisibleFieldError("cancel_at", touchedFields, submitAttempted) && fieldErrors.cancel_at) ? (
              <p className="text-[11px] text-rose-600">{fieldErrors.cancel_at}</p>
            ) : (
              <p className="text-[11px] text-slate-500">If price taps this level before fill, the pending LIMIT is cancelled.</p>
            )}
          </label>
        ) : null}
        {isQuickOrder && (
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 font-mono text-[11px] text-slate-600">
            {quickQuote ? `Completed candle H ${formatPrice(quickQuote.candle_high, [], 0, quickQuote.price_digits)} / L ${formatPrice(quickQuote.candle_low, [], 0, quickQuote.price_digits)} · ${quickQuote.timeframe}` : "Loading the last completed candle and live quote..."}
          </p>
        )}
        {hasVisibleFieldError("stop_loss", touchedFields, submitAttempted) && fieldErrors.stop_loss && (
          <p className="text-[11px] text-rose-600">{fieldErrors.stop_loss}</p>
        )}
        {hasVisibleFieldError("target", touchedFields, submitAttempted) && fieldErrors.target && (
          <p className="text-[11px] text-rose-600">{fieldErrors.target}</p>
        )}
        <label className="space-y-0.5 text-xs">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Comment</span>
          <input
            className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs outline-none focus:border-indigo-500 disabled:bg-slate-100"
            placeholder="Optional note"
            disabled={disabled}
            value={form.comment}
            onChange={(e) => setForm({ ...form, comment: e.target.value })}
          />
        </label>
      </div>
      <div className="mt-3 rounded-xl border border-slate-200 bg-white/80 p-2.5 dark:bg-slate-900">
        <div className="mb-2 space-y-0.5">
          <div>
            <h4 className="text-sm font-bold uppercase tracking-wide text-slate-700">Copy Accounts</h4>
            <p className="text-[11px] text-slate-500">Choose up to two same-broker accounts. The feed badge is optional.</p>
          </div>
          {hasVisibleFieldError("targets", touchedFields, submitAttempted) && fieldErrors.targets && (
            <p className="text-xs font-medium text-rose-600">{fieldErrors.targets}</p>
          )}
        </div>
        <div className="space-y-1.5">
          {accounts.map((account) => {
            const isChecked = selectedTargetIds.includes(account.id);
            const previewItem = previewMap[account.id];
            const isActiveFeedAccount = activeAccountId === account.id;
            const selectionDisabled = isExecutionAccountDisabled(account, selectedTargetIds, accounts, activeAccountId);
            return (
              <div
                key={account.id}
                className={`grid gap-2 rounded-xl border px-2.5 py-2 transition ${
                  isChecked ? "border-indigo-200 bg-indigo-50/70" : "border-slate-200 bg-white"
                }`}
              >
                <label className="flex min-w-0 items-center gap-2">
                  <input
                    type="checkbox"
                    checked={isChecked}
                    disabled={selectionDisabled}
                    onChange={(e) => {
                      markTouched("targets");
                      setSelectedTargetIds((current) => {
                        if (e.target.checked) {
                          return normalizeExecutionSelection(current, [...current, account.id], accounts, activeAccountId);
                        }
                        return normalizeExecutionSelection(
                          current,
                          current.filter((item) => item !== account.id),
                          accounts,
                          activeAccountId,
                        );
                      });
                    }}
                    className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 items-center gap-2">
                      <p className="min-w-0 truncate text-sm font-semibold text-slate-900" title={account.account_name}>{account.account_name}</p>
                      {isActiveFeedAccount && (
                        <span className="shrink-0 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-700">
                          Feed
                        </span>
                      )}
                    </div>
                    <p className="truncate text-[10px] text-slate-500">
                      Bal {formatCurrencyValue(account.available_margin ?? 0)} · Risk {account.risk_amount}
                    </p>
                  </div>
                </label>
                <div className="grid grid-cols-2 gap-2">
                <label className="space-y-0.5 text-xs">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Risk</span>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min="1"
                      disabled={!isChecked}
                      className="w-full rounded-lg border border-slate-300 px-2 py-1 text-xs outline-none focus:border-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-100"
                      value={riskInputs[account.id] ?? ""}
                      onChange={(e) => setRiskInputs((current) => ({ ...current, [account.id]: e.target.value }))}
                      onBlur={() => saveAccountRisk(account.id)}
                    />
                    {savingRiskIds[account.id] && <span className="text-[10px] font-medium text-slate-500">Saving</span>}
                  </div>
                </label>
                <div className="space-y-0.5 text-xs">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Qty</span>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 font-semibold text-slate-800">
                    {isChecked ? (previewItem ? formatQty(previewItem.quantity) : "—") : "Not selected"}
                  </div>
                </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {preview && (
        <div className="mt-2 grid grid-cols-5 gap-1 rounded-xl border border-indigo-100 bg-indigo-50 p-2 text-[10px] text-slate-700">
          <p><span className="block font-semibold uppercase tracking-wide text-slate-500">SL Distance</span> <span className="font-bold text-slate-900">{formatDistanceValue(form.symbol, preview.sl_pips)}</span></p>
          <p><span className="block font-semibold uppercase tracking-wide text-slate-500">Accounts</span> <span className="font-bold text-slate-900">{preview.targets.length}</span></p>
          <p><span className="block font-semibold uppercase tracking-wide text-slate-500">Risk</span> <span className="font-bold text-slate-900">{preview.targets.reduce((sum, item) => sum + Number(item.risk_amount || 0), 0)}</span></p>
          <p><span className="block font-semibold uppercase tracking-wide text-slate-500">R:R</span> <span className="font-bold text-slate-900">{preview.rr_ratio ?? "-"}</span></p>
          <p>
            <span className="block font-semibold uppercase tracking-wide text-slate-500">Exp</span>{" "}
            <span className="font-bold text-slate-900">
              {renderExpectedRewardRisk({
                stop_loss: sl,
                target,
                entry: effectiveEntry,
                risk_amount: preview.targets.reduce((sum, item) => sum + Number(item.risk_amount || 0), 0),
                rr_ratio: preview.rr_ratio,
              })}
            </span>
          </p>
        </div>
      )}
      {previewError && (
        <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
          Preview unavailable: {previewError}
        </div>
      )}
      {isQuickOrder && quickQuoteError && (
        <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
          Quick Order quote unavailable: {quickQuoteError}
        </div>
      )}
      {submitAttempted && formError && (
        <div className="mt-2 rounded-xl border border-rose-200 bg-rose-50 p-2 text-xs text-rose-700">
          <p>- {formError}</p>
        </div>
      )}
      <div className="mt-2 space-y-2">
        {!isQuickOrder && <button
          type="button"
          onClick={() => {
            setDetectorOpen(true);
            setDetectorError("");
            setDetectorResult(null);
          }}
          disabled={disabled}
          className="w-full rounded-xl border border-indigo-200 bg-white px-4 py-2 text-xs font-bold text-indigo-700 shadow-sm hover:bg-indigo-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
        >
          Candle Detector
        </button>}
        <button
          onClick={placeOrder}
          disabled={hasValidationErrors || placingOrder}
          className="w-full rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {placingOrder ? "Submitting..." : isQuickOrder ? `Quick ${titleCaseWord(form.side)} Market Order` : `Place ${titleCaseWord(effectiveOrderType)} ${titleCaseWord(form.side)} Order`}
        </button>
      </div>
      {detectorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-indigo-600">Candle Detector</p>
                <h3 className="mt-1 text-xl font-bold text-slate-900">{form.symbol.trim().toUpperCase() || "Select Symbol"}</h3>
                <p className="mt-1 text-sm text-slate-500">Scans the last 5 completed candles and populates an SL order with a 1-point buffer.</p>
              </div>
              <button type="button" onClick={() => setDetectorOpen(false)} className="rounded-lg px-3 py-1 text-sm font-semibold text-slate-500 hover:bg-slate-100">Close</button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="font-medium text-slate-600">Timeframe</span>
                <select
                  value={detectorForm.timeframe}
                  onChange={(event) => setDetectorForm((current) => ({ ...current, timeframe: event.target.value }))}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
                >
                  <option value="M1">1 minute</option>
                  <option value="M5">5 minutes</option>
                  <option value="M15">15 minutes</option>
                </select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-slate-600">Candle Type</span>
                <select
                  value={detectorForm.candle_type}
                  onChange={(event) => setDetectorForm((current) => ({ ...current, candle_type: event.target.value }))}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
                >
                  <option value="HAMMER">Hammer</option>
                  <option value="SHOOTING_STAR">Shooting Star</option>
                </select>
              </label>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={runCandleDetector}
                disabled={detectorLoading}
                className="rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {detectorLoading ? "Detecting..." : "Detect Candle"}
              </button>
              <button type="button" onClick={() => setDetectorOpen(false)} className="rounded-xl border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-700">Done</button>
            </div>
            {detectorError ? (
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">{detectorError}</div>
            ) : null}
            {detectorResult?.found ? (
              <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                <p className="text-sm font-bold text-emerald-800">Matched {String(detectorResult.candle_type || "").replace("_", " ")}</p>
                <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Side</p>
                    <p className="font-bold text-slate-900">{detectorResult.side}</p>
                  </div>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Entry</p>
                    <p className="font-bold text-slate-900">{formatPrice(detectorResult.entry, [detectorResult.stop_loss])}</p>
                  </div>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Suggested SL</p>
                    <p className="font-bold text-slate-900">{formatPrice(detectorResult.stop_loss, [detectorResult.entry])}</p>
                  </div>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">SL Distance</p>
                    <p className="font-bold text-slate-900">{detectorResult.sl_pips == null ? "-" : formatDistanceValue(detectorResult.symbol, detectorResult.sl_pips)}</p>
                  </div>
                </div>
                <p className="mt-3 text-xs text-slate-600">Point buffer applied: {formatPrice(detectorResult.point)}. Stop loss remains editable in the order ticket.</p>
              </div>
            ) : null}
            {detectorResult?.scanned_candles?.length ? (
              <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Scanned Completed Candles</p>
                <div className="space-y-2">
                  {detectorResult.scanned_candles.map((candle) => (
                    <div key={candle.time} className={`grid gap-2 rounded-xl px-3 py-2 text-xs sm:grid-cols-[1.4fr_repeat(4,1fr)] ${candle.matched ? "bg-emerald-100 text-emerald-900" : "bg-white text-slate-700"}`}>
                      <span className="font-semibold">{formatNotificationTimestamp(candle.time)}</span>
                      <span>O {formatPrice(candle.open, [candle.high, candle.low, candle.close])}</span>
                      <span>H {formatPrice(candle.high, [candle.open, candle.low, candle.close])}</span>
                      <span>L {formatPrice(candle.low, [candle.open, candle.high, candle.close])}</span>
                      <span>C {formatPrice(candle.close, [candle.open, candle.high, candle.low])}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
      {marketClosedOffer ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-slate-900">Market is closed</h3>
            <p className="mt-2 text-sm text-slate-600">
              Do you want to place a pending order? It will be saved locally and sent to the broker after Monday 04:30 IST.
            </p>
            <p className="mt-2 text-xs text-slate-500">
              {marketClosedOffer.results.length} account{marketClosedOffer.results.length === 1 ? "" : "s"} affected.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={deferBusy}
                onClick={declineMarketClosedDefer}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                No Thanks
              </button>
              <button
                type="button"
                disabled={deferBusy}
                onClick={confirmMarketClosedDefer}
                className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {deferBusy ? "Saving…" : "OK"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PendingOrdersPositionsPanel({
  TrackerComponent,
  liveOrders,
  setCloseOrder,
  setEditOrder,
  onFullClosePosition,
  onCancelPendingOrder,
  actionLoadingId,
  token,
  accounts = [],
  activeAccountId = "",
  livePrices = {},
  onNotify,
}) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <section
      className="flex h-full min-h-0 flex-col rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
      style={collapsed ? undefined : { overflow: "auto" }}
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2 dark:border-slate-800">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">Positions Terminal</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">Live positions, working orders, and broker history in one place.</p>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed((current) => !current)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </div>
      {!collapsed && (
        <div className="min-h-0 flex-1 overflow-auto p-3">
          <TrackerComponent
            rows={liveOrders}
            onOpenClose={setCloseOrder}
            onEditOrder={setEditOrder}
            onFullClose={onFullClosePosition}
            onCancelOrder={onCancelPendingOrder}
            actionLoadingId={actionLoadingId}
            token={token}
            accounts={accounts}
            activeAccountId={activeAccountId}
            livePrices={livePrices}
            onNotify={onNotify}
          />
        </div>
      )}
    </section>
  );
}

function humanizeEventType(value) {
  return String(value || "")
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function orderEventFailureReason(event) {
  if (event?.failure_reason) return String(event.failure_reason);
  if (!event?.payload_json) return "";
  try {
    const payload = typeof event.payload_json === "string" ? JSON.parse(event.payload_json) : event.payload_json;
    return String(payload?.error || payload?.failure_reason || payload?.reason || "");
  } catch {
    return "";
  }
}

function parseOrderEventPayload(event) {
  if (!event?.payload_json) return {};
  try {
    return typeof event.payload_json === "string" ? JSON.parse(event.payload_json) : event.payload_json;
  } catch {
    return {};
  }
}

function formatLogPrice(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return null;
  return String(number)
    .includes(".")
    ? number.toFixed(5).replace(/0+$/, "").replace(/\.$/, "")
    : String(number);
}

function orderEventPriceContext(event) {
  const payload = parseOrderEventPayload(event);
  const parts = [];
  if (payload.side) parts.push(String(payload.side).toUpperCase());
  const entry = formatLogPrice(payload.entry ?? payload.price);
  if (entry) parts.push(`entry ${entry}`);
  const stopLoss = formatLogPrice(payload.stop_loss ?? payload.sl);
  if (stopLoss) parts.push(`SL ${stopLoss}`);
  const target = formatLogPrice(payload.target ?? payload.tp);
  if (target) parts.push(`TP ${target}`);
  const quantity = Number(payload.quantity ?? payload.volume);
  if (Number.isFinite(quantity) && quantity > 0) parts.push(`qty ${quantity}`);
  const bid = formatLogPrice(payload.bid);
  const ask = formatLogPrice(payload.ask);
  if (bid || ask) parts.push(`bid ${bid || "-"} ask ${ask || "-"}`);
  return parts.join(" · ");
}

function OrderFailureReason({ reason, className = "mt-1 text-xs text-rose-600" }) {
  if (!reason) return null;
  return <p className={className}>Failure: {reason}</p>;
}

function OrderActivityTimeline({ orderId, token }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!orderId || !token) {
      setEvents([]);
      return;
    }
    let ignore = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await api(`/orders/${orderId}/events`, "GET", undefined, token);
        if (!ignore) setEvents(Array.isArray(data) ? data : []);
      } catch (err) {
        if (!ignore) {
          setEvents([]);
          setError(err.message || "Could not load order activity.");
        }
      } finally {
        if (!ignore) setLoading(false);
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [orderId, token]);

  if (loading) {
    return <p className="mt-3 text-sm text-slate-500">Loading activity...</p>;
  }
  if (error) {
    return <p className="mt-3 text-sm text-rose-600">{error}</p>;
  }
  if (!events.length) {
    return <p className="mt-3 text-sm text-slate-500">No saved activity yet.</p>;
  }

  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-950">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Trade Activity</p>
      <div className="mt-3 space-y-2">
        {events.map((event) => {
          const priceContext = orderEventPriceContext(event);
          const failureReason = orderEventFailureReason(event);
          return (
          <div key={event.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{humanizeEventType(event.event_type)}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{event.event_ts_ist || "-"}</p>
            </div>
            <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{event.message}</p>
            {priceContext ? (
              <p className="mt-1 text-xs font-medium text-slate-600 dark:text-slate-400">Prices: {priceContext}</p>
            ) : null}
            <OrderFailureReason reason={failureReason} className="mt-1 text-xs font-medium text-rose-600" />
            {event.status ? <p className="mt-1 text-xs font-medium text-slate-500 dark:text-slate-400">Status: {humanizeStatus(event.status)}</p> : null}
          </div>
          );
        })}
      </div>
    </div>
  );
}

function Tracker({ rows, onOpenClose, onEditOrder, onFullClose, onCancelOrder, actionLoadingId, token, accounts = [], activeAccountId = "", livePrices = {}, onNotify }) {
  const [tab, setTab] = useState("positions");
  const [historyPage, setHistoryPage] = useState(1);
  const [historyState, setHistoryState] = useState({ records: [], total: 0, page: 1, page_size: 10 });
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [historyAccountId, setHistoryAccountId] = useState(activeAccountId || accounts[0]?.id || "");
  const [historyType, setHistoryType] = useState("all");
  const [historyExporting, setHistoryExporting] = useState(false);
  const [expandedRows, setExpandedRows] = useState({});
  const [closedStatusFilter, setClosedStatusFilter] = useState("CLOSED");
  const [closedAccountFilter, setClosedAccountFilter] = useState(activeAccountId || accounts[0]?.id || "");
  const [closedBrokerRows, setClosedBrokerRows] = useState([]);
  const [closedBrokerLoading, setClosedBrokerLoading] = useState(false);
  const [closedBrokerError, setClosedBrokerError] = useState("");

  const orderAccountId = (row) => String(row?.account_id || row?.planner_plan_account_id || "").trim();
  const usesBrokerClosedToday = closedStatusFilter === "CLOSED" || closedStatusFilter === "ALL";

  const orderedRows = useMemo(() => {
    const statusPriority = {
      POSITION_OPEN: 0,
      PARTIALLY_CLOSED: 1,
      FILLED: 2,
      PENDING: 3,
      PLACEMENT_PENDING: 4,
      WAITING_TRIGGER: 5,
    };
    const timestampValue = (row, active) => {
      const candidates = active
        ? [row.opened_at, row.created_at]
        : [row.closed_at, row.updated_at, row.created_at];
      for (const candidate of candidates) {
        const parsed = parseAppTimestamp(candidate);
        if (parsed) return parsed.getTime();
      }
      return 0;
    };
    const compareRows = (left, right, active = true) => {
      const leftStatus = String(left.status || "").toUpperCase();
      const rightStatus = String(right.status || "").toUpperCase();
      const leftPriority = statusPriority[leftStatus] ?? 99;
      const rightPriority = statusPriority[rightStatus] ?? 99;
      if (leftPriority !== rightPriority) return leftPriority - rightPriority;
      const leftTime = timestampValue(left, active);
      const rightTime = timestampValue(right, active);
      if (leftTime !== rightTime) return rightTime - leftTime;
      return String(left.id || "").localeCompare(String(right.id || ""));
    };
    const active = rows
      .filter((row) => !["CLOSED", "CANCELLED", "FAILED"].includes(String(row.status || "").toUpperCase()))
      .slice()
      .sort((left, right) => compareRows(left, right, true));
    const closed = rows
      .filter((row) => ["CLOSED", "CANCELLED", "FAILED"].includes(String(row.status || "").toUpperCase()))
      .slice()
      .sort((left, right) => compareRows(left, right, false));
    return { active, closed };
  }, [rows]);

  const activeRows = orderedRows.active;
  const todayClosedRows = orderedRows.closed;
  const positionRows = useMemo(
    () => activeRows.filter((row) => ["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].includes(String(row.status || "").toUpperCase())),
    [activeRows]
  );
  const pendingRows = useMemo(
    () =>
      activeRows.filter((row) => {
        const status = String(row.status || "").toUpperCase();
        if (status === "DEFERRED_MARKET_OPEN" || isMarketClosedOfferOrder(row)) return false;
        return ["PENDING", "PLACEMENT_PENDING", "WAITING_TRIGGER"].includes(status);
      }),
    [activeRows]
  );
  const deferredPendingOrders = useMemo(
    () => activeRows.filter((row) => isDeferredMarketOpenOrder(row)),
    [activeRows]
  );
  const isConditionalWaitingOrder = (row) => {
    const status = String(row?.status || "").toUpperCase();
    if (status === "WAITING_TRIGGER") return true;
    return Boolean(row?.manual_context?.conditional_order) && !row?.meta_order_id && ["PENDING", "PLACEMENT_PENDING"].includes(status);
  };
  const { openOrders, stopOrders, conditionalOrders } = useMemo(() => {
    const isValidPrice = (value) => Number.isFinite(Number(value)) && Number(value) > 0;
    const open = [];
    const stop = [];
    const conditional = [];
    pendingRows.forEach((row) => {
      if (isConditionalWaitingOrder(row)) {
        conditional.push(row);
        return;
      }
      if (String(row.order_type || "").toUpperCase() === "LIMIT") open.push(row);
      else stop.push(row);
    });
    const inferPositionDirection = (row) => {
      const entry = Number(row.entry);
      const sl = Number(row.stop_loss);
      const tp = Number(row.target);
      if (Number.isFinite(entry) && entry > 0 && isValidPrice(sl)) {
        return sl < entry ? "LONG" : "SHORT";
      }
      if (Number.isFinite(entry) && entry > 0 && isValidPrice(tp)) {
        return tp > entry ? "LONG" : "SHORT";
      }
      const side = String(row.side || "").toUpperCase();
      if (side === "BUY") return "LONG";
      if (side === "SELL") return "SHORT";
      return "";
    };
    positionRows.forEach((row) => {
      const direction = inferPositionDirection(row);
      const exitSide = direction === "LONG" ? "SELL" : direction === "SHORT" ? "BUY" : "";
      const quantity = row.position_quantity ?? row.quantity;
      if (isValidPrice(row.target)) {
        open.push({
          id: `${row.id}-tp`,
          derived: true,
          kind: "TAKE_PROFIT",
          parent_id: row.id,
          symbol: row.symbol,
          side: exitSide,
          order_type: "LIMIT",
          price: row.target,
          quantity,
          status: "WORKING",
          broker_info: row.broker_info,
          account_id: row.account_id,
          meta_position_id: row.meta_position_id,
        });
      }
      if (isValidPrice(row.stop_loss)) {
        stop.push({
          id: `${row.id}-sl`,
          derived: true,
          kind: "STOP_LOSS",
          parent_id: row.id,
          symbol: row.symbol,
          side: exitSide,
          order_type: "SL",
          price: row.stop_loss,
          quantity,
          status: "WORKING",
          broker_info: row.broker_info,
          account_id: row.account_id,
          meta_position_id: row.meta_position_id,
        });
      }
    });
    return { openOrders: open, stopOrders: stop, conditionalOrders: conditional };
  }, [pendingRows, positionRows]);
  const accountFilteredClosedRows = useMemo(() => {
    if (closedAccountFilter === "ALL") return todayClosedRows;
    if (!closedAccountFilter) return todayClosedRows;
    return todayClosedRows.filter((row) => orderAccountId(row) === closedAccountFilter);
  }, [closedAccountFilter, todayClosedRows]);
  const localNonBrokerClosedRows = useMemo(() => {
    if (closedStatusFilter === "CLOSED") return [];
    return accountFilteredClosedRows.filter((row) => {
      const status = String(row.status || "").toUpperCase();
      if (status === "CLOSED") return false;
      if (closedStatusFilter === "ALL") return status === "CANCELLED" || status === "FAILED";
      return status === closedStatusFilter;
    });
  }, [accountFilteredClosedRows, closedStatusFilter]);
  const closedDisplayCount = useMemo(() => {
    const brokerCount = usesBrokerClosedToday ? closedBrokerRows.length : 0;
    return brokerCount + localNonBrokerClosedRows.length;
  }, [closedBrokerRows.length, localNonBrokerClosedRows.length, usesBrokerClosedToday]);
  const totalBookedPl = useMemo(() => {
    const brokerPl = usesBrokerClosedToday
      ? closedBrokerRows.reduce((sum, row) => sum + Number(row.net_profit || row.profit || 0), 0)
      : 0;
    const localPl = localNonBrokerClosedRows.reduce((sum, row) => sum + Number(row.realized_pl || 0), 0);
    return brokerPl + localPl;
  }, [closedBrokerRows, localNonBrokerClosedRows, usesBrokerClosedToday]);
  const totalHistoryPages = Math.max(1, Math.ceil((historyState.total || 0) / (historyState.page_size || 10)));

  useEffect(() => {
    if (closedAccountFilter === "ALL") return;
    if (closedAccountFilter && accounts.some((account) => account.id === closedAccountFilter)) return;
    setClosedAccountFilter(activeAccountId || accounts[0]?.id || "");
  }, [accounts, activeAccountId, closedAccountFilter]);

  useEffect(() => {
    if (tab !== "positions" || !token || !usesBrokerClosedToday) return;
    let ignore = false;

    const loadClosedBrokerToday = async () => {
      setClosedBrokerLoading(true);
      setClosedBrokerError("");
      try {
        const accountIds = closedAccountFilter === "ALL"
          ? accounts.map((account) => account.id).filter(Boolean)
          : [closedAccountFilter].filter(Boolean);
        if (!accountIds.length) {
          if (!ignore) setClosedBrokerRows([]);
          return;
        }
        const responses = await Promise.all(
          accountIds.map((accountId) => {
            const params = new URLSearchParams({
              account_id: accountId,
              page: "1",
              page_size: "500",
              type: "closed",
              today: "true",
            });
            return api(`/broker/trade-history?${params.toString()}`, "GET", undefined, token);
          })
        );
        if (!ignore) {
          setClosedBrokerRows(
            responses.flatMap((data, index) =>
              (data.records || []).map((row) => ({
                ...row,
                account_id: row.account_id || accountIds[index],
              }))
            )
          );
        }
      } catch (err) {
        if (!ignore) {
          setClosedBrokerError(err.message);
          setClosedBrokerRows([]);
        }
      } finally {
        if (!ignore) setClosedBrokerLoading(false);
      }
    };

    loadClosedBrokerToday();
    return () => {
      ignore = true;
    };
  }, [tab, token, closedAccountFilter, closedStatusFilter, accounts, usesBrokerClosedToday]);

  useEffect(() => {
    if (historyAccountId && accounts.some((account) => account.id === historyAccountId)) return;
    setHistoryAccountId(activeAccountId || accounts[0]?.id || "");
  }, [accounts, activeAccountId, historyAccountId]);

  useEffect(() => {
    setHistoryPage(1);
  }, [historyAccountId, historyType]);

  useEffect(() => {
    if (tab !== "history" || !token || !historyAccountId) return;
    let ignore = false;

    const loadHistory = async () => {
      setHistoryLoading(true);
      setHistoryError("");
      try {
        const params = new URLSearchParams({
          account_id: historyAccountId,
          page: String(historyPage),
          page_size: "10",
          type: historyType,
        });
        const data = await api(`/broker/trade-history?${params.toString()}`, "GET", undefined, token);
        if (!ignore) {
          setHistoryState(data);
        }
      } catch (err) {
        if (!ignore) {
          setHistoryError(err.message);
        }
      } finally {
        if (!ignore) {
          setHistoryLoading(false);
        }
      }
    };

    loadHistory();
    return () => {
      ignore = true;
    };
  }, [historyAccountId, historyPage, historyType, tab, token]);

  const renderRowsTable = (items, options = {}) => {
    const { showAction = true, plVariant = "active", showBroker = true } = options;
    const columnCount = showBroker ? 11 : 10;
    return (
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-950">
              <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {showBroker ? <th className="px-2 py-2">Broker</th> : null}
                <th className="px-2 py-2">Symbol</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Qty</th>
                <th className="px-2 py-2">Entry</th>
                <th className="px-2 py-2">SL</th>
                <th className="px-2 py-2">Target</th>
                <th className="px-2 py-2">R:R</th>
                <th className="px-2 py-2">Exp</th>
                <th className="px-2 py-2">{showAction ? "P/L" : "Details"}</th>
                <th className="px-2 py-2 text-right">{showAction ? "Action" : "Updated"}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const relatedPriceValues = [row.entry, row.stop_loss, row.target];
                const expanded = Boolean(expandedRows[row.id]);
                const isClosed = ["CLOSED", "CANCELLED", "FAILED"].includes(String(row.status || "").toUpperCase());
                return (
                  <Fragment key={row.id}>
                    <tr className="cursor-pointer border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60" onClick={() => setExpandedRows((current) => ({ ...current, [row.id]: !current[row.id] }))}>
                      {showBroker ? (
                        <td className="px-2 py-2">
                          <div className="max-w-[12rem]">
                            <p className="truncate text-xs font-semibold text-slate-700 dark:text-slate-300">{brokerLabel(row.broker_info)}</p>
                          </div>
                        </td>
                      ) : null}
                      <td className="px-2 py-2 font-semibold text-slate-900 dark:text-slate-100">
                        <span className="inline-flex items-center gap-2">
                          <SymbolIcon symbol={row.symbol} size="sm" />
                          {row.symbol}
                        </span>
                      </td>
                      <td className="px-2 py-2">
                        <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusTone(row.status)}`}>{humanizeStatus(row.status)}</span>
                        {row.failure_reason ? (
                          <p className="mt-1 max-w-[14rem] text-xs font-medium text-rose-600" title={row.failure_reason}>{row.failure_reason}</p>
                        ) : null}
                      </td>
                      <td className="px-2 py-2">
                        {(() => {
                          const originalQty = Number(row.quantity);
                          const remainingQty = Number(row.position_quantity ?? row.quantity);
                          const closedQty = Number.isFinite(originalQty) && Number.isFinite(remainingQty)
                            ? originalQty - remainingQty
                            : 0;
                          return (
                            <div className="space-y-0.5">
                              <p>{formatQty(row.position_quantity ?? row.quantity)}</p>
                              {closedQty > 1e-9 ? (
                                <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">Closed {formatQty(closedQty)}</p>
                              ) : null}
                            </div>
                          );
                        })()}
                      </td>
                      <td className="px-2 py-2">{formatPrice(row.entry, relatedPriceValues)}</td>
                      <td className="px-2 py-2">{formatPrice(row.stop_loss, relatedPriceValues)}</td>
                      <td className="px-2 py-2">{formatPrice(row.target, relatedPriceValues)}</td>
                      <td className="px-2 py-2">{row.rr_ratio ?? "-"}</td>
                      <td className="px-2 py-2 text-xs">{renderExpectedRewardRisk(row)}</td>
                      <td className="px-2 py-2">
                        {showAction ? (
                          plVariant === "closed" || isClosed ? (
                            <p className={`text-xs font-semibold ${Number(row.realized_pl || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                              {formatCurrencyValue(row.realized_pl || 0)}
                            </p>
                          ) : (
                          <div className="space-y-0.5 text-xs">
                            <p className={`${Number(row.unrealized_pl || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>Run {formatCurrencyValue(row.unrealized_pl || 0)}</p>
                            <p className={`${Number(row.realized_pl || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>Book {formatCurrencyValue(row.realized_pl || 0)}</p>
                          </div>
                          )
                        ) : (row.comment || row.failure_reason || (row.realized_pl ?? "-"))}
                      </td>
                      <td className="px-2 py-2 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <span className="text-xs text-slate-400">{expanded ? "Hide" : "Details"}</span>
                          {showAction && isEditablePendingOrder(row.status) ? (
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onEditOrder(row);
                                }}
                                disabled={actionLoadingId === row.id}
                                className="rounded-lg bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                Edit
                              </button>
                              <button
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onCancelOrder(row);
                                }}
                                disabled={actionLoadingId === row.id}
                                className="rounded-lg bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {actionLoadingId === row.id ? "Cancelling..." : "Cancel Order"}
                              </button>
                            </div>
                          ) : showAction && ["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].includes(String(row.status || "").toUpperCase()) ? (
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onOpenClose(row);
                                }}
                                disabled={actionLoadingId === row.id}
                                className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                Partial Exit
                              </button>
                              <button
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onFullClose(row);
                                }}
                                disabled={actionLoadingId === row.id}
                                className="rounded-lg bg-slate-900 px-3 py-1 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                              >
                                {actionLoadingId === row.id ? "Exiting..." : "Full Exit"}
                              </button>
                            </div>
                          ) : !showAction ? (
                            <span className="text-xs text-slate-400 dark:text-slate-500">
                              {row.updated_at ? formatNotificationTimestamp(row.updated_at) : "-"}
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400 dark:text-slate-500">No action</span>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expanded ? (
                      <tr className="border-b border-slate-100 bg-slate-50 dark:border-slate-800 dark:bg-slate-950/70">
                        <td colSpan={columnCount} className="px-3 py-3">
                          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Created</p>
                              <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{row.created_at ? formatNotificationTimestamp(row.created_at) : "-"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Entry Time</p>
                              <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{row.opened_at ? formatNotificationTimestamp(row.opened_at) : "-"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Exit Time</p>
                              <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{row.closed_at ? formatNotificationTimestamp(row.closed_at) : "-"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Last Broker Sync</p>
                              <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{row.last_broker_seen_at ? formatNotificationTimestamp(row.last_broker_seen_at) : "-"}</p>
                            </div>
                          </div>
                          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Running P/L</p>
                              <p className={`mt-1 text-sm font-semibold ${Number(row.unrealized_pl || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{formatCurrencyValue(row.unrealized_pl || 0)}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Booked P/L</p>
                              <p className={`mt-1 text-sm font-semibold ${Number(row.realized_pl || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{formatCurrencyValue(row.realized_pl || 0)}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Broker Order ID</p>
                              <p className="mt-1 break-all text-sm font-semibold text-slate-800 dark:text-slate-100">{row.meta_order_id || "-"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Broker Position ID</p>
                              <p className="mt-1 break-all text-sm font-semibold text-slate-800 dark:text-slate-100">{row.meta_position_id || "-"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Source</p>
                              <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{row.external_source ? humanizeStatus(row.external_source) : "App"}</p>
                            </div>
                            {row.manual_context?.cancel_at != null ? (
                              <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Cancel At</p>
                                <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">
                                  {formatPrice(row.manual_context.cancel_at, relatedPriceValues)}
                                </p>
                              </div>
                            ) : null}
                            {row.manual_context?.conditional_order && row.manual_context?.trigger_price != null ? (
                              <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Trigger</p>
                                <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">
                                  {formatPrice(row.manual_context.trigger_price, relatedPriceValues)}
                                </p>
                              </div>
                            ) : null}
                          </div>
                          {(row.comment || row.failure_reason || row.placement_fallback_reason) ? (
                            <div className="mt-3 rounded-xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-900">
                              {row.placement_fallback_reason ? (
                                <>
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">Placement Note</p>
                                  <p className="mt-1 text-sm font-medium text-amber-800">{row.placement_fallback_reason}</p>
                                </>
                              ) : null}
                              {row.failure_reason ? (
                                <>
                                  <p className={`text-[11px] font-semibold uppercase tracking-wide text-slate-500 ${row.placement_fallback_reason ? "mt-3" : ""}`}>Failure Reason</p>
                                  <p className="mt-1 text-sm font-medium text-rose-700">{row.failure_reason}</p>
                                </>
                              ) : null}
                              {row.comment ? (
                                <>
                                  <p className={`text-[11px] font-semibold uppercase tracking-wide text-slate-500 ${row.placement_fallback_reason || row.failure_reason ? "mt-3" : ""}`}>Notes</p>
                                  <p className="mt-1 text-sm text-slate-700">{row.comment}</p>
                                </>
                              ) : null}
                            </div>
                          ) : null}
                          <OrderActivityTimeline orderId={row.id} token={token} />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
    );
  };

  const accountGroupLabel = (row) => {
    const accountId = orderAccountId(row);
    const account = accounts.find((item) => item.id === accountId);
    const name = account?.account_name || brokerLabel(row.broker_info) || "Unknown broker";
    const balance = account?.available_margin ?? row.broker_info?.available_margin;
    return balance != null ? `${name} · Bal ${formatCurrencyValue(balance)}` : name;
  };

  const groupRowsByBroker = (items) => {
    const groups = new Map();
    items.forEach((row) => {
      const key = orderAccountId(row) || `label:${brokerLabel(row.broker_info) || "Unknown broker"}`;
      if (!groups.has(key)) {
        const account = accounts.find((item) => item.id === orderAccountId(row));
        groups.set(key, {
          label: accountGroupLabel(row),
          sortName: String(account?.account_name || brokerLabel(row.broker_info) || "").toLowerCase(),
          rows: [],
        });
      }
      groups.get(key).rows.push(row);
    });
    const sortRows = (left, right) => {
      const symbolCompare = String(left.symbol || "").localeCompare(String(right.symbol || ""));
      if (symbolCompare !== 0) return symbolCompare;
      return String(left.id || "").localeCompare(String(right.id || ""));
    };
    return Array.from(groups.entries())
      .map(([key, value]) => [key, value.label, value.rows.slice().sort(sortRows), value.sortName])
      .sort((left, right) => {
        const nameCompare = left[3].localeCompare(right[3]);
        if (nameCompare !== 0) return nameCompare;
        return String(left[0]).localeCompare(String(right[0]));
      })
      .map(([key, label, rows]) => [key, label, rows]);
  };

  const renderBrokerGroupHeader = (label, count) => (
    <div className="mb-2 flex items-center gap-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">{label}</p>
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-300">{count}</span>
    </div>
  );

  const renderPositionsSection = () => {
    const groups = groupRowsByBroker(positionRows);
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Open Positions</h4>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">{positionRows.length}</span>
        </div>
        {positionRows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">No open positions for today yet.</div>
        ) : (
          <div className="space-y-5">
            {groups.map(([key, label, items]) => (
              <div key={key}>
                {renderBrokerGroupHeader(label, items.length)}
                {renderRowsTable(items, { showBroker: false, showAction: true })}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const orderTypeLabel = (row) => {
    if (row.kind === "TAKE_PROFIT") return "Take Profit";
    if (row.kind === "STOP_LOSS") return "Stop Loss";
    const type = String(row.order_type || "").toUpperCase();
    if (type === "LIMIT") return "Limit";
    if (type === "SL") return "Stop";
    if (type === "MARKET") return "Market";
    return row.order_type ? humanizeStatus(row.order_type) : "-";
  };

  const renderOrdersRowsTable = (items) => (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 dark:bg-slate-950">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <th className="px-2 py-2">Symbol</th>
            <th className="px-2 py-2">Side</th>
            <th className="px-2 py-2">Type</th>
            <th className="px-2 py-2">Price</th>
            <th className="px-2 py-2">SL</th>
            <th className="px-2 py-2">Target</th>
            <th className="px-2 py-2">Qty</th>
            <th className="px-2 py-2">Exp</th>
            <th className="px-2 py-2">Status</th>
            <th className="px-2 py-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => {
            const price = row.derived ? row.price : (row.entry ?? row.price);
            const editable = !row.derived && isEditablePendingOrder(row.status);
            return (
              <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60">
                <td className="px-2 py-2 font-semibold text-slate-900 dark:text-slate-100">
                  <span className="inline-flex items-center gap-2">
                    <SymbolIcon symbol={row.symbol} size="sm" />
                    {row.symbol}
                  </span>
                </td>
                <td className="px-2 py-2">
                  <span className={`rounded-full px-2 py-1 text-xs font-semibold ${String(row.side || "").toUpperCase() === "BUY" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>{String(row.side || "-").toUpperCase()}</span>
                </td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{orderTypeLabel(row)}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(price)}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{row.stop_loss != null ? formatPrice(row.stop_loss) : "—"}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{row.target != null ? formatPrice(row.target) : "—"}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatQty(row.quantity ?? row.position_quantity)}</td>
                <td className="px-2 py-2 text-xs">{renderExpectedRewardRisk(row)}</td>
                <td className="px-2 py-2">
                  {row.derived ? (
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-200">Working</span>
                  ) : (
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusTone(row.status)}`}>{humanizeStatus(row.status)}</span>
                  )}
                </td>
                <td className="px-2 py-2 text-right">
                  {editable ? (
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => onEditOrder(row)}
                        disabled={actionLoadingId === row.id}
                        className="rounded-lg bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => onCancelOrder(row)}
                        disabled={actionLoadingId === row.id}
                        className="rounded-lg bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {actionLoadingId === row.id ? "Cancelling..." : "Cancel Order"}
                      </button>
                    </div>
                  ) : row.derived ? (
                    <span className="text-xs text-slate-400 dark:text-slate-500">From position</span>
                  ) : (
                    <span className="text-xs text-slate-400 dark:text-slate-500">No action</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const renderOrdersGroup = (sectionItems, emptyLabel) => {
    if (!sectionItems.length) {
      return <div className="rounded-xl border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">{emptyLabel}</div>;
    }
    const groups = groupRowsByBroker(sectionItems);
    return (
      <div className="space-y-5">
        {groups.map(([key, label, items]) => (
          <div key={key}>
            {renderBrokerGroupHeader(label, items.length)}
            {renderOrdersRowsTable(items)}
          </div>
        ))}
      </div>
    );
  };

  const renderConditionalOrdersRowsTable = (items) => (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 dark:bg-slate-950">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <th className="px-2 py-2">Symbol</th>
            <th className="px-2 py-2">Side</th>
            <th className="px-2 py-2">Trigger</th>
            <th className="px-2 py-2">Entry</th>
            <th className="px-2 py-2">SL</th>
            <th className="px-2 py-2">Target</th>
            <th className="px-2 py-2">Qty</th>
            <th className="px-2 py-2">Exp</th>
            <th className="px-2 py-2">Status</th>
            <th className="px-2 py-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => {
            const trigger = row.manual_context?.trigger_price;
            const editable = isEditablePendingOrder(row.status);
            return (
              <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60">
                <td className="px-2 py-2 font-semibold text-slate-900 dark:text-slate-100">
                  <span className="inline-flex items-center gap-2">
                    <SymbolIcon symbol={row.symbol} size="sm" />
                    {row.symbol}
                  </span>
                </td>
                <td className="px-2 py-2">
                  <span className={`rounded-full px-2 py-1 text-xs font-semibold ${String(row.side || "").toUpperCase() === "BUY" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>{String(row.side || "-").toUpperCase()}</span>
                </td>
                <td className="px-2 py-2 font-semibold text-indigo-700 dark:text-indigo-300">{formatPrice(trigger)}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.entry)}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.stop_loss)}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{row.target != null ? formatPrice(row.target) : "—"}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatQty(row.quantity ?? row.position_quantity)}</td>
                <td className="px-2 py-2 text-xs">{renderExpectedRewardRisk(row)}</td>
                <td className="px-2 py-2">
                  <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusTone(row.status)}`}>{humanizeStatus(row.status)}</span>
                </td>
                <td className="px-2 py-2 text-right">
                  {editable ? (
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => onEditOrder(row)}
                        disabled={actionLoadingId === row.id}
                        className="rounded-lg bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => onCancelOrder(row)}
                        disabled={actionLoadingId === row.id}
                        className="rounded-lg bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {actionLoadingId === row.id ? "Cancelling..." : "Cancel"}
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400 dark:text-slate-500">No action</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const renderConditionalOrdersGroup = (sectionItems, emptyLabel) => {
    if (!sectionItems.length) {
      return <div className="rounded-xl border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">{emptyLabel}</div>;
    }
    const groups = groupRowsByBroker(sectionItems);
    return (
      <div className="space-y-5">
        {groups.map(([key, label, items]) => (
          <div key={key}>
            {renderBrokerGroupHeader(label, items.length)}
            {renderConditionalOrdersRowsTable(items)}
          </div>
        ))}
      </div>
    );
  };

  const renderDeferredPendingOrdersRowsTable = (items) => (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead className="bg-amber-50/80 dark:bg-amber-950/40">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <th className="px-2 py-2">Symbol</th>
            <th className="px-2 py-2">Side</th>
            <th className="px-2 py-2">Type</th>
            <th className="px-2 py-2">Entry</th>
            <th className="px-2 py-2">SL</th>
            <th className="px-2 py-2">Target</th>
            <th className="px-2 py-2">Qty</th>
            <th className="px-2 py-2">Risk</th>
            <th className="px-2 py-2">RRR</th>
            <th className="px-2 py-2">Exp</th>
            <th className="px-2 py-2">Send after</th>
            <th className="px-2 py-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.id} className="border-b border-amber-100 hover:bg-amber-50/60 dark:border-amber-900/40 dark:hover:bg-amber-950/30">
              <td className="px-2 py-2 font-semibold text-slate-900 dark:text-slate-100">
                <span className="inline-flex items-center gap-2">
                  <SymbolIcon symbol={row.symbol} size="sm" />
                  {row.symbol}
                </span>
              </td>
              <td className="px-2 py-2">
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${String(row.side || "").toUpperCase() === "BUY" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                  {String(row.side || "-").toUpperCase()}
                </span>
              </td>
              <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{orderTypeLabel(row)}</td>
              <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.entry)}</td>
              <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.stop_loss)}</td>
              <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{row.target != null ? formatPrice(row.target) : "—"}</td>
              <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatQty(row.quantity)}</td>
              <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{row.risk_amount != null ? formatPrice(row.risk_amount) : "—"}</td>
              <td className="px-2 py-2 font-semibold text-indigo-700 dark:text-indigo-300">
                {row.rr_ratio != null && row.rr_ratio !== "" ? `${row.rr_ratio}R` : "—"}
              </td>
              <td className="px-2 py-2 text-xs">{renderExpectedRewardRisk(row)}</td>
              <td className="px-2 py-2 text-xs text-slate-600 dark:text-slate-400">{row.place_after ? formatNotificationTimestamp(row.place_after) : "Mon 04:30 IST"}</td>
              <td className="px-2 py-2 text-right">
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => onEditOrder(row)}
                    disabled={actionLoadingId === row.id}
                    className="rounded-lg bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => onCancelOrder(row)}
                    disabled={actionLoadingId === row.id}
                    className="rounded-lg bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {actionLoadingId === row.id ? "Cancelling..." : "Cancel"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderDeferredPendingOrdersGroup = (sectionItems) => {
    const groups = groupRowsByBroker(sectionItems);
    return (
      <div className="space-y-5">
        {groups.map(([key, label, items]) => (
          <div key={key}>
            {renderBrokerGroupHeader(label, items.length)}
            {renderDeferredPendingOrdersRowsTable(items)}
          </div>
        ))}
      </div>
    );
  };

  const renderOrdersSection = () => (
    <div className="space-y-4">
      {deferredPendingOrders.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-900/50 dark:bg-amber-950/20">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">Pending Orders</h4>
              <p className="text-xs text-slate-600 dark:text-slate-400">
                Saved locally while the market is closed. Sent to the broker after Monday 04:30 IST. Editable until then.
              </p>
            </div>
            <span className="rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-900 dark:bg-amber-900/60 dark:text-amber-100">
              {deferredPendingOrders.length}
            </span>
          </div>
          {renderDeferredPendingOrdersGroup(deferredPendingOrders)}
        </div>
      ) : null}
      <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-4 dark:border-indigo-900/50 dark:bg-indigo-950/20">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">Conditional Orders</h4>
            <p className="text-xs text-slate-600 dark:text-slate-400">Armed SL setups waiting for price to cross the trigger. The broker stop is placed only after the cross.</p>
          </div>
          <span className="rounded-full bg-indigo-100 px-2 py-1 text-xs font-semibold text-indigo-800 dark:bg-indigo-900/60 dark:text-indigo-200">{conditionalOrders.length}</span>
        </div>
        {renderConditionalOrdersGroup(conditionalOrders, "No conditional orders waiting for trigger.")}
      </div>
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Open Orders</h4>
            <p className="text-xs text-slate-500 dark:text-slate-400">Pending entry limit orders and take-profit orders working at the broker.</p>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">{openOrders.length}</span>
        </div>
        {renderOrdersGroup(openOrders, "No open orders.")}
      </div>
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Stop Orders</h4>
            <p className="text-xs text-slate-500 dark:text-slate-400">Pending entry stop orders and stop-loss orders working at the broker.</p>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">{stopOrders.length}</span>
        </div>
        {renderOrdersGroup(stopOrders, "No stop orders.")}
      </div>
    </div>
  );

  const exportBrokerHistoryCsv = async () => {
    if (!historyAccountId || historyExporting) return;
    setHistoryExporting(true);
    setHistoryError("");
    try {
      const params = new URLSearchParams({
        account_id: historyAccountId,
        page: "1",
        page_size: "500",
        type: historyType,
      });
      const data = await api(`/broker/trade-history?${params.toString()}`, "GET", undefined, token);
      const records = data.records || [];
      const headers = ["SN", "Open Time", "Open Price", "Close Time", "Close Price", "Profit", "Lots", "Commission", "Swap", "Net Profit", "Symbol", "Type", "Status", "Position ID"];
      const escapeCsv = (value) => {
        const text = value === null || value === undefined ? "" : String(value);
        return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
      };
      const lines = [
        headers.join(","),
        ...records.map((row, index) => [
          index + 1,
          row.open_time ? formatNotificationTimestamp(row.open_time) : "",
          row.open_price ?? "",
          row.is_running ? "Currently Running" : (row.close_time ? formatNotificationTimestamp(row.close_time) : ""),
          row.close_price ?? "",
          row.profit ?? "",
          row.lots ?? "",
          row.commission ?? "",
          row.swap ?? "",
          row.net_profit ?? "",
          row.symbol || "",
          row.type || "",
          row.status || "",
          row.position_id || "",
        ].map(escapeCsv).join(",")),
      ];
      const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `broker-trade-history-${historyAccountId}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setHistoryError(err.message || "Could not export broker history.");
    } finally {
      setHistoryExporting(false);
    }
  };

  const renderTodayClosedBrokerTable = (items) => (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 dark:bg-slate-950">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <th className="px-2 py-2">Account</th>
            <th className="px-2 py-2">Symbol</th>
            <th className="px-2 py-2">Type</th>
            <th className="px-2 py-2">Open</th>
            <th className="px-2 py-2">Close</th>
            <th className="px-2 py-2">Lots</th>
            <th className="px-2 py-2">Net P/L</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row, index) => {
            const accountName = row.account_name || accounts.find((account) => account.id === row.account_id)?.account_name || "Broker Account";
            const profitTone = Number(row.net_profit || row.profit || 0) >= 0 ? "text-emerald-700" : "text-rose-700";
            return (
              <tr key={row.id || `${row.position_id}-${index}`} className="border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60">
                <td className="px-2 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300">{accountName}</td>
                <td className="px-2 py-2 font-semibold text-slate-900 dark:text-slate-100">
                  <span className="inline-flex items-center gap-2">
                    <SymbolIcon symbol={row.symbol} size="sm" />
                    {row.symbol}
                  </span>
                </td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{row.type}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.open_price, [row.open_price, row.close_price])}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.close_price, [row.open_price, row.close_price])}</td>
                <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{row.lots ?? "-"}</td>
                <td className={`px-2 py-2 font-semibold ${profitTone}`}>{formatCurrencyValue(row.net_profit || row.profit || 0)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const renderClosedTodayLocalRows = (items) => (
    <div className={`overflow-auto ${usesBrokerClosedToday && closedBrokerRows.length ? "mt-4" : ""}`}>
      {usesBrokerClosedToday && closedBrokerRows.length ? (
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Platform Orders</p>
      ) : null}
      <table className="w-full text-sm">
        <thead className="bg-slate-50 dark:bg-slate-950">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <th className="px-2 py-2">Broker</th>
            <th className="px-2 py-2">Symbol</th>
            <th className="px-2 py-2">Status</th>
            <th className="px-2 py-2">Qty</th>
            <th className="px-2 py-2">Entry</th>
            <th className="px-2 py-2">SL</th>
            <th className="px-2 py-2">Target</th>
            <th className="px-2 py-2">R:R</th>
            <th className="px-2 py-2">Exp</th>
            <th className="px-2 py-2">P/L</th>
            <th className="px-2 py-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => {
            const relatedPriceValues = [row.entry, row.stop_loss, row.target];
            const expanded = Boolean(expandedRows[row.id]);
            return (
              <Fragment key={row.id}>
                <tr className="cursor-pointer border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60" onClick={() => setExpandedRows((current) => ({ ...current, [row.id]: !current[row.id] }))}>
                  <td className="px-2 py-2">
                    <div className="max-w-[12rem]">
                      <p className="truncate text-xs font-semibold text-slate-700 dark:text-slate-300">{brokerLabel(row.broker_info)}</p>
                    </div>
                  </td>
                  <td className="px-2 py-2 font-semibold text-slate-900 dark:text-slate-100">
                    <span className="inline-flex items-center gap-2">
                      <SymbolIcon symbol={row.symbol} size="sm" />
                      {row.symbol}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusTone(row.status)}`}>{humanizeStatus(row.status)}</span>
                    {row.failure_reason ? (
                      <p className="mt-1 max-w-[14rem] text-xs font-medium text-rose-600" title={row.failure_reason}>{row.failure_reason}</p>
                    ) : null}
                  </td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatQty(row.position_quantity ?? row.quantity)}</td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.entry, relatedPriceValues)}</td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.stop_loss, relatedPriceValues)}</td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{formatPrice(row.target, relatedPriceValues)}</td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-300">{row.rr_ratio ?? "-"}</td>
                  <td className="px-2 py-2 text-xs">{renderExpectedRewardRisk(row)}</td>
                  <td className="px-2 py-2">
                    <p className={`text-xs font-semibold ${Number(row.realized_pl || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                      {formatCurrencyValue(row.realized_pl || 0)}
                    </p>
                  </td>
                  <td className="px-2 py-2 text-right">
                    <span className="text-xs text-slate-400 dark:text-slate-500">{expanded ? "Hide" : "Details"}</span>
                  </td>
                </tr>
                {expanded ? (
                  <tr className="border-b border-slate-100 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-950/70">
                    <td colSpan={11} className="px-3 py-3">
                      {row.placement_fallback_reason ? (
                        <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 dark:border-amber-900/60 dark:bg-amber-950/30">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">Placement Note</p>
                          <p className="mt-1 text-sm font-medium text-amber-800 dark:text-amber-200">{row.placement_fallback_reason}</p>
                        </div>
                      ) : null}
                      {row.failure_reason ? (
                        <div className="mb-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-3 dark:border-rose-900/60 dark:bg-rose-950/30">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-rose-700 dark:text-rose-300">Failure Reason</p>
                          <p className="mt-1 text-sm font-medium text-rose-800 dark:text-rose-200">{row.failure_reason}</p>
                        </div>
                      ) : null}
                      <OrderActivityTimeline orderId={row.id} token={token} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const renderClosedTodaySection = () => {
    const emptyLabel = closedStatusFilter === "ALL"
      ? "No closed trades for today yet."
      : closedStatusFilter === "CLOSED"
        ? "No closed broker trades for today yet."
        : `No ${humanizeStatus(closedStatusFilter).toLowerCase()} orders for today yet.`;
    const headerRight = (
      <>
        <label className="flex items-center gap-2 text-xs font-semibold text-slate-500">
          Account
          <select
            value={closedAccountFilter}
            onChange={(event) => setClosedAccountFilter(event.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 outline-none focus:border-indigo-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
          >
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>{account.account_name}</option>
            ))}
            <option value="ALL">All</option>
          </select>
        </label>
        <select
          value={closedStatusFilter}
          onChange={(event) => setClosedStatusFilter(event.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 outline-none focus:border-indigo-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
        >
          <option value="CLOSED">Closed</option>
          <option value="CANCELLED">Cancelled</option>
          <option value="FAILED">Failed</option>
          <option value="ALL">All</option>
        </select>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${totalBookedPl >= 0 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
          {formatCurrencyValue(totalBookedPl)}
        </span>
      </>
    );

    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Closed Today</h4>
          <div className="flex flex-wrap items-center gap-2">
            {headerRight}
            <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">{closedDisplayCount}</span>
          </div>
        </div>
        {closedBrokerError ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
            Could not load closed broker trades: {closedBrokerError}
          </div>
        ) : null}
        {closedDisplayCount === 0 && closedBrokerLoading && usesBrokerClosedToday ? (
          <div className="rounded-xl border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            Loading today&apos;s closed broker trades...
          </div>
        ) : closedDisplayCount === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">{emptyLabel}</div>
        ) : (
          <>
            {usesBrokerClosedToday ? (
              closedBrokerLoading ? (
                <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  Loading today&apos;s closed broker trades...
                </div>
              ) : closedBrokerRows.length ? (
                renderTodayClosedBrokerTable(closedBrokerRows)
              ) : null
            ) : null}
            {localNonBrokerClosedRows.length ? renderClosedTodayLocalRows(localNonBrokerClosedRows) : null}
          </>
        )}
      </div>
    );
  };

  const renderBrokerHistoryTable = (items) => (
    <div className="overflow-auto rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 dark:bg-slate-950">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <th className="px-3 py-2">SN</th>
            <th className="px-3 py-2">Open Time</th>
            <th className="px-3 py-2">Open Price</th>
            <th className="px-3 py-2">Close Time</th>
            <th className="px-3 py-2">Close Price</th>
            <th className="px-3 py-2">Profit</th>
            <th className="px-3 py-2">Lots</th>
            <th className="px-3 py-2">Commission</th>
            <th className="px-3 py-2">Swap</th>
            <th className="px-3 py-2">Net Profit</th>
            <th className="px-3 py-2">Symbol</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2 text-right">Details</th>
          </tr>
        </thead>
        <tbody>
          {items.length ? items.map((row, index) => {
            const profitTone = Number(row.net_profit || row.profit || 0) >= 0 ? "text-emerald-700" : "text-rose-700";
            return (
              <tr key={row.id || `${row.position_id}-${index}`} className="border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60">
                <td className="px-3 py-2">{((historyState.page || historyPage) - 1) * (historyState.page_size || 10) + index + 1}</td>
                <td className="px-3 py-2">{row.open_time ? formatNotificationTimestamp(row.open_time) : "-"}</td>
                <td className="px-3 py-2">{formatPrice(row.open_price, [row.open_price, row.close_price])}</td>
                <td className="px-3 py-2">{row.is_running ? "Currently Running" : (row.close_time ? formatNotificationTimestamp(row.close_time) : "-")}</td>
                <td className="px-3 py-2">{formatPrice(row.close_price, [row.open_price, row.close_price])}</td>
                <td className={`px-3 py-2 font-semibold ${Number(row.profit || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{formatCurrencyValue(row.profit || 0)}</td>
                <td className="px-3 py-2">{row.lots ?? "-"}</td>
                <td className="px-3 py-2">{formatCurrencyValue(row.commission || 0)}</td>
                <td className="px-3 py-2">{formatCurrencyValue(row.swap || 0)}</td>
                <td className={`px-3 py-2 font-semibold ${profitTone}`}>{formatCurrencyValue(row.net_profit || 0)}</td>
                <td className="px-3 py-2 font-semibold">
                  <span className="inline-flex items-center gap-2">
                    <SymbolIcon symbol={row.symbol} size="sm" />
                    {row.symbol}
                  </span>
                </td>
                <td className="px-3 py-2">{row.type}</td>
                <td className="px-3 py-2 text-right">
                  <span title={`Position ${row.position_id || "-"}${row.order_id ? ` / Order ${row.order_id}` : ""}`} className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                    View
                  </span>
                </td>
              </tr>
            );
          }) : (
            <tr>
              <td colSpan={13} className="px-3 py-8 text-center text-sm text-slate-500 dark:text-slate-400">No broker trade history found for the selected account.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">Pending Orders & Positions</h3>
        <div className="grid grid-cols-3 gap-2 rounded-lg bg-slate-100 p-1 dark:bg-slate-950">
          <button
            onClick={() => setTab("positions")}
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${tab === "positions" ? "bg-slate-900 text-white shadow dark:bg-slate-100 dark:text-slate-950" : "text-slate-500 dark:text-slate-400"}`}
          >
            Positions
          </button>
          <button
            onClick={() => setTab("orders")}
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${tab === "orders" ? "bg-slate-900 text-white shadow dark:bg-slate-100 dark:text-slate-950" : "text-slate-500 dark:text-slate-400"}`}
          >
            Orders
          </button>
          <button
            onClick={() => setTab("history")}
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${tab === "history" ? "bg-slate-900 text-white shadow dark:bg-slate-100 dark:text-slate-950" : "text-slate-500 dark:text-slate-400"}`}
          >
            History
          </button>
        </div>
      </div>

      {tab === "positions" ? (
        <div className="space-y-4">
          {renderPositionsSection()}
          {renderClosedTodaySection()}
        </div>
      ) : tab === "orders" ? (
        <div className="space-y-4">
          {renderOrdersSection()}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Broker Trading History</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Fetched directly from MT5 for the selected account.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                Account
                <select
                  value={historyAccountId}
                  onChange={(event) => setHistoryAccountId(event.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 outline-none focus:border-indigo-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                >
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>{account.account_name}</option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                Sort By
                <select
                  value={historyType}
                  onChange={(event) => setHistoryType(event.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 outline-none focus:border-indigo-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="all">Select Type</option>
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                  <option value="closed">Closed</option>
                  <option value="running">Running</option>
                </select>
              </label>
              <button
                type="button"
                onClick={exportBrokerHistoryCsv}
                disabled={!historyAccountId || historyExporting}
                className="rounded-lg bg-indigo-950 px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {historyExporting ? "Preparing..." : "Download CSV"}
              </button>
            </div>
          </div>
          {historyError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
              Could not load history: {historyError}
            </div>
          )}
          {historyLoading ? (
            <div className="rounded-xl border border-dashed border-slate-200 px-3 py-8 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
              Loading historical records...
            </div>
          ) : (
            renderBrokerHistoryTable(historyState.records || [])
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Page {historyState.page || historyPage} of {totalHistoryPages}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setHistoryPage((current) => Math.max(1, current - 1))}
                disabled={historyPage <= 1 || historyLoading}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-800 dark:text-slate-300"
              >
                Previous
              </button>
              <button
                onClick={() => setHistoryPage((current) => Math.min(totalHistoryPages, current + 1))}
                disabled={historyPage >= totalHistoryPages || historyLoading}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-800 dark:text-slate-300"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function tradePlannerStatusTone(status) {
  const upper = String(status || "").toUpperCase();
  if (upper === "WAITING_ENTRY_ZONE") return "border border-amber-200 bg-amber-50 text-amber-700";
  if (upper === "PLACING_ORDER") return "border border-orange-200 bg-orange-50 text-orange-700";
  if (upper === "ORDER_PLACED") return "border border-indigo-200 bg-indigo-50 text-indigo-700";
  if (["POSITION_OPEN", "PARTIALLY_CLOSED", "RUNNING"].includes(upper)) return "border border-emerald-200 bg-emerald-50 text-emerald-700";
  if (["FAILED", "CANCELLED"].includes(upper)) return "border border-rose-200 bg-rose-50 text-rose-700";
  if (upper === "COMPLETED" || upper === "CLOSED") return "border border-sky-200 bg-sky-50 text-sky-700";
  if (upper === "ACTIVE") return "border border-blue-200 bg-blue-50 text-blue-700";
  if (upper === "INACTIVE") return "border border-slate-200 bg-slate-100 text-slate-600";
  return "border border-violet-200 bg-violet-50 text-violet-700";
}

function tradePlannerStatusLabel(status) {
  return humanizeStatus(status);
}

function tradePlannerPlanModeLabel(status) {
  const upper = String(status || "").toUpperCase();
  if (upper === "RUNNING") return "Auto Execution On";
  if (upper === "ACTIVE") return "Ready";
  if (upper === "COMPLETED") return "Completed";
  if (upper === "INACTIVE") return "Inactive";
  return humanizeStatus(status);
}

function tradePlannerExecutionLabel(status) {
  const upper = String(status || "").toUpperCase();
  if (upper === "WAITING_ENTRY_ZONE") return "Waiting Entry Zone";
  if (upper === "PLACING_ORDER") return "Placing Order";
  if (upper === "ORDER_PLACED") return "Limit Order Placed";
  if (upper === "POSITION_OPEN") return "Position Open";
  if (upper === "PARTIALLY_CLOSED") return "Partially Closed";
  if (upper === "CLOSED") return "Trade Closed";
  if (upper === "CANCELLED") return "Order Cancelled";
  if (upper === "FAILED") return "Execution Failed";
  if (upper === "IDLE") return "Idle";
  return humanizeStatus(status);
}

function tradePlannerMetricTone(kind) {
  if (kind === "entry") return "border-emerald-200 bg-emerald-50";
  if (kind === "stop") return "border-rose-200 bg-rose-50";
  if (kind === "swing") return "border-amber-200 bg-amber-50";
  if (kind === "risk") return "border-indigo-200 bg-indigo-50";
  if (kind === "qty") return "border-sky-200 bg-sky-50";
  if (kind === "status") return "border-violet-200 bg-violet-50";
  return "border-slate-200 bg-slate-50";
}

function tradePlannerDirectionText(strongSwingType) {
  return String(strongSwingType || "").toUpperCase() === "STRONG_HIGH" ? "SHORT" : "LONG";
}

function createTradePlannerDraft(symbol = "", riskAmount = "", activeAccountId = "") {
  return {
    symbol,
    strongSwingPrice: "",
    reversalPoints: [""],
    unmitigatedTargets: [""],
    targetAllocations: [],
    breakevenAtT1: false,
    accountTargets: activeAccountId
      ? [{ accountId: activeAccountId, riskAmount: riskAmount === null || riskAmount === undefined ? "" : String(riskAmount) }]
      : [],
    autoExecutionEnabled: true,
  };
}

function normalizePlannerList(values) {
  return (values || []).map((value) => String(value ?? "").trim()).filter((value) => value !== "");
}

function plannerLivePriceRow(symbol, livePrices) {
  const tick = lookupLiveTick(livePrices, symbol);
  if (typeof tick.price !== "number") return null;
  return tick;
}

function TradePlannerPage({
  token,
  selectedAccountExists,
  accounts,
  activeAccountId,
  subscribeLiveSymbol,
  liveOrders,
  liveWatchlist,
  livePrices,
  selectedInstrument,
  onSelectInstrument,
  onNotify,
}) {
  const plannerAccounts = useMemo(
    () => (accounts || []).filter((account) => String(account.market_type || "INTERNATIONAL").toUpperCase() === "INTERNATIONAL"),
    [accounts]
  );
  const watchlistSymbols = useMemo(() => {
    const seen = new Set();
    return (liveWatchlist || [])
      .map((item) => String(item.symbol || "").toUpperCase())
      .filter((symbol) => symbol && !seen.has(symbol) && seen.add(symbol));
  }, [liveWatchlist]);
  const selectedAccount = useMemo(
    () => plannerAccounts.find((account) => account.id === activeAccountId) || null,
    [plannerAccounts, activeAccountId]
  );
  const livePlannerOrdersByTargetKey = useMemo(() => {
    const next = new Map();
    (liveOrders || []).forEach((order) => {
      const planId = String(order.planner_plan_id || "").trim();
      const accountId = String(order.planner_plan_account_id || order.account_id || "").trim();
      if (!planId || !accountId) return;
      next.set(`${planId}:${accountId}`, order);
    });
    return next;
  }, [liveOrders]);
  const [activeTab, setActiveTab] = useState("create");
  const [viewTab, setViewTab] = useState("active");
  const [form, setForm] = useState(() => createTradePlannerDraft(selectedInstrument || "", plannerAccounts.find((account) => account.id === activeAccountId)?.risk_amount ?? "", activeAccountId || ""));
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [plans, setPlans] = useState([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingPlanId, setEditingPlanId] = useState("");
  const [editingPlanMode, setEditingPlanMode] = useState("full");
  const [expandedPlanIds, setExpandedPlanIds] = useState({});
  const [symbolSearch, setSymbolSearch] = useState(selectedInstrument || "");
  const [suggestions, setSuggestions] = useState([]);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [plannerInstrumentEditing, setPlannerInstrumentEditing] = useState(!(selectedInstrument || ""));
  const [plannerPriceDirection, setPlannerPriceDirection] = useState("flat");
  const [plannerPricePrecision, setPlannerPricePrecision] = useState(0);
  const previousPlannerPriceRef = useRef(null);

  useEffect(() => {
    if (!selectedInstrument || editingPlanId) return;
    setSymbolSearch(selectedInstrument);
    setForm((current) => ({ ...current, symbol: selectedInstrument }));
    setPlannerInstrumentEditing(false);
  }, [selectedInstrument, editingPlanId]);

  useEffect(() => {
    if (editingPlanId) return;
    setForm((current) => {
      if (!selectedAccount?.id) return current;
      const hasSelectedRow = (current.accountTargets || []).some((item) => item.accountId === selectedAccount.id);
      if (hasSelectedRow) return current;
      return {
        ...current,
        accountTargets: [
          ...(current.accountTargets || []),
          { accountId: selectedAccount.id, riskAmount: String(selectedAccount.risk_amount ?? "") },
        ],
      };
    });
  }, [selectedAccount?.risk_amount, editingPlanId]);

  const normalizedSymbol = String(form.symbol || "").toUpperCase().trim();
  const liveTick = plannerLivePriceRow(normalizedSymbol, livePrices);
  useEffect(() => {
    subscribeLiveSymbol?.(selectedAccountExists ? normalizedSymbol : "", "trade-planner");
    return () => {
      subscribeLiveSymbol?.("", "trade-planner");
    };
  }, [normalizedSymbol, selectedAccountExists, subscribeLiveSymbol]);

  useEffect(() => {
    const currentPrice = typeof liveTick?.price === "number" ? liveTick.price : null;
    const previousPrice = previousPlannerPriceRef.current;
    if (typeof currentPrice === "number" && typeof previousPrice === "number") {
      if (currentPrice > previousPrice) setPlannerPriceDirection("up");
      else if (currentPrice < previousPrice) setPlannerPriceDirection("down");
    }
    previousPlannerPriceRef.current = currentPrice;
    setPlannerPricePrecision((current) => Math.max(current, decimalPlaces(liveTick?.price), decimalPlaces(liveTick?.bid), decimalPlaces(liveTick?.ask)));
  }, [liveTick?.price, liveTick?.bid, liveTick?.ask]);

  const derivedSwingType = useMemo(() => {
    const swingPrice = Number(form.strongSwingPrice);
    const currentPrice = Number(liveTick?.price);
    if (!Number.isFinite(swingPrice) || !Number.isFinite(currentPrice)) return "";
    return swingPrice > currentPrice ? "STRONG_HIGH" : "STRONG_LOW";
  }, [form.strongSwingPrice, liveTick?.price]);
  const derivedDirection = tradePlannerDirectionText(derivedSwingType);
  const detectedSwingDisplay = useMemo(
    () => tradePlannerSwingTypeDisplay(derivedSwingType),
    [derivedSwingType]
  );

  useEffect(() => {
    if (!selectedAccountExists || symbolSearch.trim().length < 1) {
      setSuggestions([]);
      setHighlightedIndex(-1);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const data = await api(`/instruments/suggest?q=${encodeURIComponent(symbolSearch)}&limit=8`, "GET", undefined, token);
        setSuggestions(data.symbols || []);
        setHighlightedIndex((data.symbols || []).length ? 0 : -1);
      } catch {
        setSuggestions([]);
        setHighlightedIndex(-1);
      }
    }, 180);
    return () => window.clearTimeout(timer);
  }, [symbolSearch, token, selectedAccountExists]);

  const normalizedAllocationValues = useMemo(
    () => normalizePlannerList(form.targetAllocations).map((value) => Number(value)),
    [form.targetAllocations]
  );
  const plannerAllocationPayload = normalizedAllocationValues;
  const selectedPlannerTargets = useMemo(
    () =>
      (form.accountTargets || [])
        .map((target) => {
          const account = plannerAccounts.find((item) => item.id === target.accountId);
          if (!account) return null;
          return {
            account_db_id: account.id,
            account_name: account.account_name,
            risk_amount: Number(target.riskAmount),
          };
        })
        .filter(Boolean),
    [form.accountTargets, plannerAccounts]
  );

  const canPreview = Boolean(
    token &&
    selectedAccountExists &&
    normalizedSymbol &&
    form.strongSwingPrice !== "" &&
    selectedPlannerTargets.length > 0 &&
    selectedPlannerTargets.every((item) => Number.isFinite(item.risk_amount) && item.risk_amount > 0) &&
    normalizePlannerList(form.reversalPoints).length > 0 &&
    normalizePlannerList(form.unmitigatedTargets).length > 0
  );

  const updatePlannerAccountTarget = (accountId, nextRiskAmount) => {
    setForm((current) => ({
      ...current,
      accountTargets: (current.accountTargets || []).map((item) => (
        item.accountId === accountId ? { ...item, riskAmount: nextRiskAmount } : item
      )),
    }));
  };

  const togglePlannerAccountTarget = (accountId, accountRiskAmount) => {
    setForm((current) => {
      const existing = current.accountTargets || [];
      if (existing.some((item) => item.accountId === accountId)) {
        return {
          ...current,
          accountTargets: existing.filter((item) => item.accountId !== accountId),
        };
      }
      return {
        ...current,
        accountTargets: [
          ...existing,
          { accountId, riskAmount: String(accountRiskAmount ?? "") },
        ],
      };
    });
  };

  const selectPlannerSymbol = (symbol) => {
    const normalized = String(symbol || "").toUpperCase().trim();
    setSymbolSearch(normalized);
    setSuggestions([]);
    setHighlightedIndex(-1);
    setForm((current) => ({ ...current, symbol: normalized }));
    setPlannerInstrumentEditing(false);
    onSelectInstrument?.(normalized);
  };

  const handlePlannerSymbolKeyDown = (e) => {
    if (!suggestions.length) {
      if (e.key === "Enter") {
        e.preventDefault();
        selectPlannerSymbol(symbolSearch);
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIndex >= 0 && suggestions[highlightedIndex]) {
        selectPlannerSymbol(suggestions[highlightedIndex]);
      } else {
        selectPlannerSymbol(symbolSearch);
      }
    }
  };

  const loadPlans = async ({ silent = false } = {}) => {
    if (!token) {
      setPlans([]);
      return;
    }
    if (!silent) setPlansLoading(true);
    try {
      const data = await api("/trade-planner/plans", "GET", undefined, token);
      setPlans(data || []);
      setExpandedPlanIds((current) => {
        const next = { ...current };
        (data || []).forEach((plan) => {
          if (next[plan.id] === undefined) {
            next[plan.id] = String(plan.status || "").toUpperCase() !== "INACTIVE";
          }
        });
        return next;
      });
    } catch (err) {
      onNotify("error", err.message || "Could not load trade plans.");
    } finally {
      if (!silent) setPlansLoading(false);
    }
  };

  useEffect(() => {
    loadPlans();
  }, [token]);

  useEffect(() => {
    if (!canPreview) {
      setPreview(null);
      setPreviewError("");
      return;
    }
    let ignore = false;
    const timer = window.setTimeout(async () => {
      setPreviewLoading(true);
      setPreviewError("");
      try {
        const payload = {
          symbol: normalizedSymbol,
          strong_swing_price: Number(form.strongSwingPrice),
          reversal_points: normalizePlannerList(form.reversalPoints).map(Number),
          unmitigated_targets: normalizePlannerList(form.unmitigatedTargets).map(Number),
          target_allocations: plannerAllocationPayload,
          breakeven_at_t1: Boolean(form.breakevenAtT1),
          account_targets: selectedPlannerTargets.map((item) => ({
            account_db_id: item.account_db_id,
            risk_amount: item.risk_amount,
          })),
          auto_execution_enabled: Boolean(form.autoExecutionEnabled),
        };
        const data = await api("/trade-planner/preview", "POST", payload, token);
        if (!ignore) setPreview(data);
      } catch (err) {
        if (!ignore) {
          setPreview(null);
          setPreviewError(err.message || "Could not preview trade plan.");
        }
      } finally {
        if (!ignore) setPreviewLoading(false);
      }
    }, 250);
    return () => {
      ignore = true;
      window.clearTimeout(timer);
    };
  }, [token, selectedAccountExists, normalizedSymbol, form.strongSwingPrice, JSON.stringify(form.accountTargets), JSON.stringify(form.reversalPoints), JSON.stringify(form.unmitigatedTargets), JSON.stringify(plannerAllocationPayload), form.breakevenAtT1, form.autoExecutionEnabled]);

  const resetDraft = () => {
    setEditingPlanId("");
    setEditingPlanMode("full");
    const nextSymbol = normalizedSymbol || selectedInstrument || watchlistSymbols[0] || "";
    setSymbolSearch(nextSymbol);
    setForm(createTradePlannerDraft(nextSymbol, selectedAccount?.risk_amount ?? "", selectedAccount?.id || ""));
    setPreview(null);
    setPreviewError("");
    setPlannerInstrumentEditing(!nextSymbol);
  };

  const updateArrayField = (field, index, value) => {
    setForm((current) => {
      const next = [...current[field]];
      next[index] = value;
      return { ...current, [field]: next };
    });
  };

  const addArrayField = (field) => {
    setForm((current) => ({ ...current, [field]: [...current[field], ""] }));
  };

  const removeArrayField = (field, index) => {
    setForm((current) => {
      const next = current[field].filter((_, itemIndex) => itemIndex !== index);
      return { ...current, [field]: next.length ? next : [""] };
    });
  };

  const populatedTargets = normalizePlannerList(form.unmitigatedTargets);
  const allocationFieldCount = Math.max(populatedTargets.length - 1, 0);
  const visibleAllocationStartIndex = form.breakevenAtT1 ? 1 : 0;
  const visibleAllocationCount = Math.max(allocationFieldCount - visibleAllocationStartIndex, 0);
  const breakevenRequiresMoreTargets = Boolean(form.breakevenAtT1 && populatedTargets.length < 2);
  useEffect(() => {
    setForm((current) => {
      const currentAllocations = [...current.targetAllocations];
      if (currentAllocations.length === visibleAllocationCount) return current;
      while (currentAllocations.length < visibleAllocationCount) currentAllocations.push("");
      return { ...current, targetAllocations: currentAllocations.slice(0, visibleAllocationCount) };
    });
  }, [visibleAllocationCount]);

  useEffect(() => {
    if (populatedTargets.length >= 2) return;
    setForm((current) => (current.breakevenAtT1 ? { ...current, breakevenAtT1: false } : current));
  }, [populatedTargets.length]);

  const submitPlan = async () => {
    if (!selectedAccountExists) {
      onNotify("error", "Select an account before creating a trade plan.");
      return;
    }
    if (selectedPlannerTargets.length === 0) {
      onNotify("error", "Select at least one account for this plan.");
      return;
    }
    if (!preview) {
      onNotify("error", previewError || "Complete the trade plan inputs first.");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        symbol: normalizedSymbol,
        strong_swing_price: Number(form.strongSwingPrice),
        reversal_points: normalizePlannerList(form.reversalPoints).map(Number),
        unmitigated_targets: populatedTargets.map(Number),
        target_allocations: plannerAllocationPayload,
        breakeven_at_t1: Boolean(form.breakevenAtT1),
        account_targets: selectedPlannerTargets.map((item) => ({
          account_db_id: item.account_db_id,
          risk_amount: item.risk_amount,
        })),
        auto_execution_enabled: Boolean(form.autoExecutionEnabled),
      };
      if (editingPlanId) {
        await api(`/trade-planner/plans/${editingPlanId}`, "PATCH", payload, token);
        onNotify("success", "Trade plan updated.");
      } else {
        await api("/trade-planner/plans", "POST", payload, token);
        onNotify("success", "Trade plan created.");
      }
      await loadPlans();
      resetDraft();
      setActiveTab("view");
    } catch (err) {
      onNotify("error", err.message || "Could not save trade plan.");
    } finally {
      setSubmitting(false);
    }
  };

  const startEdit = (plan) => {
    const lockedStatuses = ["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"];
    const nextEditMode = lockedStatuses.includes(String(plan.effectiveLinkedOrderStatus || "").toUpperCase()) ? "targets" : "full";
    setEditingPlanId(plan.id);
    setEditingPlanMode(nextEditMode);
    setSymbolSearch(plan.symbol);
    setForm({
      symbol: plan.symbol,
      strongSwingPrice: String(plan.strong_swing_price ?? ""),
      reversalPoints: (plan.reversal_points || []).map((value) => String(value)),
      unmitigatedTargets: (plan.unmitigated_targets || []).map((value) => String(value)),
      targetAllocations: Boolean(plan.breakeven_at_t1)
        ? (plan.targets || []).slice(1, -1).map((item) => String(item.allocation_percent ?? ""))
        : (plan.targets || []).slice(0, -1).map((item) => String(item.allocation_percent ?? "")),
      breakevenAtT1: Boolean(plan.breakeven_at_t1),
      accountTargets: (plan.account_targets || []).map((item) => ({
        accountId: item.account_db_id,
        riskAmount: String(item.risk_amount ?? ""),
      })),
      autoExecutionEnabled: Boolean(plan.auto_execution_enabled),
    });
    setPlannerInstrumentEditing(false);
    onSelectInstrument?.(plan.symbol);
    setActiveTab("create");
  };

  const toggleRunning = async (plan, nextEnabled) => {
    try {
      await api(`/trade-planner/plans/${plan.id}`, "PATCH", { auto_execution_enabled: nextEnabled }, token);
      await loadPlans();
    } catch (err) {
      onNotify("error", err.message || "Could not update plan mode.");
    }
  };

  const deactivatePlan = async (planId) => {
    try {
      await api(`/trade-planner/plans/${planId}/deactivate`, "POST", {}, token);
      await loadPlans();
      onNotify("success", "Trade plan deactivated.");
    } catch (err) {
      onNotify("error", err.message || "Could not deactivate trade plan.");
    }
  };

  const deletePlan = async (planId) => {
    try {
      await api(`/trade-planner/plans/${planId}`, "DELETE", undefined, token);
      await loadPlans();
      onNotify("success", "Trade plan deleted.");
    } catch (err) {
      onNotify("error", err.message || "Could not delete trade plan.");
    }
  };

  const categorizedPlans = useMemo(() => {
    const enriched = plans.map((plan) => {
      const effectiveAccountTargets = (plan.account_targets || []).map((target) => {
        const livePlannerOrder = livePlannerOrdersByTargetKey.get(`${plan.id}:${target.account_db_id}`);
        const effectiveLinkedOrderStatus = String(livePlannerOrder?.status || target.linked_order_status || "").toUpperCase();
        const effectiveRuntimeStatus = effectiveLinkedOrderStatus
          ? ({
              PLACEMENT_PENDING: "PLACING_ORDER",
              PENDING: "ORDER_PLACED",
              FILLED: "POSITION_OPEN",
              POSITION_OPEN: "POSITION_OPEN",
              PARTIALLY_CLOSED: "PARTIALLY_CLOSED",
              CLOSED: "CLOSED",
              CANCELLED: "CANCELLED",
              FAILED: "FAILED",
            }[effectiveLinkedOrderStatus] || target.runtime_status)
          : target.runtime_status;
        return {
          ...target,
          livePlannerOrder,
          effectiveLinkedOrderStatus,
          effectiveRuntimeStatus,
          runningPl: Number(
            livePlannerOrder?.unrealized_pl !== undefined && livePlannerOrder?.unrealized_pl !== null
              ? livePlannerOrder.unrealized_pl
              : target.running_pl
          ),
        };
      });
      const runtimePriority = ["POSITION_OPEN", "PARTIALLY_CLOSED", "FILLED", "PENDING", "PLACEMENT_PENDING", "CLOSED", "CANCELLED", "FAILED"];
      const effectiveLinkedOrderStatus = runtimePriority.find((status) => effectiveAccountTargets.some((target) => target.effectiveLinkedOrderStatus === status)) || String(plan.linked_order_status || "").toUpperCase();
      const effectiveRuntimeStatus = effectiveAccountTargets.find((target) => target.effectiveLinkedOrderStatus === effectiveLinkedOrderStatus)?.effectiveRuntimeStatus || plan.runtime_status;
      const plannerRunningPl = effectiveAccountTargets.reduce((sum, target) => (
        Number.isFinite(target.runningPl) ? sum + Number(target.runningPl) : sum
      ), 0);
      const effectivePlanStatus = effectiveLinkedOrderStatus
        ? (["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].includes(effectiveLinkedOrderStatus)
            ? "RUNNING"
            : effectiveLinkedOrderStatus === "CLOSED"
              ? "INACTIVE"
              : plan.status)
        : plan.status;
      const isRunning = String(effectivePlanStatus || "").toUpperCase() === "RUNNING";
      const normalizedPlanStatus = String(effectivePlanStatus || "").toUpperCase();
      const isInactive = ["INACTIVE", "DEACTIVATED"].includes(normalizedPlanStatus);
      return {
        ...plan,
        effectiveAccountTargets,
        effectiveLinkedOrderStatus,
        effectiveRuntimeStatus,
        plannerRunningPl,
        effectivePlanStatus,
        isRunning,
        isInactive,
      };
    });
    return {
      active: enriched.filter((plan) => !plan.isInactive),
      inactive: enriched.filter((plan) => plan.isInactive),
      summary: enriched.reduce((acc, plan) => {
        acc.count += 1;
        if (plan.isInactive) acc.inactive += 1;
        else acc.active += 1;
        if (String(plan.effectivePlanStatus || "").toUpperCase() === "RUNNING") acc.running += 1;
        return acc;
      }, { count: 0, active: 0, inactive: 0, running: 0 }),
    };
  }, [plans, livePlannerOrdersByTargetKey]);
  const visiblePlans = viewTab === "inactive" ? categorizedPlans.inactive : categorizedPlans.active;
  const targetsOnlyEdit = editingPlanMode === "targets";

  return (
    <main className="min-h-0 flex-1 overflow-auto">
      <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:[&_input]:border-slate-700 dark:[&_input]:bg-slate-950 dark:[&_input]:text-slate-100 dark:[&_select]:border-slate-700 dark:[&_select]:bg-slate-950 dark:[&_select]:text-slate-100 dark:[&_.bg-white]:!bg-slate-900 dark:[&_.bg-slate-50]:!bg-slate-950 dark:[&_.bg-indigo-50]:!bg-slate-900 dark:[&_.text-slate-950]:!text-slate-100 dark:[&_.text-slate-900]:!text-slate-100 dark:[&_.text-slate-800]:!text-slate-100 dark:[&_.text-slate-700]:!text-slate-200 dark:[&_.text-slate-600]:!text-slate-300 dark:[&_.text-slate-500]:!text-slate-400 dark:[&_.border-slate-100]:!border-slate-800 dark:[&_.border-slate-200]:!border-slate-800 dark:[&_.border-slate-300]:!border-slate-700">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">Trade Planner</h2>
            <p className="text-sm text-slate-500">Build discretionary trade plans with strong swings, reversal structure, target booking, and current-risk position sizing.</p>
          </div>
          <div className="inline-flex overflow-hidden rounded-xl border border-slate-200 bg-white">
            {[
              { id: "create", label: editingPlanId ? "Edit" : "Create" },
              { id: "view", label: "View" },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-sm font-semibold ${activeTab === tab.id ? "bg-slate-900 text-white" : "text-slate-600"}`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {activeTab === "create" ? (
          <div className="space-y-4">
            {editingPlanId && targetsOnlyEdit ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                Entry order is already placed. You can still update target prices and target strategy, but the instrument, swing, reversal structure, and selected accounts are locked.
              </div>
            ) : null}
            <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-1 text-sm md:col-span-2">
                    <span className="font-medium text-slate-700">Instrument</span>
                    <div className="relative">
                      {plannerInstrumentEditing || !normalizedSymbol ? (
                        <input
                          value={symbolSearch}
                          onChange={(e) => {
                            const nextValue = e.target.value.toUpperCase();
                            setSymbolSearch(nextValue);
                            setForm((current) => ({ ...current, symbol: nextValue }));
                          }}
                          onKeyDown={handlePlannerSymbolKeyDown}
                          placeholder={selectedAccountExists ? "Type symbol..." : "Select an account first"}
                          disabled={!selectedAccountExists || targetsOnlyEdit}
                          className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500 disabled:bg-slate-100"
                        />
                      ) : (
                        <button
                          type="button"
                          onClick={() => !targetsOnlyEdit && setPlannerInstrumentEditing(true)}
                          className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-left transition hover:border-indigo-300 hover:bg-indigo-50"
                        >
                          <span className="inline-flex items-center gap-2 font-bold text-slate-900">
                            <SymbolIcon symbol={normalizedSymbol} size="sm" />
                            {normalizedSymbol}
                          </span>
                          <div
                            className={`flex items-center gap-1 font-semibold ${
                              plannerPriceDirection === "up"
                                ? "text-emerald-600"
                                : plannerPriceDirection === "down"
                                  ? "text-rose-600"
                                  : "text-slate-700"
                            }`}
                          >
                            <span>{formatPrice(liveTick?.price, [liveTick?.bid, liveTick?.ask], plannerPricePrecision || 0)}</span>
                            <span className="inline-flex w-4 shrink-0 items-center justify-center text-[11px] leading-none">
                              <span className={plannerPriceDirection === "flat" ? "invisible" : ""}>
                                {plannerPriceDirection === "up" ? "▲" : "▼"}
                              </span>
                            </span>
                          </div>
                        </button>
                      )}
                      {(plannerInstrumentEditing || !normalizedSymbol) && suggestions.length > 0 && symbolSearch && (
                        <div className="absolute z-10 mt-1 w-full rounded-xl border border-indigo-100 bg-white shadow-lg">
                          {suggestions.map((suggestion, index) => (
                            <button
                              key={suggestion}
                              type="button"
                              onClick={() => selectPlannerSymbol(suggestion)}
                              onMouseEnter={() => setHighlightedIndex(index)}
                              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${highlightedIndex === index ? "bg-indigo-100 text-indigo-900" : "hover:bg-indigo-50"}`}
                            >
                              <SymbolIcon symbol={suggestion} size="sm" />
                              {suggestion}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    <p className="text-xs text-slate-500">Press Enter to lock the instrument. Click the bold symbol to edit it again.</p>
                  </div>
                  <div className="space-y-2 text-sm md:col-span-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium text-slate-700">Enabled Accounts</span>
                      <span className="text-xs text-slate-500">Each selected account keeps its own plan risk and quantity.</span>
                    </div>
                    <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
                      <div className="hidden grid-cols-[auto_minmax(0,1fr)_140px] gap-3 border-b border-slate-200 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 md:grid">
                        <span>Select</span>
                        <span>Account</span>
                        <span>Plan Risk</span>
                      </div>
                      <div className="divide-y divide-slate-200">
                        {plannerAccounts.map((account) => {
                          const target = (form.accountTargets || []).find((item) => item.accountId === account.id);
                          const enabled = Boolean(target);
                          return (
                            <div key={account.id} className="grid gap-2 px-3 py-3 md:grid-cols-[auto_minmax(0,1fr)_140px] md:items-center md:gap-3">
                              <label className="flex items-center gap-3">
                                <input
                                  type="checkbox"
                                  checked={enabled}
                                  onChange={() => togglePlannerAccountTarget(account.id, account.risk_amount)}
                                  disabled={targetsOnlyEdit}
                                  className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <span className="md:hidden text-sm font-semibold text-slate-900">{account.account_name}</span>
                              </label>
                              <div className="min-w-0">
                                <p className="truncate text-sm font-semibold text-slate-900">{account.account_name}</p>
                                <p className="text-xs text-slate-500">Master risk {account.risk_amount}</p>
                              </div>
                              <input
                                type="number"
                                min="0.01"
                                step="0.01"
                                value={target?.riskAmount || ""}
                                onChange={(e) => updatePlannerAccountTarget(account.id, e.target.value)}
                                disabled={!enabled || targetsOnlyEdit}
                                className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 outline-none focus:border-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-100"
                                placeholder={String(account.risk_amount ?? "")}
                              />
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                  <div className="space-y-1 text-sm">
                    <span className="font-medium text-slate-700">Live Price</span>
                    <div className="flex h-[42px] items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700">
                      <span className="inline-flex items-center gap-2">
                        {normalizedSymbol ? <SymbolIcon symbol={normalizedSymbol} size="sm" /> : null}
                        {normalizedSymbol || "No symbol selected"}
                      </span>
                      {liveTick?.price ? <span className="font-semibold text-slate-900">{formatPrice(liveTick.price, [liveTick.bid, liveTick.ask])}</span> : null}
                    </div>
                  </div>
                  <label className="space-y-1 text-sm">
                    <span className="font-medium text-slate-700">Strong Swing Price</span>
                    <input
                      type="number"
                      step="any"
                      value={form.strongSwingPrice}
                      onChange={(e) => setForm((current) => ({ ...current, strongSwingPrice: e.target.value }))}
                      disabled={targetsOnlyEdit}
                      className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500 disabled:bg-slate-100"
                      placeholder="Enter strong swing price"
                    />
                  </label>
                  <div className="space-y-1 text-sm">
                    <span className="font-medium text-slate-700">Detected Swing Type</span>
                    <div className="flex min-h-[42px] items-center">
                      {detectedSwingDisplay ? (
                        <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm font-semibold ${detectedSwingDisplay.tone}`}>
                          <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${detectedSwingDisplay.iconTone}`}>
                            {detectedSwingDisplay.icon}
                          </span>
                          <span>{detectedSwingDisplay.detail} / {detectedSwingDisplay.label}</span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>
              <div className="rounded-2xl border border-indigo-100 bg-indigo-50/70 p-4 text-sm text-slate-700 shadow-sm">
                <p className="font-semibold text-slate-900">Plan logic</p>
                <p className="mt-2 leading-6">
                  {derivedDirection === "LONG"
                    ? "For a long plan, the lowest reversal low drives entry while stop loss stays anchored below the strong low. Any newly added lower reversal low will automatically recalculate entry, RR, and quantity."
                    : "For a short plan, the highest reversal high drives entry while stop loss stays anchored above the strong high. Any newly added higher reversal high will automatically recalculate entry, RR, and quantity."}
                </p>
              </div>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-slate-900">Reversal Points</h3>
                  <button type="button" onClick={() => addArrayField("reversalPoints")} disabled={targetsOnlyEdit} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50">Add</button>
                </div>
                <div className="space-y-3">
                  {form.reversalPoints.map((value, index) => (
                    <div key={`reversal-${index}`} className="flex items-center gap-2">
                      <input
                        type="number"
                        step="any"
                        value={value}
                        onChange={(e) => updateArrayField("reversalPoints", index, e.target.value)}
                        disabled={targetsOnlyEdit}
                        className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500 disabled:bg-slate-100"
                        placeholder={derivedDirection === "LONG" ? "Early long reversal low" : "Early short reversal high"}
                      />
                      {form.reversalPoints.length > 1 ? (
                        <button type="button" onClick={() => removeArrayField("reversalPoints", index)} disabled={targetsOnlyEdit} className="rounded-lg border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700 disabled:cursor-not-allowed disabled:opacity-50">Remove</button>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-slate-900">Unmitigated Targets</h3>
                  <button type="button" onClick={() => addArrayField("unmitigatedTargets")} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700">Add</button>
                </div>
                <div className="space-y-3">
                  {form.unmitigatedTargets.map((value, index) => (
                    <div key={`target-${index}`} className="flex items-center gap-2">
                      <input
                        type="number"
                        step="any"
                        value={value}
                        onChange={(e) => updateArrayField("unmitigatedTargets", index, e.target.value)}
                        className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
                        placeholder={`Target ${index + 1}`}
                      />
                      {form.unmitigatedTargets.length > 1 ? (
                        <button type="button" onClick={() => removeArrayField("unmitigatedTargets", index)} className="rounded-lg border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700">Remove</button>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">Target Strategy</h3>
                <ToggleSwitch checked={form.autoExecutionEnabled} onChange={(checked) => setForm((current) => ({ ...current, autoExecutionEnabled: checked }))} onLabel="Running" offLabel="Active" />
              </div>
              <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
                <label className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={Boolean(form.breakevenAtT1)}
                    disabled={populatedTargets.length < 2}
                    onChange={(e) => setForm((current) => ({ ...current, breakevenAtT1: e.target.checked }))}
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-slate-900">Breakeven at T1</span>
                    <span className="block text-xs leading-5 text-slate-600">
                      Move stop loss to entry price as soon as Target 1 is reached. This option is available only when the plan has at least two targets.
                    </span>
                  </span>
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {visibleAllocationCount > 0 ? (
                  <>
                    {Array.from({ length: visibleAllocationCount }).map((_, index) => (
                      <label key={`allocation-${index}`} className="space-y-1 text-sm">
                        <span className="font-medium text-slate-700">% to book at T{index + 1 + visibleAllocationStartIndex}</span>
                        <input
                          type="number"
                          step="0.01"
                          value={form.targetAllocations[index] || ""}
                          onChange={(e) => updateArrayField("targetAllocations", index, e.target.value)}
                          className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
                          placeholder="Enter %"
                        />
                      </label>
                    ))}
                    <div className="space-y-1 text-sm">
                      <span className="font-medium text-slate-700">Final target</span>
                      <div className="flex h-[42px] items-center rounded-xl border border-slate-200 bg-slate-50 px-3 text-slate-600">
                        Remaining allocation auto-calculates to 100%
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600 md:col-span-2 xl:col-span-4">
                    {form.breakevenAtT1 && populatedTargets.length >= 2
                      ? "T1 is reserved for breakeven only. Remaining quantity auto-books at the final target."
                      : "With one target, the planner books 100% at T1 automatically."}
                  </div>
                )}
              </div>
              {breakevenRequiresMoreTargets ? (
                <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-700">
                  Breakeven at T1 requires at least two targets.
                </div>
              ) : null}
            </div>

            {previewError ? <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{previewError}</div> : null}
            {preview ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                  {[
                    ["Direction", preview.direction],
                    ["Entry", formatPrice(preview.entry_price, [preview.stop_loss, preview.strong_swing_price])],
                    ["Stop Loss", formatPrice(preview.stop_loss, [preview.entry_price, preview.strong_swing_price])],
                    ["Accounts", `${(preview.account_targets || []).length}`],
                    ["SL Distance", formatDistanceValue(preview.symbol, preview.sl_pips)],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
                      <p className="mt-1 text-lg font-bold text-slate-900">{value}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 overflow-hidden rounded-xl border border-slate-100">
                  <div className="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Selected Accounts</div>
                  <div className="divide-y divide-slate-100 bg-white">
                    {(preview.account_targets || []).map((target) => (
                      <div key={target.account_db_id} className="grid gap-2 px-3 py-3 md:grid-cols-[minmax(0,1fr)_120px_120px] md:items-center">
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-slate-900">{target.account_name}</p>
                        </div>
                        <div className="text-sm text-slate-600">
                          <span className="font-medium text-slate-500">Risk</span> {target.risk_amount}
                        </div>
                        <div className="text-sm text-slate-600">
                          <span className="font-medium text-slate-500">Qty</span> {formatQty(target.quantity)} lots
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="mt-4 overflow-auto rounded-xl border border-slate-100">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-3 py-2">Target</th>
                        <th className="px-3 py-2">Price</th>
                        <th className="px-3 py-2">RR</th>
                        <th className="px-3 py-2">Book %</th>
                        <th className="px-3 py-2">Management</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(preview.targets || []).map((target) => (
                        <tr key={`${target.target_index}-${target.price}`} className="border-t border-slate-100">
                          <td className="px-3 py-2 font-semibold text-slate-900">T{target.target_index}</td>
                          <td className="px-3 py-2 text-slate-700">{formatPrice(target.price, [preview.entry_price, preview.stop_loss])}</td>
                          <td className="px-3 py-2 text-slate-700">{target.rr_ratio ?? "-"}R</td>
                          <td className="px-3 py-2 text-slate-700">{target.allocation_percent}%</td>
                          <td className="px-3 py-2 text-slate-700">
                            {target.breakeven_trigger ? (
                              <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700">Move SL to Entry</span>
                            ) : (
                              "-"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={submitPlan} disabled={submitting || previewLoading || !preview} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
                {submitting ? "Saving..." : editingPlanId ? (targetsOnlyEdit ? "Update Targets" : "Update Plan") : "Create Plan"}
              </button>
              {editingPlanId ? (
                <button type="button" onClick={resetDraft} className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700">Cancel Edit</button>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Plan View</p>
                <p className="mt-1 text-lg font-bold text-slate-900">{viewTab === "inactive" ? "Inactive / Deactivated Plans" : "Active Plans"}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
                  Active {categorizedPlans.summary.active}
                </span>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
                  Running {categorizedPlans.summary.running}
                </span>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
                  Inactive {categorizedPlans.summary.inactive}
                </span>
              </div>
            </div>
            <div className="inline-flex overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              {[
                { id: "active", label: `Active (${categorizedPlans.summary.active})` },
                { id: "inactive", label: `Inactive (${categorizedPlans.summary.inactive})` },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setViewTab(tab.id)}
                  className={`px-4 py-2 text-sm font-semibold ${viewTab === tab.id ? "bg-slate-900 text-white" : "text-slate-600"}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="space-y-3">
              {plansLoading ? (
                <div className="rounded-2xl border border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">Loading plans...</div>
              ) : visiblePlans.length === 0 ? (
                <div className="rounded-2xl border border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">
                  {viewTab === "inactive" ? "No inactive or deactivated trade plans yet." : "No active trade plans right now."}
                </div>
              ) : (
                visiblePlans.map((plan) => {
                  const { effectiveLinkedOrderStatus, effectiveRuntimeStatus, plannerRunningPl, effectivePlanStatus, isRunning } = plan;
                  const isExpanded = expandedPlanIds[plan.id] ?? true;
                  const swingTypeDisplay = tradePlannerSwingTypeDisplay(plan.strong_swing_type);
                  return (
                    <article key={plan.id} className={`rounded-2xl border bg-white shadow-sm ${isRunning ? "border-emerald-200 ring-1 ring-emerald-100" : "border-slate-200"}`}>
                      <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-4">
                        <button type="button" onClick={() => setExpandedPlanIds((current) => ({ ...current, [plan.id]: !isExpanded }))} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                          <InstrumentIcon symbol={plan.symbol} />
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-base font-semibold text-slate-900">{plan.symbol}</p>
                              <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${instrumentDirectionBadge(plan.direction).tone}`}>{instrumentDirectionBadge(plan.direction).label}</span>
                              {swingTypeDisplay ? (
                                <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${swingTypeDisplay.tone}`}>
                                  <span className={`inline-flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold ${swingTypeDisplay.iconTone}`}>
                                    {swingTypeDisplay.icon}
                                  </span>
                                  <span>{swingTypeDisplay.label}</span>
                                </span>
                              ) : null}
                              <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${tradePlannerStatusTone(effectivePlanStatus)}`}>{tradePlannerPlanModeLabel(effectivePlanStatus)}</span>
                              {effectiveRuntimeStatus ? (
                                <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${tradePlannerStatusTone(effectiveRuntimeStatus)}`}>{tradePlannerExecutionLabel(effectiveRuntimeStatus)}</span>
                              ) : null}
                              {Number.isFinite(plannerRunningPl) && ["POSITION_OPEN", "PARTIALLY_CLOSED", "FILLED"].includes(effectiveLinkedOrderStatus) ? (
                                <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${plannerRunningPl >= 0 ? "border border-emerald-200 bg-emerald-50 text-emerald-700" : "border border-rose-200 bg-rose-50 text-rose-700"}`}>
                                  Running P/L {plannerRunningPl >= 0 ? "+" : ""}{plannerRunningPl.toFixed(2)}
                                </span>
                              ) : null}
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
                              <span><span className="font-medium text-slate-500">Entry</span> {formatPrice(plan.entry_price, [plan.stop_loss, plan.strong_swing_price])}</span>
                              <span><span className="font-medium text-slate-500">SL</span> {formatPrice(plan.stop_loss, [plan.entry_price, plan.strong_swing_price])}</span>
                              <span><span className="font-medium text-slate-500">Accounts</span> {(plan.effectiveAccountTargets || []).length}</span>
                              <span><span className="font-medium text-slate-500">Total Risk</span> {plan.risk_amount}</span>
                            </div>
                          </div>
                        </button>
                        <div className="flex flex-wrap items-center justify-end gap-2">
                          <ToggleSwitch checked={Boolean(plan.auto_execution_enabled)} onChange={(checked) => toggleRunning(plan, checked)} onLabel="Running" offLabel="Active" />
                          <button type="button" onClick={() => startEdit(plan)} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700">
                            {["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].includes(String(plan.effectiveLinkedOrderStatus || "").toUpperCase()) ? "Edit Targets" : "Edit"}
                          </button>
                          {String(plan.status || "").toUpperCase() !== "INACTIVE" ? (
                            <button type="button" onClick={() => deactivatePlan(plan.id)} className="rounded-lg border border-amber-200 px-3 py-2 text-xs font-semibold text-amber-700">Deactivate</button>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => deletePlan(plan.id)}
                            className="rounded-lg border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700"
                            title="Delete plan"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {isExpanded ? (
                        <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-4 text-sm text-slate-700">
                          <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                            <div className="space-y-4">
                              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                                <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Strong Swing</p>
                                  <p className="mt-1 font-semibold text-slate-900">{formatPrice(plan.strong_swing_price, [plan.entry_price, plan.stop_loss])}</p>
                                </div>
                                <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Direction Bias</p>
                                  {swingTypeDisplay ? (
                                    <div className={`mt-2 inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-semibold ${swingTypeDisplay.tone}`}>
                                      <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${swingTypeDisplay.iconTone}`}>
                                        {swingTypeDisplay.icon}
                                      </span>
                                      <span>{swingTypeDisplay.detail} / {swingTypeDisplay.label}</span>
                                    </div>
                                  ) : (
                                    <p className="mt-1 font-semibold text-slate-900">-</p>
                                  )}
                                </div>
                                <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Protection</p>
                                  <p className="mt-1 font-semibold text-slate-900">
                                    {plan.breakeven_at_t1 ? (plan.breakeven_activated_at ? "Breakeven active" : "Breakeven at T1") : "No breakeven rule"}
                                  </p>
                                </div>
                              </div>

                              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                                <div className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Enabled Accounts</div>
                                <div className="divide-y divide-slate-100">
                                  {(plan.effectiveAccountTargets || []).map((target) => (
                                    <div key={`${plan.id}-${target.account_db_id}`} className="grid gap-2 px-3 py-3 md:grid-cols-[minmax(0,1fr)_100px_110px_140px] md:items-center">
                                      <div className="min-w-0">
                                        <p className="truncate font-semibold text-slate-900">{target.account_name}</p>
                                      </div>
                                      <div className="text-sm text-slate-600">
                                        <span className="font-medium text-slate-500">Risk</span> {target.risk_amount}
                                      </div>
                                      <div className="text-sm text-slate-600">
                                        <span className="font-medium text-slate-500">Qty</span> {formatQty(target.quantity)} lots
                                      </div>
                                      <div className="flex flex-wrap gap-2">
                                        {target.effectiveRuntimeStatus ? (
                                          <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${tradePlannerStatusTone(target.effectiveRuntimeStatus)}`}>
                                            {tradePlannerExecutionLabel(target.effectiveRuntimeStatus)}
                                          </span>
                                        ) : null}
                                        {Number.isFinite(target.runningPl) && ["POSITION_OPEN", "PARTIALLY_CLOSED", "FILLED"].includes(target.effectiveLinkedOrderStatus) ? (
                                          <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${target.runningPl >= 0 ? "border border-emerald-200 bg-emerald-50 text-emerald-700" : "border border-rose-200 bg-rose-50 text-rose-700"}`}>
                                            {target.runningPl >= 0 ? "+" : ""}{target.runningPl.toFixed(2)}
                                          </span>
                                        ) : null}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Reversal Points</p>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {(plan.reversal_points || []).length ? (
                                    (plan.reversal_points || []).map((value, index) => (
                                      <span key={`${plan.id}-reversal-${index}`} className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">
                                        {formatPrice(value, plan.reversal_points)}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="text-slate-500">-</span>
                                  )}
                                </div>
                              </div>

                              <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Target Levels</p>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {(plan.unmitigated_targets || []).length ? (
                                    (plan.unmitigated_targets || []).map((value, index) => (
                                      <span key={`${plan.id}-target-${index}`} className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800">
                                        {formatPrice(value, plan.unmitigated_targets)}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="text-slate-500">-</span>
                                  )}
                                </div>
                              </div>
                            </div>

                            <div className="space-y-4">
                              <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                                <div className="flex flex-wrap gap-2">
                                  <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${tradePlannerStatusTone(plan.status)}`}>{tradePlannerPlanModeLabel(plan.status)}</span>
                                  {effectiveRuntimeStatus ? (
                                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${tradePlannerStatusTone(effectiveRuntimeStatus)}`}>Execution: {tradePlannerExecutionLabel(effectiveRuntimeStatus)}</span>
                                  ) : null}
                                  {effectiveLinkedOrderStatus ? (
                                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${tradePlannerStatusTone(effectiveLinkedOrderStatus)}`}>Broker: {tradePlannerExecutionLabel(effectiveLinkedOrderStatus)}</span>
                                  ) : null}
                                </div>
                                <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                                  <div>
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Updated</p>
                                    <p className="mt-1 font-semibold text-slate-900">{formatNotificationTimestamp(plan.updated_at)}</p>
                                  </div>
                                  {plan.last_execution_at ? (
                                    <div>
                                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Last Execution</p>
                                      <p className="mt-1 font-semibold text-slate-900">{formatNotificationTimestamp(plan.last_execution_at)}</p>
                                    </div>
                                  ) : null}
                                </div>
                                {Number.isFinite(plannerRunningPl) && ["POSITION_OPEN", "PARTIALLY_CLOSED", "FILLED"].includes(effectiveLinkedOrderStatus) ? (
                                  <div className={`mt-3 rounded-xl border px-3 py-2 ${plannerRunningPl >= 0 ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Running P/L</p>
                                    <p className={`mt-1 font-semibold ${plannerRunningPl >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{plannerRunningPl >= 0 ? "+" : ""}{plannerRunningPl.toFixed(2)}</p>
                                  </div>
                                ) : null}
                              </div>

                              <div className="overflow-auto rounded-xl border border-slate-200 bg-white">
                              <table className="w-full text-sm">
                                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                                  <tr>
                                  <th className="px-3 py-2">Target</th>
                                  <th className="px-3 py-2">Price</th>
                                  <th className="px-3 py-2">RR</th>
                                  <th className="px-3 py-2">Book %</th>
                                  <th className="px-3 py-2">Management</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(plan.targets || []).map((target) => (
                                  <tr key={`${plan.id}-${target.target_index}`} className="border-t border-slate-100">
                                    <td className="px-3 py-2 font-semibold text-slate-900">T{target.target_index}</td>
                                    <td className="px-3 py-2 font-semibold text-emerald-700">{formatPrice(target.price, [plan.entry_price, plan.stop_loss])}</td>
                                    <td className="px-3 py-2 font-semibold text-indigo-700">{target.rr_ratio ?? "-"}R</td>
                                    <td className="px-3 py-2 font-semibold text-slate-700">{target.allocation_percent}%</td>
                                    <td className="px-3 py-2 text-slate-700">
                                      {target.breakeven_trigger ? (
                                        <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700">Move SL to Entry</span>
                                      ) : (
                                        "-"
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                              </table>
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </article>
                  );
                })
              )}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

function AdminConsolePage({ token, me, onNotify, adminFlowRuns }) {
  const adminTabs = [
    { id: "users", label: "Manage Users" },
    { id: "repositories", label: "Manage Repositories" },
  ];
  const [users, setUsers] = useState([]);
  const [repositories, setRepositories] = useState([]);
  const [githubAccount, setGitHubAccount] = useState({ connected: false });
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [loadingRepositories, setLoadingRepositories] = useState(false);
  const [submittingRepositoryImport, setSubmittingRepositoryImport] = useState(false);
  const [loadingGitHubAccount, setLoadingGitHubAccount] = useState(false);
  const [connectingGitHub, setConnectingGitHub] = useState(false);
  const [activeAdminTab, setActiveAdminTab] = useState("users");
  const [userForm, setUserForm] = useState({ username: "", full_name: "", password: "", is_admin: false, is_active: true });
  const [userDrafts, setUserDrafts] = useState({});
  const [repoDrafts, setRepoDrafts] = useState({});
  const [selectedRepoId, setSelectedRepoId] = useState("");
  const [workflowsByRepo, setWorkflowsByRepo] = useState({});
  const [branchesByRepo, setBranchesByRepo] = useState({});
  const [repoActionsDraftByRepo, setRepoActionsDraftByRepo] = useState({});
  const [runningFlowByRepo, setRunningFlowByRepo] = useState({});
  const [flowLogsByRepo, setFlowLogsByRepo] = useState({});
  const [draggingRepositoryAction, setDraggingRepositoryAction] = useState(null);
  const [dismissedFlowRunIdsByRepo, setDismissedFlowRunIdsByRepo] = useState({});

  const selectedRepository = useMemo(
    () => repositories.find((repository) => repository.id === selectedRepoId) || null,
    [repositories, selectedRepoId]
  );
  const selectedRepositoryId = selectedRepository?.id || "";
  const selectedRepositoryBranches = branchesByRepo[selectedRepositoryId] || [];
  const selectedRepositoryWorkflows = workflowsByRepo[selectedRepositoryId] || [];
  const selectedRepositoryActionsDraft = repoActionsDraftByRepo[selectedRepositoryId] || [];
  const selectedRepositoryFlowLogs = flowLogsByRepo[selectedRepositoryId] || null;
  const selectedRepositoryFlowRunning = Boolean(runningFlowByRepo[selectedRepositoryId]);

  useEffect(() => {
    if (!Array.isArray(adminFlowRuns) || !adminFlowRuns.length) return;
    const latestByRepo = {};
    adminFlowRuns.forEach((run) => {
      if (!run?.repository_id) return;
      if (!latestByRepo[run.repository_id]) {
        latestByRepo[run.repository_id] = run;
      }
    });
    setFlowLogsByRepo((current) => {
      const next = { ...current };
      Object.entries(latestByRepo).forEach(([repoId, run]) => {
        if (dismissedFlowRunIdsByRepo[repoId] && dismissedFlowRunIdsByRepo[repoId] === run.id) {
          return;
        }
        next[repoId] = run;
      });
      return next;
    });
    setRunningFlowByRepo((current) => {
      const next = { ...current };
      Object.entries(latestByRepo).forEach(([repoId, run]) => {
        next[repoId] = ["queued", "running"].includes(String(run?.status || "").toLowerCase());
      });
      return next;
    });
    setDismissedFlowRunIdsByRepo((current) => {
      const next = { ...current };
      Object.entries(latestByRepo).forEach(([repoId, run]) => {
        if (next[repoId] && next[repoId] !== run.id) {
          delete next[repoId];
        }
      });
      return next;
    });
  }, [adminFlowRuns, dismissedFlowRunIdsByRepo]);

  const loadUsers = async () => {
    setLoadingUsers(true);
    try {
      const records = await api("/admin/users", "GET", undefined, token);
      setUsers(records);
      setUserDrafts((current) => {
        const next = {};
        records.forEach((user) => {
          next[user.id] = current[user.id] || {
            username: user.username,
            full_name: user.full_name,
            password: "",
            is_admin: user.is_admin,
            is_active: user.is_active,
          };
        });
        return next;
      });
    } catch (err) {
      onNotify("error", err.message);
    } finally {
      setLoadingUsers(false);
    }
  };

  const loadRepositories = async () => {
    setLoadingRepositories(true);
    try {
      const records = await api("/admin/repositories", "GET", undefined, token);
      setRepositories(records);
      setRepoDrafts((current) => {
        const next = {};
        records.forEach((repository) => {
          next[repository.id] = current[repository.id] || {
            name: repository.name,
            default_branch: repository.default_branch || "",
            is_active: repository.is_active,
          };
        });
        return next;
      });
      setRepoActionsDraftByRepo((current) => {
        const next = {};
        records.forEach((repository) => {
          next[repository.id] = (current[repository.id] || repository.actions || []).map((action, index) => ({
            id: action.id || `action-${index + 1}`,
            type: action.type || "MERGE",
            enabled: action.enabled !== false,
            source_branch: action.source_branch || "",
            target_branch: action.target_branch || "",
            workflow_id: action.workflow_id || "",
            workflow_name: action.workflow_name || "",
            dispatch_mode: action.dispatch_mode || "WORKFLOW_DISPATCH",
            event_type: action.event_type || "",
            ref: action.ref || "",
            saved: true,
          }));
        });
        return next;
      });
      setSelectedRepoId((current) => current || records[0]?.id || "");
    } catch (err) {
      onNotify("error", err.message);
    } finally {
      setLoadingRepositories(false);
    }
  };

  const refreshRepositories = async () => {
    if (loadingRepositories || submittingRepositoryImport) return;
    if (!githubAccount?.connected) {
      await loadRepositories();
      return;
    }
    try {
      setLoadingRepositories(true);
      await api("/admin/repositories", "POST", undefined, token);
      await loadRepositories();
    } catch (err) {
      onNotify("error", err.message);
      setLoadingRepositories(false);
    }
  };

  const loadGitHubAccount = async () => {
    setLoadingGitHubAccount(true);
    try {
      const payload = await api("/admin/github/account", "GET", undefined, token);
      setGitHubAccount(payload || { connected: false });
    } catch (err) {
      onNotify("error", err.message);
    } finally {
      setLoadingGitHubAccount(false);
    }
  };

  useEffect(() => {
    if (!token || !me?.is_admin) return;
    loadUsers();
    loadGitHubAccount();
    loadRepositories();
  }, [token, me?.is_admin]);

  useEffect(() => {
    if (!selectedRepository) return;
    loadWorkflows(selectedRepository.id);
    loadBranches(selectedRepository.id);
  }, [selectedRepository]);

  const loadWorkflows = async (repositoryId) => {
    try {
      const payload = await api(`/admin/repositories/${repositoryId}/workflows`, "GET", undefined, token);
      const workflows = payload.records || [];
      setWorkflowsByRepo((current) => ({ ...current, [repositoryId]: workflows }));
    } catch (err) {
      onNotify("error", err.message);
    }
  };

  const loadBranches = async (repositoryId) => {
    try {
      const payload = await api(`/admin/repositories/${repositoryId}/branches`, "GET", undefined, token);
      setBranchesByRepo((current) => ({ ...current, [repositoryId]: payload.records || [] }));
    } catch (err) {
      onNotify("error", err.message);
    }
  };

  const submitNewUser = async (event) => {
    event.preventDefault();
    try {
      await api("/admin/users", "POST", userForm, token);
      onNotify("success", "User created.");
      setUserForm({ username: "", full_name: "", password: "", is_admin: false, is_active: true });
      await loadUsers();
    } catch (err) {
      onNotify("error", err.message);
    }
  };

  const saveUser = async (userId) => {
    try {
      await api(`/admin/users/${userId}`, "PATCH", userDrafts[userId], token);
      onNotify("success", "User updated.");
      await loadUsers();
    } catch (err) {
      onNotify("error", err.message);
    }
  };

  const submitRepository = async (event) => {
    if (event?.preventDefault) event.preventDefault();
    if (submittingRepositoryImport) return;
    try {
      setSubmittingRepositoryImport(true);
      await api("/admin/repositories", "POST", undefined, token);
      onNotify("success", "Repositories imported.");
      await loadRepositories();
    } catch (err) {
      onNotify("error", err.message);
    } finally {
      setSubmittingRepositoryImport(false);
    }
  };

  const saveRepository = async (repositoryId) => {
    const draft = repoDrafts[repositoryId] || {};
    const payload = {
      name: draft.name,
      default_branch: draft.default_branch,
      is_active: draft.is_active,
    };
    try {
      await api(`/admin/repositories/${repositoryId}`, "PATCH", payload, token);
      onNotify("success", "Repository updated.");
      await loadRepositories();
    } catch (err) {
      onNotify("error", err.message);
    }
  };

  const deleteRepository = async (repositoryId) => {
    try {
      await api(`/admin/repositories/${repositoryId}`, "DELETE", undefined, token);
      setRepositories((current) => {
        const next = current.filter((repository) => repository.id !== repositoryId);
        setSelectedRepoId((selectedCurrent) => {
          if (selectedCurrent !== repositoryId) return selectedCurrent;
          return next[0]?.id || "";
        });
        return next;
      });
      setRepoDrafts((current) => {
        const next = { ...current };
        delete next[repositoryId];
        return next;
      });
      setWorkflowsByRepo((current) => {
        const next = { ...current };
        delete next[repositoryId];
        return next;
      });
      setBranchesByRepo((current) => {
        const next = { ...current };
        delete next[repositoryId];
        return next;
      });
      setRepoActionsDraftByRepo((current) => {
        const next = { ...current };
        delete next[repositoryId];
        return next;
      });
      setRunningFlowByRepo((current) => {
        const next = { ...current };
        delete next[repositoryId];
        return next;
      });
      setFlowLogsByRepo((current) => {
        const next = { ...current };
        delete next[repositoryId];
        return next;
      });
      onNotify("success", "Repository removed from admin console.");
    } catch (err) {
      onNotify("error", err.message);
    }
  };

  const addRepositoryAction = (repositoryId) => {
    setRepoActionsDraftByRepo((current) => {
      const nextList = [
        ...(current[repositoryId] || []),
        {
          id: `draft-${Date.now()}`,
          type: "MERGE",
          enabled: true,
          source_branch: "",
          target_branch: "",
          workflow_id: "",
          workflow_name: "",
          dispatch_mode: "WORKFLOW_DISPATCH",
          event_type: "",
          ref: selectedRepository?.default_branch || "develop",
          saved: false,
        },
      ];
      return { ...current, [repositoryId]: nextList };
    });
  };

  const updateRepositoryAction = (repositoryId, actionId, updates) => {
    setRepoActionsDraftByRepo((current) => ({
      ...current,
      [repositoryId]: (current[repositoryId] || []).map((action) => {
        if (action.id !== actionId) return action;
        const nextAction = { ...action, ...updates, saved: false };
        if (nextAction.type === "MERGE") {
          nextAction.workflow_id = "";
          nextAction.workflow_name = "";
          nextAction.dispatch_mode = "WORKFLOW_DISPATCH";
          nextAction.event_type = "";
          nextAction.ref = "";
        } else {
          nextAction.source_branch = "";
          nextAction.target_branch = "";
        }
        return nextAction;
      }),
    }));
  };

  const validateRepositoryAction = (action) => {
    if (!action) return "Action is required.";
    if (action.enabled === false) return "";
    if (action.type === "MERGE") {
      if (!action.source_branch || !action.target_branch) return "Source and destination branches are required.";
      if (action.source_branch === action.target_branch) return "Source and destination branches must be different.";
      return "";
    }
    if (action.type === "RUN_WORKFLOW") {
      const mode = action.dispatch_mode || "WORKFLOW_DISPATCH";
      if (mode === "REPOSITORY_DISPATCH") {
        if (!action.event_type || !action.ref) return "Event type and branch are required.";
        return "";
      }
      if (!action.workflow_id || !action.workflow_name || !action.ref) return "Workflow name and branch are required.";
      return "";
    }
    return "Unsupported action type.";
  };

  const saveRepositoryActionDraft = (repositoryId, actionId) => {
    const action = (repoActionsDraftByRepo[repositoryId] || []).find((item) => item.id === actionId);
    const validationMessage = validateRepositoryAction(action);
    if (validationMessage) {
      onNotify("error", validationMessage);
      return;
    }
    setRepoActionsDraftByRepo((current) => ({
      ...current,
      [repositoryId]: (current[repositoryId] || []).map((item) => (item.id === actionId ? { ...item, saved: true } : item)),
    }));
    onNotify("success", "Action saved locally.");
  };

  const removeRepositoryAction = (repositoryId, actionId) => {
    setRepoActionsDraftByRepo((current) => ({
      ...current,
      [repositoryId]: (current[repositoryId] || []).filter((action) => action.id !== actionId),
    }));
  };

  const moveRepositoryAction = (repositoryId, draggedActionId, targetActionId) => {
    if (!repositoryId || !draggedActionId || !targetActionId || draggedActionId === targetActionId) return;
    setRepoActionsDraftByRepo((current) => {
      const actions = [...(current[repositoryId] || [])];
      const fromIndex = actions.findIndex((action) => action.id === draggedActionId);
      const toIndex = actions.findIndex((action) => action.id === targetActionId);
      if (fromIndex === -1 || toIndex === -1 || fromIndex === toIndex) {
        return current;
      }
      const [moved] = actions.splice(fromIndex, 1);
      actions.splice(toIndex, 0, { ...moved, saved: false });
      return { ...current, [repositoryId]: actions };
    });
  };

  const saveRepositoryActions = async (repositoryId) => {
    const drafts = repoActionsDraftByRepo[repositoryId] || [];
    for (const [index, action] of drafts.entries()) {
      const validationMessage = validateRepositoryAction(action);
      if (validationMessage) {
        console.error("Repository action validation blocked save", {
          repositoryId,
          actionIndex: index,
          action,
          validationMessage,
        });
        onNotify("error", validationMessage);
        return;
      }
    }
    const actions = drafts.map((action) => ({
      type: action.type,
      enabled: action.enabled !== false,
      source_branch: action.source_branch || undefined,
      target_branch: action.target_branch || undefined,
      workflow_id: action.workflow_id || undefined,
      workflow_name: action.workflow_name || undefined,
      dispatch_mode: action.dispatch_mode || undefined,
      event_type: action.event_type || undefined,
      ref: action.ref || undefined,
    }));
    try {
      console.log("Save Flow payload", { repositoryId, actions });
      const updated = await api(`/admin/repositories/${repositoryId}/actions`, "PUT", { actions }, token);
      setRepositories((current) => current.map((repository) => (repository.id === repositoryId ? updated : repository)));
      setRepoActionsDraftByRepo((current) => ({
        ...current,
        [repositoryId]: (updated.actions || []).map((action) => ({
          id: action.id,
          type: action.type,
          enabled: action.enabled !== false,
          source_branch: action.source_branch || "",
          target_branch: action.target_branch || "",
          workflow_id: action.workflow_id || "",
          workflow_name: action.workflow_name || "",
          dispatch_mode: action.dispatch_mode || "WORKFLOW_DISPATCH",
          event_type: action.event_type || "",
          ref: action.ref || "",
          saved: true,
        })),
      }));
      onNotify("success", "Flow saved.");
    } catch (err) {
      console.error("Save Flow failed", { repositoryId, actions, error: err });
      onNotify("error", err.message);
    }
  };

  const runRepositoryFlow = async (repositoryId) => {
    const repository = repositories.find((item) => item.id === repositoryId);
    const drafts = repoActionsDraftByRepo[repositoryId] || [];
    const persisted = repository?.actions || [];
    const normalizedDrafts = drafts.map((action) => ({
      type: action.type,
      enabled: action.enabled !== false,
      source_branch: action.source_branch || "",
      target_branch: action.target_branch || "",
      workflow_id: action.workflow_id || "",
      workflow_name: action.workflow_name || "",
      dispatch_mode: action.dispatch_mode || "WORKFLOW_DISPATCH",
      event_type: action.event_type || "",
      ref: action.ref || "",
    }));
    const normalizedPersisted = persisted.map((action) => ({
      type: action.type,
      enabled: action.enabled !== false,
      source_branch: action.source_branch || "",
      target_branch: action.target_branch || "",
      workflow_id: action.workflow_id || "",
      workflow_name: action.workflow_name || "",
      dispatch_mode: action.dispatch_mode || "WORKFLOW_DISPATCH",
      event_type: action.event_type || "",
      ref: action.ref || "",
    }));
    if (JSON.stringify(normalizedDrafts) !== JSON.stringify(normalizedPersisted)) {
      console.warn("Run Flow blocked because draft actions differ from persisted actions", {
        repositoryId,
        normalizedDrafts,
        normalizedPersisted,
      });
      onNotify("error", "Save Flow before running it.");
      return;
    }
    setRunningFlowByRepo((current) => ({ ...current, [repositoryId]: true }));
    try {
      const result = await api(`/admin/repositories/${repositoryId}/run-flow`, "POST", {}, token);
      setDismissedFlowRunIdsByRepo((current) => {
        const next = { ...current };
        delete next[repositoryId];
        return next;
      });
      setFlowLogsByRepo((current) => ({ ...current, [repositoryId]: result }));
      onNotify("success", "Flow started.");
    } catch (err) {
      onNotify("error", err.message);
      setRunningFlowByRepo((current) => ({ ...current, [repositoryId]: false }));
    }
  };

  const dismissFlowLogs = (repositoryId) => {
    const runId = flowLogsByRepo[repositoryId]?.id;
    if (runId) {
      setDismissedFlowRunIdsByRepo((current) => ({ ...current, [repositoryId]: runId }));
    }
    setFlowLogsByRepo((current) => {
      const next = { ...current };
      delete next[repositoryId];
      return next;
    });
  };

  const connectGitHub = async () => {
    if (connectingGitHub) return;
    try {
      setConnectingGitHub(true);
      const payload = await api("/admin/github/auth-url", "GET", undefined, token);
      const popup = window.open(payload.url, "signalbridge-github-connect", "width=640,height=760");
      if (!popup) {
        setConnectingGitHub(false);
        onNotify("error", "Popup blocked.");
        return;
      }
      const closePoll = window.setInterval(() => {
        if (popup.closed) {
          window.clearInterval(closePoll);
          setConnectingGitHub(false);
        }
      }, 500);
    } catch (err) {
      setConnectingGitHub(false);
      onNotify("error", err.message);
    }
  };

  const disconnectGitHub = async () => {
    try {
      await api("/admin/github/account", "DELETE", undefined, token);
      setGitHubAccount({ connected: false });
      onNotify("success", "GitHub disconnected.");
    } catch (err) {
      onNotify("error", err.message);
    }
  };

  useEffect(() => {
    if (!token || !me?.is_admin) return undefined;
    const handleMessage = async (event) => {
      const payload = event.data;
      if (!payload || payload.type !== "github-admin-connect") return;
      setConnectingGitHub(false);
      if (payload.status === "success") {
        await loadGitHubAccount();
        await loadRepositories();
        onNotify("success", payload.message || "GitHub connected.");
        return;
      }
      onNotify("error", payload.message || "GitHub connection failed.");
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [token, me?.is_admin]);


  return (
    <div className="space-y-4">
      <section className="rounded-3xl border border-indigo-100 bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">Admin Console</p>
        <h2 className="mt-1 text-2xl font-black text-slate-950">Manage users and connected GitHub repositories</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {adminTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveAdminTab(tab.id)}
              className={`${tab.id === "repositories" ? "hidden sm:inline-flex" : "inline-flex"} rounded-full px-4 py-2 text-sm font-semibold transition ${
                activeAdminTab === tab.id
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "border border-slate-200 bg-white text-slate-700 hover:border-indigo-200 hover:text-indigo-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {activeAdminTab === "users" && (
        <section className="rounded-3xl border border-indigo-100 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">Users</p>
              <h3 className="mt-1 text-xl font-bold text-slate-950">Add, activate, deactivate, and elevate users</h3>
            </div>
            <button type="button" onClick={loadUsers} className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700">
              {loadingUsers ? "Refreshing..." : "Refresh"}
            </button>
          </div>

          <form onSubmit={submitNewUser} className="mt-4 grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-2">
            <input value={userForm.full_name} onChange={(e) => setUserForm((current) => ({ ...current, full_name: e.target.value }))} placeholder="Full name" className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
            <input value={userForm.username} onChange={(e) => setUserForm((current) => ({ ...current, username: e.target.value }))} placeholder="Username" className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
            <input type="password" value={userForm.password} onChange={(e) => setUserForm((current) => ({ ...current, password: e.target.value }))} placeholder="Password" className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
            <div className="flex items-center gap-4 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700">
              <label className="flex items-center gap-2"><input type="checkbox" checked={userForm.is_admin} onChange={(e) => setUserForm((current) => ({ ...current, is_admin: e.target.checked }))} /> Admin</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={userForm.is_active} onChange={(e) => setUserForm((current) => ({ ...current, is_active: e.target.checked }))} /> Active</label>
            </div>
            <div className="md:col-span-2">
              <button type="submit" className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">Add User</button>
            </div>
          </form>

          <div className="mt-4 space-y-3">
            {users.map((user) => {
              const draft = userDrafts[user.id] || {};
              return (
                <div key={user.id} className="rounded-2xl border border-slate-200 p-4">
                  <div className="grid gap-3 md:grid-cols-[1fr_1fr_220px_auto]">
                    <input value={draft.full_name || ""} onChange={(e) => setUserDrafts((current) => ({ ...current, [user.id]: { ...current[user.id], full_name: e.target.value } }))} className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
                    <input value={draft.username || ""} onChange={(e) => setUserDrafts((current) => ({ ...current, [user.id]: { ...current[user.id], username: e.target.value } }))} className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
                    <input type="password" value={draft.password || ""} onChange={(e) => setUserDrafts((current) => ({ ...current, [user.id]: { ...current[user.id], password: e.target.value } }))} placeholder="New password (optional)" className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
                    <button type="button" onClick={() => saveUser(user.id)} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Save</button>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-slate-600">
                    <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(draft.is_admin)} onChange={(e) => setUserDrafts((current) => ({ ...current, [user.id]: { ...current[user.id], is_admin: e.target.checked } }))} /> Admin</label>
                    <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(draft.is_active)} onChange={(e) => setUserDrafts((current) => ({ ...current, [user.id]: { ...current[user.id], is_active: e.target.checked } }))} /> Active</label>
                    <span>{user.account_count} broker account(s)</span>
                    <span>Updated {formatDisplayTimestamp(user.updated_at)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {activeAdminTab === "repositories" && (
        <>
          <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
            <section className="rounded-3xl border border-indigo-100 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">Repositories</p>
                  <h3 className="mt-1 text-xl font-bold text-slate-950">Connect GitHub and manage repositories</h3>
                </div>
                <button type="button" onClick={refreshRepositories} className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700">
                  {loadingRepositories ? "Refreshing..." : "Refresh"}
                </button>
              </div>

              <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                {githubAccount?.connected ? (
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-3">
                      {githubAccount.avatar_url ? (
                        <img src={githubAccount.avatar_url} alt={githubAccount.login || "GitHub"} className="h-12 w-12 rounded-full border border-slate-200 object-cover" />
                      ) : (
                        <div className="flex h-12 w-12 items-center justify-center rounded-full border border-slate-200 bg-white text-sm font-bold text-slate-600">
                          {(githubAccount.login || "GH").slice(0, 2).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <p className="text-sm font-semibold text-slate-950">{githubAccount.name || githubAccount.login}</p>
                        <p className="text-sm text-slate-600">@{githubAccount.login}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={submitRepository}
                        disabled={submittingRepositoryImport}
                        className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-indigo-300"
                      >
                        {submittingRepositoryImport ? "Importing..." : "Fetch Repositories"}
                      </button>
                      <button
                        type="button"
                        onClick={connectGitHub}
                        disabled={connectingGitHub}
                        className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:bg-slate-100"
                      >
                        {connectingGitHub ? "Connecting..." : "Reconnect GitHub"}
                      </button>
                      <button type="button" onClick={disconnectGitHub} className="rounded-xl border border-rose-300 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50">
                        Disconnect
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={connectGitHub}
                    disabled={connectingGitHub || loadingGitHubAccount}
                    className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                  >
                    {connectingGitHub ? "Connecting..." : "Login with GitHub"}
                  </button>
                )}
              </div>

              <div className="mt-4 space-y-3">
                {repositories.map((repository) => {
                  const draft = repoDrafts[repository.id] || {};
                  return (
                    <div key={repository.id} className={`rounded-2xl border p-4 ${selectedRepoId === repository.id ? "border-indigo-400 bg-indigo-50/40" : "border-slate-200"}`}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <button type="button" onClick={() => setSelectedRepoId(repository.id)} className="text-left">
                          <p className="text-lg font-bold text-slate-950">{repository.name}</p>
                          <p className="text-sm text-slate-600">{repository.owner}/{repository.repo}</p>
                          <p className="mt-1 text-xs text-slate-500">Branch {repository.default_branch || "-"}</p>
                        </button>
                        <button type="button" onClick={() => setSelectedRepoId(repository.id)} className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700">
                          {selectedRepoId === repository.id ? "Selected" : "Select"}
                        </button>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <input value={draft.name || ""} onChange={(e) => setRepoDrafts((current) => ({ ...current, [repository.id]: { ...current[repository.id], name: e.target.value } }))} className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
                        <input value={draft.default_branch || ""} onChange={(e) => setRepoDrafts((current) => ({ ...current, [repository.id]: { ...current[repository.id], default_branch: e.target.value } }))} className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
                        <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">{repository.owner}</div>
                        <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">{repository.repo}</div>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-3">
                        <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={Boolean(draft.is_active)} onChange={(e) => setRepoDrafts((current) => ({ ...current, [repository.id]: { ...current[repository.id], is_active: e.target.checked } }))} /> Active</label>
                        <button type="button" onClick={() => saveRepository(repository.id)} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Save Changes</button>
                        <button type="button" onClick={() => deleteRepository(repository.id)} className="rounded-xl border border-rose-300 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50">Delete</button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="rounded-3xl border border-indigo-100 bg-white p-5 shadow-sm">
              {selectedRepository ? (
        <>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">Repository Detail</p>
              <h3 className="mt-1 text-xl font-bold text-slate-950">{selectedRepository.owner}/{selectedRepository.repo}</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => addRepositoryAction(selectedRepositoryId)} className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700">Add Action</button>
              <button type="button" onClick={() => saveRepositoryActions(selectedRepositoryId)} className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700">Save Flow</button>
              <button type="button" onClick={() => runRepositoryFlow(selectedRepositoryId)} disabled={selectedRepositoryFlowRunning} className="rounded-xl bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-indigo-300">
                {selectedRepositoryFlowRunning ? "Running..." : "Run Flow"}
              </button>
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-slate-200 p-4">
            <div>
              <h4 className="text-lg font-bold text-slate-900">Automated Workflow</h4>
              <p className="mt-1 text-sm text-slate-600">Build a repo flow from saved actions. Merge creates a PR from source to destination and merges it. Workflow actions use the selected workflow and branch.</p>
            </div>
            <div className="mt-4 space-y-3">
              {selectedRepositoryActionsDraft.length ? (
                selectedRepositoryActionsDraft.map((action) => (
                  <div
                    key={action.id}
                    draggable
                    onDragStart={() => setDraggingRepositoryAction({ repositoryId: selectedRepositoryId, actionId: action.id })}
                    onDragEnd={() => setDraggingRepositoryAction(null)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault();
                      if (draggingRepositoryAction?.repositoryId !== selectedRepositoryId) return;
                      moveRepositoryAction(selectedRepositoryId, draggingRepositoryAction?.actionId, action.id);
                      setDraggingRepositoryAction(null);
                    }}
                    className={`rounded-2xl border bg-slate-50 p-4 transition ${
                      draggingRepositoryAction?.repositoryId === selectedRepositoryId && draggingRepositoryAction?.actionId === action.id
                        ? "border-indigo-400 opacity-60"
                        : "border-slate-200"
                    }`}
                  >
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="cursor-grab select-none text-lg text-slate-400 active:cursor-grabbing" title="Drag to reorder">
                          ::
                        </span>
                        <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                          <input
                            type="checkbox"
                            checked={action.enabled !== false}
                            onChange={(e) => updateRepositoryAction(selectedRepositoryId, action.id, { enabled: e.target.checked })}
                          />
                          Include in execution
                        </label>
                      </div>
                    </div>
                    <div className="grid gap-3 lg:grid-cols-[220px_1fr_auto]">
                      <select
                        value={action.type}
                        onChange={(e) => updateRepositoryAction(selectedRepositoryId, action.id, { type: e.target.value })}
                        className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold outline-none focus:border-indigo-500"
                      >
                        <option value="MERGE">Merge</option>
                        <option value="RUN_WORKFLOW">Run Workflow</option>
                      </select>
                      {action.type === "MERGE" ? (
                        <div className="grid gap-3 md:grid-cols-2">
                          <select
                            value={action.source_branch || ""}
                            onChange={(e) => updateRepositoryAction(selectedRepositoryId, action.id, { source_branch: e.target.value })}
                            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
                          >
                            <option value="">Source branch</option>
                            {selectedRepositoryBranches.map((branch) => (
                              <option key={`${action.id}-source-${branch.name}`} value={branch.name}>{branch.name}</option>
                            ))}
                          </select>
                          <select
                            value={action.target_branch || ""}
                            onChange={(e) => updateRepositoryAction(selectedRepositoryId, action.id, { target_branch: e.target.value })}
                            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
                          >
                            <option value="">Dest branch</option>
                            {selectedRepositoryBranches.map((branch) => (
                              <option key={`${action.id}-target-${branch.name}`} value={branch.name}>{branch.name}</option>
                            ))}
                          </select>
                        </div>
                      ) : (
                        <div className="grid gap-3 md:grid-cols-3">
                          <select
                            value={action.dispatch_mode || "WORKFLOW_DISPATCH"}
                            onChange={(e) => updateRepositoryAction(selectedRepositoryId, action.id, { dispatch_mode: e.target.value })}
                            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
                          >
                            <option value="WORKFLOW_DISPATCH">Workflow dispatch</option>
                            <option value="REPOSITORY_DISPATCH">Repository dispatch</option>
                          </select>
                          {(action.dispatch_mode || "WORKFLOW_DISPATCH") === "REPOSITORY_DISPATCH" ? (
                            <input
                              type="text"
                              value={action.event_type || ""}
                              onChange={(e) => updateRepositoryAction(selectedRepositoryId, action.id, { event_type: e.target.value })}
                              placeholder="Dispatch event type"
                              className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
                            />
                          ) : (
                            <select
                              value={action.workflow_id || ""}
                              onChange={(e) => {
                                const chosenWorkflow = selectedRepositoryWorkflows.find((workflow) => String(workflow.id) === e.target.value);
                                updateRepositoryAction(selectedRepositoryId, action.id, {
                                  workflow_id: e.target.value,
                                  workflow_name: chosenWorkflow?.name || "",
                                });
                              }}
                              className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
                            >
                              <option value="">GH action name</option>
                              {selectedRepositoryWorkflows.map((workflow) => (
                                <option key={`${action.id}-workflow-${workflow.id}`} value={String(workflow.id)}>{workflow.name}</option>
                              ))}
                            </select>
                          )}
                          <select
                            value={action.ref || ""}
                            onChange={(e) => updateRepositoryAction(selectedRepositoryId, action.id, { ref: e.target.value })}
                            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
                          >
                            <option value="">Branch</option>
                            {selectedRepositoryBranches.map((branch) => (
                              <option key={`${action.id}-branch-${branch.name}`} value={branch.name}>{branch.name}</option>
                            ))}
                          </select>
                        </div>
                      )}
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <button type="button" onClick={() => saveRepositoryActionDraft(selectedRepositoryId, action.id)} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700">
                          Save Action
                        </button>
                        <button type="button" onClick={() => removeRepositoryAction(selectedRepositoryId, action.id)} className="rounded-xl border border-rose-300 px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50">
                          Remove
                        </button>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-600">
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${action.saved ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                        {action.saved ? "Saved" : "Unsaved"}
                      </span>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${action.enabled !== false ? "bg-indigo-100 text-indigo-700" : "bg-slate-200 text-slate-600"}`}>
                        {action.enabled !== false ? "Included" : "Skipped"}
                      </span>
                      <span>
                        {action.type === "MERGE"
                          ? `${action.source_branch || "-"} -> ${action.target_branch || "-"}`
                          : `${(action.dispatch_mode || "WORKFLOW_DISPATCH") === "REPOSITORY_DISPATCH" ? (action.event_type || "-") : (action.workflow_name || "-")} on ${action.ref || "-"}`}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-4 text-sm text-slate-500">No actions added yet.</div>
              )}
            </div>
            {selectedRepositoryFlowLogs && (
              <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-950 p-4 text-sm text-emerald-200">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-white">Flow Output</p>
                    <p className="text-xs text-slate-400">
                      {selectedRepositoryFlowLogs.status === "completed"
                        ? "Completed"
                        : selectedRepositoryFlowLogs.status === "failed"
                          ? "Stopped with error"
                          : selectedRepositoryFlowLogs.status === "running"
                            ? "Running"
                            : "Queued"}
                    </p>
                  </div>
                  <button type="button" onClick={() => dismissFlowLogs(selectedRepositoryId)} className="rounded-xl border border-slate-600 px-3 py-2 text-xs font-semibold text-slate-200">
                    Dismiss
                  </button>
                </div>
                <div className="max-h-[420px] space-y-1 overflow-auto rounded-xl border border-slate-800 bg-black/30 p-3 font-mono text-xs leading-6">
                  {(selectedRepositoryFlowLogs.logs || []).map((entry, index) => (
                    <div key={`${entry.timestamp}-${index}`} className={entry.level === "error" ? "text-rose-300" : "text-emerald-200"}>
                      {formatDisplayTimestamp(entry.timestamp)}: {entry.message}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
              ) : (
                <div className="flex h-full min-h-[320px] items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
                  Select a repository from the left column to view details and manage its flow.
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}

function EditPendingOrderModal({ order, onClose, onSubmit, token }) {
  const symbol = order?.symbol || "";
  const side = String(order?.side || "").toUpperCase();
  const orderType = String(order?.order_type || order?.orderType || "SL").toUpperCase();
  const isDeferred = isDeferredMarketOpenOrder(order);
  const [entry, setEntry] = useState(order?.entry != null ? String(order.entry) : "");
  const [stopLoss, setStopLoss] = useState(order?.stop_loss != null ? String(order.stop_loss) : "");
  const [target, setTarget] = useState(order?.target != null && order?.target !== "" ? String(order.target) : "");
  const [quantity, setQuantity] = useState(order?.quantity != null ? formatQty(order.quantity) : "");
  const [riskAmount, setRiskAmount] = useState(order?.risk_amount != null ? String(order.risk_amount) : "");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const lastEdited = useRef(isDeferred ? "risk" : "qty");

  useEffect(() => {
    if (!order) {
      setEntry("");
      setStopLoss("");
      setTarget("");
      setQuantity("");
      setRiskAmount("");
      setError("");
      setSubmitting(false);
      return;
    }
    setEntry(order.entry != null ? String(order.entry) : "");
    setStopLoss(order.stop_loss != null ? String(order.stop_loss) : "");
    setTarget(order.target != null && order.target !== "" ? String(order.target) : "");
    setQuantity(order.quantity != null ? formatQty(order.quantity) : "");
    setRiskAmount(order.risk_amount != null ? String(order.risk_amount) : "");
    setError("");
    setSubmitting(false);
    lastEdited.current = isDeferredMarketOpenOrder(order) ? "risk" : "qty";
  }, [order]);

  useEffect(() => {
    if (!isDeferred || !order?.account_id || !token) return undefined;
    const numericEntry = Number(entry);
    const numericStop = Number(stopLoss);
    const numericRisk = Number(riskAmount);
    const numericQty = Number(quantity);
    if (!Number.isFinite(numericEntry) || numericEntry <= 0 || !Number.isFinite(numericStop) || numericStop <= 0) {
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      if (lastEdited.current === "risk") {
        if (!Number.isFinite(numericRisk) || numericRisk <= 0) return;
        setPreviewBusy(true);
        try {
          const preview = await api(
            "/risk-preview/multi",
            "POST",
            {
              symbol,
              side,
              order_type: orderType,
              entry: numericEntry,
              stop_loss: numericStop,
              target: target.trim() === "" ? null : Number(target),
              targets: [{ account_db_id: order.account_id, risk_amount: numericRisk }],
            },
            token
          );
          const qty = preview?.targets?.[0]?.quantity;
          if (!cancelled && qty != null) setQuantity(formatQty(qty));
        } catch {
          /* keep manual values */
        } finally {
          if (!cancelled) setPreviewBusy(false);
        }
      } else if (lastEdited.current === "qty" || lastEdited.current === "levels") {
        if (!Number.isFinite(numericQty) || numericQty <= 0) return;
        // Approximate risk from prior risk/qty ratio when SL distance changes proportionally via modify on save.
        // Live risk refresh: scale from last known ratio when only qty changes; otherwise wait for save.
        if (lastEdited.current === "qty" && Number(order.quantity) > 0 && order.risk_amount != null) {
          const scaled = (numericQty / Number(order.quantity)) * Number(order.risk_amount);
          if (!cancelled && Number.isFinite(scaled)) setRiskAmount(String(Math.round(scaled * 100) / 100));
        }
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [entry, stopLoss, riskAmount, quantity, isDeferred, order, symbol, side, orderType, target, token]);

  if (!order) return null;

  const submit = async () => {
    const numericEntry = Number(entry);
    const numericStop = Number(stopLoss);
    const numericTarget = target.trim() === "" ? null : Number(target);
    const numericQuantity = Number(quantity);
    const numericRisk = Number(riskAmount);
    if (!Number.isFinite(numericEntry) || numericEntry <= 0) {
      setError("Enter a valid entry price.");
      return;
    }
    if (!Number.isFinite(numericStop) || numericStop <= 0) {
      setError("Enter a valid stop loss.");
      return;
    }
    if (numericTarget != null && (!Number.isFinite(numericTarget) || numericTarget <= 0)) {
      setError("Enter a valid target or leave it blank.");
      return;
    }
    if (isDeferred) {
      if (lastEdited.current === "risk") {
        if (!Number.isFinite(numericRisk) || numericRisk <= 0) {
          setError("Enter a valid risk amount.");
          return;
        }
      } else if (!Number.isFinite(numericQuantity) || numericQuantity <= 0) {
        setError("Enter a valid quantity.");
        return;
      }
    } else if (!Number.isFinite(numericQuantity) || numericQuantity <= 0) {
      setError("Enter a valid quantity.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const payload = {
        entry: numericEntry,
        stop_loss: numericStop,
        target: numericTarget,
      };
      if (isDeferred && lastEdited.current === "risk") {
        payload.risk_amount = numericRisk;
      } else {
        payload.quantity = numericQuantity;
        if (isDeferred && Number.isFinite(numericRisk) && numericRisk > 0) {
          // quantity path; backend recomputes risk
        }
      }
      await onSubmit(order.id, payload);
    } catch (err) {
      setError(err?.message || "Unable to update the order.");
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-slate-900">{isDeferred ? "Edit Deferred Pending Order" : "Edit Pending Order"}</h3>
            <p className="mt-1 text-sm text-slate-600">
              {symbol ? `${symbol} · ${side} · ${orderType}` : "Pending order"}
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-sm font-semibold text-slate-500 hover:bg-slate-100">
            Close
          </button>
        </div>
        <p className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
          {isDeferred
            ? "Changes stay local until Monday 04:30 IST when the order is sent to the broker. Updating risk recalculates quantity; updating quantity recalculates risk."
            : "Changing quantity cancels the broker order and places a new one. Entry, stop loss, and target updates are sent to the broker when quantity stays the same."}
        </p>
        <div className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-slate-600">Entry</span>
            <input
              value={entry}
              onChange={(e) => {
                lastEdited.current = "levels";
                setEntry(e.target.value);
              }}
              type="number"
              step="any"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-400"
              disabled={orderType === "MARKET"}
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-slate-600">Stop loss</span>
            <input
              value={stopLoss}
              onChange={(e) => {
                lastEdited.current = "levels";
                setStopLoss(e.target.value);
              }}
              type="number"
              step="any"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-400"
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-slate-600">Target (optional)</span>
            <input value={target} onChange={(e) => setTarget(e.target.value)} type="number" step="any" className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-400" />
          </label>
          {isDeferred ? (
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-slate-600">Risk amount {previewBusy ? "(updating…)" : ""}</span>
              <input
                value={riskAmount}
                onChange={(e) => {
                  lastEdited.current = "risk";
                  setRiskAmount(e.target.value);
                }}
                type="number"
                step="any"
                min="0"
                className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-400"
              />
            </label>
          ) : null}
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-slate-600">Quantity</span>
            <input
              value={quantity}
              onChange={(e) => {
                lastEdited.current = "qty";
                setQuantity(e.target.value);
              }}
              type="number"
              step="0.01"
              min="0.01"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-400"
            />
          </label>
        </div>
        {error ? <p className="mt-3 text-sm font-semibold text-rose-600">{error}</p> : null}
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
          >
            {submitting ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ClosePositionModal({ order, onClose, onSubmit, livePrices = {} }) {
  const availableQuantity = Number(order?.position_quantity ?? order?.quantity ?? 0);
  const symbol = order?.symbol || "";
  const side = String(order?.side || "").toUpperCase();
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!order) {
      setQuantity("");
      setPrice("");
      setError("");
      setSubmitting(false);
      return;
    }
    const qty = Number(order?.position_quantity ?? order?.quantity ?? 0);
    const quote = livePrices?.[String(order.symbol || "").toUpperCase()] || livePrices?.[order.symbol] || {};
    const bid = Number(quote.bid ?? quote.price);
    const ask = Number(quote.ask ?? quote.price);
    const orderSide = String(order.side || "").toUpperCase();
    const fromOrder = Number(order.defaultClosePrice);
    let closePrice = Number.isFinite(fromOrder) && fromOrder > 0 ? fromOrder : null;
    if (closePrice == null) {
      closePrice = orderSide === "SELL"
        ? (Number.isFinite(ask) ? ask : Number(quote.price))
        : (Number.isFinite(bid) ? bid : Number(quote.price));
    }
    setQuantity(qty > 0 ? formatQty(qty) : "");
    setPrice(Number.isFinite(closePrice) && closePrice > 0 ? String(closePrice) : "");
    setError("");
    setSubmitting(false);
    // Intentionally seed once when the modal target order changes, not on every live tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order]);

  if (!order) return null;

  const numericQuantity = Number(quantity);
  const numericPrice = Number(price);

  const submit = async () => {
    if (!Number.isFinite(numericQuantity) || numericQuantity <= 0) {
      setError("Enter a valid quantity to close.");
      return;
    }
    if (availableQuantity > 0 && numericQuantity > availableQuantity) {
      setError("Close quantity cannot exceed the open quantity.");
      return;
    }
    if (!Number.isFinite(numericPrice) || numericPrice <= 0) {
      setError("Enter a valid limit price.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(order.id, numericQuantity, { order_type: "LIMIT", price: numericPrice });
    } catch (err) {
      setError(err?.message || "Unable to close the position.");
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Partial Exit</h3>
            <p className="mt-1 text-sm text-slate-600">
              {symbol ? `${symbol} · ${side || "Position"}` : "Limit close"}
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-sm font-semibold text-slate-500 hover:bg-slate-100">
            Close
          </button>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Open Quantity</p>
          <p className="mt-1 text-lg font-semibold text-slate-900">{availableQuantity || "-"}</p>
        </div>
        <label className="mt-4 block space-y-1 text-sm">
          <span className="font-medium text-slate-600">Quantity to close</span>
          <input
            type="number"
            min="0"
            step="any"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
            placeholder="Enter quantity"
          />
        </label>
        <label className="mt-4 block space-y-1 text-sm">
          <span className="font-medium text-slate-600">Limit price</span>
          <input
            type="number"
            min="0"
            step="any"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500"
            placeholder="Close price"
          />
          <p className="text-[11px] text-slate-500">Defaults to the current live close price. Leave near market for a marketable limit, or edit for a resting close.</p>
        </label>
        {error ? <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div> : null}
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700">
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {submitting ? "Placing..." : "Place Limit Close"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const hostname = currentHostname();
  const marketingHost = isMarketingHostname(hostname);
  const searchParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const authModeFromUrl = searchParams?.get("mode") === "register" ? "register" : "login";
  const [token, setToken] = useState(localStorage.getItem("sb_token") || "");
  const [me, setMe] = useState(null);
  const [currentPage, setCurrentPage] = useState("trading");
  const [manageAccountOpen, setManageAccountOpen] = useState(false);
  const [liveOrders, setLiveOrders] = useState([]);
  const [liveWatchlist, setLiveWatchlist] = useState([]);
  const [livePrices, setLivePrices] = useState({});
  const [liveScheduledTrades, setLiveScheduledTrades] = useState([]);
  const [symbolPriceDigits, setSymbolPriceDigits] = useState({});
  const [indianMarketOverview, setIndianMarketOverview] = useState({ status: "CLOSED", indices: [], watchlist: [] });
  const [notifications, setNotifications] = useState([]);
  const [adminFlowRuns, setAdminFlowRuns] = useState([]);
  const [notificationFilters, setNotificationFilters] = useState({ query: "", category: "ALL", status: "ALL" });
  const [flashQueue, setFlashQueue] = useState([]);
  const [liveStatus, setLiveStatus] = useState("disconnected");
  const [switchingAccount, setSwitchingAccount] = useState(false);
  const [closeOrder, setCloseOrder] = useState(null);
  const [editOrder, setEditOrder] = useState(null);
  const [actionLoadingId, setActionLoadingId] = useState("");
  const [selectedInstrument, setSelectedInstrument] = useState("");
  const [mobileWatchlistOpen, setMobileWatchlistOpen] = useState(false);
  const [notificationDetailsOpen, setNotificationDetailsOpen] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileLoadingMessage, setProfileLoadingMessage] = useState("Welcome, there 🙂");
  const [sessionName, setSessionName] = useState(localStorage.getItem("sb_session_name") || "");
  const [indianSessionAccount, setIndianSessionAccount] = useState(null);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [backendMessage, setBackendMessage] = useState("We’re checking SignalBridge Cloud availability.");
  const [lastServerStateLogAt, setLastServerStateLogAt] = useState(null);
  const [polledEquity, setPolledEquity] = useState(null);
  const selectedMarket = String(me?.selected_market || "INTERNATIONAL").toUpperCase();
  const isInternationalMarket = selectedMarket === "INTERNATIONAL";
  const isIndianMarket = selectedMarket === "INDIAN";
  const primaryNavIds = useMemo(() => {
    const configured = me?.ui_settings?.header_primary_tabs;
    return Array.isArray(configured) ? configured.map((item) => String(item || "")) : [];
  }, [me?.ui_settings]);
  const internationalAccounts = useMemo(
    () => (me?.accounts || []).filter((account) => String(account.market_type || "INTERNATIONAL").toUpperCase() === "INTERNATIONAL"),
    [me?.accounts]
  );
  const selectedMarketAccounts = useMemo(
    () => (me?.accounts || []).filter((account) => String(account.market_type || "INTERNATIONAL").toUpperCase() === selectedMarket),
    [me?.accounts, selectedMarket]
  );
  const selectedMarketAccountId = isIndianMarket ? me?.selected_indian_account_id : me?.selected_account_id;
  const selectedMarketAccount = useMemo(
    () => selectedMarketAccounts.find((account) => account.id === selectedMarketAccountId) || selectedMarketAccounts[0] || null,
    [selectedMarketAccounts, selectedMarketAccountId]
  );
  const shellNavItems = useMemo(
    () => ([
      { id: "trading", label: "Watchlist", shortLabel: "Watch", icon: List },
      { id: "trap-reversal", label: "FSM Engines", shortLabel: "FSM", icon: Workflow },
      { id: "master-break", label: "Master Break", shortLabel: "MB", icon: Crosshair },
      { id: "scheduled-trade", label: "Scheduled Trade", shortLabel: "Sched", icon: AlarmClock },
      { id: "unmitigated-swings", label: "Unmitigated Swings", shortLabel: "Swings", icon: Layers },
      { id: "positions", label: "Positions", shortLabel: "Pos", icon: Activity },
      { id: "settings", label: "Settings", shortLabel: "Set", icon: Settings },
    ]),
    []
  );

  const reconnectTimer = useRef(null);
  const reconnectAttempts = useRef(0);
  const liveSocketRef = useRef(null);
  const lastLiveDataAtRef = useRef(0);
  const staleWatchdogRef = useRef(null);
  const lastHiddenAtRef = useRef(null);
  const pendingSymbolRef = useRef({});
  const sessionExpiryTimerRef = useRef(null);
  const profileLoaderTimersRef = useRef([]);
  const seenNotificationIdsRef = useRef(new Set());
  const notificationsHydratedRef = useRef(false);
  const authSessionEpochRef = useRef(0);

  const checkBackendAvailability = useCallback(async () => {
    setBackendStatus((current) => (current === "ready" ? "checking-soft" : "checking"));
    const result = await pingBackendHealth();
    if (result.ok) {
      setBackendStatus("ready");
      setBackendMessage("");
      setLastServerStateLogAt(new Date());
      return true;
    }
    setBackendStatus("down");
    setBackendMessage(result.error || "The backend is unavailable right now. Please try again shortly.");
    return false;
  }, []);

  useEffect(() => {
    let active = true;
    const run = async () => {
      const result = await pingBackendHealth();
      if (!active) return;
      if (result.ok) {
        setBackendStatus("ready");
        setBackendMessage("");
        setLastServerStateLogAt(new Date());
      } else {
        setBackendStatus("down");
        setBackendMessage(result.error || "The backend is unavailable right now. Please try again shortly.");
      }
    };
    run();
    const timer = window.setInterval(run, 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const selectedAccountExists = useMemo(() => Boolean(me?.selected_account_id) && isInternationalMarket, [me, isInternationalMarket]);
  const activeAccountSymbolAliases = useMemo(() => {
    const account = (me?.accounts || []).find((item) => item.id === me?.selected_account_id);
    return account?.symbol_aliases || {};
  }, [me]);

  useEffect(() => {
    if (currentPage === "admin" && me && !me.is_admin) {
      setCurrentPage("trading");
    }
  }, [currentPage, me]);

  const notify = (type, message) => {
    setFlashQueue((current) => [...current, { id: Date.now() + Math.random(), type, message }]);
  };

  const clearSession = (message) => {
    stopProfileLoader();
    localStorage.removeItem("sb_token");
    localStorage.removeItem("sb_session_name");
    setToken("");
    setMe(null);
    setLiveOrders([]);
    setLiveWatchlist([]);
    setLivePrices({});
    setLiveScheduledTrades([]);
    setSymbolPriceDigits({});
    setIndianMarketOverview({ status: "CLOSED", indices: [], watchlist: [] });
    setNotifications([]);
    setAdminFlowRuns([]);
    setFlashQueue([]);
    setSelectedInstrument("");
    setSessionName("");
    setLiveStatus("disconnected");
    seenNotificationIdsRef.current = new Set();
    notificationsHydratedRef.current = false;
    if (message) {
      setFlashQueue([{ id: Date.now() + Math.random(), type: "error", message }]);
    }
  };

  const stopProfileLoader = () => {
    profileLoaderTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    profileLoaderTimersRef.current = [];
    setProfileLoading(false);
  };

  const startProfileLoader = ({ accountName = "" } = {}) => {
    const greetingName = sessionName || "there";
    const accountFetchMessage = accountName
      ? `Fetching details of ${accountName}...`
      : "We are loading your profile 🙂";
    stopProfileLoader();
    setProfileLoading(true);
    setProfileLoadingMessage(`Welcome, ${greetingName} 🙂`);
    profileLoaderTimersRef.current = [
      window.setTimeout(() => setProfileLoadingMessage(accountFetchMessage), 2000),
      window.setTimeout(() => setProfileLoadingMessage("Fetching your accounts now ⏳"), 5000),
      window.setTimeout(() => setProfileLoadingMessage("Still fetching things for you... thanks for waiting 🙂"), 10000),
      window.setTimeout(() => setProfileLoadingMessage("Almost there. Please bear with us a bit longer 🙏"), 15000)
    ];
  };

  const loadMe = async (accessToken, options = {}) => {
    const silent = options.silent === true;
    const epoch = authSessionEpochRef.current;
    if (!silent) {
      startProfileLoader(options);
    }
    try {
      const data = await api("/auth/me", "GET", undefined, accessToken);
      if (epoch !== authSessionEpochRef.current) {
        return null;
      }
      setMe(data);
      setSessionName(data.full_name || data.username || "");
      localStorage.setItem("sb_session_name", data.full_name || data.username || "");
      return data;
    } finally {
      if (!silent) {
        stopProfileLoader();
      }
    }
  };

  useEffect(() => {
    if (backendStatus !== "ready") return;
    if (!token) return;
    const epoch = authSessionEpochRef.current;
    loadMe(token).catch(() => {
      if (epoch !== authSessionEpochRef.current) return;
      clearSession("Session expired. Please log in again.");
    });
  }, [token, backendStatus]);

  useEffect(() => {
    if (backendStatus !== "ready" || !token || !isInternationalMarket) return;
    const accountId = selectedMarketAccountId;
    if (!accountId) {
      setPolledEquity(null);
      return undefined;
    }

    let cancelled = false;
    const refreshEquity = async () => {
      try {
        const data = await api(`/accounts/${accountId}/equity`, "GET", undefined, token);
        if (cancelled) return;
        const equity = Number(data?.equity_balance ?? data?.equity);
        if (!Number.isFinite(equity)) return;
        // Keep equity in local header state — do not rewrite me.accounts (that
        // recreates internationalAccounts and resets open settings forms).
        setPolledEquity({
          accountId,
          equity,
          balance: Number.isFinite(Number(data?.balance)) ? Number(data.balance) : null,
          currency: data?.currency || null,
        });
      } catch {
        // Keep last known equity; MT5 may be briefly unavailable.
      }
    };

    refreshEquity();
    const timer = window.setInterval(refreshEquity, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [token, backendStatus, isInternationalMarket, selectedMarketAccountId]);

  useEffect(() => {
    if (sessionExpiryTimerRef.current) {
      window.clearTimeout(sessionExpiryTimerRef.current);
      sessionExpiryTimerRef.current = null;
    }

    if (!token) return undefined;

    const expiryMs = getTokenExpiryMs(token);
    if (!expiryMs) return undefined;

    const remainingMs = expiryMs - Date.now();

    if (remainingMs <= 0) {
      clearSession("Session expired. Please log in again.");
      return undefined;
    }

    sessionExpiryTimerRef.current = window.setTimeout(() => clearSession("Session expired. Please log in again."), remainingMs);

    return () => {
      if (sessionExpiryTimerRef.current) {
        window.clearTimeout(sessionExpiryTimerRef.current);
        sessionExpiryTimerRef.current = null;
      }
    };
  }, [token]);

  useEffect(() => {
    if (backendStatus !== "ready") return undefined;
    if (!token) {
      setLiveStatus("disconnected");
      return undefined;
    }

    let closedByEffect = false;
    let ignoreNextClose = false;
    let socket;

    const clearReconnectTimer = () => {
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
    };

    const closeActiveSocket = () => {
      const activeSocket = liveSocketRef.current;
      if (!activeSocket) return;
      liveSocketRef.current = null;
      ignoreNextClose = true;
      activeSocket.stopHeartbeat?.();
      try {
        if (activeSocket.readyState === WebSocket.OPEN || activeSocket.readyState === WebSocket.CONNECTING) {
          activeSocket.close(4000, "replace");
        }
      } catch {
        // ignore close errors on suspended tabs
      }
    };

    const forceReconnect = () => {
      if (closedByEffect) return;
      clearReconnectTimer();
      closeActiveSocket();
      connect();
    };

    const connect = () => {
      if (closedByEffect) return;
      clearReconnectTimer();
      closeActiveSocket();
      setLiveStatus(reconnectAttempts.current > 0 ? "reconnecting" : "disconnected");
      socket = openLiveSocket(token, (payload) => {
        if (payload.error === "Session expired" || payload.error === "Invalid token" || payload.error === "Missing token") {
          clearSession("Session expired. Please log in again.");
          return;
        }
        if (payload.type === "force_logout") {
          clearSession(payload.reason || "Signed in on another device.");
          return;
        }
        setLastServerStateLogAt(new Date());
        if (liveSnapshotHasFreshPrices(payload)) {
          lastLiveDataAtRef.current = Date.now();
        }
        setLiveOrders(normalizeLiveOrders(payload.orders || []));
        setLiveWatchlist((current) => mergeWatchlistPrices(current, payload.watchlist || []));
        setLivePrices((current) => mergeLivePrices(current, payload.prices || {}));
        if (Array.isArray(payload.scheduled_trades)) {
          setLiveScheduledTrades(payload.scheduled_trades);
        }
        setSymbolPriceDigits((current) => mergeSymbolPriceDigits(current, payload.prices || {}, payload.watchlist || []));
        setIndianMarketOverview(payload.indian_market || { status: "CLOSED", indices: [], watchlist: [] });
        if (payload.notifications) {
          const incomingNotifications = payload.notifications || [];
          if (!notificationsHydratedRef.current) {
            seenNotificationIdsRef.current = new Set(incomingNotifications.map((notification) => notification.id));
            notificationsHydratedRef.current = true;
          } else {
            const newNotifications = incomingNotifications.filter(
              (notification) => !seenNotificationIdsRef.current.has(notification.id)
            );
            if (newNotifications.length) {
              newNotifications
                .slice()
                .reverse()
                .forEach((notification) => {
                  notify(notificationToastType(notification), notification.activity);
                  seenNotificationIdsRef.current.add(notification.id);
                });
            }
          }
          incomingNotifications.forEach((notification) => seenNotificationIdsRef.current.add(notification.id));
          setNotifications(incomingNotifications);
        }
        if (payload.admin?.repository_flow_runs) {
          setAdminFlowRuns(payload.admin.repository_flow_runs || []);
        }
      }, {
        onOpen: () => {
          reconnectAttempts.current = 0;
          lastLiveDataAtRef.current = Date.now();
          setLiveStatus("connected");
          const pendingSubscriptions = pendingSymbolRef.current && typeof pendingSymbolRef.current === "object" ? pendingSymbolRef.current : {};
          const symbols = [...new Set(Object.values(pendingSubscriptions).filter(Boolean))];
          if (symbols.length) {
            socket.send(JSON.stringify({ type: "subscribe_symbols", symbols }));
          }
        },
        onClose: () => {
          if (closedByEffect || ignoreNextClose) {
            ignoreNextClose = false;
            return;
          }
          setLiveStatus("reconnecting");
          reconnectAttempts.current += 1;
          const delay = Math.min(5000, 1000 * reconnectAttempts.current);
          reconnectTimer.current = window.setTimeout(connect, delay);
        },
        onError: () => {
          const activeSocket = liveSocketRef.current;
          if (activeSocket && (activeSocket.readyState === WebSocket.OPEN || activeSocket.readyState === WebSocket.CONNECTING)) {
            return;
          }
          setLiveStatus("reconnecting");
          forceReconnect();
        },
      });
      liveSocketRef.current = socket;
    };

    const resumeLiveFeed = () => {
      if (closedByEffect) return;
      reconnectAttempts.current = 0;
      forceReconnect();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        lastHiddenAtRef.current = Date.now();
        return;
      }
      if (closedByEffect) return;
      const hiddenForMs = lastHiddenAtRef.current ? Date.now() - lastHiddenAtRef.current : 0;
      lastHiddenAtRef.current = null;
      const activeSocket = liveSocketRef.current;
      const staleForMs = Date.now() - lastLiveDataAtRef.current;
      const needsReconnect =
        hiddenForMs >= 2000
        || staleForMs > WS_LIVE_STALE_MS
        || !activeSocket
        || activeSocket.readyState !== WebSocket.OPEN;
      if (needsReconnect) {
        resumeLiveFeed();
        return;
      }
      activeSocket.sendPing?.();
    };

    const handleOnline = () => {
      if (closedByEffect) return;
      resumeLiveFeed();
    };

    const handlePageShow = (event) => {
      if (closedByEffect || !event.persisted) return;
      resumeLiveFeed();
    };

    staleWatchdogRef.current = window.setInterval(() => {
      if (closedByEffect || document.visibilityState !== "visible") return;
      const activeSocket = liveSocketRef.current;
      if (!activeSocket || activeSocket.readyState !== WebSocket.OPEN) return;
      if (Date.now() - lastLiveDataAtRef.current > WS_LIVE_STALE_MS * 1.5) {
        forceReconnect();
      }
    }, 10000);

    connect();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("online", handleOnline);
    window.addEventListener("pageshow", handlePageShow);

    return () => {
      closedByEffect = true;
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("pageshow", handlePageShow);
      if (staleWatchdogRef.current) {
        window.clearInterval(staleWatchdogRef.current);
        staleWatchdogRef.current = null;
      }
      clearReconnectTimer();
      closeActiveSocket();
    };
  }, [token, backendStatus]);

  const subscribeLiveSymbol = useMemo(
    () => (symbol, source = "default") => {
      const normalized = (symbol || "").trim().toUpperCase();
      const subscriptions = pendingSymbolRef.current && typeof pendingSymbolRef.current === "object"
        ? { ...pendingSymbolRef.current }
        : {};
      if (normalized) {
        subscriptions[source] = normalized;
      } else {
        delete subscriptions[source];
      }
      pendingSymbolRef.current = subscriptions;
      const symbols = [...new Set(Object.values(subscriptions).filter(Boolean))];
      const socket = liveSocketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "subscribe_symbols", symbols }));
      }
    },
    []
  );

  const onAuth = (authData) => {
    authSessionEpochRef.current += 1;
    localStorage.setItem("sb_token", authData.access_token);
    localStorage.setItem("sb_session_name", authData.full_name || authData.username || "");
    setSessionName(authData.full_name || authData.username || "");
    setToken(authData.access_token);
  };

  const onLogout = () => {
    clearSession();
  };

  const onPageChange = (nextPage) => {
    const normalizedPage = String(nextPage || "").trim();
    if (!normalizedPage || normalizedPage === currentPage) {
      return;
    }

    setCurrentPage(normalizedPage);
    setMe((current) => {
      if (!current) return current;
      const currentSettings = current.ui_settings && typeof current.ui_settings === "object" ? current.ui_settings : {};
      const currentUsage = currentSettings.page_usage && typeof currentSettings.page_usage === "object" ? currentSettings.page_usage : {};
      const nextUsage = {
        ...currentUsage,
        [normalizedPage]: Number(currentUsage[normalizedPage] || 0) + 1,
      };
      const orderedPages = [
        "trading",
        "positions",
        "trap-reversal",
        "master-break",
        "scheduled-trade",
        "unmitigated-swings",
        "settings",
        "trade-planner",
        ...(current.is_admin ? ["admin"] : []),
      ];
      const nextPrimaryTabs = orderedPages
        .slice()
        .sort((left, right) => {
          const usageDelta = Number(nextUsage[right] || 0) - Number(nextUsage[left] || 0);
          if (usageDelta !== 0) return usageDelta;
          return orderedPages.indexOf(left) - orderedPages.indexOf(right);
        })
        .slice(0, 2);
      return {
        ...current,
        ui_settings: {
          ...currentSettings,
          page_usage: nextUsage,
          header_primary_tabs: nextPrimaryTabs,
        },
      };
    });

    if (token) {
      api("/auth/ui-settings", "POST", { page_id: normalizedPage }, token)
        .then((snapshot) => {
          setMe(snapshot);
        })
        .catch(() => {
          // Keep the optimistic header state even if the background save misses once.
        });
    }
  };

  const onAccountChange = async (accountDbId) => {
    if (!accountDbId || accountDbId === me?.selected_account_id) {
      return;
    }
    setSwitchingAccount(true);
    try {
      const accountName = me?.accounts?.find((account) => account.id === accountDbId)?.account_name || "";
      await api("/accounts/select", "POST", { account_db_id: accountDbId }, token);
      await loadMe(token, { accountName, silent: true });
      notify("success", "Active account updated.");
    } catch (err) {
      notify("error", err.message);
    } finally {
      setSwitchingAccount(false);
    }
  };

  const onMarketChange = async (marketType) => {
    if (!marketType || marketType === selectedMarket) {
      return;
    }
    setSwitchingAccount(true);
    try {
      await api("/market/select", "POST", { market_type: marketType }, token);
      await loadMe(token, { silent: true });
      notify("success", marketType === "INDIAN" ? "Indian market selected." : "International market selected.");
    } catch (err) {
      notify("error", err.message);
    } finally {
      setSwitchingAccount(false);
    }
  };

  const onAddAccount = async (accountPayload) => {
    const account = await api("/accounts", "POST", accountPayload, token);
    const snapshot = await loadMe(token, { silent: true });
    if (String(accountPayload.market_type || "").toUpperCase() === "INDIAN") {
      const nextAccount = (snapshot?.accounts || []).find((item) => item.id === account.id) || account;
      setIndianSessionAccount(nextAccount);
    }
    notify("success", "Broker account added.");
  };

  const onDeleteAccount = async (accountId) => {
    try {
      await api(`/accounts/${accountId}`, "DELETE", undefined, token);
      if (indianSessionAccount?.id === accountId) {
        setIndianSessionAccount(null);
      }
      await loadMe(token, { silent: true });
      notify("success", "Broker account deleted.");
    } catch (err) {
      notify("error", err.message || "Unable to delete broker account.");
      throw err;
    }
  };

  const onRequestIndianOtp = async (accountId) => {
    await api(`/indian/accounts/${accountId}/request-otp`, "POST", undefined, token);
    await loadMe(token, { silent: true });
    notify("success", "OTP requested from Mstock.");
  };

  const onVerifyIndianOtp = async (accountId, otp) => {
    await api(`/indian/accounts/${accountId}/verify-otp`, "POST", { otp }, token);
    const snapshot = await loadMe(token, { silent: true });
    const refreshed = (snapshot?.accounts || []).find((item) => item.id === accountId) || null;
    setIndianSessionAccount(
      String(refreshed?.session_status || "").toUpperCase() === "CONNECTED" ? null : refreshed
    );
    notify("success", "Indian broker session connected.");
  };

  const onClosePosition = async (orderId, quantity, options = {}) => {
    setActionLoadingId(orderId);
    try {
      const orderType = String(options.order_type || "MARKET").toUpperCase();
      const payload = {
        quantity,
        order_type: orderType,
      };
      if (orderType === "LIMIT" && options.price != null) {
        payload.price = Number(options.price);
      }
      await api(`/orders/${orderId}/close`, "POST", payload, token);
      setCloseOrder(null);
      notify("success", orderType === "LIMIT" ? "Limit close placed." : "Position closed.");
    } catch (err) {
      notify("error", err.message);
      throw err;
    } finally {
      setActionLoadingId("");
    }
  };

  const onModifyPendingOrder = async (orderId, payload) => {
    setActionLoadingId(orderId);
    try {
      await api(`/orders/${orderId}/modify`, "POST", payload, token);
      setEditOrder(null);
      notify("success", "Pending order updated.");
    } catch (err) {
      notify("error", err.message);
      throw err;
    } finally {
      setActionLoadingId("");
    }
  };

  const onFullClosePosition = async (row) => {
    const quantity = Number(row.position_quantity || row.quantity || 0);
    if (!quantity) {
      notify("error", "No open quantity available for full exit.");
      return;
    }

    setActionLoadingId(row.id);
    try {
      await api(`/orders/${row.id}/close`, "POST", { quantity, order_type: "MARKET" }, token);
      notify("success", "Position closed.");
    } catch (err) {
      notify("error", err.message);
    } finally {
      setActionLoadingId("");
    }
  };

  const onOpenPartialClose = (row, defaultPrice = null) => {
    const price = Number(defaultPrice);
    setCloseOrder({
      ...row,
      defaultClosePrice: Number.isFinite(price) && price > 0 ? price : undefined,
    });
  };

  const onCancelPendingOrder = async (row) => {
    setActionLoadingId(row.id);
    try {
      await api(`/orders/${row.id}/cancel`, "POST", undefined, token);
    } catch (err) {
      notify("error", err.message);
    } finally {
      setActionLoadingId("");
    }
  };

  const onAccountRiskSaved = (updatedAccount) => {
    setMe((current) => {
      if (!current) return current;
      return {
        ...current,
        accounts: current.accounts.map((account) => (account.id === updatedAccount.id ? updatedAccount : account))
      };
    });
  };

  const onAccountUpdated = onAccountRiskSaved;

  const onSymbolDigits = (symbol, digits) => {
    const key = String(symbol || "").toUpperCase().trim();
    if (!key || digits === null || digits === undefined) return;
    setSymbolPriceDigits((current) => ({ ...current, [key]: Number(digits) }));
  };

  const headerRunningPnl = useMemo(
    () => (liveOrders || [])
      .filter((row) => ["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].includes(String(row.status || "").toUpperCase()))
      .reduce((sum, row) => {
        const value = Number(row.unrealized_pl ?? 0);
        return sum + (Number.isFinite(value) ? value : 0);
      }, 0),
    [liveOrders]
  );

  if (backendStatus === "checking") {
    return (
      <MaintenancePage
        checking
        message="Checking whether SignalBridge Cloud is available before opening the workspace."
        onRetry={checkBackendAvailability}
      />
    );
  }

  if (backendStatus === "down") {
    return <MaintenancePage message={backendMessage} onRetry={checkBackendAvailability} />;
  }

  if (!token) {
    if (marketingHost) {
      return <MarketingLandingPage />;
    }
    return <Auth onAuth={onAuth} initialMode={authModeFromUrl} />;
  }

  return (
    <AppShell
      currentPage={currentPage}
      onPageChange={onPageChange}
      navItems={shellNavItems}
      serverConnected={backendStatus === "ready" && liveStatus === "connected"}
      lastServerStateLogAt={lastServerStateLogAt}
      totalEquity={
        isInternationalMarket
          ? (polledEquity && polledEquity.accountId === selectedMarketAccountId
            ? polledEquity.equity
            : null)
            ?? selectedMarketAccount?.equity_balance
            ?? selectedMarketAccount?.balance
          : selectedMarketAccount?.available_margin ?? selectedMarketAccount?.equity_balance
      }
      selectedAccountLabel={selectedMarketAccount?.account_name || selectedMarketAccount?.account_id || ""}
      notificationsCount={notifications.length}
      onOpenNotifications={() => setNotificationDetailsOpen(true)}
    >
      <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
        <FlashMessages
          flashes={flashQueue}
          onDismiss={(flashId) => setFlashQueue((current) => current.filter((flash) => flash.id !== flashId))}
        />
        <ProfileLoader open={profileLoading} message={profileLoadingMessage} />
        {currentPage === "trading" ? (
          isIndianMarket ? (
            <IndianMarketWorkspace
              me={me}
              token={token}
              onOpenAddAccount={() => setManageAccountOpen(true)}
              onOpenConnectSession={setIndianSessionAccount}
              indianMarketOverview={indianMarketOverview}
              mobileWatchlistOpen={mobileWatchlistOpen}
              setMobileWatchlistOpen={setMobileWatchlistOpen}
              onNotify={notify}
            />
          ) : (
            <main className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
              <InternationalMarketWorkspace
                mobileWatchlistOpen={mobileWatchlistOpen}
                setMobileWatchlistOpen={setMobileWatchlistOpen}
                WatchlistComponent={Watchlist}
                selectedAccountExists={selectedAccountExists}
                liveWatchlist={liveWatchlist}
                notify={notify}
                selectedInstrument={selectedInstrument}
                setSelectedInstrument={setSelectedInstrument}
                liveStatus={liveStatus}
                me={me}
                internationalAccounts={internationalAccounts}
                activeAccountSymbolAliases={activeAccountSymbolAliases}
                symbolPriceDigits={symbolPriceDigits}
                onSymbolDigits={onSymbolDigits}
                OrderScreenComponent={OrderScreen}
                token={token}
                livePrices={livePrices}
                liveOrders={liveOrders}
                subscribeLiveSymbol={subscribeLiveSymbol}
                onAccountRiskSaved={onAccountRiskSaved}
                onFullClosePosition={onFullClosePosition}
                onOpenPartialClose={onOpenPartialClose}
                actionLoadingId={actionLoadingId}
                onMeUpdated={setMe}
              />
            </main>
          )
        ) : currentPage === "positions" ? (
          isIndianMarket ? (
            <main className="min-h-0 flex-1 overflow-auto">
              <section className="terminal-panel">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Positions</p>
                <h2 className="mt-2 text-2xl font-bold text-[color:var(--text-strong)]">International workflow only for now</h2>
                <p className="mt-3 max-w-2xl text-sm text-[color:var(--text-muted)]">
                  Pending orders and MT5 positions are available for international accounts. Indian broker positions will stay separated when added.
                </p>
              </section>
            </main>
          ) : (
            <main className="min-h-0 flex-1 overflow-hidden">
              <PendingOrdersPositionsPanel
                TrackerComponent={Tracker}
                liveOrders={liveOrders}
                setCloseOrder={setCloseOrder}
                setEditOrder={setEditOrder}
                onFullClosePosition={onFullClosePosition}
                onCancelPendingOrder={onCancelPendingOrder}
                actionLoadingId={actionLoadingId}
                token={token}
                accounts={internationalAccounts}
                activeAccountId={me?.selected_account_id || ""}
                livePrices={livePrices}
                onNotify={(payload) => notify(payload?.type || "info", payload?.message || "")}
              />
            </main>
          )
        ) : currentPage === "trade-planner" ? (
          isIndianMarket ? (
            <main className="min-h-0 flex-1 overflow-auto">
              <section className="terminal-panel">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Trade Planner</p>
                <h2 className="mt-2 text-2xl font-bold text-[color:var(--text-strong)]">International workflow only for now</h2>
                <p className="mt-3 max-w-2xl text-sm text-[color:var(--text-muted)]">
                  Trade Planner continues to use the existing international market workflow. Indian broker accounts stay fully separated, so
                  this page will stay unavailable until the Indian planning flow is implemented.
                </p>
              </section>
            </main>
          ) : (
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
                <Watchlist
                  token={token}
                  selectedAccountExists={selectedAccountExists}
                  selectedAccountId={me?.selected_account_id || ""}
                  symbolAliases={activeAccountSymbolAliases}
                  onSymbolDigits={onSymbolDigits}
                  items={liveWatchlist}
                  onNotify={notify}
                  selectedInstrument={selectedInstrument}
                  onSelectInstrument={setSelectedInstrument}
                  showHeader
                />
              </aside>
              <TradePlannerPage
                token={token}
                selectedAccountExists={selectedAccountExists}
                accounts={internationalAccounts}
                activeAccountId={me?.selected_account_id || ""}
                subscribeLiveSymbol={subscribeLiveSymbol}
                liveOrders={liveOrders}
                liveWatchlist={liveWatchlist}
                livePrices={livePrices}
                selectedInstrument={selectedInstrument}
                onSelectInstrument={setSelectedInstrument}
                onNotify={notify}
              />
            </div>
          )
        ) : currentPage === "trap-reversal" ? (
          isIndianMarket ? (
            <main className="min-h-0 flex-1 overflow-auto">
              <section className="terminal-panel">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Trap Reversal</p>
                <h2 className="mt-2 text-2xl font-bold text-[color:var(--text-strong)]">International MT5 only</h2>
                <p className="mt-3 max-w-2xl text-sm text-[color:var(--text-muted)]">
                  Trap reversal runs only on international MT5 accounts with broker candle history and live tick access.
                </p>
              </section>
            </main>
          ) : (
            <main className="min-h-0 flex-1 overflow-auto">
              <TrapReversalDashboard
                token={token}
                selectedAccountExists={selectedAccountExists}
                onNotify={notify}
              />
            </main>
          )
        ) : currentPage === "master-break" ? (
          isIndianMarket ? (
            <main className="min-h-0 flex-1 overflow-auto">
              <section className="terminal-panel">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Master Break</p>
                <h2 className="mt-2 text-2xl font-bold text-[color:var(--text-strong)]">International MT5 only</h2>
                <p className="mt-3 max-w-2xl text-sm text-[color:var(--text-muted)]">
                  Master Break runs only on international MT5 accounts for XAUUSD/GOLD with broker candle history and live ticks.
                </p>
              </section>
            </main>
          ) : (
            <main className="min-h-0 flex-1 overflow-auto">
              <MasterBreakDashboard
                token={token}
                selectedAccountExists={selectedAccountExists}
                onNotify={notify}
              />
            </main>
          )
        ) : currentPage === "scheduled-trade" ? (
          isIndianMarket ? (
            <main className="min-h-0 flex-1 overflow-auto">
              <section className="terminal-panel">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Scheduled Trade</p>
                <h2 className="mt-2 text-2xl font-bold text-[color:var(--text-strong)]">International MT5 only</h2>
                <p className="mt-3 max-w-2xl text-sm text-[color:var(--text-muted)]">
                  Scheduled Break Trade watches an M1/M5/M15 close past your level, then arms on the next valid red/green candle before placing an SL.
                </p>
              </section>
            </main>
          ) : (
            <main className="min-h-0 flex-1 overflow-auto p-4">
              <section className="mb-4">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Scheduled Trade</p>
                <h2 className="mt-2 text-2xl font-bold text-[color:var(--text-strong)]">Break level → signal candle → SL</h2>
                <p className="mt-2 max-w-3xl text-sm text-[color:var(--text-muted)]">
                  Set a price and timeframe on the selected international account. Level above live mid is short; below is long.
                  After a close past the level, the next valid red (short) or green (long) candle places the stop order.
                </p>
              </section>
              <ScheduledTradePanel
                token={token}
                accounts={internationalAccounts}
                activeAccountId={me?.selected_account_id || ""}
                livePrices={livePrices}
                liveScheduledTrades={liveScheduledTrades}
                subscribeLiveSymbol={subscribeLiveSymbol}
                onNotify={notify}
              />
            </main>
          )
        ) : currentPage === "unmitigated-swings" ? (
          isIndianMarket ? (
            <main className="min-h-0 flex-1 overflow-auto">
              <section className="terminal-panel">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Unmitigated Swings</p>
                <h2 className="mt-2 text-2xl font-bold text-[color:var(--text-strong)]">International MT5 only</h2>
                <p className="mt-3 max-w-2xl text-sm text-[color:var(--text-muted)]">
                  Structure swings analysis and M1 break automation require an international MT5 account.
                </p>
              </section>
            </main>
          ) : (
            <main className="min-h-0 flex-1 overflow-auto p-4">
              <section className="mb-4">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Unmitigated Swings</p>
                <h2 className="mt-2 text-2xl font-bold text-[color:var(--text-strong)]">Structure → M1 break automation</h2>
                <p className="mt-2 max-w-3xl text-sm text-[color:var(--text-muted)]">
                  Analyze H4/H1/M15 unmitigated highs and lows, then Execute Automation to arm one-shot M1 Scheduled Break
                  trades. Taken-out levels mark Mitigated. Target is 4R or the prior structure candle extreme, whichever is farther.
                </p>
              </section>
              <UnmitigatedSwingsPanel
                token={token}
                accounts={internationalAccounts}
                activeAccountId={me?.selected_account_id || ""}
                liveScheduledTrades={liveScheduledTrades}
                onNotify={notify}
              />
            </main>
          )
        ) : currentPage === "settings" ? (
          <main className="min-h-0 flex-1 overflow-hidden">
            <SettingsTerminalPage
              selectedMarket={selectedMarket}
              onMarketChange={onMarketChange}
              selectedAccountId={selectedMarketAccountId}
              marketAccounts={selectedMarketAccounts}
              onAccountChange={onAccountChange}
              switchingAccount={switchingAccount}
              onOpenManageAccount={() => setManageAccountOpen(true)}
              onOpenNotifications={() => setNotificationDetailsOpen(true)}
              onOpenPlanner={() => setCurrentPage("trade-planner")}
              onOpenAdmin={() => setCurrentPage("admin")}
              onLogout={onLogout}
              isAdmin={Boolean(me?.is_admin)}
            />
          </main>
        ) : currentPage === "admin" ? (
          <main className="min-h-0 flex-1 overflow-auto">
            <AdminConsolePage token={token} me={me} onNotify={notify} adminFlowRuns={adminFlowRuns} />
          </main>
        ) : (
          <main className="min-h-0 flex-1 overflow-auto" />
        )}
      </div>
      <NotificationDetailsModal
        open={notificationDetailsOpen}
        notifications={notifications}
        filters={notificationFilters}
        onFiltersChange={setNotificationFilters}
        onClose={() => setNotificationDetailsOpen(false)}
      />
      <ManageAccountModal
        open={manageAccountOpen}
        token={token}
        accounts={me?.accounts || []}
        selectedMarket={selectedMarket}
        selectedAccountId={me?.selected_account_id || ""}
        switchingAccount={switchingAccount}
        onClose={() => setManageAccountOpen(false)}
        onSubmitAdd={onAddAccount}
        onDeleteAccount={onDeleteAccount}
        onSelectAccount={onAccountChange}
        onAccountUpdated={onAccountUpdated}
      />
      <IndianSessionModal
        open={Boolean(indianSessionAccount)}
        accountName={indianSessionAccount?.account_name || ""}
        onClose={() => setIndianSessionAccount(null)}
        onRequestOtp={() => onRequestIndianOtp(indianSessionAccount.id)}
        onVerifyOtp={(otp) => onVerifyIndianOtp(indianSessionAccount.id, otp)}
      />
      <ClosePositionModal
        order={closeOrder}
        livePrices={livePrices}
        onClose={() => setCloseOrder(null)}
        onSubmit={onClosePosition}
      />
      <EditPendingOrderModal order={editOrder} onClose={() => setEditOrder(null)} onSubmit={onModifyPendingOrder} token={token} />
    </AppShell>
  );
}
