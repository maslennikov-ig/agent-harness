export interface ThroughputTotals {
  anomaly_codes?: unknown;
  available_repo_count?: unknown;
  level_distribution?: unknown;
  orchestration_commits?: unknown;
  product_commits?: unknown;
  proof_commits?: unknown;
  reuse_count?: unknown;
  stage_count?: unknown;
  unavailable_repo_count?: unknown;
  verification_decisions?: unknown;
}

export interface ThroughputSimulation {
  classification?: string;
  legacy?: { command_executions?: unknown };
  savings?: { command_executions?: unknown };
  target?: { command_executions?: unknown; release_full_runs?: unknown };
}

export interface ThroughputRepo {
  action?: string;
  anomalies?: string[];
  available: boolean;
  orchestration_commits?: unknown;
  orchestration_to_product_ratio?: unknown;
  product_commits?: unknown;
  proof_commits?: unknown;
  repo?: string;
  stage_density?: unknown;
  telemetry?: {
    level_distribution?: unknown;
    verification_decisions?: unknown;
  };
}

export interface ThroughputWarning {
  kind?: string;
  repo?: string;
}

export interface ThroughputPayload {
  repos?: ThroughputRepo[];
  schema_version?: string;
  simulation?: ThroughputSimulation;
  totals?: ThroughputTotals;
  warnings?: ThroughputWarning[];
}
