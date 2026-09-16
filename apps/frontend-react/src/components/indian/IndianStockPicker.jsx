import { useEffect, useState } from "react";
import { api } from "../../api";
import SymbolIcon from "../SymbolIcon";

function suggestionLabel(item) {
  const parts = [];
  if (item.exchange) parts.push(item.exchange);
  if (item.lot_size) parts.push(`Lot ${item.lot_size}`);
  if (item.underlying && item.underlying !== item.symbol) parts.push(item.underlying);
  return parts.join(" · ");
}

/**
 * F&O equity stock picker — typeahead that keeps the selected chip.
 */
export default function IndianStockPicker({
  token,
  disabled = false,
  value = null,
  onChange,
  onError,
  placeholder = "Search F&O stocks...",
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
        const data = await api(
          `/indian/instruments/suggest?q=${encodeURIComponent(query)}&limit=12&kind=fno_equity`,
          "GET",
          undefined,
          token,
        );
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
  }, [disabled, onError, query, token]);

  const commitSelection = (item) => {
    if (!item) return;
    onChange?.(item);
    setQuery("");
    setSuggestions([]);
    setHighlightedIndex(-1);
  };

  const handleKeyDown = (event) => {
    if (!suggestions.length) return;
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
      commitSelection(suggestions[highlightedIndex] || null);
    }
  };

  return (
    <div className={`relative ${className}`}>
      {value ? (
        <div className="mb-2 flex items-center justify-between gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <SymbolIcon symbol={value.symbol} />
            <div className="min-w-0">
              <p className="font-semibold text-slate-900">{value.symbol}</p>
              <p className="text-xs text-slate-500">{suggestionLabel(value) || value.display_name}</p>
            </div>
          </div>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange?.(null)}
            className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50"
          >
            Clear
          </button>
        </div>
      ) : null}
      <input
        className="w-full rounded-xl border border-indigo-200 px-3 py-2 outline-none focus:border-indigo-500 disabled:bg-slate-100"
        disabled={disabled}
        value={query}
        onChange={(event) => setQuery(event.target.value.toUpperCase())}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
      />
      {suggestions.length > 0 && query ? (
        <div className="absolute z-20 mt-1 max-h-80 w-full overflow-auto rounded-xl border border-indigo-100 bg-white shadow-lg">
          {suggestions.map((item, index) => (
            <button
              key={`${item.symbol}-${item.exchange}-${item.instrument_token}`}
              type="button"
              onClick={() => commitSelection(item)}
              onMouseEnter={() => setHighlightedIndex(index)}
              className={`block w-full px-3 py-2 text-left text-sm ${
                highlightedIndex === index ? "bg-indigo-100 text-indigo-900" : "hover:bg-indigo-50"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <SymbolIcon symbol={item.symbol} />
                  <div className="min-w-0">
                    <p className="font-semibold">{item.symbol}</p>
                    <p className="text-xs text-slate-500">{item.display_name}</p>
                    {suggestionLabel(item) ? (
                      <p className="mt-0.5 text-[11px] text-slate-400">{suggestionLabel(item)}</p>
                    ) : null}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
