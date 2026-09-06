import type { ClaudeAgentInstallResult } from "@/features/claude-agents/types";
import { ToneBadge } from "@/shared/ui/projection";

export function AgentInstallResult({
  result,
}: {
  result: ClaudeAgentInstallResult;
}) {
  return (
    <section
      aria-label="Результат установки"
      className="rounded-xl border border-secondary/50 bg-secondary/10 p-4"
      role="status"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold">Claude agent добавлен</h2>
        <ToneBadge tone="ok">{result.scope}</ToneBadge>
        {result.restart_recommended ? (
          <ToneBadge tone="warn">перезапуск рекомендован</ToneBadge>
        ) : null}
      </div>
      <div className="mt-3 space-y-1 break-all font-mono text-xs text-muted-foreground">
        <p>agent: {result.name}</p>
        <p>target: {result.target}</p>
        <p>
          source: {result.source_kind || "unknown"} {result.source_path || ""}
        </p>
        {result.note ? <p>{result.note}</p> : null}
      </div>
    </section>
  );
}
