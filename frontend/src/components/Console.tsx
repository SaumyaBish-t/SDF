import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { JobInfo, ProviderConfig, ProviderKey } from "../lib/api";

type Health = "checking" | "ok" | "down";

const EMPTY_KEY: ProviderKey = { api_key: "", model: "", base_url: "", batch_size: 5 };

const ROLE_META = [
  { id: "generator", color: "var(--color-ember)", batch: 5 },
  { id: "prefilter", color: "var(--color-prefilter)", batch: 8 },
  { id: "scorer", color: "var(--color-scorer)", batch: 4 },
] as const;

type RoleId = (typeof ROLE_META)[number]["id"];

export default function Console() {
  const [health, setHealth] = useState<Health>("checking");
  const [domains, setDomains] = useState<string[]>([]);

  const [domain, setDomain] = useState("");
  const [target, setTarget] = useState(100);

  const [byok, setByok] = useState(false);
  const [providers, setProviders] = useState<Record<RoleId, ProviderKey>>({
    generator: { ...EMPTY_KEY, batch_size: 5 },
    prefilter: { ...EMPTY_KEY, batch_size: 8 },
    scorer: { ...EMPTY_KEY, batch_size: 4 },
  });
  const [showKeys, setShowKeys] = useState(false);

  const [job, setJob] = useState<JobInfo | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const checkBackend = useCallback(async () => {
    setHealth("checking");
    try {
      await api.health();
      setHealth("ok");
      const d = await api.domains();
      setDomains(d.domains);
      if (d.domains.length && !domain) setDomain(d.domains[0]);
    } catch {
      setHealth("down");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    checkBackend();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [checkBackend]);

  const startPolling = (jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const info = await api.getRun(jobId);
        setJob(info);
        if (info.status !== "running" && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        /* transient poll failure — keep trying */
      }
    }, 2000);
  };

  const byokValid =
    !byok ||
    ROLE_META.every(({ id }) => {
      const p = providers[id];
      return p.api_key.trim() && p.model.trim() && p.base_url.trim();
    });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!domain) return setError("Pick a domain.");
    if (!byokValid)
      return setError("BYOK is on — fill api_key, model and base_url for all three roles.");

    setSubmitting(true);
    try {
      const body = {
        domain,
        target,
        providers: byok ? (providers as unknown as ProviderConfig) : null,
      };
      const info = await api.startRun(body);
      setJob(info);
      startPolling(info.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const setProviderField = (role: RoleId, field: keyof ProviderKey, value: string | number) =>
    setProviders((prev) => ({ ...prev, [role]: { ...prev[role], [field]: value } }));

  const progress = job ? Math.min(1, job.accepted / job.target) : 0;
  const running = job?.status === "running";

  return (
    <section id="console" className="relative mx-auto max-w-6xl px-5 py-28 md:py-36">
      <p className="mb-3 font-mono text-sm tracking-widest text-faint">FORGE CONSOLE</p>
      <h2 className="max-w-2xl text-3xl font-bold tracking-tight md:text-4xl">
        Point it at a domain. Watch the dataset assemble.
      </h2>
      <p className="mt-4 max-w-2xl text-muted">
        This console talks to the FastAPI backend (<span className="font-mono text-sm">uvicorn api.app:app</span>).
        Start it locally, then launch a run from here.
      </p>

      {/* backend status */}
      <div className="mt-8 flex items-center gap-3 font-mono text-sm">
        <span
          className={`inline-flex h-2.5 w-2.5 rounded-full ${
            health === "ok"
              ? "bg-accept shadow-[0_0_10px_var(--color-accept)]"
              : health === "down"
                ? "bg-reject"
                : "bg-ember animate-pulse"
          }`}
        />
        <span className="text-muted">
          {health === "ok" && "backend connected"}
          {health === "down" && "backend unreachable — run `uvicorn api.app:app --port 8000`"}
          {health === "checking" && "checking backend…"}
        </span>
        {health === "down" && (
          <button
            onClick={checkBackend}
            className="cursor-pointer rounded border border-line px-2.5 py-1 text-xs text-text transition-colors hover:border-faint"
          >
            retry
          </button>
        )}
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_400px]">
        {/* ---- form --------------------------------------------------- */}
        <form onSubmit={submit} className="rounded-2xl border border-line bg-surface p-6 md:p-8">
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <label htmlFor="domain" className="mb-1.5 block text-sm font-medium">
                Domain
              </label>
              <select
                id="domain"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                disabled={health !== "ok"}
                className="w-full cursor-pointer rounded-lg border border-line bg-raised px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-ember disabled:opacity-50"
              >
                {domains.length === 0 && <option value="">— backend offline —</option>}
                {domains.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-faint">from taxonomy/domains/</p>
            </div>
            <div>
              <label htmlFor="target" className="mb-1.5 block text-sm font-medium">
                Target accepted examples
              </label>
              <input
                id="target"
                type="number"
                min={1}
                max={100000}
                value={target}
                onChange={(e) => setTarget(Math.max(1, Number(e.target.value)))}
                className="w-full rounded-lg border border-line bg-raised px-3.5 py-2.5 font-mono text-sm outline-none transition-colors focus:border-ember"
              />
              <p className="mt-1.5 text-xs text-faint">run stops when this many survive all gates</p>
            </div>
          </div>

          {/* BYOK toggle */}
          <div className="mt-7 flex items-center justify-between rounded-xl border border-line bg-raised px-5 py-4">
            <div>
              <p className="text-sm font-semibold">Bring your own keys</p>
              <p className="mt-0.5 text-xs text-muted">
                Off = the server's configured providers. On = your keys, your bill.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={byok}
              aria-label="Toggle bring your own keys"
              onClick={() => setByok((v) => !v)}
              className={`relative h-7 w-12 cursor-pointer rounded-full transition-colors ${
                byok ? "bg-ember" : "bg-line"
              }`}
            >
              <span
                className={`absolute top-1 h-5 w-5 rounded-full bg-text transition-transform ${
                  byok ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          {/* BYOK cards */}
          {byok && (
            <div className="mt-5 space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted">
                  All three roles are required — partial overrides are rejected by the API.
                </p>
                <button
                  type="button"
                  onClick={() => setShowKeys((v) => !v)}
                  className="cursor-pointer font-mono text-xs text-muted transition-colors hover:text-text"
                >
                  {showKeys ? "hide keys" : "show keys"}
                </button>
              </div>
              {ROLE_META.map(({ id, color }) => (
                <fieldset key={id} className="rounded-xl border border-line p-4">
                  <legend className="px-2 font-mono text-xs font-semibold" style={{ color }}>
                    {id}
                  </legend>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <label htmlFor={`${id}-key`} className="mb-1 block text-xs text-muted">
                        api_key
                      </label>
                      <input
                        id={`${id}-key`}
                        type={showKeys ? "text" : "password"}
                        autoComplete="off"
                        value={providers[id].api_key}
                        onChange={(e) => setProviderField(id, "api_key", e.target.value)}
                        placeholder="sk-…"
                        className="w-full rounded-lg border border-line bg-raised px-3 py-2 font-mono text-xs outline-none transition-colors focus:border-ember"
                      />
                    </div>
                    <div>
                      <label htmlFor={`${id}-model`} className="mb-1 block text-xs text-muted">
                        model
                      </label>
                      <input
                        id={`${id}-model`}
                        type="text"
                        value={providers[id].model}
                        onChange={(e) => setProviderField(id, "model", e.target.value)}
                        placeholder="gpt-4o-mini"
                        className="w-full rounded-lg border border-line bg-raised px-3 py-2 font-mono text-xs outline-none transition-colors focus:border-ember"
                      />
                    </div>
                    <div>
                      <label htmlFor={`${id}-url`} className="mb-1 block text-xs text-muted">
                        base_url
                      </label>
                      <input
                        id={`${id}-url`}
                        type="text"
                        value={providers[id].base_url}
                        onChange={(e) => setProviderField(id, "base_url", e.target.value)}
                        placeholder="https://api.openai.com/v1"
                        className="w-full rounded-lg border border-line bg-raised px-3 py-2 font-mono text-xs outline-none transition-colors focus:border-ember"
                      />
                    </div>
                    <div>
                      <label htmlFor={`${id}-batch`} className="mb-1 block text-xs text-muted">
                        batch_size (concurrency)
                      </label>
                      <input
                        id={`${id}-batch`}
                        type="number"
                        min={1}
                        max={32}
                        value={providers[id].batch_size}
                        onChange={(e) =>
                          setProviderField(id, "batch_size", Math.max(1, Number(e.target.value)))
                        }
                        className="w-full rounded-lg border border-line bg-raised px-3 py-2 font-mono text-xs outline-none transition-colors focus:border-ember"
                      />
                    </div>
                  </div>
                </fieldset>
              ))}
            </div>
          )}

          {error && (
            <p role="alert" className="mt-5 rounded-lg border border-reject/40 bg-reject/10 px-4 py-3 text-sm text-reject">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={health !== "ok" || submitting || running}
            className="mt-7 w-full cursor-pointer rounded-lg bg-ember px-6 py-3.5 font-semibold text-bg transition-all hover:bg-ember-hot hover:shadow-[0_0_30px_rgba(251,146,60,0.35)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:shadow-none"
          >
            {submitting ? "Igniting…" : running ? "Run in progress…" : "Ignite the forge"}
          </button>
        </form>

        {/* ---- live run panel ------------------------------------------ */}
        <div className="rounded-2xl border border-line bg-surface p-6 md:p-8">
          <h3 className="font-mono text-sm text-muted">RUN STATUS</h3>

          {!job && (
            <div className="mt-10 flex flex-col items-center text-center">
              <div className="grid h-16 w-16 place-items-center rounded-full border border-dashed border-line">
                <svg viewBox="0 0 24 24" className="h-7 w-7 text-faint" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
                  <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" strokeLinejoin="round" />
                </svg>
              </div>
              <p className="mt-4 text-sm text-muted">No run yet.</p>
              <p className="mt-1 text-xs text-faint">Counters update live from pipeline checkpoints.</p>
            </div>
          )}

          {job && (
            <div className="mt-6 space-y-6">
              <div className="flex items-center justify-between">
                <span
                  className={`rounded-full px-3 py-1 font-mono text-xs font-semibold ${
                    job.status === "running"
                      ? "bg-ember/15 text-ember"
                      : job.status === "done"
                        ? "bg-accept/15 text-accept"
                        : "bg-reject/15 text-reject"
                  }`}
                >
                  {job.status}
                  {job.status === "running" && <span className="ml-1 animate-pulse">●</span>}
                </span>
                <span className="font-mono text-xs text-faint">{job.job_id.slice(0, 8)}</span>
              </div>

              <div>
                <div className="mb-2 flex justify-between font-mono text-sm">
                  <span className="text-accept">{job.accepted} accepted</span>
                  <span className="text-faint">target {job.target}</span>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-raised">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-ember via-ember-hot to-accept transition-[width] duration-700 ease-out"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 font-mono text-sm">
                <div className="rounded-lg border border-line bg-raised p-3.5">
                  <p className="text-xs text-faint">domain</p>
                  <p className="mt-1 truncate text-text">{job.domain}</p>
                </div>
                <div className="rounded-lg border border-line bg-raised p-3.5">
                  <p className="text-xs text-faint">rejected</p>
                  <p className="mt-1 text-reject">{job.rejected}</p>
                </div>
              </div>

              {job.status === "failed" && job.error && (
                <p role="alert" className="rounded-lg border border-reject/40 bg-reject/10 px-4 py-3 font-mono text-xs text-reject">
                  {job.error}
                </p>
              )}

              {job.status === "done" && (
                <a
                  href={api.exportUrl(job.job_id)}
                  download
                  className="block w-full rounded-lg bg-accept px-6 py-3 text-center font-semibold text-bg transition-all hover:shadow-[0_0_26px_rgba(34,197,94,0.4)]"
                >
                  Download dataset (.jsonl)
                </a>
              )}

              {job.status !== "running" && (
                <button
                  onClick={() => setJob(null)}
                  className="w-full cursor-pointer rounded-lg border border-line px-6 py-2.5 text-sm text-muted transition-colors hover:border-faint hover:text-text"
                >
                  New run
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
