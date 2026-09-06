import { toast } from "sonner";
import { ReviewPanel } from "@/features/workspace/review/review-panel";
import { postJson } from "@/shared/api/client";
import type {
  CoordinationDispatch,
  CoordinationReviewExecutor,
} from "@/shared/api/types";
import { Button } from "@/shared/ui/button";

export function RunCard({
  dispatch,
  maxRounds,
  onChanged,
  review,
}: {
  dispatch: CoordinationDispatch;
  maxRounds: number;
  onChanged: () => Promise<unknown>;
  review?: CoordinationReviewExecutor;
}) {
  const active =
    dispatch.state === "running" || dispatch.state === "needs_input";
  const role = dispatch.role === "judge" ? "судья" : "исполнитель";
  const cancel = async () => {
    try {
      await postJson("/api/coordination/dispatches/cancel", {
        dispatch_id: dispatch.dispatch_id,
      });
      await onChanged();
      toast.success("Отмена отправлена");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Отмена не удалась");
    }
  };

  return (
    <article
      className="rounded-xl border border-border-soft bg-card p-4"
      data-dispatch-id={dispatch.dispatch_id}
      data-role={dispatch.role}
      data-state={dispatch.state}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{dispatch.provider}</span>
        <span className="rounded-md bg-surface-mid px-2 py-1 text-xs">
          {role}
        </span>
        <span className="rounded-md bg-runtime-accent-soft px-2 py-1 font-mono text-xs text-primary">
          {dispatch.state}
        </span>
        {active ? (
          <Button
            className="ml-auto"
            onClick={() => void cancel()}
            size="sm"
            type="button"
            variant="outline"
          >
            Отменить
          </Button>
        ) : null}
      </header>
      <dl className="mt-4 grid gap-2 font-mono text-xs sm:grid-cols-2">
        <Fact label="dispatch" value={dispatch.dispatch_id} />
        <Fact label="beads issue" value={dispatch.beads_issue_id || "—"} />
        <Fact
          label="runtime session"
          value={dispatch.runtime_session_id || "—"}
        />
        <Fact
          label="write zone"
          value={
            dispatch.write_zone ||
            (dispatch.role === "judge" ? "нет — read-only" : "—")
          }
        />
        <Fact
          label="prompt digest"
          value={dispatch.prompt_digest.slice(0, 16) || "—"}
        />
      </dl>
      {dispatch.detail ? (
        <p className="mt-3 rounded-lg bg-surface-low p-3 text-sm">
          {dispatch.detail}
        </p>
      ) : null}
      {dispatch.role === "executor" && review ? (
        <ReviewPanel
          entry={review}
          maxRounds={maxRounds}
          onChanged={onChanged}
        />
      ) : null}
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg bg-surface-low p-2.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-all text-foreground">{value}</dd>
    </div>
  );
}
