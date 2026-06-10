import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "../lib/scrollState";

gsap.registerPlugin(ScrollTrigger);

const STAGES = [
  {
    n: "01",
    name: "Generator",
    color: "var(--color-ember)",
    headline: "Examples are forged from a taxonomy, not scraped.",
    body: "A seed sampler walks your domain taxonomy — topic, tone, complexity — and hands the generator one scenario at a time. Each call returns a batch of distinct (instruction, response) pairs, so coverage is engineered upfront instead of hoped for.",
    mono: "meta-prompt → JSON array → RawExample[]",
  },
  {
    n: "02",
    name: "Prefilter",
    color: "var(--color-prefilter)",
    headline: "A cheap critic kills the obvious garbage first.",
    body: "Before anything expensive happens, a fast model screens every batch for format, relevance, and coherence. Unparseable verdicts conservatively fail. Roughly a third of raw output dies here — at a fraction of a cent.",
    mono: "pass / fail · batched · fail-safe defaults",
  },
  {
    n: "03",
    name: "Scorer",
    color: "var(--color-scorer)",
    headline: "Survivors face a five-dimension rubric.",
    body: "Factuality, instruction clarity, response quality, domain relevance, format compliance — weighted, composited, and judged: accept, revise, or reject. Accepted examples are deduped twice (MinHash + semantic cosine) before they earn a row in your dataset.",
    mono: "composite ≥ 4.0 → accept · two-layer dedup",
  },
];

export default function Pipeline() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const railRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;

    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: wrap,
        start: "top top",
        end: "+=250%",
        pin: true,
        scrub: true,
        onUpdate: (self) => {
          const idx = Math.min(2, Math.floor(self.progress * 3));
          setActive((prev) => (prev === idx ? prev : idx));
          if (railRef.current) {
            railRef.current.style.transform = `scaleY(${self.progress})`;
          }
        },
      });
    }, wrap);

    return () => ctx.revert();
  }, []);

  const stage = STAGES[active];

  return (
    <section id="pipeline" className="relative">
      <div ref={wrapRef} className="flex h-[100svh] items-center overflow-hidden">
        <div className="mx-auto grid w-full max-w-6xl gap-12 px-5 md:grid-cols-[1fr_auto]">
          {/* copy */}
          <div className="flex max-w-xl flex-col justify-center">
            <p className="mb-3 font-mono text-sm tracking-widest text-faint">
              THE PIPELINE
            </p>
            <div
              key={stage.n}
              className={prefersReducedMotion ? "" : "animate-[fadeUp_.45s_ease-out]"}
            >
              <p
                className="font-mono text-6xl font-semibold md:text-7xl"
                style={{ color: stage.color }}
              >
                {stage.n}
              </p>
              <h2 className="mt-3 text-3xl font-bold tracking-tight md:text-4xl">
                {stage.headline}
              </h2>
              <p className="mt-5 text-base leading-relaxed text-muted md:text-lg">
                {stage.body}
              </p>
              <p className="mt-6 inline-block rounded border border-line bg-surface px-3 py-1.5 font-mono text-xs text-muted">
                {stage.mono}
              </p>
            </div>
          </div>

          {/* rail */}
          <div className="hidden items-center md:flex">
            <div className="relative flex h-[420px] flex-col items-center">
              {/* track */}
              <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-line" />
              {/* progress */}
              <div
                ref={railRef}
                className="absolute inset-y-0 left-1/2 w-px origin-top -translate-x-1/2 bg-gradient-to-b from-ember via-prefilter to-accept"
                style={{ transform: "scaleY(0)" }}
              />
              {STAGES.map((s, i) => (
                <div
                  key={s.n}
                  className="relative z-10 flex flex-1 flex-col items-center justify-center"
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-full border bg-surface font-mono text-sm transition-all duration-300"
                    style={{
                      borderColor: i <= active ? s.color : "var(--color-line)",
                      color: i <= active ? s.color : "var(--color-faint)",
                      boxShadow: i === active ? `0 0 26px ${s.color}55` : "none",
                    }}
                  >
                    {s.n}
                  </div>
                  <span
                    className="mt-2 text-xs font-medium transition-colors duration-300"
                    style={{ color: i <= active ? "var(--color-text)" : "var(--color-faint)" }}
                  >
                    {s.name}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(18px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </section>
  );
}
