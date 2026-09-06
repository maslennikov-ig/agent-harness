import { TailBranchRow } from "@/features/tails/tail-branch";
import type { TailGroup, TailPrPayload } from "@/features/tails/types";
import { tailKey } from "@/features/tails/tails-lib";
import { Button } from "@/shared/ui/button";
import { ToneBadge } from "@/shared/ui/projection";

export function TailGroupCard({
  expanded,
  expandedTails,
  loadingPr,
  onCheckPr,
  onCopy,
  onToggle,
  onToggleTail,
  prStatus,
  group,
}: {
  expanded: boolean;
  expandedTails: Set<string>;
  group: TailGroup;
  loadingPr: boolean;
  onCheckPr: () => void;
  onCopy: (command: string) => void;
  onToggle: () => void;
  onToggleTail: (key: string) => void;
  prStatus?: TailPrPayload;
}) {
  const preview = group.tails
    .slice(0, 3)
    .map((tail) => tail.branch)
    .join(" · ");
  return (
    <article className="min-w-0 overflow-hidden rounded-xl border border-border-soft bg-card">
      <button
        aria-expanded={expanded}
        className="flex w-full min-w-0 flex-col gap-3 px-4 py-4 text-left hover:bg-accent/40 lg:flex-row lg:items-center lg:justify-between"
        onClick={onToggle}
        type="button"
      >
        <span className="min-w-0">
          <span className="block font-semibold">{group.project}</span>
          <span className="mt-1 block break-all font-mono text-xs text-muted-foreground">
            {group.repo_path}
          </span>
          <span className="mt-1 block truncate text-xs text-muted-foreground">
            {preview}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <ToneBadge tone="warn">{group.oldest}d max</ToneBadge>
          <ToneBadge>{group.count} tails</ToneBadge>
          <ToneBadge tone="muted">{group.local} local</ToneBadge>
          <ToneBadge tone="muted">{group.remote} remote</ToneBadge>
          <span className="font-mono text-xs text-muted-foreground">
            {group.base}
          </span>
        </span>
      </button>
      {expanded ? (
        <div className="border-t border-border-soft">
          <div className="flex flex-wrap items-center gap-3 bg-surface-low px-4 py-3">
            <Button
              disabled={loadingPr}
              onClick={onCheckPr}
              size="sm"
              type="button"
              variant="outline"
            >
              {loadingPr
                ? "Проверяю PR..."
                : prStatus
                  ? "Обновить PR-статусы"
                  : "Проверить PR"}
            </Button>
            {prStatus?.available ? (
              <span className="font-mono text-xs text-muted-foreground">
                gh: {prStatus.slug || "—"}
              </span>
            ) : null}
            {prStatus && !prStatus.available ? (
              <ToneBadge tone="warn">
                {prStatus.error || "gh недоступен"}
              </ToneBadge>
            ) : null}
          </div>
          {group.tails.map((tail) => {
            const key = tailKey(tail);
            return (
              <TailBranchRow
                expanded={expandedTails.has(key)}
                key={key}
                onCopy={onCopy}
                onToggle={() => onToggleTail(key)}
                prStatus={prStatus}
                tail={tail}
              />
            );
          })}
        </div>
      ) : null}
    </article>
  );
}
