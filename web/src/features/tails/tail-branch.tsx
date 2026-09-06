import type { Tail, TailPrPayload } from "@/features/tails/types";
import { diagnosticCommands } from "@/features/tails/tails-lib";
import { Button } from "@/shared/ui/button";
import { LabelledRow, ToneBadge } from "@/shared/ui/projection";

function prForTail(tail: Tail, status?: TailPrPayload) {
  if (!status?.available) return undefined;
  const branch = tail.branch.startsWith("origin/")
    ? tail.branch.slice(7)
    : tail.branch;
  return status.prs?.[branch] ?? null;
}

export function TailBranchRow({
  expanded,
  onCopy,
  onToggle,
  prStatus,
  tail,
}: {
  expanded: boolean;
  onCopy: (command: string) => void;
  onToggle: () => void;
  prStatus?: TailPrPayload;
  tail: Tail;
}) {
  const pr = prForTail(tail, prStatus);
  const prLabel = pr
    ? `PR #${pr.number} ${pr.is_draft ? "draft" : pr.state.toLowerCase()}${pr.checks && pr.checks !== "none" ? ` · checks ${pr.checks}` : ""}`
    : pr === null
      ? "no PR"
      : "";
  return (
    <article className="min-w-0 border-t border-border-soft first:border-t-0">
      <button
        aria-expanded={expanded}
        className="flex w-full min-w-0 flex-col gap-3 px-4 py-3 text-left hover:bg-accent/40 sm:flex-row sm:items-center sm:justify-between"
        onClick={onToggle}
        type="button"
      >
        <span className="min-w-0">
          <span className="block break-all font-mono text-sm font-semibold">
            {tail.branch}
          </span>
          <span className="mt-1 block break-words text-sm text-muted-foreground">
            {tail.subject}
          </span>
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <ToneBadge tone="warn">{tail.age_days}d</ToneBadge>
          <ToneBadge tone={tail.kind === "remote" ? "muted" : "neutral"}>
            {tail.kind}
          </ToneBadge>
          {prLabel ? (
            <ToneBadge
              tone={
                pr?.checks === "failing" ? "warn" : pr ? "neutral" : "muted"
              }
            >
              {prLabel}
            </ToneBadge>
          ) : null}
          <span className="break-all font-mono text-xs text-muted-foreground">
            {tail.commit} · {tail.date}
          </span>
        </span>
      </button>
      {expanded ? (
        <div className="border-t border-border-soft bg-surface-low">
          <LabelledRow label="Repo">{tail.repo_path}</LabelledRow>
          <LabelledRow label="Base">{tail.base}</LabelledRow>
          <LabelledRow label="Commit">{tail.commit}</LabelledRow>
          <LabelledRow label="Date">{tail.date}</LabelledRow>
          <div className="grid gap-2 px-4 py-3">
            {diagnosticCommands(tail).map((command) => (
              <div
                className="flex min-w-0 flex-col gap-2 rounded-lg border border-border-soft p-2 sm:flex-row sm:items-center sm:justify-between"
                key={command}
              >
                <code className="min-w-0 break-all text-xs">{command}</code>
                <Button
                  onClick={() => onCopy(command)}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  Copy
                </Button>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}
