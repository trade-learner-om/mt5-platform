import { useEffect, useMemo, useState } from "react";

import ActivePositions from "./ActivePositions";
import FSMCommandCenter from "./FSMCommandCenter";
import LiveWatchlist from "./LiveWatchlist";
import { resolveSymbolPriceDigits } from "../../utils/pricePrecision";

const POSITIONS_HEIGHT_KEY = "sb_active_positions_height";
const DEFAULT_POSITIONS_HEIGHT = 192;
const MIN_POSITIONS_HEIGHT = 120;
const MAX_POSITIONS_HEIGHT = 560;

function loadPositionsHeight() {
  try {
    const value = Number(localStorage.getItem(POSITIONS_HEIGHT_KEY));
    if (Number.isFinite(value) && value >= MIN_POSITIONS_HEIGHT && value <= MAX_POSITIONS_HEIGHT) {
      return value;
    }
  } catch {
    // ignore storage errors
  }
  return DEFAULT_POSITIONS_HEIGHT;
}

function normalizePositionRows(liveOrders = [], livePrices = {}, symbolPriceDigits = {}) {
  return (liveOrders || [])
    .filter((row) => ["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].includes(String(row.status || "").toUpperCase()))
    .map((row) => {
      const side = String(row.side || "").toUpperCase();
      const symbol = row.symbol;
      const priceQuote = livePrices?.[String(symbol || "").toUpperCase()] || livePrices?.[symbol] || {};
      const bid = Number(priceQuote.bid ?? priceQuote.price);
      const ask = Number(priceQuote.ask ?? priceQuote.price);
      const closePrice = side === "SELL"
        ? (Number.isFinite(ask) ? ask : Number(priceQuote.price))
        : (Number.isFinite(bid) ? bid : Number(priceQuote.price));
      return {
        id: row.id,
        symbol,
        side,
        type: side === "SELL" ? "Short" : "Long",
        size: Number(row.position_quantity ?? row.quantity ?? 0).toFixed(2),
        positionQuantity: Number(row.position_quantity ?? row.quantity ?? 0),
        openPrice: row.entry,
        pnl: Number(row.unrealized_pl ?? 0),
        priceDigits: resolveSymbolPriceDigits(row.symbol, livePrices, symbolPriceDigits),
        currentPrice: Number.isFinite(closePrice) ? closePrice : null,
        raw: row,
      };
    });
}

export default function TerminalDashboard({
  token,
  selectedAccountExists,
  selectedAccountId = "",
  liveWatchlist = [],
  liveOrders = [],
  selectedInstrument,
  onSelectInstrument,
  onNotify,
  livePrices = {},
  symbolPriceDigits = {},
  OrderScreenComponent,
  accounts = [],
  activeAccountId = "",
  onSymbolDigits,
  subscribeLiveSymbol,
  onAccountRiskSaved,
  me,
  onMeUpdated,
  onFullClosePosition,
  onOpenPartialClose,
  actionLoadingId = "",
}) {
  const [positionsHeight, setPositionsHeight] = useState(loadPositionsHeight);

  useEffect(() => {
    try {
      localStorage.setItem(POSITIONS_HEIGHT_KEY, String(positionsHeight));
    } catch {
      // ignore storage errors
    }
  }, [positionsHeight]);

  const positionRows = useMemo(
    () => normalizePositionRows(liveOrders, livePrices, symbolPriceDigits),
    [liveOrders, livePrices, symbolPriceDigits]
  );

  const watchlistRows = useMemo(
    () => (liveWatchlist || []).filter((item) => item?.symbol),
    [liveWatchlist]
  );

  const onPositionsResizePointerDown = (event) => {
    if (event.button != null && event.button !== 0) return;
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = positionsHeight;

    const onMove = (moveEvent) => {
      const delta = startY - moveEvent.clientY;
      const next = Math.min(
        MAX_POSITIONS_HEIGHT,
        Math.max(MIN_POSITIONS_HEIGHT, startHeight + delta)
      );
      setPositionsHeight(next);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.style.removeProperty("cursor");
      document.body.style.removeProperty("user-select");
    };

    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,8fr)] xl:grid-rows-[minmax(0,1fr)_auto]">
      <div className="min-h-0 xl:row-span-2">
        <LiveWatchlist
          rows={watchlistRows}
          selectedInstrument={selectedInstrument}
          onSelectInstrument={onSelectInstrument}
          token={token}
          selectedAccountExists={selectedAccountExists}
          selectedAccountId={selectedAccountId || activeAccountId}
          onNotify={onNotify}
          onSymbolDigits={onSymbolDigits}
        />
      </div>

      <div className="grid min-h-0 gap-3 xl:grid-cols-[minmax(0,5fr)_minmax(0,3fr)]">
        <FSMCommandCenter
          token={token}
          selectedAccountExists={selectedAccountExists}
          onNotify={onNotify}
          livePrices={livePrices}
          symbolPriceDigits={symbolPriceDigits}
          selectedInstrument={selectedInstrument}
        />
        {OrderScreenComponent ? (
          <OrderScreenComponent
            token={token}
            accounts={accounts}
            activeAccountId={activeAccountId}
            selectedAccountExists={selectedAccountExists}
            onNotify={onNotify}
            livePrices={livePrices}
            symbolPriceDigits={symbolPriceDigits}
            onSymbolDigits={onSymbolDigits}
            subscribeLiveSymbol={subscribeLiveSymbol}
            selectedInstrument={selectedInstrument}
            onAccountRiskSaved={onAccountRiskSaved}
            me={me}
            onMeUpdated={onMeUpdated}
          />
        ) : null}
      </div>

      <div className="relative min-h-0" style={{ height: positionsHeight }}>
        <div
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize active positions"
          aria-valuemin={MIN_POSITIONS_HEIGHT}
          aria-valuemax={MAX_POSITIONS_HEIGHT}
          aria-valuenow={positionsHeight}
          tabIndex={0}
          onPointerDown={onPositionsResizePointerDown}
          onKeyDown={(event) => {
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setPositionsHeight((current) => Math.min(MAX_POSITIONS_HEIGHT, current + 16));
            } else if (event.key === "ArrowDown") {
              event.preventDefault();
              setPositionsHeight((current) => Math.max(MIN_POSITIONS_HEIGHT, current - 16));
            }
          }}
          className="absolute -top-2 left-0 right-0 z-10 flex h-4 cursor-row-resize items-center justify-center"
        >
          <span className="h-1 w-12 rounded-full bg-slate-300 transition hover:bg-indigo-400 dark:bg-slate-600 dark:hover:bg-indigo-500" />
        </div>
        <div className="h-full min-h-0">
          <ActivePositions
            rows={positionRows}
            actionLoadingId={actionLoadingId}
            onFullClose={onFullClosePosition}
            onPartialClose={onOpenPartialClose}
          />
        </div>
      </div>
    </div>
  );
}
