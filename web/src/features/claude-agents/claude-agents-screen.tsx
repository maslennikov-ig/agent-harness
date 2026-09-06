import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { ClaudeAgentCard } from "@/features/claude-agents/agent-card";
import { AgentInstallConfirmation } from "@/features/claude-agents/install-confirmation";
import { AgentInstallResult } from "@/features/claude-agents/install-result";
import type {
  ClaudeAgentCandidate,
  ClaudeAgentInstallResult,
  ClaudeAgentsPayload,
} from "@/features/claude-agents/types";
import { postJson } from "@/shared/api/client";
import { useProjectionQuery } from "@/shared/api/projection";
import { Button } from "@/shared/ui/button";
import { RawInspector } from "@/shared/ui/raw-inspector";
import { ToneBadge } from "@/shared/ui/projection";

const screen = screenById("claude-agents");

export function ClaudeAgentsScreen() {
  const { query, refresh } =
    useProjectionQuery<ClaudeAgentsPayload>("/api/claude-agents");
  const [candidate, setCandidate] = useState<ClaudeAgentCandidate | null>(null);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<ClaudeAgentInstallResult | null>(null);
  const [installError, setInstallError] = useState("");
  const data = query.data;

  const copy = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      toast.success("Команда скопирована");
    } catch {
      toast.error("Не удалось скопировать");
    }
  };

  const install = async () => {
    if (!candidate || sending) return;
    setSending(true);
    setInstallError("");
    try {
      const response = await postJson<ClaudeAgentInstallResult>(
        "/api/claude-agents/install",
        { name: candidate.name, scope: "project" },
      );
      setResult(response);
      setCandidate(null);
      await refresh();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Установка не удалась";
      setInstallError(message);
      setCandidate(null);
    } finally {
      setSending(false);
    }
  };

  const installed =
    data?.installed_agents
      .map((item) => `${item.source_scope}:${item.name}`)
      .join(", ") || "none";
  return (
    <ScreenFrame
      actions={
        <Button onClick={refresh} size="sm" type="button" variant="outline">
          <RefreshCw aria-hidden="true" /> Обновить
        </Button>
      }
      marker={{ kind: "native", id: "claude-agents" }}
      screen={screen}
    >
      {query.isLoading ? (
        <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
          Loading Claude agent library…
        </p>
      ) : query.error ? (
        <p className="rounded-xl border border-destructive p-5 text-destructive">
          Claude agent library failed to load:{" "}
          {query.error instanceof Error ? query.error.message : "unknown"}
        </p>
      ) : data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <ToneBadge>candidates {data.candidate_count || 0}</ToneBadge>
            <ToneBadge>
              local templates {data.local_template_count || 0}
            </ToneBadge>
            <ToneBadge>
              installed matches {data.matching_agent_count || 0}
            </ToneBadge>
            <span className="break-all font-mono text-xs text-muted-foreground">
              project: {data.project_agents_dir || ""}
            </span>
            <span className="break-all font-mono text-xs text-muted-foreground">
              installed: {installed}
            </span>
          </div>
          {result ? <AgentInstallResult result={result} /> : null}
          {installError ? (
            <p
              className="rounded-xl border border-destructive p-4 text-destructive"
              role="alert"
            >
              {installError}
            </p>
          ) : null}
          {data.candidates.length ? (
            <section
              aria-label="Claude agent candidates"
              className="grid gap-3 lg:grid-cols-2"
            >
              {data.candidates.map((item) => (
                <ClaudeAgentCard
                  candidate={item}
                  key={item.name}
                  onCopy={copy}
                  onInstall={setCandidate}
                />
              ))}
            </section>
          ) : (
            <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
              No Claude agent candidates found.
            </p>
          )}
          <RawInspector data={data} />
        </div>
      ) : null}
      <AgentInstallConfirmation
        candidate={candidate}
        onConfirm={install}
        onOpenChange={(open) => {
          if (!open && !sending) setCandidate(null);
        }}
        sending={sending}
      />
    </ScreenFrame>
  );
}
