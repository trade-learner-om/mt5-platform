export function livePriceKey(symbol) {
  return String(symbol || "").toUpperCase().trim().replace(/\//g, "").replace(/-/g, "");
}

export function lookupLiveTick(livePrices = {}, symbol) {
  const key = livePriceKey(symbol);
  if (!key) return {};
  return livePrices?.[key] || {};
}

export function livePriceFromTick(tick) {
  if (!tick || typeof tick !== "object") return null;
  if (typeof tick.price === "number" && Number.isFinite(tick.price)) return tick.price;
  if (typeof tick.bid === "number" && typeof tick.ask === "number") return (tick.bid + tick.ask) / 2;
  return null;
}

export function clampDigits(digits, fallback = 5) {
  const parsed = Number(digits);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(0, Math.min(Math.trunc(parsed), 10));
}

export function roundPriceToDigits(value, digits) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return value;
  const precision = clampDigits(digits, 5);
  return Number(numeric.toFixed(precision));
}

export function priceStepForDigits(digits) {
  const precision = clampDigits(digits, 5);
  if (precision <= 0) return "1";
  return (1 / 10 ** precision).toFixed(precision);
}

export function decimalPlaces(value) {
  if (value === null || value === undefined) return 0;
  const text = typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(10).replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "")
    : String(value);
  if (text.includes("e-")) {
    const [, exponent] = text.split("e-");
    return Number(exponent) || 0;
  }
  const parts = text.split(".");
  return parts[1]?.length || 0;
}

export function formatPriceWithDigits(value, digits, relatedValues = [], minimumPrecision = 0) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value !== "number" || Number.isNaN(value)) return String(value);

  const brokerDigits = digits === null || digits === undefined ? null : clampDigits(digits, 5);
  const precision = brokerDigits !== null
    ? brokerDigits
    : Math.min(Math.max(minimumPrecision, decimalPlaces(value), ...(relatedValues || []).map(decimalPlaces)), 10);
  const rounded = Number(value.toFixed(precision));
  return precision > 0 ? rounded.toFixed(precision) : String(Math.round(rounded));
}

export function resolveSymbolPriceDigits(symbol, livePrices = {}, symbolPriceDigits = {}) {
  const key = livePriceKey(symbol);
  if (!key) return null;
  const tickDigits = livePrices?.[key]?.price_digits;
  if (tickDigits !== null && tickDigits !== undefined) return clampDigits(tickDigits, 5);
  const cached = symbolPriceDigits?.[key];
  if (cached !== null && cached !== undefined) return clampDigits(cached, 5);
  return null;
}

export function inferSymbolPriceDigits(symbol) {
  const key = livePriceKey(symbol);
  if (!key) return 5;
  if (/XAU|XAG|GOLD|SILVER/i.test(key)) return 2;
  if (key.includes("JPY")) return 3;
  return 5;
}

export function resolveDisplayPriceDigits(symbol, livePrices = {}, symbolPriceDigits = {}) {
  return resolveSymbolPriceDigits(symbol, livePrices, symbolPriceDigits) ?? inferSymbolPriceDigits(symbol);
}
