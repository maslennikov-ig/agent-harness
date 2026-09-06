import { formatTelemetryBreakdown } from "@/features/telemetry/format";
import type { ThroughputRepo } from "@/features/throughput/types";
import { ToneBadge } from "@/shared/ui/projection";

const diagnosticLabels: Record<string, string> = {
  suspicious_micro_stage:
    "Proposed boundary may be a helper/test/docs/proof unit instead of a cohesive outcome",
  repeated_full_verification_without_material_source_change:
    "Prior PASS evidence was still exactly reusable but ignored; legal must_run retries remain allowed",
};

export function formatThroughputValue(value: unknown, suffix = "") {
  if (value === null || value === undefined) return "unavailable";
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return "unavailable";
  return `${numeric}${suffix}`;
}

function formatAnomalies(codes: string[] | undefined) {
  if (!codes?.length) return "none";
  return codes
    .map((code) =>
      diagnosticLabels[code] ? `${code} — ${diagnosticLabels[code]}` : code,
    )
    .join(" · ");
}

export function ThroughputRepoRow({ repo }: { repo: ThroughputRepo }) {
  const name = repo.repo || "repo";
  if (!repo.available) {
    return (
      <article
        aria-label={name}
        className="rounded-xl border border-border-soft bg-surface-low p-4"
      >
        <header className="flex items-start justify-between gap-3">
          <h3 className="font-semibold">{name}</h3>
          <ToneBadge tone="muted">unavailable</ToneBadge>
        </header>
        <p className="mt-3 font-mono text-xs text-muted-foreground">
          Bounded Git history is unavailable. No count was inferred.
        </p>
      </article>
    );
  }
  const telemetry = repo.telemetry || {};
  const action = repo.action || "none";
  return (
    <article
      aria-label={name}
      className="rounded-xl border border-border-soft bg-card p-4"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{name}</h3>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            observed · {action}
          </p>
        </div>
        <ToneBadge tone={action === "replan_required" ? "warn" : "ok"}>
          {action}
        </ToneBadge>
      </header>
      <div className="mt-3 space-y-2 font-mono text-xs leading-5 text-muted-foreground">
        <p>
          commits product {formatThroughputValue(repo.product_commits)} ·
          orchestration {formatThroughputValue(repo.orchestration_commits)} ·
          proof {formatThroughputValue(repo.proof_commits)}
        </p>
        <p>
          stage density {formatThroughputValue(repo.stage_density)} · commit
          ratio {formatThroughputValue(repo.orchestration_to_product_ratio)}
        </p>
        <p>
          levels {formatTelemetryBreakdown(telemetry.level_distribution)} ·
          run/reuse {formatTelemetryBreakdown(telemetry.verification_decisions)}
        </p>
        <p>anomaly codes: {formatAnomalies(repo.anomalies)}</p>
      </div>
    </article>
  );
}
