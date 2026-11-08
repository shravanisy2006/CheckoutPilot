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
  createScan: (body: { store_url: string; include_mobile: boolean }) =>
    request<{ job_id: string; scan_id?: string }>("/api/scans", { method: "POST", body: JSON.stringify(body) }),
  getJob: <T = unknown>(id: string) => request<Job<T>>(`/api/jobs/${encodeURIComponent(id)}`),
  getScan: (id: string) => request<ScanResult>(`/api/scans/${encodeURIComponent(id)}`),
  createFix: (body: { scan_id: string; recommendation_ids: string[] }) =>
    request<{ job_id: string }>("/api/fixes", { method: "POST", body: JSON.stringify(body) }),
  createVerification: (body: { scan_id: string; fix_id: string }) =>
    request<{ job_id: string }>("/api/verifications", { method: "POST", body: JSON.stringify(body) }),
};

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
    return (u.protocol === "http:" || u.protocol === "https:") && u.hostname.includes(".");
  } catch {
    return false;
  }
}
