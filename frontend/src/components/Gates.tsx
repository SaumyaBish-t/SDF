import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "../lib/scrollState";

gsap.registerPlugin(ScrollTrigger);

const WEIGHTS = [
  { name: "factuality", w: 0.3 },
  { name: "response_quality", w: 0.25 },
  { name: "instruction_clarity", w: 0.2 },
  { name: "domain_relevance", w: 0.15 },
  { name: "format_compliance", w: 0.1 },
];

const VERDICTS = [
  { label: "accept", range: "composite ≥ 4.0", color: "var(--color-accept)", desc: "earns a row in the dataset" },
  { label: "revise", range: "3.0 – 3.9", color: "var(--color-ember)", desc: "flagged for regeneration" },
  { label: "reject", range: "< 3.0", color: "var(--color-reject)", desc: "discarded, logged with rubric" },
];

export default function Gates() {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion) return;

    const ctx = gsap.context(() => {
      gsap.fromTo(
        el.querySelectorAll("[data-bar]"),
        { scaleX: 0 },
        {
          scaleX: 1,
          duration: 1.0,
          ease: "power3.out",
          stagger: 0.08,
          scrollTrigger: { trigger: el, start: "top 65%" },
        },
      );
      gsap.fromTo(
        el.querySelectorAll("[data-card]"),
        { y: 26, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.7,
          ease: "power3.out",
          stagger: 0.1,
          scrollTrigger: { trigger: el, start: "top 65%" },
        },
      );
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={ref} id="gates" className="relative mx-auto max-w-6xl px-5 py-28 md:py-36">
      <p className="mb-3 font-mono text-sm tracking-widest text-faint">QUALITY GATES</p>
      <h2 className="max-w-2xl text-3xl font-bold tracking-tight md:text-4xl">
        Every example is judged on five dimensions — and the weights are yours to read.
      </h2>

      <div className="mt-14 grid gap-14 md:grid-cols-2">
        {/* rubric weights */}
        <div>
          <h3 className="mb-6 font-mono text-sm text-muted">RUBRIC_WEIGHTS</h3>
          <div className="space-y-5">
            {WEIGHTS.map((d) => (
              <div key={d.name}>
                <div className="mb-1.5 flex items-baseline justify-between font-mono text-sm">
                  <span className="text-text">{d.name}</span>
                  <span className="text-muted">{d.w.toFixed(2)}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-raised">
                  <div
                    data-bar
                    className="h-full origin-left rounded-full bg-gradient-to-r from-ember to-ember-hot"
                    style={{ width: `${(d.w / 0.3) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-6 text-sm leading-relaxed text-muted">
            The scorer returns a 1–5 score per dimension. The weighted composite decides the
            verdict — and the full rubric is persisted with every example, accepted or not.
          </p>
        </div>

        {/* verdicts */}
        <div>
          <h3 className="mb-6 font-mono text-sm text-muted">VERDICTS</h3>
          <div className="space-y-4">
            {VERDICTS.map((v) => (
              <div
                key={v.label}
                data-card
                className="flex items-center gap-5 rounded-xl border border-line bg-surface p-5"
              >
                <span
                  className="inline-flex h-3 w-3 shrink-0 rounded-full"
                  style={{ background: v.color, boxShadow: `0 0 14px ${v.color}` }}
                />
                <div className="min-w-0">
                  <p className="font-mono text-sm font-semibold" style={{ color: v.color }}>
                    {v.label}
                    <span className="ml-3 font-normal text-faint">{v.range}</span>
                  </p>
                  <p className="mt-0.5 text-sm text-muted">{v.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div data-card className="mt-4 rounded-xl border border-line bg-surface p-5">
            <p className="font-mono text-sm font-semibold text-text">
              then: two-layer dedup
              <span className="ml-3 font-normal text-faint">before anything is written</span>
            </p>
            <p className="mt-0.5 text-sm text-muted">
              MinHash LSH catches near-exact copies; cosine similarity over local embeddings
              catches paraphrases. No embedding API calls — it runs on-device.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
