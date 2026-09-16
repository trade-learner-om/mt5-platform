import { animate, motion, useMotionValue } from "framer-motion";
import { useEffect, useRef, useState } from "react";

export default function PriceCell({
  value,
  formatter = (next) => String(next ?? "-"),
  className = "",
  tone = "price",
  align = "right",
}) {
  const previousValueRef = useRef(null);
  const background = useMotionValue("rgba(0,0,0,0)");
  const [direction, setDirection] = useState("flat");

  useEffect(() => {
    const current = Number(value);
    const previous = Number(previousValueRef.current);

    if (Number.isFinite(current) && Number.isFinite(previous)) {
      if (current > previous) setDirection("up");
      else if (current < previous) setDirection("down");
      else setDirection("flat");
    }

    if (Number.isFinite(current) && Number.isFinite(previous) && current !== previous) {
      const flash = current > previous ? "rgba(16,185,129,0.20)" : "rgba(244,63,94,0.20)";
      background.set(flash);
      const controls = animate(background, "rgba(0,0,0,0)", { duration: 0.5, ease: "easeOut" });
      previousValueRef.current = current;
      return () => controls.stop();
    }

    previousValueRef.current = current;
    return undefined;
  }, [background, value]);

  const toneClass =
    tone === "pnl"
      ? (() => {
          const numeric = Number(value);
          if (!Number.isFinite(numeric) || numeric === 0) {
            return "text-slate-700 dark:text-slate-300";
          }
          return numeric > 0
            ? "text-emerald-600 dark:text-emerald-400"
            : "text-rose-600 dark:text-rose-400";
        })()
      : direction === "up"
        ? "text-emerald-600 dark:text-emerald-400"
        : direction === "down"
          ? "text-rose-600 dark:text-rose-400"
          : "text-slate-700 dark:text-slate-300";

  return (
    <motion.span
      style={{ backgroundColor: background }}
      className={`inline-flex rounded px-2 py-1 font-mono tabular-nums ${align === "right" ? "justify-end text-right" : "justify-start text-left"} ${toneClass} ${className || "text-xs"}`}
    >
      {formatter(value)}
    </motion.span>
  );
}
