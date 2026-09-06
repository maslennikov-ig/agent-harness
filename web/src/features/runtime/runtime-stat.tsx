import type { RuntimeStatValue } from "@/features/runtime/types";
import { ToneBadge } from "@/shared/ui/projection";

export function RuntimeStat({ label, tone, value }: RuntimeStatValue) {
  return (
    <fieldset className="min-w-0 rounded-xl border border-border-soft bg-card p-4">
      <legend className="px-1 text-xs font-medium text-muted-foreground">
        {label}
      </legend>
      <div className="my-2 break-words font-mono text-sm font-semibold">
        {value}
      </div>
      <ToneBadge
        tone={tone === "warn" ? "warn" : tone === "ok" ? "ok" : "neutral"}
      >
        {tone}
      </ToneBadge>
    </fieldset>
  );
}
