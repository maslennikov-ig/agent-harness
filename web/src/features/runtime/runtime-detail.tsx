import type { ReactNode } from "react";
import type { ClaudeRuntimePayload } from "@/features/runtime/types";

function DetailCard({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="min-w-0 rounded-xl border border-border-soft bg-surface-low p-4">
      <h2 className="font-semibold">{title}</h2>
      <div className="mt-3 space-y-2 break-words font-mono text-xs leading-5 text-muted-foreground">
        {children}
      </div>
    </section>
  );
}

function mcpStatus(data: ClaudeRuntimePayload) {
  const mcp = data.mcp || {};
  const refreshed = mcp.last_refreshed
    ? `, refreshed ${new Date(mcp.last_refreshed * 1000).toLocaleTimeString()}`
    : "";
  if (mcp.list_ok) return `ok (${mcp.refresh_state || "fresh"}${refreshed})`;
  if (mcp.refresh_state === "pending") return "pending background refresh";
  if (mcp.refresh_state === "stale") {
    return `stale snapshot, refresh running${refreshed}`;
  }
  if (mcp.list_timed_out) return "timed out";
  return `check (${mcp.list_returncode ?? "unknown"})`;
}

export function ClaudeRuntimeDetail({ data }: { data: ClaudeRuntimePayload }) {
  const settings = data.settings || {};
  const vscode = data.vscode_wsl || {};
  const inventory = data.agent_inventory || {};
  const aitmpl = data.aitmpl || {};
  const candidates = (aitmpl.candidates || [])
    .map(
      (item) =>
        `${item.matching_claude_agent ? "match" : "candidate"} ${item.name || "agent"}`,
    )
    .join(", ");
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <DetailCard title="Claude runtime">
        <p>home: {data.home || ""}</p>
        <p>binary: {data.version?.binary || "not found"}</p>
        <p>warnings: {data.warnings?.join(", ") || "none"}</p>
        <p>settings: {settings.path || ""}</p>
      </DetailCard>
      <DetailCard title="VS Code / WSL">
        <p>{vscode.cli_mode_note || ""}</p>
        <p>settings: {vscode.vscode_settings_path || "not found"}</p>
        <p>terminal GPU: {vscode.terminal_gpu_setting || "not-set"}</p>
        <p>
          extensions: {vscode.claude_extensions?.join(", ") || "not detected"}
        </p>
      </DetailCard>
      <DetailCard title="Plugins">
        <p>enabled: {settings.enabled_plugins?.join(", ") || "none"}</p>
        <p>disabled: {settings.disabled_plugins?.join(", ") || "none"}</p>
      </DetailCard>
      <DetailCard title="MCP / Agents">
        <p>mcp: {data.mcp?.configured_servers?.join(", ") || "none"}</p>
        <p>mcp list: {mcpStatus(data)}</p>
        <p>background sessions: {data.agents?.count || 0}</p>
        <p>
          definitions: {inventory.user_agents || 0} user,{" "}
          {inventory.project_agents || 0} project,{" "}
          {inventory.plugin_agents || 0} plugin
        </p>
      </DetailCard>
      <DetailCard title="aitmpl candidates">
        <p>policy: {aitmpl.policy || ""}</p>
        <p>preview: {candidates || "none"}</p>
        <p>vetting: {aitmpl.vetting_checklist?.join("; ") || "none"}</p>
        <p>
          approval-required dry-run:{" "}
          {aitmpl.candidates?.[0]?.name
            ? // The command belongs to the candidate payload in production; keep
              // the legacy safe fallback when that optional field is absent.
              aitmpl.candidates[0].dry_run_command ||
              "npx claude-code-templates@latest --agent security/security-auditor --dry-run"
            : "npx claude-code-templates@latest --agent security/security-auditor --dry-run"}
        </p>
      </DetailCard>
    </div>
  );
}
