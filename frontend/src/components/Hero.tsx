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
  const imgRef     = useRef<HTMLImageElement>(null);
  const [imgState, setImgState] = useState<"loading" | "ok" | "fail">("loading");

  useEffect(() => {
    const section = sectionRef.current;
    if (!section || prefersReducedMotion) return;
    const ctx = gsap.context(() => {
      if (imgRef.current) {
        gsap.fromTo(
          imgRef.current,
          { opacity: 0, scale: 0.985 },
          { opacity: 1, scale: 1, duration: 1.0, ease: "power2.out", delay: 0.1 },
        );
        gsap.to(imgRef.current, {
          y: -40,
          ease: "none",
          scrollTrigger: { trigger: section, start: "top top", end: "bottom top", scrub: true },
        });
      }
      if (copyRef.current) {
        gsap.fromTo(
          copyRef.current.children,
          { y: 18, opacity: 0 },
          {
            y: 0,
            opacity: 1,
            stagger: 0.06,
            duration: 0.6,
            ease: "power2.out",
            scrollTrigger: { trigger: copyRef.current, start: "top 85%" },
          },
        );
      }
    }, section);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} id="top" className="relative pt-20">
      {/* ── hero image, centered ─────────────────────────────────────────── */}
      <div className="relative mx-auto max-w-6xl px-5">
        {/* corner brackets — frame the image like a tactical display */}
        <div className="relative overflow-hidden rounded-[6px] border border-line bg-surface">
          {/* aspect-ratio box — keeps layout calm while the image loads */}
          <div className="relative aspect-[16/9] w-full">
            {imgState !== "ok" && (
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_60%_at_22%_55%,rgba(0,255,149,0.30),transparent_60%),radial-gradient(ellipse_50%_60%_at_50%_50%,rgba(20,200,255,0.35),transparent_60%),radial-gradient(ellipse_60%_60%_at_78%_55%,rgba(255,49,98,0.30),transparent_60%)]" />
            )}
            <img
              ref={imgRef}
              src="/hero.png"
              alt="Three robed judges — Generator (emerald), Prefilter (cyan), Scorer (crimson) — adjudicating a floating instruction-response pair in a circuit-lit chamber"
              onLoad={() => setImgState("ok")}
              onError={() => setImgState("fail")}
              className={`absolute inset-0 h-full w-full object-cover object-center transition-opacity duration-700 ${
                imgState === "ok" ? "opacity-100" : "opacity-0"
              }`}
              style={{ filter: "saturate(1.15) contrast(1.05) brightness(1.03)" }}
              fetchPriority="high"
              decoding="async"
            />
            {/* mix-screen halo lifts triad auras */}
            <div className="pointer-events-none absolute inset-0 mix-blend-screen opacity-25 bg-[radial-gradient(ellipse_28%_45%_at_22%_50%,rgba(0,255,149,0.45),transparent_70%),radial-gradient(ellipse_28%_45%_at_55%_42%,rgba(20,200,255,0.45),transparent_70%),radial-gradient(ellipse_28%_45%_at_82%_50%,rgba(255,49,98,0.45),transparent_70%)]" />
            {/* soft inner edge feathering so the image dissolves into the panel */}
            <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_60px_rgba(10,14,20,0.55)]" />
          </div>
          {/* tactical corner ticks */}
          {[
            { c: "top-2 left-2 border-t border-l", color: "var(--color-generator)" },
            { c: "top-2 right-2 border-t border-r", color: "var(--color-prefilter)" },
            { c: "bottom-2 left-2 border-b border-l", color: "var(--color-prefilter)" },
            { c: "bottom-2 right-2 border-b border-r", color: "var(--color-scorer)" },
          ].map((t, i) => (
            <span
              key={i}
              aria-hidden
              className={`absolute h-4 w-4 ${t.c}`}
              style={{ borderColor: t.color }}
            />
          ))}
        </div>
        {/* ambient glow under the image */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-10 -bottom-10 h-32 opacity-60 blur-3xl"
          style={{
            background:
              "radial-gradient(ellipse 50% 100% at 18% 50%, rgba(0,255,149,0.35), transparent 70%), radial-gradient(ellipse 50% 100% at 50% 50%, rgba(20,200,255,0.40), transparent 70%), radial-gradient(ellipse 50% 100% at 82% 50%, rgba(255,49,98,0.35), transparent 70%)",
          }}
        />
      </div>

      {/* ── copy, centered, AFTER the hero ───────────────────────────────── */}
      <div className="relative mx-auto mt-20 max-w-3xl px-5 pb-24 text-center md:mt-24 md:pb-32">
        <div ref={copyRef}>
          <p className="eyebrow mb-4" style={{ color: "var(--color-prefilter)" }}>
            syntropic · data pipeline authority
          </p>
          <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight md:text-6xl">
            Every example faces{" "}
            <span className="triad-text">the three judges.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted md:text-lg">
            Syntropic forges fine-tuning data from a taxonomy — generated, screened,
            scored on a five-dimension rubric, and deduped before it earns a row in your
            dataset. Bring your own keys; any OpenAI-compatible provider drops in.
          </p>

          {/* triad chips */}
          <div className="mt-8 flex flex-wrap justify-center gap-2">
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

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
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
    </section>
  );
}
