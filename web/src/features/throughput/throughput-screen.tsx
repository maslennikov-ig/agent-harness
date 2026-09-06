import { RefreshCw } from "lucide-react";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { formatTelemetryBreakdown } from "@/features/telemetry/format";
import {
  ProjectionStat,
  ProjectionWarning,
} from "@/features/telemetry/telemetry-ui";
import {
  formatThroughputValue,
  ThroughputRepoRow,
} from "@/features/throughput/throughput-repo";
import type { ThroughputPayload } from "@/features/throughput/types";
import { useProjectionQuery } from "@/shared/api/projection";
import { Button } from "@/shared/ui/button";
import { RawInspector } from "@/shared/ui/raw-inspector";
import { ToneBadge } from "@/shared/ui/projection";

const screen = screenById("throughput");

function hasEntries(value: unknown) {
  return Boolean(
    value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).length,
  );
}

export function ThroughputScreen() {
  const { query, refresh } =
    useProjectionQuery<ThroughputPayload>("/api/throughput");
  const data = query.data;
  const totals = data?.totals || {};
  const simulation = data?.simulation || {};
  const legacy = simulation.legacy || {};
  const target = simulation.target || {};
  const savings = simulation.savings || {};
  const warnings = data?.warnings || [];
  const observedStats = [
    ["Product commits", formatThroughputValue(totals.product_commits)],
    [
      "Orchestration commits",
      formatThroughputValue(totals.orchestration_commits),
    ],
    ["Proof commits", formatThroughputValue(totals.proof_commits)],
    ["Stage summaries", formatThroughputValue(totals.stage_count)],
    ["Execution levels", formatTelemetryBreakdown(totals.level_distribution)],
    [
      "Verification run / reuse",
      formatTelemetryBreakdown(totals.verification_decisions),
    ],
    ["Evidence reuse count", formatThroughputValue(totals.reuse_count)],
    ["Anomaly codes", formatTelemetryBreakdown(totals.anomaly_codes)],
  ];
  const estimatedStats = [
    ["Legacy commands", formatThroughputValue(legacy.command_executions)],
    ["Target commands", formatThroughputValue(target.command_executions)],
    [
      "Estimated commands saved",
      formatThroughputValue(savings.command_executions),
    ],
    ["Release full runs", formatThroughputValue(target.release_full_runs)],
  ];

  return (
    <ScreenFrame
      actions={
        <Button onClick={refresh} size="sm" type="button" variant="outline">
          <RefreshCw aria-hidden="true" /> Обновить
        </Button>
      }
      marker={{ kind: "native", id: "throughput" }}
      screen={screen}
    >
      {query.isLoading ? (
        <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
          Загружаем throughput…
        </p>
      ) : query.error ? (
        <p className="rounded-xl border border-destructive p-5 text-destructive">
          {query.error instanceof Error
            ? query.error.message
            : "Throughput недоступен"}
        </p>
      ) : data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <ToneBadge tone="ok">
              observed repos{" "}
              {formatThroughputValue(totals.available_repo_count)}
            </ToneBadge>
            <ToneBadge
              tone={Number(totals.unavailable_repo_count) ? "warn" : "muted"}
            >
              unavailable {formatThroughputValue(totals.unavailable_repo_count)}
            </ToneBadge>
            <ToneBadge tone="warn">
              estimate · command executions only
            </ToneBadge>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {observedStats.map(([label, value]) => (
              <ProjectionStat
                classification="observed"
                key={label}
                label={label}
                tone={
                  label === "Anomaly codes" && hasEntries(totals.anomaly_codes)
                    ? "warn"
                    : undefined
                }
                value={value}
              />
            ))}
            {estimatedStats.map(([label, value]) => (
              <ProjectionStat
                classification="estimate"
                key={label}
                label={label}
                value={value}
              />
            ))}
          </div>
          {warnings.length ? (
            <ProjectionWarning title="Unavailable repositories">
              {warnings
                .map(
                  (warning) =>
                    `${warning.repo || "repo"}: ${warning.kind || "unavailable"}`,
                )
                .join(" · ")}
            </ProjectionWarning>
          ) : null}
          <section aria-label="Throughput repositories" className="grid gap-3">
            {(data.repos || []).map((repo) => (
              <ThroughputRepoRow key={repo.repo || "repo"} repo={repo} />
            ))}
          </section>
          <RawInspector data={data} />
        </div>
      ) : null}
    </ScreenFrame>
  );
}
