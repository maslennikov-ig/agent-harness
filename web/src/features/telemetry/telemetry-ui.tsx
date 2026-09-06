import type { ReactNode } from "react";
import type { TelemetryWarning } from "@/features/telemetry/types";
import { ToneBadge } from "@/shared/ui/projection";

export function ProjectionStat({
  classification = "reported",
  label,
  tone,
  value,
}: {
  classification?: string;
  label: string;
  tone?: "neutral" | "warn";
  value: string;
}) {
  const unavailable = value === "unavailable";
  const status = unavailable ? "unavailable" : classification;
  const statusTone = unavailable
    ? "muted"
    : (tone ?? (classification === "estimate" ? "warn" : "ok"));
  return (
    <fieldset className="min-w-0 rounded-xl border border-border-soft bg-card p-4">
      <legend className="px-1 text-xs font-medium text-muted-foreground">
        {label}
      </legend>
      <div className="my-2 break-words font-mono text-sm font-semibold">
        {value}
      </div>
      <ToneBadge tone={statusTone}>{status}</ToneBadge>
    </fieldset>
  );
}

export function ProjectionWarning({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <aside
      aria-label={title}
      className="rounded-xl border border-warning/50 bg-warning/10 px-4 py-3 font-mono text-xs text-warning"
      role="alert"
    >
      <strong>{title}:</strong> {children}
    </aside>
  );
}

export function TelemetryWarnings({
  warnings,
}: {
  warnings: TelemetryWarning[];
}) {
  if (!warnings.length) return null;
  return (
    <ProjectionWarning title="Ignored sidecars">
      {warnings
        .map(
          (warning) =>
            `${warning.repo || "repo"}/${warning.stage_id || "stage"}: ${warning.kind || "invalid"}`,
        )
        .join(" · ")}
    </ProjectionWarning>
  );
}
