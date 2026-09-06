export interface TelemetryWarning {
  kind?: string;
  repo?: string;
  stage_id?: string;
}

export interface TelemetryMetrics {
  findings?: { p0?: unknown; p1?: unknown };
  queue_seconds?: unknown;
  review_rounds?: unknown;
  worker_wall_seconds?: unknown;
}

export interface TelemetryDelegation {
  agent_wall_seconds?: unknown;
  coordination_seconds?: unknown;
  decision?: string;
  reasons?: string[];
  subagent_count?: unknown;
}

export interface TelemetryStage {
  delegation?: TelemetryDelegation;
  metrics?: TelemetryMetrics;
  repo?: string;
  stage_id?: string;
  status?: string;
  updated_at?: string;
  verification?: Record<string, unknown>;
}

export interface TelemetryTotals {
  agent_wall_seconds?: unknown;
  coordination_seconds?: unknown;
  delegation_decisions?: unknown;
  delegation_reasons?: unknown;
  integration_seconds?: unknown;
  p0_findings?: unknown;
  p1_findings?: unknown;
  queue_seconds?: unknown;
  rebase_seconds?: unknown;
  review_rounds?: unknown;
  subagent_count?: unknown;
  verification_seconds?: Record<string, unknown>;
  worker_wall_seconds?: unknown;
}

export interface TelemetryPayload {
  available: boolean;
  repo_count: number;
  sidecar_count: number;
  stage_count: number;
  stages?: TelemetryStage[];
  totals?: TelemetryTotals;
  unavailable_reason?: string;
  warnings?: TelemetryWarning[];
}
