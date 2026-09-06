import { RefreshCw } from "lucide-react";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { ClaudeRuntimeDetail } from "@/features/runtime/runtime-detail";
import { RuntimeStat } from "@/features/runtime/runtime-stat";
import type {
  ClaudeRuntimePayload,
  CodexRuntimePayload,
  RuntimePayload,
  RuntimeStatValue,
} from "@/features/runtime/types";
import { useProjectionQuery } from "@/shared/api/projection";
import { useAppearance } from "@/shared/theme/appearance-provider";
import { Button } from "@/shared/ui/button";
import { RawInspector } from "@/shared/ui/raw-inspector";

const screen = screenById("runtime");

function codexStats(data: CodexRuntimePayload): RuntimeStatValue[] {
  return [
    { label: "Codex Home", value: data.paths?.home || "", tone: "ok" },
    { label: "Local skill files", value: data.skills?.count || 0, tone: "ok" },
    { label: "Agents", value: data.agents?.count || 0, tone: "ok" },
    {
      label: "Catalog staged",
      value: data.catalog?.staged_sources || 0,
      tone: "ok",
    },
    {
      label: "Context MCP",
      value: data.mcp?.codex_available ? "codex mcp" : "not found",
      tone: data.mcp?.codex_available ? "ok" : "warn",
    },
  ];
}

function claudeStats(data: ClaudeRuntimePayload): RuntimeStatValue[] {
  const settings = data.settings || {};
  const plugins = data.plugins || {};
  const vscode = data.vscode_wsl || {};
  const inventory = data.agent_inventory || {};
  const aitmpl = data.aitmpl || {};
  const mcp = data.mcp || {};
  const bridge =
    settings.orchestration_bridge_enabled ||
    plugins.orchestration_bridge_enabled;
  const template =
    settings.template_bridge_enabled || plugins.template_bridge_enabled;
  const mcpLabel = mcp.list_ok
    ? "ok"
    : mcp.refresh_state === "pending"
      ? "pending"
      : mcp.refresh_state === "stale"
        ? "stale"
        : mcp.list_timed_out
          ? "timeout"
          : "check";
  return [
    {
      label: "Claude CLI",
      value: data.version?.version || "missing",
      tone: data.version?.available ? "ok" : "warn",
    },
    {
      label: "Plugin bridge",
      value: bridge ? "enabled" : "not enabled",
      tone: bridge ? "ok" : "warn",
    },
    {
      label: "template-bridge",
      value: template ? "enabled" : "disabled",
      tone: template ? "warn" : "ok",
    },
    {
      label: "claude-mem",
      value: settings.claude_mem_enabled ? "enabled" : "disabled",
      tone: settings.claude_mem_enabled ? "warn" : "ok",
    },
    {
      label: "Claude agents",
      value: `${inventory.user_agents || 0} user / ${inventory.project_agents || 0} project / ${inventory.plugin_agents || 0} plugin`,
      tone: "ok",
    },
    {
      label: "aitmpl matches",
      value: `${aitmpl.matching_agent_count || 0}/${aitmpl.candidate_count || 0}`,
      tone: "info",
    },
    {
      label: "Danger mode prompt",
      value: settings.skip_dangerous_mode_permission_prompt
        ? "skipped (by choice)"
        : "active",
      tone: settings.skip_dangerous_mode_permission_prompt ? "info" : "ok",
    },
    {
      label: "VS Code mode",
      value: vscode.wsl ? "WSL" : "check",
      tone: vscode.wsl ? "ok" : "warn",
    },
    {
      label: "Workspace FS",
      value: vscode.workspace_on_linux_fs ? "/home" : "not /home",
      tone: vscode.workspace_on_linux_fs ? "ok" : "warn",
    },
    {
      label: "ripgrep",
      value: vscode.ripgrep || "missing",
      tone: vscode.ripgrep ? "ok" : "warn",
    },
    {
      label: "MCP list",
      value: mcpLabel,
      tone: mcp.list_ok
        ? "ok"
        : mcp.refresh_state === "pending" || mcp.refresh_state === "stale"
          ? "info"
          : "warn",
    },
    {
      label: "Memory lines",
      value: data.memory?.line_count || 0,
      tone:
        data.memory?.line_count && data.memory.line_count <= 200
          ? "ok"
          : "warn",
    },
  ];
}

export function RuntimeScreen() {
  const { runtime } = useAppearance();
  const { query, refresh } = useProjectionQuery<RuntimePayload>(
    `/api/runtime/${runtime}`,
  );
  const data = query.data;
  const stats = data
    ? data.id === "claude"
      ? claudeStats(data)
      : codexStats(data)
    : [];
  return (
    <ScreenFrame
      actions={
        <Button onClick={refresh} size="sm" type="button" variant="outline">
          <RefreshCw aria-hidden="true" /> Обновить
        </Button>
      }
      marker={{ kind: "native", id: "runtime" }}
      screen={screen}
    >
      {query.isLoading ? (
        <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
          Loading {runtime} runtime…
        </p>
      ) : query.error ? (
        <p className="rounded-xl border border-destructive p-5 text-destructive">
          Runtime load failed:{" "}
          {query.error instanceof Error ? query.error.message : "unknown"}
        </p>
      ) : data && data.id === runtime ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {stats.map((stat) => (
              <RuntimeStat key={stat.label} {...stat} />
            ))}
          </div>
          {data.id === "claude" ? (
            <ClaudeRuntimeDetail data={data} />
          ) : (
            <section className="rounded-xl border border-border-soft bg-surface-low p-4">
              <h2 className="font-semibold">Codex runtime</h2>
              <p className="mt-3 break-all font-mono text-xs text-muted-foreground">
                workspace: {data.paths?.workspace || ""}
              </p>
            </section>
          )}
          <RawInspector data={data} />
        </div>
      ) : (
        <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
          Runtime not loaded for {runtime}.
        </p>
      )}
    </ScreenFrame>
  );
}
