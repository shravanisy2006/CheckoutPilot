export type Severity = "critical" | "high" | "medium" | "low";
export type Mode = "demo" | "live";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface Job<T = unknown> {
  job_id: string;
  status: JobStatus;
  progress?: number; // 0-100
  stage?: string | undefined;
  error?: string | undefined;
  result?: T;
  result_id?: string;
}

export interface Issue {
  id: string;
  title: string;
  severity: Severity;
  explanation: string;
  evidence: string[];
  surface?: "desktop" | "mobile" | "both";
}

export interface Recommendation {
  id: string;
  issue_id: string;
  title: string;
  description: string;
  severity: Severity;
  priority: number;
  rationale: string;
  estimated_conversion_impact?: string | null;
}

export interface ScanResult {
  scan_id: string;
  store_url: string;
  health_score: number;
  issues: Issue[];
  recommendations: Recommendation[];
  screenshots?: { desktop?: string | null; mobile?: string | null };
  created_at?: string;
}

export interface FileChange {
  path: string;
  category?: "sdk" | "checkout" | "other";
  before: string;
  after: string;
}

export interface FixResult {
  fix_id: string;
  confirmed: boolean; // backend confirms code was actually changed
  files: FileChange[];
  pull_request_url?: string | null;
  summary?: string;
}

export interface VerificationResult {
  verification_id: string;
  passed: boolean;
  environment: "sandbox";
  status: string;
  order_id?: string | null;
  simulated?: boolean;
  evidence: string[];
  screenshots?: { before?: string | null; after?: string | null };
}
