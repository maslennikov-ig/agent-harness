import { RefreshCw } from "lucide-react";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import {
  formatTelemetryBreakdown,
  formatTelemetryCount,
  formatTelemetryDuration,
} from "@/features/telemetry/format";
import { TelemetryStageRow } from "@/features/telemetry/telemetry-stage";
import {
  ProjectionStat,
  TelemetryWarnings,
} from "@/features/telemetry/telemetry-ui";
import type { TelemetryPayload } from "@/features/telemetry/types";
import { useProjectionQuery } from "@/shared/api/projection";
import { LIST_REFRESH_INTERVAL_MS } from "@/shared/api/queries";
import { Button } from "@/shared/ui/button";
import { Freshness } from "@/shared/ui/freshness";
import { RawInspector } from "@/shared/ui/raw-inspector";
import { ToneBadge } from "@/shared/ui/projection";

const screen = screenById("telemetry");

export function TelemetryScreen() {
  const { query, refresh } = useProjectionQuery<TelemetryPayload>(
    "/api/telemetry",
    {
      refetchInterval: LIST_REFRESH_INTERVAL_MS,
    },
  );
  const data = query.data;
  const warnings = data?.warnings || [];
  const totals = data?.totals || {};
  const stats: Array<{
    label: string;
    tone?: "warn";
    value: string;
  }> = data
    ? [
        {
          label: "Worker wall",
          value: formatTelemetryDuration(totals.worker_wall_seconds),
        },
        {
          label: "Queue wait",
          value: formatTelemetryDuration(totals.queue_seconds),
        },
        {
          label: "Review rounds",
          value: formatTelemetryCount(totals.review_rounds),
        },
        {
          label: "P0 findings",
          tone: "warn",
          value: formatTelemetryCount(totals.p0_findings),
        },
        {
          label: "P1 findings",
          tone: "warn",
          value: formatTelemetryCount(totals.p1_findings),
        },
        {
          label: "Integration",
          value: formatTelemetryDuration(totals.integration_seconds),
        },
        {
          label: "Rebase",
          value: formatTelemetryDuration(totals.rebase_seconds),
        },
        {
          label: "Subagents",
          value: formatTelemetryCount(totals.subagent_count),
        },
        {
          label: "Cumulative agent time",
          value: formatTelemetryDuration(totals.agent_wall_seconds),
        },
        {
          label: "Coordination",
          value: formatTelemetryDuration(totals.coordination_seconds),
        },
        {
          label: "Decisions",
          value: formatTelemetryBreakdown(totals.delegation_decisions),
        },
        {
          label: "Reasons",
          value: formatTelemetryBreakdown(totals.delegation_reasons),
        },
        ...Object.entries(totals.verification_seconds || {}).map(
          ([name, seconds]) => ({
            label: `Check: ${name}`,
            value: formatTelemetryDuration(seconds),
          }),
        ),
      ]
    : [];

  return (
    <ScreenFrame
      actions={
        <>
          <Freshness
            isFetching={query.isFetching}
            updatedAt={query.dataUpdatedAt}
          />
          <Button onClick={refresh} size="sm" type="button" variant="outline">
            <RefreshCw aria-hidden="true" /> Обновить
          </Button>
        </>
      }
      marker={{ kind: "native", id: "telemetry" }}
      screen={screen}
    >
      {query.isLoading ? (
        <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
          Загружаем телеметрию…
        </p>
      ) : query.error ? (
        <p className="rounded-xl border border-destructive p-5 text-destructive">
          {query.error instanceof Error
            ? query.error.message
            : "Телеметрия недоступна"}
        </p>
      ) : data && !data.available ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <ToneBadge tone="muted">unavailable</ToneBadge>
            <span className="font-mono text-xs text-muted-foreground">
              repos {data.repo_count || 0} · sidecars {data.sidecar_count || 0}
            </span>
          </div>
          <p className="rounded-xl border border-border-soft bg-surface-low p-5 text-muted-foreground">
            {data.unavailable_reason || "No usable stage telemetry yet."}
          </p>
          <TelemetryWarnings warnings={warnings} />
          <RawInspector data={data} />
        </div>
      ) : data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <ToneBadge tone="ok">stages {data.stage_count || 0}</ToneBadge>
            <ToneBadge>repos {data.repo_count || 0}</ToneBadge>
            <ToneBadge tone={warnings.length ? "warn" : "muted"}>
              ignored {warnings.length}
            </ToneBadge>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {stats.map(({ label, tone, value }) => (
              <ProjectionStat
                key={label}
                label={label}
                tone={
                  tone === "warn" && value !== "0" && value !== "unavailable"
                    ? "warn"
                    : undefined
                }
                value={value}
              />
            ))}
          </div>
          <TelemetryWarnings warnings={warnings} />
          <section aria-label="Telemetry stages" className="grid gap-3">
            {(data.stages || []).map((stage) => (
              <TelemetryStageRow
                key={`${stage.repo || "repo"}:${stage.stage_id || "stage"}`}
                stage={stage}
              />
            ))}
          </section>
          <RawInspector data={data} />
        </div>
      ) : null}
    </ScreenFrame>
  );
}
