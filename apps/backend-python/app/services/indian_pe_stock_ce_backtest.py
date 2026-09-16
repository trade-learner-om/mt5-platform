"""PE → Stock → CE monthly cycle backtest (Indian / mStock)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from .indian_fno_contracts import (
    lot_size_for,
    monthly_expiries_on_or_after,
    parse_expiry_date,
    pick_equity,
    pick_monthly_ce,
    pick_monthly_option,
    pick_monthly_pe,
)

STATE_FLAT = "FLAT"
STATE_SHORT_PE = "SHORT_PE"
STATE_LONG_STOCK_SHORT_CE = "LONG_STOCK_SHORT_CE"


CandleLoader = Callable[[dict, str, str], list[dict]]


def _parse_day(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")[:19]).date()
    except ValueError:
        return None


def _index_candles_by_day(candles: list[dict]) -> dict[date, dict]:
    indexed: dict[date, dict] = {}
    for candle in candles:
        day = _parse_day(candle.get("time"))
        if day is None:
            continue
        indexed[day] = candle
    return indexed


def _fill_price(candle: Optional[dict]) -> Optional[float]:
    if not candle:
        return None
    close = candle.get("close")
    if close is not None:
        try:
            return float(close)
        except (TypeError, ValueError):
            pass
    try:
        high = float(candle.get("high") or 0)
        low = float(candle.get("low") or 0)
        if high > 0 and low > 0:
            return (high + low) / 2.0
    except (TypeError, ValueError):
        return None
    return None


@dataclass
class PeCyclePosition:
    pe: Optional[dict] = None
    pe_entry_premium: Optional[float] = None
    pe_qty: int = 0
    stock: Optional[dict] = None
    stock_entry: Optional[float] = None
    stock_qty: int = 0
    ce: Optional[dict] = None
    ce_entry_premium: Optional[float] = None
    ce_qty: int = 0
    ce_expiry: Optional[date] = None


@dataclass
class PeCycleEngine:
    catalog: list[dict]
    underlying: str
    spot_instrument: dict
    load_candles: CandleLoader
    state: str = STATE_FLAT
    position: PeCyclePosition = field(default_factory=PeCyclePosition)
    events: list[dict] = field(default_factory=list)
    cumulative_pnl: float = 0.0
    spot_by_day: dict[date, dict] = field(default_factory=dict)
    option_cache: dict[str, dict[date, dict]] = field(default_factory=dict)

    def _append_event(self, event_type: str, day: date, message: str, **extra: Any) -> None:
        pnl_update = float(extra.pop("pnl_update", 0.0) or 0.0)
        self.cumulative_pnl = round(self.cumulative_pnl + pnl_update, 2)
        self.events.append(
            {
                "event_type": event_type,
                "event_time": day.isoformat(),
                "message": message,
                "pnl_update": pnl_update,
                "cumulative_pnl": self.cumulative_pnl,
                "state": self.state,
                **extra,
            }
        )

    def _option_day_map(self, instrument: dict, from_date: str, to_date: str) -> dict[date, dict]:
        token = str(instrument.get("instrument_token"))
        cache_key = f"{token}:{from_date}:{to_date}"
        if cache_key not in self.option_cache:
            candles = self.load_candles(instrument, from_date, to_date)
            self.option_cache[cache_key] = _index_candles_by_day(candles)
        return self.option_cache[cache_key]

    def _data_gap(self, day: date, message: str, **extra: Any) -> None:
        self._append_event("DATA_GAP", day, message, **extra)

    def _sell_pe(self, day: date, spot: float, from_date: str, to_date: str) -> bool:
        pe = pick_monthly_pe(self.catalog, self.underlying, day, spot)
        if not pe:
            self._data_gap(day, "No monthly PE near -10% of spot", spot=spot)
            return False
        day_map = self._option_day_map(pe, from_date, to_date)
        premium = _fill_price(day_map.get(day))
        if premium is None:
            # No candle for this day — contract may not have started trading yet,
            # or it is a market holiday. Skip silently and retry on the next trading day.
            return False
        qty = lot_size_for(pe, lot_size_for(self.spot_instrument, 1))
        self.position.pe = pe
        self.position.pe_entry_premium = premium
        self.position.pe_qty = qty
        self.state = STATE_SHORT_PE
        self._append_event(
            "PE_SOLD",
            day,
            f"Sold PE {pe.get('symbol')} @ {premium}",
            symbol=pe.get("symbol"),
            strike=pe.get("strike"),
            expiry=pe.get("expiry"),
            premium=premium,
            quantity=qty,
            side="SELL",
            spot=spot,
        )
        return True

    def _square_pe_buy_stock_sell_ce(self, day: date, spot: float, from_date: str, to_date: str) -> bool:
        pe = self.position.pe
        if not pe:
            return False
        pe_map = self._option_day_map(pe, from_date, to_date)
        pe_exit = _fill_price(pe_map.get(day))
        if pe_exit is None:
            self._data_gap(day, "Missing PE exit candle", symbol=pe.get("symbol"))
            return False
        pe_pnl = (float(self.position.pe_entry_premium or 0) - pe_exit) * self.position.pe_qty
        self._append_event(
            "PE_HIT_SQUARE",
            day,
            f"Squared PE {pe.get('symbol')} @ {pe_exit}",
            symbol=pe.get("symbol"),
            strike=pe.get("strike"),
            premium=pe_exit,
            quantity=self.position.pe_qty,
            side="BUY",
            pnl_update=round(pe_pnl, 2),
            spot=spot,
        )

        stock_candle = self.spot_by_day.get(day)
        stock_price = _fill_price(stock_candle)
        if stock_price is None:
            self._data_gap(day, "Missing stock candle for buy")
            return False
        qty = lot_size_for(pe, lot_size_for(self.spot_instrument, 1))
        self.position.stock = self.spot_instrument
        self.position.stock_entry = stock_price
        self.position.stock_qty = qty
        self._append_event(
            "STOCK_BOUGHT",
            day,
            f"Bought stock {self.underlying} @ {stock_price}",
            symbol=self.spot_instrument.get("symbol"),
            price=stock_price,
            quantity=qty,
            side="BUY",
            spot=spot,
        )

        ce = pick_monthly_ce(self.catalog, self.underlying, day, spot)
        if not ce:
            self._data_gap(day, "No monthly CE near +10% of spot", spot=spot)
            return False
        ce_map = self._option_day_map(ce, from_date, to_date)
        ce_premium = _fill_price(ce_map.get(day))
        if ce_premium is None:
            self._data_gap(day, "Missing CE historical candle", symbol=ce.get("symbol"))
            return False
        self.position.ce = ce
        self.position.ce_entry_premium = ce_premium
        self.position.ce_qty = qty
        self.position.ce_expiry = parse_expiry_date(ce.get("expiry"))
        self.position.pe = None
        self.position.pe_entry_premium = None
        self.position.pe_qty = 0
        self.state = STATE_LONG_STOCK_SHORT_CE
        self._append_event(
            "CE_SOLD",
            day,
            f"Sold CE {ce.get('symbol')} @ {ce_premium}",
            symbol=ce.get("symbol"),
            strike=ce.get("strike"),
            expiry=ce.get("expiry"),
            premium=ce_premium,
            quantity=qty,
            side="SELL",
            spot=spot,
        )
        return True

    def _close_stock_and_ce(self, day: date, spot: float, from_date: str, to_date: str) -> bool:
        ce = self.position.ce
        if not ce:
            return False
        ce_map = self._option_day_map(ce, from_date, to_date)
        ce_exit = _fill_price(ce_map.get(day))
        if ce_exit is None:
            # On expiry, worthless OTM would be 0; ITM path still needs a price — gap if missing.
            self._data_gap(day, "Missing CE exit candle on expiry", symbol=ce.get("symbol"))
            return False
        ce_pnl = (float(self.position.ce_entry_premium or 0) - ce_exit) * self.position.ce_qty
        self._append_event(
            "CE_CLOSED",
            day,
            f"Closed CE {ce.get('symbol')} @ {ce_exit}",
            symbol=ce.get("symbol"),
            strike=ce.get("strike"),
            premium=ce_exit,
            quantity=self.position.ce_qty,
            side="BUY",
            pnl_update=round(ce_pnl, 2),
            spot=spot,
        )

        stock_price = _fill_price(self.spot_by_day.get(day))
        if stock_price is None:
            self._data_gap(day, "Missing stock candle for sell")
            return False
        stock_pnl = (stock_price - float(self.position.stock_entry or 0)) * self.position.stock_qty
        self._append_event(
            "STOCK_SOLD",
            day,
            f"Sold stock {self.underlying} @ {stock_price}",
            symbol=self.spot_instrument.get("symbol"),
            price=stock_price,
            quantity=self.position.stock_qty,
            side="SELL",
            pnl_update=round(stock_pnl, 2),
            spot=spot,
        )
        self.position = PeCyclePosition()
        self.state = STATE_FLAT
        return True

    def _sell_next_ce_keep_stock(self, day: date, spot: float, from_date: str, to_date: str) -> bool:
        # Close current CE (OTM — buy back; premium may be near 0).
        ce = self.position.ce
        if ce:
            ce_map = self._option_day_map(ce, from_date, to_date)
            ce_exit = _fill_price(ce_map.get(day))
            if ce_exit is None:
                ce_exit = 0.0
            ce_pnl = (float(self.position.ce_entry_premium or 0) - ce_exit) * self.position.ce_qty
            self._append_event(
                "CE_CLOSED",
                day,
                f"Closed OTM CE {ce.get('symbol')} @ {ce_exit}",
                symbol=ce.get("symbol"),
                strike=ce.get("strike"),
                premium=ce_exit,
                quantity=self.position.ce_qty,
                side="BUY",
                pnl_update=round(ce_pnl, 2),
                spot=spot,
            )

        # Next monthly CE after current expiry.
        current_expiry = self.position.ce_expiry or day
        next_asof = current_expiry + timedelta(days=1)
        expiries = monthly_expiries_on_or_after(self.catalog, self.underlying, next_asof)
        next_ce = None
        for expiry in expiries:
            next_ce = pick_monthly_option(
                self.catalog,
                underlying=self.underlying,
                option_type="CE",
                asof=next_asof,
                spot=spot,
                offset_pct=0.10,
            )
            if next_ce and parse_expiry_date(next_ce.get("expiry")) == expiry:
                break
            next_ce = None
        if not next_ce:
            self._data_gap(day, "No next monthly CE for OTM roll", spot=spot)
            self.position.ce = None
            self.position.ce_entry_premium = None
            self.position.ce_qty = 0
            self.position.ce_expiry = None
            return False

        ce_map = self._option_day_map(next_ce, from_date, to_date)
        premium = _fill_price(ce_map.get(day))
        if premium is None:
            self._data_gap(day, "Missing next CE historical candle", symbol=next_ce.get("symbol"))
            return False
        qty = self.position.stock_qty or lot_size_for(next_ce, lot_size_for(self.spot_instrument, 1))
        self.position.ce = next_ce
        self.position.ce_entry_premium = premium
        self.position.ce_qty = qty
        self.position.ce_expiry = parse_expiry_date(next_ce.get("expiry"))
        self.state = STATE_LONG_STOCK_SHORT_CE
        self._append_event(
            "EXPIRY_OTM_SELL_CE",
            day,
            f"Kept stock; sold next CE {next_ce.get('symbol')} @ {premium}",
            symbol=next_ce.get("symbol"),
            strike=next_ce.get("strike"),
            expiry=next_ce.get("expiry"),
            premium=premium,
            quantity=qty,
            side="SELL",
            spot=spot,
        )
        return True

    def run(self, from_date: str, to_date: str) -> dict:
        start = _parse_day(from_date)
        end = _parse_day(to_date)
        if start is None or end is None or end < start:
            raise ValueError("Invalid from_date/to_date")

        spot_candles = self.load_candles(self.spot_instrument, from_date, to_date)
        self.spot_by_day = _index_candles_by_day(spot_candles)
        if not self.spot_by_day:
            raise ValueError("No spot historical candles for the selected range.")

        days = sorted(day for day in self.spot_by_day if start <= day <= end)
        for day in days:
            candle = self.spot_by_day[day]
            spot_close = float(candle.get("close") or 0)
            spot_low = float(candle.get("low") or spot_close)
            if spot_close <= 0:
                continue

            if self.state == STATE_FLAT:
                self._sell_pe(day, spot_close, from_date, to_date)
                continue

            if self.state == STATE_SHORT_PE:
                pe_strike = float((self.position.pe or {}).get("strike") or 0)
                if pe_strike > 0 and spot_low <= pe_strike:
                    self._square_pe_buy_stock_sell_ce(day, spot_close, from_date, to_date)
                continue

            if self.state == STATE_LONG_STOCK_SHORT_CE:
                expiry = self.position.ce_expiry
                if expiry is None or day < expiry:
                    continue
                ce_strike = float((self.position.ce or {}).get("strike") or 0)
                if ce_strike > 0 and spot_close >= ce_strike:
                    if self._close_stock_and_ce(day, spot_close, from_date, to_date):
                        self._append_event(
                            "EXPIRY_ITM_FLAT",
                            day,
                            "CE ITM on expiry; closed stock+CE; cycle restarts",
                            spot=spot_close,
                            strike=ce_strike,
                        )
                        self._sell_pe(day, spot_close, from_date, to_date)
                else:
                    self._sell_next_ce_keep_stock(day, spot_close, from_date, to_date)

        self._append_event("EXIT", end, "Backtest range complete")
        return {
            "strategy_type": "indian_pe_stock_ce",
            "underlying": self.underlying,
            "from_date": from_date,
            "to_date": to_date,
            "final_state": self.state,
            "cumulative_pnl": self.cumulative_pnl,
            "event_count": len(self.events),
            "events": self.events,
            "spot_symbol": self.spot_instrument.get("symbol"),
            "lot_size": lot_size_for(self.spot_instrument, 1),
        }


def simulate_pe_stock_ce_backtest(
    *,
    catalog: list[dict],
    underlying: str,
    from_date: str,
    to_date: str,
    load_candles: CandleLoader,
) -> dict:
    equity = pick_equity(catalog, underlying)
    if not equity:
        raise ValueError(f"Equity instrument not found for {underlying}")
    engine = PeCycleEngine(
        catalog=catalog,
        underlying=str(underlying).upper(),
        spot_instrument=equity,
        load_candles=load_candles,
    )
    return engine.run(from_date, to_date)
