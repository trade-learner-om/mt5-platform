import { cn } from "../../lib/cn";

const WORKSTATION_TIMEZONE = "IST (UTC+5:30)";

function formatServerStateLog(value) {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString([], {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Calcutta",
  });
}

export default function TerminalStatusFooter({ serverConnected = false, lastServerStateLogAt = null }) {
  return (
    <footer className="shrink-0 border-t border-slate-200 bg-white px-4 py-1.5 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px] leading-tight text-slate-500 dark:text-slate-400">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span>
            Workstation timezone:
            {" "}
            <span className="font-semibold text-slate-700 dark:text-slate-200">{WORKSTATION_TIMEZONE}</span>
          </span>
          <span className="hidden text-slate-300 sm:inline">|</span>
          <span>
            Last Server State Log:
            {" "}
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {formatServerStateLog(lastServerStateLogAt)}
            </span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              serverConnected ? "bg-lime-500" : "bg-rose-500",
              serverConnected ? "animate-pulse" : ""
            )}
          />
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            {serverConnected ? "Server Ping" : "Server Offline"}
          </span>
        </div>
      </div>
    </footer>
  );
}
