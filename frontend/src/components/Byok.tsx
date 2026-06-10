import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "../lib/scrollState";

gsap.registerPlugin(ScrollTrigger);

const ROLES = [
  {
    name: "generator",
    color: "var(--color-ember)",
    spend: "output tokens",
    pick: "a mid-tier model with good structured-JSON output",
    icon: (
      <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" strokeLinejoin="round" />
    ),
  },
  {
    name: "prefilter",
    color: "var(--color-prefilter)",
    spend: "input tokens",
    pick: "the cheapest fast model you can find — verdicts are tiny",
    icon: (
      <>
        <path d="M3 5h18l-7 8v5l-4 2v-7L3 5Z" strokeLinejoin="round" />
      </>
    ),
  },
  {
    name: "scorer",
    color: "var(--color-scorer)",
    spend: "capability",
    pick: "a reasoning-tier model — sycophancy here poisons the dataset",
    icon: (
      <>
        <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
        <path d="M12 7v5l3 3" strokeLinecap="round" strokeLinejoin="round" />
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
        { y: 34, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.8,
          ease: "power3.out",
          stagger: 0.12,
          scrollTrigger: { trigger: el, start: "top 70%" },
        },
      );
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={ref} id="byok" className="relative border-y border-line bg-surface/40 py-28 md:py-36">
      <div className="mx-auto max-w-6xl px-5">
        <p className="mb-3 font-mono text-sm tracking-widest text-faint">BRING YOUR OWN KEYS</p>
        <h2 className="max-w-2xl text-3xl font-bold tracking-tight md:text-4xl">
          Three roles. Three keys. Any provider that speaks{" "}
          <span className="font-mono text-ember">/chat/completions</span>.
        </h2>
        <p className="mt-5 max-w-2xl text-muted">
          Each role takes its own <span className="font-mono text-sm">api_key + model + base_url</span>.
          Mix OpenAI, Anthropic, Groq, DeepSeek, a local proxy — per role, per request.
          Keys live in memory for the duration of a run and are never logged or persisted.
        </p>

        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {ROLES.map((r) => (
            <div
              key={r.name}
              data-role
              className="group rounded-2xl border border-line bg-surface p-6 transition-colors hover:border-faint"
            >
              <div
                className="mb-5 inline-flex h-11 w-11 items-center justify-center rounded-lg border"
                style={{ borderColor: r.color, color: r.color }}
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                  {r.icon}
                </svg>
              </div>
              <h3 className="font-mono text-lg font-semibold" style={{ color: r.color }}>
                {r.name}
              </h3>
              <p className="mt-1 font-mono text-xs text-faint">spends: {r.spend}</p>
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
