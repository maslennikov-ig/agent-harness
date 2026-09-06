export interface RuntimeStatValue {
  label: string;
  tone: "info" | "ok" | "warn";
  value: string | number;
}

export interface CodexRuntimePayload {
  agents?: { count?: number };
  catalog?: { staged_sources?: number };
  id: "codex";
  label?: string;
  mcp?: { codex_available?: boolean };
  paths?: { home?: string; workspace?: string };
  skills?: { count?: number };
  status?: string;
}

export interface ClaudeRuntimePayload {
  agent_inventory?: {
    plugin_agents?: number;
    project_agents?: number;
    user_agents?: number;
  };
  agents?: { count?: number };
  aitmpl?: {
    candidate_count?: number;
    candidates?: Array<{
      dry_run_command?: string;
      matching_claude_agent?: boolean;
      name?: string;
    }>;
    matching_agent_count?: number;
    policy?: string;
    vetting_checklist?: string[];
  };
  home?: string;
  id: "claude";
  label?: string;
  mcp?: {
    configured_servers?: string[];
    last_refreshed?: number;
    list_ok?: boolean;
    list_returncode?: number;
    list_timed_out?: boolean;
    refresh_state?: string;
  };
  memory?: { line_count?: number };
  plugins?: {
    orchestration_bridge_enabled?: boolean;
    template_bridge_enabled?: boolean;
  };
  settings?: {
    claude_mem_enabled?: boolean;
    disabled_plugins?: string[];
    enabled_plugins?: string[];
    orchestration_bridge_enabled?: boolean;
    path?: string;
    skip_dangerous_mode_permission_prompt?: boolean;
    template_bridge_enabled?: boolean;
  };
  status?: string;
  version?: { available?: boolean; binary?: string; version?: string };
  vscode_wsl?: {
    claude_extensions?: string[];
    cli_mode_note?: string;
    ripgrep?: string;
    terminal_gpu_setting?: string;
    vscode_settings_path?: string;
    workspace_on_linux_fs?: boolean;
    wsl?: boolean;
  };
  warnings?: string[];
}

export type RuntimePayload = CodexRuntimePayload | ClaudeRuntimePayload;
