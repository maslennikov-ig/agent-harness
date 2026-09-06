import { Play } from "lucide-react";
import { RunCard } from "@/features/workspace/runs/run-card";
import type {
  CoordinationDispatch,
  CoordinationProvider,
  CoordinationReviewsPayload,
} from "@/shared/api/types";
import { Button } from "@/shared/ui/button";

export function RunsPanel({
  dispatches,
  enabled,
  onChanged,
  onOpenStart,
  providers,
  reviews,
}: {
  dispatches: CoordinationDispatch[];
  enabled: boolean;
  onChanged: () => Promise<unknown>;
  onOpenStart: () => void;
  providers: CoordinationProvider[];
  reviews?: CoordinationReviewsPayload;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-xl bg-surface-low p-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="break-words font-mono text-xs text-muted-foreground">
          {providers
            .map(
              (provider) =>
                `${provider.id}: ${provider.available ? provider.command : provider.error || "не найден"}`,
            )
            .join(" · ")}
        </p>
        <Button disabled={!enabled} onClick={onOpenStart} type="button">
          <Play aria-hidden="true" /> Запустить runtime
        </Button>
      </div>
      {dispatches.length ? (
        <div className="grid gap-3">
          {dispatches.map((dispatch) => (
            <RunCard
              dispatch={dispatch}
              key={dispatch.dispatch_id}
              maxRounds={reviews?.max_judge_rounds ?? 2}
              onChanged={onChanged}
              review={reviews?.executors.find(
                (entry) => entry.dispatch_id === dispatch.dispatch_id,
              )}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border-soft p-6 text-sm text-muted-foreground">
          Запусков ещё не было.
        </div>
      )}
    </div>
  );
}
