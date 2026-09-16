import { useEffect, useState } from "react";
import { api } from "../../api";
import SymbolIcon from "../SymbolIcon";

function suggestionLabel(item) {
  const parts = [];
  if (item.exchange) parts.push(item.exchange);
  if (item.instrument_type) parts.push(item.instrument_type);
  if (item.expiry) parts.push(item.expiry);
  if (item.strike) parts.push(String(item.strike));
  if (item.option_type) parts.push(item.option_type);
  if (item.lot_size) parts.push(`Lot ${item.lot_size}`);
  return parts.join(" · ");
}

export default function IndianInstrumentSearch({
  token,
  disabled = false,
  placeholder = "Search instruments...",
  onSelect,
  onError,
  limit = 12,
  autoClear = true,
  className = "",
}) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  useEffect(() => {
    if (disabled || query.trim().length < 1) {
      setSuggestions([]);
      setHighlightedIndex(-1);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await api(`/indian/instruments/suggest?q=${encodeURIComponent(query)}&limit=${limit}`, "GET", undefined, token);
        const items = data.items || [];
        setSuggestions(items);
        setHighlightedIndex(items.length ? 0 : -1);
      } catch (err) {
        setSuggestions([]);
        setHighlightedIndex(-1);
        onError?.(err);
      }
    }, 160);
    return () => clearTimeout(timer);
  }, [disabled, limit, onError, query, token]);

  const commitSelection = async (item) => {
    if (!item) return;
    await onSelect?.(item);
    if (autoClear) {
      setQuery("");
      setSuggestions([]);
      setHighlightedIndex(-1);
    }
  };

  const handleKeyDown = async (event) => {
    if (!suggestions.length) {
      if (event.key === "Enter") {
        event.preventDefault();
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      await commitSelection(suggestions[highlightedIndex] || null);
    }
  };

  return (
    <div className={`relative ${className}`}>
      <input
        className="w-full rounded-xl border border-indigo-200 px-3 py-2 outline-none focus:border-indigo-500 disabled:bg-slate-100"
        disabled={disabled}
        value={query}
        onChange={(event) => setQuery(event.target.value.toUpperCase())}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
      />
      {suggestions.length > 0 && query && (
        <div className="absolute z-20 mt-1 max-h-80 w-full overflow-auto rounded-xl border border-indigo-100 bg-white shadow-lg">
          {suggestions.map((item, index) => (
            <button
              key={`${item.symbol}-${item.exchange}-${item.instrument_token}`}
              type="button"
              onClick={() => commitSelection(item)}
              onMouseEnter={() => setHighlightedIndex(index)}
              className={`block w-full px-3 py-2 text-left text-sm ${highlightedIndex === index ? "bg-indigo-100 text-indigo-900" : "hover:bg-indigo-50"}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <SymbolIcon symbol={item.symbol} />
                  <div className="min-w-0">
                  <p className="font-semibold">{item.symbol}</p>
                  <p className="text-xs text-slate-500">{item.display_name}</p>
                  {suggestionLabel(item) ? <p className="mt-0.5 text-[11px] text-slate-400">{suggestionLabel(item)}</p> : null}
                  </div>
                </div>
                {item.underlying ? <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-600">{item.underlying}</span> : null}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
