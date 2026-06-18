import { useEffect, useRef, useState } from "react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion, useReveal } from "../lib/motion";

interface Stage {
  n: string;
  id: string;
  color: string;
  spend: string;
  title: string;
  body: string;
  out: string;
  glyph: React.ReactNode;
}

const STAGES: Stage[] = [
  {
    n: "01",
    id: "generator",
    color: "var(--color-generator)",
    spend: "spends · output tokens",
    title: "Generator",
    body: "A meta-prompt turns each sampled taxonomy node-set into a batch of distinct instruction/response pairs, emitted as one structured JSON array. Mid-tier model, long structured output.",
    out: "→ raw_queue",
    glyph: <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" strokeLinejoin="round" />,
  },
  {
    n: "02",
    id: "prefilter",
    color: "var(--color-prefilter)",
    spend: "spends · input tokens",
    title: "Prefilter",
    body: "A cheap, fast judge reads the whole batch and emits tiny pass/fail verdicts on format, relevance and coherence. Unparseable verdicts fail closed — it kills roughly a third of garbage before the scorer ever sees it.",
    out: "→ scored_queue",
    glyph: <path d="M3 5h18l-7 8v5l-4 2v-7L3 5Z" strokeLinejoin="round" />,
  },
  {
    n: "03",
    id: "scorer",
    color: "var(--color-scorer)",
    spend: "spends · capability",
    title: "Scorer",
    body: "A reasoning-tier model rates every survivor on a 5-dimension weighted rubric — factuality, response quality, clarity, relevance, format. Composite ≥ 4.0 accepts; ≥ 3.0 revises; else reject.",
    out: "→ accepted_queue",
    glyph: <path d="M12 3v18M5 7l7-4 7 4M5 7l-2 7a4 4 0 0 0 8 0L9 7M19 7l-2 7a4 4 0 0 0 8 0l-2-7" strokeLinecap="round" strokeLinejoin="round" />,
  },
];

export default function Pipeline() {
  const ref = useRef<HTMLElement>(null);
  const [active, setActive] = useState(0);
  useReveal(ref);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion) return;
    const triggers = STAGES.map((_, i) =>
      ScrollTrigger.create({
        trigger: el.querySelectorAll("[data-stage]")[i] as Element,
        start: "top 60%",
        end: "bottom 60%",
        onToggle: (self) => self.isActive && setActive(i),
      }),
    );
    return () => triggers.forEach((t) => t.kill());
  }, []);

  const cur = STAGES[active];

  return (
    <section ref={ref} id="pipeline" className="relative mx-auto max-w-7xl px-5 py-28 md:px-8 md:py-40">
      <div data-reveal className="mb-16 max-w-2xl">
        <p className="eyebrow mb-4">the pipeline</p>
        <h2 className="display fluid-h2">
          Three roles, not one big judge.
        </h2>
        <p className="mt-5 text-muted">
          Splitting the work lets a cheap model kill garbage early, a mid-tier model do the
          writing, and your capability budget land where calibration actually matters.
        </p>
      </div>

      <div className="grid gap-10 lg:grid-cols-[0.85fr_1.15fr] lg:gap-16">
        {/* sticky visual */}
        <div className="hidden lg:block">
          <div className="sticky top-28">
            <div
              className="panel relative aspect-square overflow-hidden p-8"
              style={{ boxShadow: `inset 0 0 0 1px ${cur.color}22, 0 0 80px ${cur.color}14` }}
            >
              <div
                className="absolute -right-20 -top-20 h-64 w-64 rounded-full blur-3xl t-fast"
                style={{ background: cur.color, opacity: 0.16 }}
              />
              <div className="relative flex h-full flex-col justify-between">
                <div className="flex items-start justify-between">
                  <span className="font-mono text-6xl font-semibold text-faint">{cur.n}</span>
                  <svg
                    viewBox="0 0 24 24"
                    className="h-12 w-12 t-fast"
                    fill="none"
                    stroke={cur.color}
                    strokeWidth="1.5"
                    aria-hidden
                  >
                    {cur.glyph}
                  </svg>
                </div>

                <div>
                  <p className="eyebrow" style={{ color: cur.color }}>
                    {cur.spend}
                  </p>
                  <h3 className="mt-2 font-display text-4xl font-semibold" style={{ color: cur.color }}>
                    {cur.title}
                  </h3>
                  <p className="mt-4 font-mono text-sm text-muted">{cur.out}</p>
                </div>

                {/* mini queue diagram */}
                <div className="flex items-center gap-1.5">
                  {STAGES.map((s, i) => (
                    <span
                      key={s.id}
                      className="t-fast h-1 flex-1 rounded-full"
                      style={{
                        background: i <= active ? s.color : "var(--color-line)",
                        opacity: i <= active ? 1 : 0.5,
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* scrolling stages */}
        <div className="flex flex-col">
          {STAGES.map((s, i) => (
            <article
              key={s.id}
              data-stage
              data-reveal
              className="border-t border-line py-10 first:border-t-0 first:pt-0 lg:py-16"
            >
              <div className="mb-4 flex items-center gap-4">
                <span
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border lg:hidden"
                  style={{ borderColor: s.color, color: s.color }}
                >
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
                    {s.glyph}
                  </svg>
                </span>
                <span className="font-mono text-sm text-faint">{s.n}</span>
                <span className="eyebrow" style={{ color: s.color }}>
                  {s.spend}
                </span>
              </div>
              <h3 className="font-display text-3xl font-semibold md:text-4xl" style={{ color: s.color }}>
                {s.title}
              </h3>
              <p className="mt-4 max-w-xl text-muted">{s.body}</p>
              <p className="mt-4 font-mono text-sm" style={{ color: s.color, opacity: i === active ? 1 : 0.55 }}>
                {s.out}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
