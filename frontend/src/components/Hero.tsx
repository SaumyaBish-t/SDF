import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "../lib/scrollState";

gsap.registerPlugin(ScrollTrigger);

const JUDGES = [
  { id: "generator", title: "GENERATOR", sub: "creation",             color: "var(--color-generator)" },
  { id: "prefilter", title: "PREFILTER", sub: "logic · binary",       color: "var(--color-prefilter)" },
  { id: "scorer",    title: "SCORER",    sub: "authority · judgment", color: "var(--color-scorer)" },
];

export default function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const copyRef    = useRef<HTMLDivElement>(null);
  const mediaRef   = useRef<HTMLDivElement>(null);
  const [imgState, setImgState] = useState<"loading" | "ok" | "fail">("loading");

  useEffect(() => {
    const section = sectionRef.current;
    if (!section || prefersReducedMotion) return;
    const ctx = gsap.context(() => {
      if (copyRef.current) {
        gsap.fromTo(
          copyRef.current.children,
          { y: 16, opacity: 0 },
          { y: 0, opacity: 1, stagger: 0.06, duration: 0.55, ease: "power2.out", delay: 0.2 },
        );
      }
      if (mediaRef.current) {
        gsap.fromTo(
          mediaRef.current,
          { scale: 1.0 },
          {
            scale: 1.08,
            ease: "none",
            scrollTrigger: { trigger: section, start: "top top", end: "bottom top", scrub: true },
          },
        );
      }
    }, section);
    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={sectionRef}
      id="top"
      className="relative grid h-[100svh] min-h-[680px] overflow-hidden md:grid-cols-[minmax(0,520px)_1fr]"
    >
      {/* ── LEFT: copy column, clean obsidian background ───────────────────── */}
      <div className="relative z-20 flex flex-col justify-center bg-bg px-6 pt-20 pb-10 md:px-12">
        {/* faint triad rim along the right edge — visually hands off to the image */}
        <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-32 bg-gradient-to-l from-bg via-bg/30 to-transparent md:block" />
        <div ref={copyRef} className="relative">
          <p className="eyebrow mb-4" style={{ color: "var(--color-prefilter)" }}>
            syntropic · data pipeline authority
          </p>
          <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight md:text-6xl">
            Every example faces{" "}
            <span className="triad-text">the three judges.</span>
          </h1>
          <p className="mt-5 max-w-md text-sm leading-relaxed text-muted md:text-base">
            Syntropic forges fine-tuning data from a taxonomy — generated, screened,
            scored on a five-dimension rubric, and deduped before it earns a row in your
            dataset. Bring your own keys; any OpenAI-compatible provider drops in.
          </p>

          {/* triad chips */}
          <div className="mt-7 flex flex-wrap gap-2">
            {JUDGES.map((j) => (
              <span
                key={j.id}
                className="t-fast inline-flex items-center gap-2 border bg-surface/60 px-3 py-1.5 font-mono text-[11px] tracking-[0.18em]"
                style={{ borderRadius: 4, borderColor: `color-mix(in srgb, ${j.color} 40%, var(--color-line))` }}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: j.color, boxShadow: `0 0 10px ${j.color}` }}
                />
                <span style={{ color: j.color }}>{j.title}</span>
                <span className="hidden text-faint sm:inline">{j.sub}</span>
              </span>
            ))}
          </div>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <a
              href="#console"
              className="t-fast rounded-[4px] bg-generator px-6 py-3 font-semibold text-bg hover:shadow-[0_0_36px_rgba(0,255,149,0.55)]"
            >
              Open the console
            </a>
            <a
              href="#pipeline"
              className="t-fast rounded-[4px] border border-line bg-surface/70 px-6 py-3 font-semibold text-text hover:border-prefilter hover:text-prefilter"
            >
              See the pipeline
            </a>
          </div>
        </div>
      </div>

      {/* ── RIGHT: hero artwork, full-bleed, color-graded ──────────────────── */}
      <div ref={mediaRef} className="relative">
        {imgState !== "ok" && (
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_60%_at_22%_55%,rgba(0,255,149,0.30),transparent_60%),radial-gradient(ellipse_50%_60%_at_50%_50%,rgba(20,200,255,0.35),transparent_60%),radial-gradient(ellipse_60%_60%_at_78%_55%,rgba(255,49,98,0.30),transparent_60%)]" />
        )}
        <img
          src="/hero.png"
          alt="Three robed judges — Generator (emerald), Prefilter (cyan), Scorer (crimson) — adjudicating a floating instruction-response pair in a circuit-lit chamber"
          onLoad={() => setImgState("ok")}
          onError={() => setImgState("fail")}
          className={`absolute inset-0 h-full w-full object-cover object-[50%_28%] transition-opacity duration-700 ${
            imgState === "ok" ? "opacity-100" : "opacity-0"
          }`}
          style={{ filter: "saturate(1.18) contrast(1.06) brightness(1.04)" }}
          fetchPriority="high"
          decoding="async"
        />

        {/* light triad halo — image stays the star */}
        <div className="pointer-events-none absolute inset-0 mix-blend-screen opacity-15 bg-[radial-gradient(ellipse_28%_45%_at_22%_50%,rgba(0,255,149,0.4),transparent_70%),radial-gradient(ellipse_28%_45%_at_55%_42%,rgba(20,200,255,0.4),transparent_70%),radial-gradient(ellipse_28%_45%_at_82%_50%,rgba(255,49,98,0.4),transparent_70%)]" />

        {/* seam from copy column — soft left edge */}
        <div className="pointer-events-none absolute inset-y-0 left-0 hidden w-28 bg-gradient-to-r from-bg to-transparent md:block" />
        {/* fade into page below */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-bg to-transparent" />

        {/* mobile-only: re-show the legibility fade because copy column is no longer side-by-side */}
        <div className="pointer-events-none absolute inset-0 bg-bg/55 md:hidden" />
      </div>
    </section>
  );
}
