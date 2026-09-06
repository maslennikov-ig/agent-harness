import type { RadarRow } from "@/features/tails/types";
import { Button } from "@/shared/ui/button";
import { SectionList, ToneBadge } from "@/shared/ui/projection";

function worktreeLabel(row: RadarRow) {
  return (
    row.worktrees
      .map(
        (entry) => `${entry.path}${entry.branch ? ` (${entry.branch})` : ""}`,
      )
      .join(", ") || "нет"
  );
}

export function RepoRadar({
  beadCounts,
  expanded,
  onCopy,
  onToggle,
  rows,
}: {
  beadCounts: Map<string, { ready: number }>;
  expanded: Set<string>;
  onCopy: (command: string) => void;
  onToggle: (repoPath: string) => void;
  rows: RadarRow[];
}) {
  if (!rows.length) return null;

  return (
    <SectionList title="Радар репозиториев">
      {rows.map((row) => {
        const isExpanded = expanded.has(row.repo_path);
        const cleanupCount = row.merged_branches.length + row.worktrees.length;
        const counts = beadCounts.get(row.repo_path);
        return (
          <article key={row.repo_path}>
            <button
              aria-expanded={isExpanded}
              className="flex w-full flex-col gap-3 px-4 py-3 text-left hover:bg-accent/40 sm:flex-row sm:items-center sm:justify-between"
              onClick={() => onToggle(row.repo_path)}
              type="button"
            >
              <span className="font-semibold">{row.project}</span>
              <span className="flex flex-wrap items-center gap-2">
                <ToneBadge tone={row.dirty ? "warn" : "muted"}>
                  {row.dirty ? "dirty" : "clean"}
                </ToneBadge>
                <ToneBadge tone={row.tail_count ? "warn" : "muted"}>
                  {row.tail_count} tails
                </ToneBadge>
                {counts ? (
                  <ToneBadge tone={counts.ready ? "neutral" : "muted"}>
                    bd ready {counts.ready || 0}
                  </ToneBadge>
                ) : null}
                {cleanupCount ? (
                  <ToneBadge tone="warn">cleanup {cleanupCount}</ToneBadge>
                ) : null}
                {Number.isInteger(row.head_age_days) ? (
                  <ToneBadge tone="muted">HEAD {row.head_age_days}d</ToneBadge>
                ) : null}
              </span>
            </button>
            {isExpanded ? (
              <div className="space-y-2 border-t border-border-soft bg-surface-low px-4 py-3">
                <p className="break-all font-mono text-xs">
                  repo: {row.repo_path}
                </p>
                <p className="break-all font-mono text-xs">
                  merged, но не удалены:{" "}
                  {row.merged_branches.join(", ") || "нет"}
                </p>
                <p className="break-all font-mono text-xs">
                  worktrees: {worktreeLabel(row)}
                </p>
                {row.cleanup_commands.length ? (
                  <>
                    <div className="grid gap-2 pt-1">
                      {row.cleanup_commands.map((command) => (
                        <div
                          className="flex min-w-0 flex-col gap-2 rounded-lg border border-border-soft p-2 sm:flex-row sm:items-center sm:justify-between"
                          key={command}
                        >
                          <code className="min-w-0 break-all text-xs">
                            {command}
                          </code>
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
                    <p className="font-mono text-xs text-muted-foreground">
                      Команды только для копирования — панель ничего не
                      выполняет.
                    </p>
                  </>
                ) : null}
              </div>
            ) : null}
          </article>
        );
      })}
    </SectionList>
  );
}
