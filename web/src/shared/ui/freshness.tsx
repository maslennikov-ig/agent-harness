import { useEffect, useState } from "react";

import { cn } from "@/shared/lib/cn";
import { formatFreshness } from "@/shared/lib/freshness";

/**
 * Age of the data on screen. The screens that poll say how old what they show
 * is, so an auto-refresh that silently stops is visible instead of looking
 * like fresh data.
 */
export function Freshness({
  className,
  isFetching,
  updatedAt,
}: {
  className?: string;
  isFetching?: boolean;
  updatedAt: number;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  if (!updatedAt) return null;
  const ageSeconds = Math.max(0, Math.floor((now - updatedAt) / 1000));

  return (
    <p
      aria-live="polite"
      className={cn(
        "whitespace-nowrap text-xs text-muted-foreground tabular-nums",
        className,
      )}
      data-testid="freshness"
    >
      {isFetching ? "обновляем…" : formatFreshness(ageSeconds)}
    </p>
  );
}
