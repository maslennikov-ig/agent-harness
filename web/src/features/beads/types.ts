export interface BeadsIssue {
  assignee: string;
  external_ref?: string;
  id: string;
  issue_type: string;
  priority: number | null;
  status: string;
  title: string;
  updated_at: string;
}

export interface BeadsCounts {
  blocked: number;
  in_progress: number;
  ready: number;
}

export interface BeadsRepo {
  blocked: BeadsIssue[];
  counts: BeadsCounts;
  errors: string[];
  in_progress: BeadsIssue[];
  project: string;
  ready: BeadsIssue[];
  repo_path: string;
}

export interface BeadsPayload {
  available: boolean;
  error?: string;
  generated_at: number;
  issue_limit: number | null;
  repos: BeadsRepo[];
  totals?: BeadsCounts;
}
