export type DocsFilter = "all" | "fallback" | "missing" | "ok" | "stale";

export interface DocsCommands {
  add_template?: string;
  install?: string;
  query?: string;
}

export interface DocsDependency {
  commands?: DocsCommands;
  dependency: string;
  docs_package?: string;
  docs_target_version: string;
  docs_version?: string;
  ecosystem: string;
  fallback: boolean;
  project: string;
  status: string;
  track?: string;
  used_version: string;
}

export interface DocsSyncEntry {
  add_template?: string;
  command?: string;
  dependency: string;
  docs_target_version: string;
  ecosystem: string;
  id?: string;
  priority?: string;
  projects?: string[];
  status: string;
  track: string;
}

export interface DocsContextPayload {
  commands?: { sync_dry_run?: string; sync_write?: string };
  context7?: { inline_key_in_codex_config?: boolean; status?: string };
  dependencies?: DocsDependency[];
  packages?: unknown;
  summary: {
    dependencies: number;
    projects: number;
    stack_path: string;
    status_counts?: Record<string, number>;
    tracks: number;
  };
  sync_plan?: {
    entries?: DocsSyncEntry[];
    summary?: {
      actionable_counts?: Record<string, number>;
      status_counts?: Record<string, number>;
    };
  };
}
