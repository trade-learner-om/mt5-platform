import { useEffect, useState } from "react";

const MIN_PAGE_SIZE = 1;
const MAX_PAGE_SIZE = 50;

function clampPage(value, totalPages) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) return 1;
  return Math.min(Math.max(1, totalPages || 1), Math.max(1, parsed));
}

function clampPageSize(value) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) return MIN_PAGE_SIZE;
  return Math.min(MAX_PAGE_SIZE, Math.max(MIN_PAGE_SIZE, parsed));
}

export default function BacktestResultsPagination({
  page,
  pageSize,
  totalCount,
  totalPages,
  onPageChange,
  onPageSizeChange,
  disabled = false,
}) {
  const safeTotalPages = Math.max(1, Number(totalPages) || 1);
  const rangeStart = totalCount ? (page - 1) * pageSize + 1 : 0;
  const rangeEnd = totalCount ? Math.min(page * pageSize, totalCount) : 0;
  const [draftPage, setDraftPage] = useState(String(page));

  useEffect(() => {
    setDraftPage(String(page));
  }, [page]);

  function commitPage(raw) {
    const next = clampPage(raw, safeTotalPages);
    setDraftPage(String(next));
    if (next !== page) onPageChange(next);
  }

  return (
    <div className="mt-2 flex shrink-0 flex-col gap-2 border-t border-slate-200 pt-2 dark:border-slate-700">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {totalCount
            ? `Showing records ${rangeStart}-${rangeEnd} of total ${totalCount}`
            : "No results"}
        </p>
        {typeof onPageSizeChange === "function" ? (
          <label className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-300">
            <span>Per page</span>
            <input
              type="number"
              min={MIN_PAGE_SIZE}
              max={MAX_PAGE_SIZE}
              value={pageSize}
              disabled={disabled}
              onChange={(event) => onPageSizeChange(clampPageSize(event.target.value))}
              className="w-16 rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </label>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-1">
        <button
          type="button"
          disabled={disabled || page <= 1}
          onClick={() => onPageChange(1)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200"
        >
          First
        </button>
        <button
          type="button"
          disabled={disabled || page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200"
        >
          Prev
        </button>
        <label className="flex items-center gap-1 px-1 text-xs font-medium text-slate-600 dark:text-slate-300">
          <span>Page</span>
          <input
            type="number"
            min={1}
            max={safeTotalPages}
            value={draftPage}
            disabled={disabled}
            onChange={(event) => setDraftPage(event.target.value)}
            onBlur={() => commitPage(draftPage)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitPage(draftPage);
              }
            }}
            className="w-14 rounded-lg border border-slate-200 bg-white px-2 py-1 text-center text-sm text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
          <span>of {safeTotalPages}</span>
        </label>
        <button
          type="button"
          disabled={disabled || page >= safeTotalPages}
          onClick={() => onPageChange(page + 1)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200"
        >
          Next
        </button>
        <button
          type="button"
          disabled={disabled || page >= safeTotalPages}
          onClick={() => onPageChange(safeTotalPages)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200"
        >
          Last
        </button>
      </div>
    </div>
  );
}
