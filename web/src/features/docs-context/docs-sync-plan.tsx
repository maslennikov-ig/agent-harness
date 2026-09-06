import type { DocsContextPayload } from "@/features/docs-context/types";
import { Button } from "@/shared/ui/button";
import { ToneBadge } from "@/shared/ui/projection";

export function DocsSyncPlan({
  data,
  onCopy,
}: {
  data: DocsContextPayload;
  onCopy: (command: string) => void;
}) {
  const plan = data.sync_plan;
  if (!plan?.entries) {
    return (
      <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
        L1 sync plan not loaded.
      </p>
    );
  }
  const entries = plan.entries.filter(
    (entry) => entry.status === "missing" || entry.status === "stale",
  );
  const counts = plan.summary?.status_counts || {};
  const actionable = plan.summary?.actionable_counts || {};
  const dryRun =
    data.commands?.sync_dry_run || "codex-prompts docs-context-sync";
  const writeRun =
    data.commands?.sync_write ||
    "codex-prompts docs-context-sync --write --limit 20";
  return (
    <section className="overflow-hidden rounded-xl border border-border-soft bg-card">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border-soft px-4 py-3">
        <div>
          <h2 className="font-semibold">L1 sync plan</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            <ToneBadge tone={counts.missing ? "warn" : "muted"}>
              missing tracks {counts.missing || 0}
            </ToneBadge>
            <ToneBadge tone={counts.stale ? "warn" : "muted"}>
              stale tracks {counts.stale || 0}
            </ToneBadge>
            <ToneBadge tone={counts.future ? "warn" : "muted"}>
              future-docs {counts.future || 0}
            </ToneBadge>
            <ToneBadge>
              actionable {(actionable.missing || 0) + (actionable.stale || 0)}
            </ToneBadge>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() => onCopy(dryRun)}
            size="sm"
            type="button"
            variant="outline"
          >
            dry-run
          </Button>
          <Button
            onClick={() => onCopy(writeRun)}
            size="sm"
            type="button"
            variant="outline"
          >
            write
          </Button>
        </div>
      </header>
      <p className="border-b border-border-soft bg-warning/10 px-4 py-3 text-xs text-warning">
        UI does not execute installs. Run write mode explicitly from the
        terminal after reviewing this plan.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[56rem] text-left text-sm">
          <thead className="bg-surface-low text-xs text-muted-foreground">
            <tr>
              {[
                "Priority",
                "Track",
                "Target",
                "Status",
                "Projects",
                "Commands",
              ].map((label) => (
                <th className="px-3 py-2 font-medium" key={label} scope="col">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-soft">
            {entries.length ? (
              entries.map((entry) => (
                <tr
                  key={
                    entry.id ||
                    `${entry.ecosystem}:${entry.dependency}:${entry.track}`
                  }
                >
                  <td className="px-3 py-2">
                    <ToneBadge
                      tone={entry.priority === "high" ? "warn" : "muted"}
                    >
                      {entry.priority || "normal"}
                    </ToneBadge>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {entry.ecosystem}/{entry.dependency}@{entry.track}
                  </td>
                  <td className="px-3 py-2">{entry.docs_target_version}</td>
                  <td className="px-3 py-2">
                    <ToneBadge tone="warn">{entry.status}</ToneBadge>
                  </td>
                  <td className="px-3 py-2">
                    {entry.projects?.join(", ") || ""}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <Button
                        onClick={() => onCopy(entry.command || "")}
                        size="sm"
                        type="button"
                        variant="outline"
                      >
                        install
                      </Button>
                      <Button
                        onClick={() => onCopy(entry.add_template || "")}
                        size="sm"
                        type="button"
                        variant="outline"
                      >
                        add
                      </Button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-4 text-muted-foreground" colSpan={6}>
                  Нет missing/stale tracks в плане.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
