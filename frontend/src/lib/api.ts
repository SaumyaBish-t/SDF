/** Typed client for the Syntropic FastAPI backend. */

// 127.0.0.1 (not localhost) — on machines where Docker/WSL squat on the
// IPv6 side of the port, `localhost` can resolve to ::1 and miss uvicorn.
export const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://127.0.0.1:8000";

export interface ProviderKey {
  api_key: string;
  model: string;
  base_url: string;
  batch_size: number;
}

export interface ProviderConfig {
  generator: ProviderKey;
  prefilter: ProviderKey;
  scorer: ProviderKey;
}

export interface StartRunRequest {
  domain: string;
  target: number;
  seed?: number | null;
  resume?: boolean;
  providers?: ProviderConfig | null;
}

export type JobStatus = "running" | "done" | "failed";

export interface JobInfo {
  job_id: string;
  domain: string;
  target: number;
  status: JobStatus;
  run_id: string | null;
  output_path: string | null;
  accepted: number;
  rejected: number;
  last_node_idx: number;
  error: string | null;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => http<{ status: string }>("/healthz"),
  domains: () => http<{ domains: string[] }>("/domains"),
  startRun: (req: StartRunRequest) =>
    http<JobInfo>("/runs", { method: "POST", body: JSON.stringify(req) }),
  getRun: (jobId: string) => http<JobInfo>(`/runs/${jobId}`),
  listRuns: () => http<JobInfo[]>("/runs"),
  exportUrl: (jobId: string) => `${API_BASE}/runs/${jobId}/export`,
};
