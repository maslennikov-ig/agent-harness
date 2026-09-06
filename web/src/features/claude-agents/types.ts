export interface InstalledClaudeAgent {
  name: string;
  source_scope: string;
}

export interface ClaudeAgentCandidate {
  agent_ref: string;
  dry_run_command?: string;
  install_project_command?: string;
  local_template_available: boolean;
  local_template_path?: string;
  matching_claude_agent: boolean;
  name: string;
  project_install_target?: string;
  purpose: string;
}

export interface ClaudeAgentsPayload {
  candidate_count: number;
  candidates: ClaudeAgentCandidate[];
  installed_agents: InstalledClaudeAgent[];
  local_template_count: number;
  matching_agent_count: number;
  project_agents_dir: string;
}

export interface ClaudeAgentInstallResult {
  name: string;
  note?: string;
  ok: boolean;
  restart_recommended?: boolean;
  scope: string;
  source_kind?: string;
  source_path?: string;
  target: string;
}
