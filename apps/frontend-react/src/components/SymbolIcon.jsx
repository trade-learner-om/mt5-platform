import flagAu from "flag-icons/flags/4x3/au.svg?url";
import flagCa from "flag-icons/flags/4x3/ca.svg?url";
import flagCh from "flag-icons/flags/4x3/ch.svg?url";
import flagCn from "flag-icons/flags/4x3/cn.svg?url";
import flagCz from "flag-icons/flags/4x3/cz.svg?url";
import flagDk from "flag-icons/flags/4x3/dk.svg?url";
import flagEu from "flag-icons/flags/4x3/eu.svg?url";
import flagGb from "flag-icons/flags/4x3/gb.svg?url";
import flagHk from "flag-icons/flags/4x3/hk.svg?url";
import flagHu from "flag-icons/flags/4x3/hu.svg?url";
import flagJp from "flag-icons/flags/4x3/jp.svg?url";
import flagMx from "flag-icons/flags/4x3/mx.svg?url";
import flagNo from "flag-icons/flags/4x3/no.svg?url";
import flagNz from "flag-icons/flags/4x3/nz.svg?url";
import flagPl from "flag-icons/flags/4x3/pl.svg?url";
import flagSe from "flag-icons/flags/4x3/se.svg?url";
import flagSg from "flag-icons/flags/4x3/sg.svg?url";
import flagTr from "flag-icons/flags/4x3/tr.svg?url";
import flagUs from "flag-icons/flags/4x3/us.svg?url";
import flagZa from "flag-icons/flags/4x3/za.svg?url";

const FLAG_ASSETS = {
  AU: flagAu,
  CA: flagCa,
  CH: flagCh,
  CN: flagCn,
  CZ: flagCz,
  DK: flagDk,
  EU: flagEu,
  GB: flagGb,
  HK: flagHk,
  HU: flagHu,
  JP: flagJp,
  MX: flagMx,
  NO: flagNo,
  NZ: flagNz,
  PL: flagPl,
  SE: flagSe,
  SG: flagSg,
  TR: flagTr,
  US: flagUs,
  ZA: flagZa,
};

const CURRENCY_FLAGS = {
  USD: "US",
  EUR: "EU",
  GBP: "GB",
  JPY: "JP",
  CHF: "CH",
  AUD: "AU",
  CAD: "CA",
  NZD: "NZ",
  SEK: "SE",
  NOK: "NO",
  DKK: "DK",
  SGD: "SG",
  HKD: "HK",
  CNH: "CN",
  CNY: "CN",
  MXN: "MX",
  ZAR: "ZA",
  TRY: "TR",
  PLN: "PL",
  CZK: "CZ",
  HUF: "HU",
};

const SIZE_CLASSES = {
  sm: { wrapper: "h-6 w-6" },
  md: { wrapper: "h-8 w-8" },
  lg: { wrapper: "h-10 w-10" },
};

function normalizeSymbol(symbol) {
  return String(symbol || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function parseCurrencyPair(symbol) {
  const normalized = normalizeSymbol(symbol);
  if (normalized.length < 6) return null;
  const base = normalized.slice(0, 3);
  const quote = normalized.slice(3, 6);
  const baseCountry = CURRENCY_FLAGS[base];
  const quoteCountry = CURRENCY_FLAGS[quote];
  const baseFlag = FLAG_ASSETS[baseCountry];
  const quoteFlag = FLAG_ASSETS[quoteCountry];
  if (!baseFlag || !quoteFlag) return null;
  return { base, quote, baseFlag, quoteFlag };
}

function instrumentMeta(symbol) {
  const upper = normalizeSymbol(symbol);
  if (upper.startsWith("XAU")) return { label: "AU", tone: "bg-amber-100 text-amber-700 ring-amber-200" };
  if (upper.startsWith("XAG")) return { label: "AG", tone: "bg-slate-200 text-slate-700 ring-slate-300" };
  if (upper.startsWith("BTC")) return { label: "BTC", tone: "bg-orange-100 text-orange-700 ring-orange-200" };
  if (upper.startsWith("ETH")) return { label: "ETH", tone: "bg-violet-100 text-violet-700 ring-violet-200" };
  if (/(US30|US500|NAS100|SPX|DJI|GER40|UK100|JP225)/.test(upper)) {
    return { label: "IDX", tone: "bg-sky-100 text-sky-700 ring-sky-200" };
  }
  if (/(NIFTY|BANKNIFTY|SENSEX|FINNIFTY|MIDCPNIFTY)/.test(upper)) {
    return { label: "IN", tone: "bg-orange-100 text-orange-700 ring-orange-200" };
  }
  return { label: (upper || "--").slice(0, 3), tone: "bg-indigo-100 text-indigo-700 ring-indigo-200" };
}

export default function SymbolIcon({ symbol, size = "md", className = "" }) {
  const pair = parseCurrencyPair(symbol);
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;

  if (pair) {
    return (
      <span className={`inline-flex ${sizeClass.wrapper} shrink-0 overflow-hidden rounded-full border border-white/80 bg-slate-100 shadow-sm ring-1 ring-slate-200 ${className}`} title={`${pair.base}/${pair.quote}`}>
        <span className="flex h-full w-full flex-col leading-none">
          <span className="flex h-1/2 items-center justify-center overflow-hidden bg-slate-100">
            <img src={pair.baseFlag} alt={pair.base} className="h-full w-full object-cover" draggable="false" />
          </span>
          <span className="flex h-1/2 items-center justify-center overflow-hidden bg-slate-100">
            <img src={pair.quoteFlag} alt={pair.quote} className="h-full w-full object-cover" draggable="false" />
          </span>
        </span>
      </span>
    );
  }

  const meta = instrumentMeta(symbol);
  return (
    <span className={`inline-flex ${sizeClass.wrapper} shrink-0 items-center justify-center rounded-full text-[0.62em] font-black leading-none ring-1 ${meta.tone} ${className}`} title={String(symbol || "")}>
      {meta.label}
    </span>
  );
}
