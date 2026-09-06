import {
  formatTelemetryCount,
  formatTelemetryDuration,
} from "@/features/telemetry/format";
import type { TelemetryStage } from "@/features/telemetry/types";
import { ToneBadge } from "@/shared/ui/projection";

export function TelemetryStageRow({ stage }: { stage: TelemetryStage }) {
  const metrics = stage.metrics || {};
  const findings = metrics.findings || {};
  const delegation = stage.delegation || {};
  const reasons = delegation.reasons?.length
    ? delegation.reasons.join(", ")
    : "none reported";
  const verification =
    Object.entries(stage.verification || {})
      .map(([name, seconds]) => `${name}: ${formatTelemetryDuration(seconds)}`)
      .join(" · ") || "no checks reported";
  const repo = stage.repo || "repo";
  const stageId = stage.stage_id || "stage";
  const status = stage.status || "unknown";
  return (
    <article
      aria-label={`${repo} / ${stageId}`}
      className="rounded-xl border border-border-soft bg-card p-4"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">
            {repo} / {stageId}
          </h3>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            {status} · {stage.updated_at || ""}
          </p>
        </div>
        <ToneBadge>{status}</ToneBadge>
      </header>
      <div className="mt-3 space-y-2 font-mono text-xs leading-5 text-muted-foreground">
        <p>
          worker {formatTelemetryDuration(metrics.worker_wall_seconds)} · queue{" "}
          {formatTelemetryDuration(metrics.queue_seconds)} · review{" "}
          {formatTelemetryCount(metrics.review_rounds)} · P0{" "}
          {formatTelemetryCount(findings.p0)} · P1{" "}
          {formatTelemetryCount(findings.p1)}
        </p>
        <p>
          delegation {delegation.decision || "unavailable"} · subagents{" "}
          {formatTelemetryCount(delegation.subagent_count)} · agent wall{" "}
          {formatTelemetryDuration(delegation.agent_wall_seconds)} ·
          coordination{" "}
          {formatTelemetryDuration(delegation.coordination_seconds)} · reasons{" "}
          {reasons}
        </p>
        <p>verification: {verification}</p>
      </div>
    </article>
  );
}
