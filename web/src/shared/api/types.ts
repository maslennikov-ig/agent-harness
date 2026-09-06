export interface RuntimeSummary {
  id: "codex" | "claude";
  label: string;
  status: "ok" | "warn";
  summary: string;
  warnings?: string[];
}

export interface ToolHealth {
  id: string;
  label: string;
  present: boolean;
  ok: boolean;
  detail: string;
}

export interface CatalogSummary {
  generated_at: string;
  staged_sources: number;
  staged_skills: number;
  staged_agents: number;
  installed_skills: number;
  custom_agents: number;
  path: string;
  home: string;
  runtime_home: string;
  runner: string;
  runner_exists: boolean;
  errors: string[];
}

export interface ClaudeCatalogSummary {
  enabled_plugins: number;
  disabled_plugins: number;
  skill_packs: number;
  plugin_skills: number;
  agents: number;
  user_agents: number;
  project_agents: number;
  plugin_agents: number;
  aitmpl_candidates: number;
  aitmpl_matching_agents: number;
  orchestration_bridge: boolean;
}

export interface OverviewPayload {
  health: { online: boolean; timestamp: number };
  paths: {
    console_dir: string;
    codex_home: string;
    codex_asset_home: string;
    claude_home: string;
    agents_home: string;
    workspace: string;
    prompts_dir: string;
    prompt_manifest: string;
    state_dir: string;
  };
  runtimes: { active: "codex"; items: RuntimeSummary[] };
  prompts: { source: string; manifest_exists: boolean };
  tools: ToolHealth[];
  catalog: CatalogSummary;
  catalog_claude: ClaudeCatalogSummary;
  skills: { count: number; items: Array<{ name: string; path: string }> };
  agents: { count: number; items: Array<{ name: string; path: string }> };
  beads: {
    bd_present: boolean;
    dolt_present: boolean;
    embedded_dolt_repos: number;
    summary: string;
  };
  notes: { path: string; preview: string };
}

export interface CoordinationProject {
  project_id: string;
  name: string;
  repo_path: string;
}

export interface CoordinationEpic {
  epic_id: string;
  project_id: string;
  title: string;
  beads_issue_id: string | null;
  source_kind?: string;
  source_ref?: string;
  source_url?: string;
}

export interface CoordinationRepository {
  repo_path: string;
  name: string;
}

export interface CoordinationOverviewPayload {
  enabled: boolean;
  flag: string;
  schema_version: number;
  providers: CoordinationProvider[];
  projects: CoordinationProject[];
  epics: CoordinationEpic[];
  latest_seq: number;
  console_repo: string;
  repositories?: CoordinationRepository[];
}

export interface CoordinationProvider {
  id: "codex" | "claude";
  available: boolean;
  status: string;
  error: string;
  command: string;
  home: string;
  root_role: string;
}

export interface CoordinationDispatch {
  dispatch_id: string;
  project_id: string;
  epic_id: string;
  beads_issue_id: string | null;
  provider: "codex" | "claude";
  state:
    | "draft"
    | "awaiting_start"
    | "running"
    | "needs_input"
    | "awaiting_review"
    | "blocked"
    | "cancelled"
    | "accepted"
    | "failed";
  runtime_session_id: string | null;
  write_zone: string;
  prompt_card_id: string;
  prompt_digest: string;
  detail: string;
  created_at: string;
  updated_at: string;
  role: "executor" | "judge";
  review_required: boolean;
  parent_dispatch_id: string;
}

export type BoardColumnId = "ready" | "running" | "blocked" | "done";

export interface CoordinationBoardCard {
  id: string;
  title: string;
  status: string;
  priority: number | null;
  issue_type: string;
  assignee: string;
  updated_at: string;
  column: BoardColumnId;
  phase: "planning" | "execution" | "review" | "accepted" | string;
  targets: BoardColumnId[];
  dependency_blocked: boolean;
  blocked_by: string[];
}

export interface CoordinationBoardPayload {
  epic_id: string;
  columns: Array<{ id: BoardColumnId; issues: CoordinationBoardCard[] }>;
  available: boolean;
  writable: boolean;
  errors: string[];
  project_id?: string;
  beads_issue_id?: string | null;
  repo_path?: string;
  off_board: CoordinationBoardCard[];
}

export interface CoordinationPlanningArtifact {
  kind: "specification" | "plan";
  path: string;
  digest: string;
  beads_issue_id: string | null;
  registered_at: string;
}

export interface CoordinationFinding {
  id: string;
  severity: "blocker" | "major" | "minor" | "note";
  summary: string;
  actionable: boolean;
}

export interface CoordinationReviewRound {
  review_id: string;
  round: number;
  executor_dispatch_id: string;
  executor_provider: string;
  judge_dispatch_id: string;
  judge_provider: string;
  judge_session_id: string;
  outcome: "accepted" | "changes_requested" | "unreadable";
  summary: string;
  findings: CoordinationFinding[];
  revision_returned: boolean;
  decided_by: string;
  created_at: string;
}

export interface CoordinationReviewExecutor {
  dispatch_id: string;
  beads_issue_id: string | null;
  executor_provider: string;
  state: string;
  review_required: boolean;
  is_current: boolean;
  next_action: "request_review" | "return_findings" | "escalate" | string;
  done_allowed: boolean;
  done_blocked_reason: string;
  rounds: CoordinationReviewRound[];
}

export interface CoordinationReviewsPayload {
  epic_id: string;
  beads_issue_id: string | null;
  max_judge_rounds: number;
  executors: CoordinationReviewExecutor[];
}
