import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "../lib/scrollState";

gsap.registerPlugin(ScrollTrigger);

const WEIGHTS = [
  { name: "factuality", w: 0.3 },
  { name: "instruction_clarity", w: 0.2 },
  { name: "response_quality", w: 0.25 },
  { name: "domain_relevance", w: 0.15 },
  { name: "format_compliance", w: 0.1 },
];

const VERDICTS = [
  { label: "accept", range: "composite ≥ 4.0", color: "var(--color-gold)", desc: "pure output — earns a row in the dataset" },
  { label: "revise", range: "3.0 – 3.9", color: "var(--color-muted)", desc: "flagged for regeneration" },
  { label: "reject", range: "< 3.0", color: "var(--color-scorer)", desc: "discarded, logged with full rubric" },
];

/** Minimal radar — 1px glowing outline on a dark grid, no fills. */
function RubricRadar() {
  const CX = 110;
  const CY = 112;
  const R = 84;
  const MAX_W = 0.3;

  const pt = (i: number, v: number): [number, number] => {
    const a = ((-90 + i * 72) * Math.PI) / 180;
    return [CX + R * v * Math.cos(a), CY + R * v * Math.sin(a)];
  };

  const poly = WEIGHTS.map((d, i) => pt(i, d.w / MAX_W).join(",")).join(" ");
  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <svg viewBox="0 0 220 224" className="mx-auto w-full max-w-[340px]" role="img" aria-label="Rubric weight radar chart">
      <defs>
        <filter id="radar-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor="#FF3162" floodOpacity="0.95" />
        </filter>
        <linearGradient id="radar-stroke" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FF3162" />
          <stop offset="1" stopColor="#FBBF24" />
        </linearGradient>
      </defs>

      {/* grid rings */}
      {rings.map((r) => (
        <polygon
          key={r}
          points={WEIGHTS.map((_, i) => pt(i, r).join(",")).join(" ")}
          fill="none"
          stroke="#272A30"
          strokeWidth="1"
        />
      ))}
      {/* axes */}
      {WEIGHTS.map((_, i) => {
        const [x, y] = pt(i, 1);
        return <line key={i} x1={CX} y1={CY} x2={x} y2={y} stroke="#272A30" strokeWidth="1" />;
      })}

      {/* weight polygon — glowing 1.5px outline, gradient stroke, no fill */}
      <polygon points={poly} fill="none" stroke="url(#radar-stroke)" strokeWidth="1.6" filter="url(#radar-glow)" />
      {WEIGHTS.map((d, i) => {
        const [x, y] = pt(i, d.w / MAX_W);
        return <circle key={d.name} cx={x} cy={y} r="2.8" fill="#FF3162" filter="url(#radar-glow)" />;
      })}

      {/* labels */}
      {WEIGHTS.map((d, i) => {
        const [x, y] = pt(i, 1.24);
        const anchor = x < CX - 8 ? "end" : x > CX + 8 ? "start" : "middle";
        return (
          <text
            key={d.name}
            x={x}
            y={y}
            textAnchor={anchor}
            className="fill-[#94A3B8]"
            style={{ font: "500 7.5px 'JetBrains Mono', monospace", letterSpacing: "0.06em" }}
          >
            {d.name}
            <tspan className="fill-[#565F6E]"> {d.w.toFixed(2)}</tspan>
          </text>
        );
      })}
    </svg>
  );
}

/** Terminal-styled accepted-example preview with syntax highlighting. */
function OutputTerminal() {
  const [copied, setCopied] = useState(false);

  const sample = {
    instruction: "My refund hasn't arrived after 10 days. What is going on?",
    response: "I understand the wait has been frustrating. Refunds typically settle in 5–7 business days; at 10 days, let's escalate…",
    metadata: { composite: 4.55, verdict: "accept", node: "billing_dispute·frustrated" },
  };

  const copy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(sample, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="terminal overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-3">
          <span className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-generator" />
            <span className="h-2.5 w-2.5 rounded-full bg-prefilter" />
            <span className="h-2.5 w-2.5 rounded-full bg-scorer" />
          </span>
          <span className="font-mono text-xs text-faint">accepted_000041.jsonl</span>
        </div>
        <button
          onClick={copy}
          className="t-fast cursor-pointer rounded-[4px] border border-line px-2.5 py-1 font-mono text-[11px] text-muted hover:border-faint hover:text-text"
        >
          {copied ? "copied ✓" : "Copy JSON"}
        </button>
      </div>
      <pre className="overflow-x-auto px-5 py-4 text-[13px] leading-relaxed">
        <code>
          <span className="text-faint">{"{"}</span>
          {"\n  "}
          <span className="text-prefilter">"instruction"</span>
          <span className="text-faint">: </span>
          <span className="text-generator">"{sample.instruction}"</span>
          <span className="text-faint">,</span>
          {"\n  "}
          <span className="text-prefilter">"response"</span>
          <span className="text-faint">: </span>
          <span className="text-generator">"{sample.response}"</span>
          <span className="text-faint">,</span>
          {"\n  "}
          <span className="text-prefilter">"metadata"</span>
          <span className="text-faint">: {"{"} </span>
          <span className="text-prefilter">"composite"</span>
          <span className="text-faint">: </span>
          <span className="text-gold">4.55</span>
          <span className="text-faint">, </span>
          <span className="text-prefilter">"verdict"</span>
          <span className="text-faint">: </span>
          <span className="text-gold">"accept"</span>
          <span className="text-faint">, </span>
          <span className="text-prefilter">"node"</span>
          <span className="text-faint">: </span>
          <span className="text-generator">"billing_dispute·frustrated"</span>
          <span className="text-faint"> {"}"}</span>
          {"\n"}
          <span className="text-faint">{"}"}</span>
        </code>
      </pre>
    </div>
  );
}

export default function Gates() {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion) return;

    const ctx = gsap.context(() => {
      gsap.fromTo(
        el.querySelectorAll("[data-card]"),
        { y: 14, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.3,
          ease: "power1.out",
          stagger: 0.07,
          scrollTrigger: { trigger: el, start: "top 65%" },
        },
      );
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={ref} id="gates" className="relative mx-auto max-w-6xl px-5 py-28 md:py-36">
      <p className="eyebrow mb-4">rubric score</p>
      <h2 className="max-w-2xl font-display text-3xl font-bold tracking-tight md:text-4xl">
        Five dimensions. One composite. Three possible fates.
      </h2>

      <div className="mt-12 grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        {/* radar panel */}
        <div data-card className="panel p-6 md:p-8">
          <p className="eyebrow mb-6">scorer · weight geometry</p>
          <RubricRadar />
          <p className="mt-6 text-sm leading-relaxed text-muted">
            The scorer returns a 1–5 score per dimension. The weighted composite decides the
            verdict — and the full rubric is persisted with every example, accepted or not.
          </p>
        </div>

        {/* verdicts */}
        <div className="flex flex-col gap-5">
          {VERDICTS.map((v) => (
            <div key={v.label} data-card className="panel flex items-center gap-5 p-5">
              <span
                className="inline-flex h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: v.color, boxShadow: `0 0 12px ${v.color}` }}
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
          <div data-card className="panel p-5">
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

      {/* terminal */}
      <div data-card className="mt-5">
        <OutputTerminal />
      </div>
    </section>
  );
}
