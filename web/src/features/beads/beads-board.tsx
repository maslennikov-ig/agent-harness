import type { BeadsIssue, BeadsRepo } from "@/features/beads/types";
import { Button } from "@/shared/ui/button";
import { ToneBadge } from "@/shared/ui/projection";

type ColumnId = "in_progress" | "ready" | "blocked";

const columns: { id: ColumnId; label: string; mark: string }[] = [
  { id: "in_progress", label: "In progress", mark: "▶" },
  { id: "ready", label: "Ready", mark: "○" },
  { id: "blocked", label: "Blocked", mark: "▬" },
];

const tones: Record<ColumnId, "neutral" | "warn"> = {
  in_progress: "warn",
  ready: "neutral",
  blocked: "warn",
};

function BoardCard({
  issue,
  onCopyCommand,
  onCopyPrompt,
  onOpenWorkspace,
  repo,
  showProject,
  tone,
}: {
  issue: BeadsIssue;
  onCopyCommand: (repoPath: string, issue: BeadsIssue) => void;
  onCopyPrompt: (repoPath: string, issue: BeadsIssue) => void;
  onOpenWorkspace: (repoPath: string, issue: BeadsIssue) => void;
  repo: BeadsRepo;
  showProject: boolean;
  tone: "neutral" | "warn";
}) {
  return (
    <article className="min-w-0 rounded-lg border border-border-soft bg-card p-3">
      <h4 className="break-words text-sm font-semibold">{issue.title}</h4>
      <div className="mt-2 flex min-w-0 flex-wrap items-center gap-1.5">
        <span className="break-all font-mono text-xs">{issue.id}</span>
        {Number.isInteger(issue.priority) ? (
          <ToneBadge tone={tone}>P{issue.priority}</ToneBadge>
        ) : null}
        {issue.issue_type ? (
          <ToneBadge tone="muted">{issue.issue_type}</ToneBadge>
        ) : null}
        {issue.external_ref?.startsWith("https://") ? (
          <a
            className="text-xs text-primary underline underline-offset-2"
            href={issue.external_ref}
            rel="noreferrer"
            target="_blank"
          >
            GitHub
          </a>
        ) : null}
      </div>
      {showProject ? (
        <p className="mt-1.5 break-words font-mono text-xs text-muted-foreground">
          {repo.project}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          onClick={() => onCopyPrompt(repo.repo_path, issue)}
          size="sm"
          type="button"
        >
          Промпт
        </Button>
        <Button
          onClick={() => onOpenWorkspace(repo.repo_path, issue)}
          size="sm"
          type="button"
          variant="outline"
        >
          В Workspace
        </Button>
        <Button
          onClick={() => onCopyCommand(repo.repo_path, issue)}
          size="sm"
          type="button"
          variant="outline"
        >
          bd show
        </Button>
      </div>
    </article>
  );
}

export function BeadsBoard({
  onCopyCommand,
  onCopyPrompt,
  onOpenWorkspace,
  repos,
  showProject,
}: {
  onCopyCommand: (repoPath: string, issue: BeadsIssue) => void;
  onCopyPrompt: (repoPath: string, issue: BeadsIssue) => void;
  onOpenWorkspace: (repoPath: string, issue: BeadsIssue) => void;
  repos: BeadsRepo[];
  showProject: boolean;
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {columns.map((column) => {
        const cards = repos.flatMap((repo) =>
          repo[column.id].map((issue) => ({ issue, repo })),
        );
        const total = repos.reduce(
          (sum, repo) => sum + (repo.counts[column.id] || 0),
          0,
        );
        return (
          <section
            aria-label={column.label}
            className="min-w-0 rounded-xl bg-surface-low p-2.5"
            data-beads-column={column.id}
            key={column.id}
          >
            <header className="mb-2 flex items-center justify-between px-1 py-1">
              <h3 className="text-sm font-semibold">
                <span aria-hidden="true" className="mr-1.5 text-primary">
                  {column.mark}
                </span>
                {column.label}
              </h3>
              <span className="font-mono text-xs text-muted-foreground">
                {total}
              </span>
            </header>
            <div className="grid min-h-24 content-start gap-2">
              {cards.map(({ issue, repo }) => (
                <BoardCard
                  issue={issue}
                  key={`${repo.repo_path}:${issue.id}`}
                  onCopyCommand={onCopyCommand}
                  onCopyPrompt={onCopyPrompt}
                  onOpenWorkspace={onOpenWorkspace}
                  repo={repo}
                  showProject={showProject}
                  tone={tones[column.id]}
                />
              ))}
              {cards.length === 0 ? (
                <p className="grid min-h-20 place-items-center rounded-lg border border-dashed border-border-soft text-xs text-muted-foreground">
                  пусто
                </p>
              ) : null}
              {cards.length < total ? (
                // The server bound is per repository, so say it on the column too.
                <p className="px-1 py-1 text-xs text-warning">
                  Показаны {cards.length} из {total}
                </p>
              ) : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}
