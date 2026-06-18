import { useRef } from "react";
import { useReveal } from "../lib/motion";

const ROLES = [
  { name: "generator", color: "var(--color-generator)", tip: "a mid-tier model with clean structured-JSON output" },
  { name: "prefilter", color: "var(--color-prefilter)", tip: "the cheapest fast model you can find — verdicts are tiny" },
  { name: "scorer", color: "var(--color-scorer)", tip: "a reasoning-tier model — sycophancy here poisons the set" },
];

export default function Byok() {
  const ref = useRef<HTMLElement>(null);
  useReveal(ref);

  return (
    <section ref={ref} id="byok" className="relative mx-auto max-w-7xl px-5 py-28 md:px-8 md:py-40">
      <div data-reveal className="max-w-2xl">
        <p className="eyebrow mb-4">bring your own keys</p>
        <h2 className="display fluid-h2">
          Any provider that speaks <span className="font-mono text-generator">/chat/completions</span>.
        </h2>
        <p className="mt-5 text-muted">
          Each role takes its own <span className="font-mono text-sm text-text">api_key + model + base_url</span>.
          Mix OpenAI, Anthropic, Groq, DeepSeek or a local proxy — per role, per request. Keys live in
          memory for the run, wrapped in <span className="font-mono text-sm text-text">SecretStr</span>:
          never logged, never persisted.
        </p>
      </div>

      <div className="mt-14 grid gap-5 md:grid-cols-3">
        {ROLES.map((r, i) => (
          <div
            key={r.name}
            data-reveal
            data-reveal-delay={i * 80}
            style={{ transitionDelay: `${i * 80}ms` }}
            className="panel t-fast group relative overflow-hidden p-7 hover:-translate-y-1"
          >
            <span
              className="absolute -right-10 -top-10 h-28 w-28 rounded-full blur-2xl opacity-20 t-fast group-hover:opacity-40"
              style={{ background: r.color }}
            />
            <div className="relative">
              <span className="font-mono text-xs text-faint">0{i + 1}</span>
              <h3 className="mt-2 font-display text-xl font-semibold" style={{ color: r.color }}>
                {r.name}
              </h3>
              <p className="mt-3 text-sm text-muted">Pick {r.tip}.</p>
              <div className="mt-6 space-y-1.5 border-t border-faint-line pt-5 font-mono text-xs text-faint">
                <p><span className="text-muted">api_key</span> = sk-••••••••</p>
                <p><span className="text-muted">model</span> = any</p>
                <p><span className="text-muted">base_url</span> = any /v1</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
