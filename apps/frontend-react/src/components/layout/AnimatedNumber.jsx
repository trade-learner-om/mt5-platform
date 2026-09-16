import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect } from "react";

export default function AnimatedNumber({
  value,
  format = (next) => String(next),
  className = "",
}) {
  const numericValue = Number(value);
  const motionValue = useMotionValue(Number.isFinite(numericValue) ? numericValue : 0);
  const text = useTransform(motionValue, (latest) => format(latest));

  useEffect(() => {
    if (!Number.isFinite(numericValue)) return undefined;
    const controls = animate(motionValue, numericValue, {
      duration: 0.35,
      ease: "easeOut",
    });
    return () => controls.stop();
  }, [motionValue, numericValue]);

  if (!Number.isFinite(numericValue)) {
    return <span className={className}>{format(value)}</span>;
  }

  return <motion.span className={className}>{text}</motion.span>;
}
