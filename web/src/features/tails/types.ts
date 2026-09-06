export interface Tail {
  age_days: number;
  base: string;
  branch: string;
  commit: string;
  date: string;
  kind: "local" | "remote";
  project: string;
  repo_path: string;
  subject: string;
}

export interface RadarWorktree {
  branch?: string;
  path: string;
}

export interface RadarRow {
  base: string;
  cleanup_commands: string[];
  dirty: boolean;
  head_age_days: number | null;
  merged_branches: string[];
  project: string;
  repo_path: string;
  tail_count: number;
  worktrees: RadarWorktree[];
}

export interface TailsPayload {
  generated_at: number;
  radar: RadarRow[];
  repo_count: number;
  tails: Tail[];
  threshold_days: number;
}

export interface TailPr {
  checks: string;
  is_draft: boolean;
  number: number;
  state: string;
  title: string;
  url: string;
}

export interface TailPrPayload {
  available: boolean;
  error?: string;
  generated_at: number;
  prs?: Record<string, TailPr>;
  repo_path?: string;
  slug?: string;
}

export interface TailGroup {
  base: string;
  count: number;
  key: string;
  local: number;
  oldest: number;
  project: string;
  remote: number;
  repo_path: string;
  tails: Tail[];
}
