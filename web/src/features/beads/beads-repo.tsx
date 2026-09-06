import type { BeadsIssue, BeadsRepo } from "@/features/beads/types";
import { Button } from "@/shared/ui/button";
import { SectionList, ToneBadge } from "@/shared/ui/projection";

function IssueRow({
  issue,
  onCopyCommand,
  onCopyPrompt,
  onOpenWorkspace,
  tone,
}: {
  issue: BeadsIssue;
  onCopyCommand: (issue: BeadsIssue) => void;
  onCopyPrompt: (issue: BeadsIssue) => void;
  onOpenWorkspace: (issue: BeadsIssue) => void;
  tone: "neutral" | "warn";
}) {
  return (
    <article className="flex min-w-0 flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h3 className="break-words text-sm font-semibold">{issue.title}</h3>
        <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2">
          <span className="break-all font-mono text-xs">{issue.id}</span>
          {Number.isInteger(issue.priority) ? (
            <ToneBadge tone={tone}>P{issue.priority}</ToneBadge>
          ) : null}
          <ToneBadge tone="muted">{issue.status}</ToneBadge>
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
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        <Button onClick={() => onCopyPrompt(issue)} size="sm" type="button">
          Промпт
        </Button>
        <Button
          onClick={() => onOpenWorkspace(issue)}
          size="sm"
          type="button"
          variant="outline"
        >
          В Workspace
        </Button>
        <Button
          onClick={() => onCopyCommand(issue)}
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

function CategoryBound({
  label,
  shown,
  total,
}: {
  label: string;
  shown: number;
  total: number;
}) {
  return shown < total ? (
    <p className="px-4 py-2 text-xs text-warning">
      Показаны {shown} из {total} {label}
    </p>
  ) : null;
}

export function BeadsRepoCard({
  onCopyCommand,
  onCopyPrompt,
  onOpenWorkspace,
  repo,
}: {
  onCopyCommand: (repoPath: string, issue: BeadsIssue) => void;
  onCopyPrompt: (repoPath: string, issue: BeadsIssue) => void;
  onOpenWorkspace: (repoPath: string, issue: BeadsIssue) => void;
  repo: BeadsRepo;
}) {
  const active = [...repo.in_progress, ...repo.ready];
  return (
    <SectionList
      actions={
        <div className="flex flex-wrap gap-2">
          <ToneBadge tone={repo.counts.ready ? "neutral" : "muted"}>
            ready {repo.counts.ready || 0}
          </ToneBadge>
          <ToneBadge tone={repo.counts.in_progress ? "warn" : "muted"}>
            in progress {repo.counts.in_progress || 0}
          </ToneBadge>
          <ToneBadge tone={repo.counts.blocked ? "warn" : "muted"}>
            blocked {repo.counts.blocked || 0}
          </ToneBadge>
        </div>
      }
      description={<span className="font-mono text-xs">{repo.repo_path}</span>}
      title={repo.project}
    >
      {active.length ? (
        <>
          {repo.in_progress.map((issue) => (
            <IssueRow
              issue={issue}
              key={`in-progress:${issue.id}`}
              onCopyCommand={(item) => onCopyCommand(repo.repo_path, item)}
              onCopyPrompt={(item) => onCopyPrompt(repo.repo_path, item)}
              onOpenWorkspace={(item) => onOpenWorkspace(repo.repo_path, item)}
              tone="warn"
            />
          ))}
          <CategoryBound
            label="in progress"
            shown={repo.in_progress.length}
            total={repo.counts.in_progress || 0}
          />
          {repo.ready.map((issue) => (
            <IssueRow
              issue={issue}
              key={`ready:${issue.id}`}
              onCopyCommand={(item) => onCopyCommand(repo.repo_path, item)}
              onCopyPrompt={(item) => onCopyPrompt(repo.repo_path, item)}
              onOpenWorkspace={(item) => onOpenWorkspace(repo.repo_path, item)}
              tone="neutral"
            />
          ))}
          <CategoryBound
            label="ready"
            shown={repo.ready.length}
            total={repo.counts.ready || 0}
          />
        </>
      ) : (
        <p className="px-4 py-3 font-mono text-sm text-muted-foreground">
          Нет ready/in-progress задач.
        </p>
      )}
      {repo.errors.length ? (
        <p className="bg-warning/10 px-4 py-3 font-mono text-xs text-warning">
          {repo.errors.join("; ")}
        </p>
      ) : null}
    </SectionList>
  );
}
