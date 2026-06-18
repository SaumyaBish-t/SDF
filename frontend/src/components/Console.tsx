import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { JobInfo, ProviderConfig, ProviderKey } from "../lib/api";

type Health = "checking" | "ok" | "down";

const EMPTY_KEY: ProviderKey = { api_key: "", model: "", base_url: "", batch_size: 5 };

const ROLE_META = [
  { id: "generator", color: "var(--color-generator)", batch: 5 },
  { id: "prefilter", color: "var(--color-prefilter)", batch: 8 },
  { id: "scorer", color: "var(--color-scorer)", batch: 4 },
] as const;

type RoleId = (typeof ROLE_META)[number]["id"];

interface StreamLine {
  id: number;
  ts: string;
  text: string;
  tone: "muted" | "gold" | "scorer" | "generator";
}

const INPUT =
  "t-fast w-full rounded-lg border border-line bg-raised px-3.5 py-2.5 text-sm outline-none focus:border-generator focus:bg-bg2";

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

  const [stream, setStream] = useState<StreamLine[]>([]);
  const [preview, setPreview] = useState<string[] | null>(null);
  const [copiedPreview, setCopiedPreview] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevCounts = useRef({ accepted: 0, rejected: 0 });
  const lineId = useRef(0);
  const streamBox = useRef<HTMLDivElement>(null);

  const pushLine = useCallback((text: string, tone: StreamLine["tone"] = "muted") => {
    const ts = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setStream((prev) => [...prev.slice(-60), { id: ++lineId.current, ts, text, tone }]);
  }, []);

  useEffect(() => {
    const box = streamBox.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [stream]);

  const checkBackend = useCallback(async () => {
    setHealth("checking");
    try {
      await api.health();
      setHealth("ok");
      const d = await api.domains();
      setDomains(d.domains);
      setDomain((cur) => cur || d.domains[0] || "");
      pushLine("backend connected", "generator");
    } catch {
      setHealth("down");
    }
  }, [pushLine]);

  useEffect(() => {
    checkBackend();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [checkBackend]);

  const fetchPreview = useCallback(async (jobId: string) => {
    try {
      const res = await fetch(api.exportUrl(jobId));
      if (!res.ok) return;
      const text = await res.text();
      setPreview(text.split("\n").filter(Boolean).slice(0, 2));
    } catch {
      /* preview is best-effort */
    }
  }, []);

  const startPolling = (jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    prevCounts.current = { accepted: 0, rejected: 0 };
    pollRef.current = setInterval(async () => {
      try {
        const info = await api.getRun(jobId);
        setJob(info);
        const dA = info.accepted - prevCounts.current.accepted;
        const dR = info.rejected - prevCounts.current.rejected;
        if (dA > 0) pushLine(`+${dA} accepted · total ${info.accepted}/${info.target}`, "gold");
        if (dR > 0) pushLine(`+${dR} rejected · total ${info.rejected}`, "scorer");
        prevCounts.current = { accepted: info.accepted, rejected: info.rejected };

        if (info.status !== "running") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          pushLine(
            info.status === "done"
              ? "run complete — dataset ready"
              : `run failed: ${info.error ?? "unknown"}`,
            info.status === "done" ? "gold" : "scorer",
          );
          if (info.status === "done") fetchPreview(jobId);
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
      return setError("BYOK is on — fill api_key, model and base_url for all three judges.");

    setSubmitting(true);
    setPreview(null);
    try {
      const info = await api.startRun({
        domain,
        target,
        providers: byok ? (providers as unknown as ProviderConfig) : null,
      });
      setJob(info);
      pushLine(`run ignited · domain=${domain} target=${target}${byok ? " · byok" : ""}`, "generator");
      startPolling(info.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const setProviderField = (role: RoleId, field: keyof ProviderKey, value: string | number) =>
    setProviders((prev) => ({ ...prev, [role]: { ...prev[role], [field]: value } }));

  const copyPreview = async () => {
    if (!preview) return;
    await navigator.clipboard.writeText(preview.join("\n"));
    setCopiedPreview(true);
    setTimeout(() => setCopiedPreview(false), 1800);
  };

  const progress = job ? Math.min(1, job.accepted / job.target) : 0;
  const running = job?.status === "running";

  const toneClass: Record<StreamLine["tone"], string> = {
    muted: "text-muted",
    gold: "text-gold",
    scorer: "text-scorer",
    generator: "text-generator",
  };

  return (
    <section id="console" className="relative mx-auto max-w-7xl px-5 py-28 md:px-8 md:py-40">
      <div className="mb-10 max-w-2xl">
        <p className="eyebrow mb-4">forge console</p>
        <h2 className="display fluid-h2">Point it at a domain. Watch it assemble.</h2>
      </div>

      {/* backend status */}
      <div className="mb-8 flex flex-wrap items-center gap-3 font-mono text-sm">
        <span
          className={`inline-flex h-2 w-2 rounded-full ${
            health === "ok"
              ? "bg-generator shadow-[0_0_10px_var(--color-generator)]"
              : health === "down"
                ? "bg-scorer"
                : "animate-pulse bg-gold"
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
            className="t-fast cursor-pointer rounded-md border border-line px-2.5 py-1 text-xs text-text hover:border-faint"
          >
            retry
          </button>
        )}
      </div>

      {/* bento grid: config | stream | stats */}
      <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr_0.9fr]">
        {/* CONFIG */}
        <form onSubmit={submit} className="panel min-w-0 p-6">
          <p className="eyebrow mb-5">configuration</p>

          <div className="space-y-4">
            <div>
              <label htmlFor="domain" className="mb-1.5 block text-sm font-medium">
                Domain
              </label>
              <select
                id="domain"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                disabled={health !== "ok"}
                className={`${INPUT} cursor-pointer disabled:opacity-50`}
              >
                {domains.length === 0 && <option value="">— backend offline —</option>}
                {domains.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
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
                className={`${INPUT} font-mono`}
              />
            </div>
          </div>

          {/* BYOK toggle */}
          <div className="mt-5 flex items-center justify-between rounded-lg border border-line bg-raised px-4 py-3.5">
            <div>
              <p className="text-sm font-semibold">Bring your own keys</p>
              <p className="mt-0.5 text-xs text-muted">Off = server defaults. On = your keys, your bill.</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={byok}
              aria-label="Toggle bring your own keys"
              onClick={() => setByok((v) => !v)}
              className={`t-fast relative h-6 w-11 shrink-0 cursor-pointer rounded-full ${byok ? "bg-generator" : "bg-line"}`}
            >
              <span
                className={`t-fast absolute top-0.5 h-5 w-5 rounded-full bg-text ${byok ? "translate-x-[22px]" : "translate-x-0.5"}`}
              />
            </button>
          </div>

          {byok && (
            <div className="mt-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted">All three judges required — no partial overrides.</p>
                <button
                  type="button"
                  onClick={() => setShowKeys((v) => !v)}
                  className="t-fast cursor-pointer font-mono text-xs text-muted hover:text-text"
                >
                  {showKeys ? "hide keys" : "show keys"}
                </button>
              </div>
              {ROLE_META.map(({ id, color }) => (
                <fieldset key={id} className="rounded-lg border border-line p-3.5">
                  <legend className="px-1.5 font-mono text-[11px] font-semibold tracking-[0.14em] uppercase" style={{ color }}>
                    {id}
                  </legend>
                  <div className="grid gap-2.5 sm:grid-cols-2">
                    <div>
                      <label htmlFor={`${id}-key`} className="mb-1 block text-xs text-muted">api_key</label>
                      <input
                        id={`${id}-key`}
                        type={showKeys ? "text" : "password"}
                        autoComplete="off"
                        value={providers[id].api_key}
                        onChange={(e) => setProviderField(id, "api_key", e.target.value)}
                        placeholder="sk-…"
                        className={`${INPUT} px-3 py-2 font-mono text-xs`}
                      />
                    </div>
                    <div>
                      <label htmlFor={`${id}-model`} className="mb-1 block text-xs text-muted">model</label>
                      <input
                        id={`${id}-model`}
                        type="text"
                        value={providers[id].model}
                        onChange={(e) => setProviderField(id, "model", e.target.value)}
                        placeholder="gpt-4o-mini"
                        className={`${INPUT} px-3 py-2 font-mono text-xs`}
                      />
                    </div>
                    <div>
                      <label htmlFor={`${id}-url`} className="mb-1 block text-xs text-muted">base_url</label>
                      <input
                        id={`${id}-url`}
                        type="text"
                        value={providers[id].base_url}
                        onChange={(e) => setProviderField(id, "base_url", e.target.value)}
                        placeholder="https://api.openai.com/v1"
                        className={`${INPUT} px-3 py-2 font-mono text-xs`}
                      />
                    </div>
                    <div>
                      <label htmlFor={`${id}-batch`} className="mb-1 block text-xs text-muted">batch_size</label>
                      <input
                        id={`${id}-batch`}
                        type="number"
                        min={1}
                        max={32}
                        value={providers[id].batch_size}
                        onChange={(e) => setProviderField(id, "batch_size", Math.max(1, Number(e.target.value)))}
                        className={`${INPUT} px-3 py-2 font-mono text-xs`}
                      />
                    </div>
                  </div>
                </fieldset>
              ))}
            </div>
          )}

          {error && (
            <p role="alert" className="mt-4 rounded-lg border border-scorer/40 bg-scorer/10 px-3.5 py-2.5 text-sm text-scorer">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={health !== "ok" || submitting || running}
            className="t-fast mt-6 w-full cursor-pointer rounded-lg bg-generator px-6 py-3 font-semibold text-bg hover:shadow-[0_0_26px_var(--color-generator-soft)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:shadow-none"
          >
            {submitting ? "Igniting…" : running ? "Run in progress…" : "Ignite"}
          </button>
        </form>

        {/* LIVE PIPELINE STREAM */}
        <div className="terminal flex min-h-[440px] min-w-0 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <div className="flex items-center gap-3">
              <span className="flex gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-generator" />
                <span className="h-2.5 w-2.5 rounded-full bg-prefilter" />
                <span className="h-2.5 w-2.5 rounded-full bg-scorer" />
              </span>
              <span className="eyebrow">pipeline stream</span>
            </div>
            {running && <span className="animate-pulse font-mono text-[11px] text-gold">live</span>}
          </div>
          <div ref={streamBox} className="flex-1 space-y-1 overflow-y-auto px-4 py-3">
            {stream.length === 0 && <p className="font-mono text-xs text-faint">— awaiting ignition —</p>}
            {stream.map((l) => (
              <p key={l.id} className="stream-line font-mono text-xs leading-relaxed break-words">
                <span className="text-faint">[{l.ts}] </span>
                <span className={toneClass[l.tone]}>{l.text}</span>
              </p>
            ))}
          </div>
        </div>

        {/* STATS */}
        <div className="flex min-w-0 flex-col gap-5">
          <div className="panel flex-1 p-6">
            <p className="eyebrow mb-5">run status</p>

            {!job ? (
              <p className="text-sm text-faint">No run yet. Counters update live from pipeline checkpoints.</p>
            ) : (
              <div className="space-y-5">
                <div className="flex items-center justify-between">
                  <span
                    className={`rounded-md px-2.5 py-1 font-mono text-[11px] font-semibold tracking-[0.14em] uppercase ${
                      job.status === "running"
                        ? "bg-prefilter/15 text-prefilter"
                        : job.status === "done"
                          ? "bg-gold/15 text-gold"
                          : "bg-scorer/15 text-scorer"
                    }`}
                  >
                    {job.status}
                  </span>
                  <span className="font-mono text-xs text-faint">{job.job_id.slice(0, 8)}</span>
                </div>

                <div>
                  <div className="mb-1.5 flex justify-between font-mono text-sm">
                    <span className="text-gold">{job.accepted}</span>
                    <span className="text-faint">/ {job.target}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-generator to-gold transition-[width] duration-300 ease-in-out"
                      style={{ width: `${progress * 100}%` }}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2.5 font-mono text-sm">
                  <div className="rounded-lg border border-line bg-raised p-3">
                    <p className="eyebrow">accepted</p>
                    <p className="mt-1 text-gold">{job.accepted}</p>
                  </div>
                  <div className="rounded-lg border border-line bg-raised p-3">
                    <p className="eyebrow">rejected</p>
                    <p className="mt-1 text-scorer">{job.rejected}</p>
                  </div>
                </div>

                {job.status === "done" && (
                  <a
                    href={api.exportUrl(job.job_id)}
                    download
                    className="t-fast block w-full rounded-lg bg-gold px-5 py-2.5 text-center font-semibold text-bg hover:shadow-[0_0_22px_var(--color-gold-soft)]"
                  >
                    Download .jsonl
                  </a>
                )}
                {job.status !== "running" && (
                  <button
                    onClick={() => {
                      setJob(null);
                      setPreview(null);
                      setStream([]);
                    }}
                    className="t-fast w-full cursor-pointer rounded-lg border border-line px-5 py-2 text-sm text-muted hover:border-faint hover:text-text"
                  >
                    New run
                  </button>
                )}
              </div>
            )}
          </div>

          {/* output preview terminal */}
          {preview && (
            <div className="terminal overflow-hidden">
              <div className="flex items-center justify-between border-b border-line px-4 py-2">
                <span className="eyebrow">output preview</span>
                <button
                  onClick={copyPreview}
                  className="t-fast cursor-pointer rounded-md border border-line px-2 py-0.5 font-mono text-[11px] text-muted hover:border-faint hover:text-text"
                >
                  {copiedPreview ? "copied ✓" : "Copy JSON"}
                </button>
              </div>
              <div className="max-h-44 overflow-auto px-4 py-3">
                {preview.map((line, i) => (
                  <p key={i} className="truncate font-mono text-[11px] leading-relaxed text-generator">
                    {line}
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
