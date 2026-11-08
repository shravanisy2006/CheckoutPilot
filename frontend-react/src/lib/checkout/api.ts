import { adaptFix, adaptScan, adaptVerification } from "./adapt";
import type { FixResult, Job, ScanResult, VerificationResult } from "./types";

export const API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) throw new ApiError("VITE_API_BASE_URL is not configured. Switch to Demo Mode or set the backend URL.");
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(`Could not reach backend at ${API_BASE_URL}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  /** Raw POST; used by run* below. */
  post: <T = unknown>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  getJob: <T = unknown>(id: string) => request<Job<T>>(`/api/jobs/${encodeURIComponent(id)}`),
};

/* eslint-disable @typescript-eslint/no-explicit-any */
type Raw = Record<string, any>;
type OnProgress = (progress: number | undefined, stage: string | undefined) => void;

/**
 * Call a CheckoutPilot endpoint. The backend may answer straight away (current
 * /api/scan) or with a { job_id } to poll (for long tasks); both are handled.
 */
async function call(path: string, body: unknown, onProgress: OnProgress, missing: string): Promise<Raw> {
  let res: Raw;
  try {
    res = await api.post<Raw>(path, body);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) throw new ApiError(missing, e.status);
    throw e;
  }
  if (res["job_id"] && !res["status"]?.toString().match(/completed|failed/)) {
    const job = await pollJob<Raw>(String(res["job_id"]), (j) => onProgress(j.progress, j.stage));
    res = job.result ?? {};
  }
  if (res["status"] === "failed") throw new ApiError(String(res["message"] ?? "The backend reported a failure."));
  return res;
}

/** FIND: POST /api/scan (see docs/api_contract.md). */
export async function runScan(storeUrl: string, includeMobile: boolean, onProgress: OnProgress): Promise<ScanResult> {
  onProgress(10, "Scanning the store (about 10-60 seconds)");
  const raw = await call("/api/scan", { store_url: storeUrl, include_mobile: includeMobile }, onProgress,
    "The backend has no /api/scan endpoint. Check VITE_API_BASE_URL.");
  return adaptScan(raw, API_BASE_URL);
}

/** FIX: POST /api/fix with the issue IDs behind the selected recommendations. */
export async function runFix(scanId: string, recommendationIds: string[], onProgress: OnProgress): Promise<FixResult> {
  onProgress(10, "Writing the upgrade");
  const issueIds = recommendationIds.map((id) => id.replace(/^r_/, ""));
  const raw = await call("/api/fix", { scan_id: scanId, issue_ids: issueIds }, onProgress,
    "The backend does not have /api/fix yet (the code agent is still being built). Use Demo Mode to see the recorded fix.");
  return adaptFix(raw);
}

/** PROVE: POST /api/verify, which makes real PayPal Sandbox payments (1-2 minutes). */
export async function runVerify(fixId: string, onProgress: OnProgress): Promise<VerificationResult> {
  onProgress(10, "Making a PayPal Sandbox test payment (1-2 minutes)");
  const raw = await call("/api/verify", { fix_id: fixId }, onProgress,
    "The backend does not have /api/verify yet. Use Demo Mode to see the recorded Sandbox payments.");
  return adaptVerification(raw, API_BASE_URL);
}

export async function pollJob<T>(
  jobId: string,
  onUpdate: (job: Job<T>) => void,
  opts: { intervalMs?: number; timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<Job<T>> {
  const { intervalMs = 1500, timeoutMs = 10 * 60_000, signal } = opts;
  const started = Date.now();
  while (true) {
    if (signal?.aborted) throw new ApiError("Cancelled");
    const job = await api.getJob<T>(jobId);
    onUpdate(job);
    if (job.status === "succeeded") return job;
    if (job.status === "failed") throw new ApiError(job.error ?? "Job failed");
    if (Date.now() - started > timeoutMs) throw new ApiError("Job timed out");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export function isValidStoreUrl(v: string) {
  try {
    const u = new URL(v.trim());
    const local = u.hostname === "localhost" || u.hostname === "127.0.0.1";
    return (u.protocol === "http:" || u.protocol === "https:") && (local || u.hostname.includes("."));
  } catch {
    return false;
  }
}
