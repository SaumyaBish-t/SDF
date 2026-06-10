import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "../lib/scrollState";

gsap.registerPlugin(ScrollTrigger);

const ROLES = [
  {
    name: "generator",
    color: "var(--color-generator)",
    spend: "output tokens",
    pick: "a mid-tier model with good structured-JSON output",
    icon: <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" strokeLinejoin="round" />,
  },
  {
    name: "prefilter",
    color: "var(--color-prefilter)",
    spend: "input tokens",
    pick: "the cheapest fast model you can find — verdicts are tiny",
    icon: <path d="M3 5h18l-7 8v5l-4 2v-7L3 5Z" strokeLinejoin="round" />,
  },
  {
    name: "scorer",
    color: "var(--color-scorer)",
    spend: "capability",
    pick: "a reasoning-tier model — sycophancy here poisons the dataset",
    icon: (
      <>
        <path d="M12 3v18M5 7l7-4 7 4" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M5 7l-2 7a4 4 0 0 0 8 0L9 7M19 7l-2 7a4 4 0 0 0 8 0l-2-7" strokeLinecap="round" strokeLinejoin="round" transform="scale(0.78) translate(3.4 3)" />
      </>
    ),
  },
];

export default function Byok() {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        el.querySelectorAll("[data-role]"),
        { y: 14, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.3,
          ease: "power1.out",
          stagger: 0.08,
          scrollTrigger: { trigger: el, start: "top 70%" },
        },
      );
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={ref} id="byok" className="relative border-y border-line bg-surface/40 py-28 md:py-36">
      <div className="mx-auto max-w-6xl px-5">
        <p className="eyebrow mb-4">bring your own keys</p>
        <h2 className="max-w-2xl font-display text-3xl font-bold tracking-tight md:text-4xl">
          Three judges. Three keys. Any provider that speaks{" "}
          <span className="font-mono text-generator">/chat/completions</span>.
        </h2>
        <p className="mt-5 max-w-2xl text-muted">
          Each role takes its own <span className="font-mono text-sm">api_key + model + base_url</span>.
          Mix OpenAI, Anthropic, Groq, DeepSeek, a local proxy — per role, per request.
          Keys live in memory for the duration of a run and are never logged or persisted.
        </p>

        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {ROLES.map((r) => (
            <div key={r.name} data-role className="panel t-fast group p-6 hover:border-faint">
              <div
                className="mb-5 inline-flex h-11 w-11 items-center justify-center rounded-[6px] border"
                style={{ borderColor: r.color, color: r.color }}
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                  {r.icon}
                </svg>
              </div>
              <h3 className="font-mono text-lg font-semibold" style={{ color: r.color }}>
                {r.name}
              </h3>
              <p className="eyebrow mt-1.5">spends · {r.spend}</p>
              <p className="mt-3 text-sm leading-relaxed text-muted">Pick {r.pick}.</p>
              <div className="mt-5 space-y-1.5 font-mono text-xs text-faint">
                <p><span className="text-muted">api_key</span> = sk-••••••••</p>
                <p><span className="text-muted">model</span> = any</p>
                <p><span className="text-muted">base_url</span> = any /v1</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
