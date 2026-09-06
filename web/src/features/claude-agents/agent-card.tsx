import type { ClaudeAgentCandidate } from "@/features/claude-agents/types";
import { Button } from "@/shared/ui/button";
import { ToneBadge } from "@/shared/ui/projection";

export function ClaudeAgentCard({
  candidate,
  onCopy,
  onInstall,
}: {
  candidate: ClaudeAgentCandidate;
  onCopy: (command: string) => void;
  onInstall: (candidate: ClaudeAgentCandidate) => void;
}) {
  return (
    <article
      aria-label={candidate.name}
      className="rounded-xl border border-border-soft bg-card p-4"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">{candidate.name}</h2>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            {candidate.agent_ref} ·{" "}
            {candidate.local_template_available ? "local" : "generated"}
          </p>
        </div>
        <ToneBadge tone={candidate.matching_claude_agent ? "neutral" : "muted"}>
          {candidate.matching_claude_agent ? "installed" : "available"}
        </ToneBadge>
      </header>
      <p className="mt-3 text-sm">{candidate.purpose}</p>
      <div className="mt-3 space-y-1 break-all font-mono text-xs text-muted-foreground">
        <p>template: {candidate.local_template_path || "generated fallback"}</p>
        <p>target: {candidate.project_install_target || ""}</p>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button onClick={() => onInstall(candidate)} size="sm" type="button">
          В проект
        </Button>
        <Button
          onClick={() => onCopy(candidate.install_project_command || "")}
          size="sm"
          type="button"
          variant="outline"
        >
          install cmd
        </Button>
        <Button
          onClick={() => onCopy(candidate.dry_run_command || "")}
          size="sm"
          type="button"
          variant="outline"
        >
          dry-run
        </Button>
      </div>
    </article>
  );
}
