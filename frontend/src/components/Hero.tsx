import { useEffect, useRef } from "react";
import gsap from "gsap";
import { Forge } from "../three/forge";
import { prefersReducedMotion } from "../lib/motion";

export default function Hero() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rootRef = useRef<HTMLElement>(null);

  // WebGL forge — skippable via ?static / localStorage for static capture & low-end
  useEffect(() => {
    if (!canvasRef.current) return;
    const noForge =
      new URLSearchParams(window.location.search).has("static") ||
      localStorage.getItem("sdf-no-forge") === "1";
    if (noForge) return;
    const forge = new Forge(canvasRef.current, prefersReducedMotion);
    return () => forge.dispose();
  }, []);

  // GSAP intro timeline
  useEffect(() => {
    const el = rootRef.current;
    if (!el || prefersReducedMotion) return;
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: "expo.out" } });
      tl.from("[data-hero-line] > span", {
        yPercent: 120,
        duration: 1.1,
        stagger: 0.09,
        delay: 0.35,
      })
        .from("[data-hero-eyebrow]", { y: 16, opacity: 0, duration: 0.8 }, "-=0.7")
        .from("[data-hero-sub]", { y: 20, opacity: 0, duration: 0.8 }, "-=0.6")
        .from("[data-hero-cta]", { y: 18, opacity: 0, duration: 0.7, stagger: 0.1 }, "-=0.6")
        .from("[data-hero-stat]", { y: 14, opacity: 0, duration: 0.6, stagger: 0.08 }, "-=0.5")
        .to("[data-hero-scroll]", { opacity: 1, duration: 0.6 }, "-=0.3");
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} id="top" className="relative min-h-[100svh] overflow-hidden">
      {/* WebGL canvas */}
      <canvas
        ref={canvasRef}
        className="pointer-events-none absolute inset-0 h-full w-full"
        aria-hidden
      />
      {/* legibility veil + grid */}
      <div className="grid-lines absolute inset-0 opacity-60" aria-hidden />
      <div
        className="absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_60%,transparent,rgba(5,7,10,0.72))]"
        aria-hidden
      />

      <div className="relative mx-auto flex min-h-[100svh] max-w-7xl flex-col justify-center px-5 pt-24 pb-16 md:px-8">
        <p data-hero-eyebrow className="eyebrow mb-6 flex items-center gap-3">
          <span className="inline-block h-px w-8 bg-faint" />
          Taxonomy-driven dataset forge · BYOK
        </p>

        <h1 className="display fluid-hero max-w-[14ch]">
          <span data-hero-line className="block overflow-hidden">
            <span className="block">Forge data</span>
          </span>
          <span data-hero-line className="block overflow-hidden">
            <span className="block">
              you can <span className="triad-text">train on.</span>
            </span>
          </span>
        </h1>

        <p data-hero-sub className="mt-7 max-w-xl text-base leading-relaxed text-muted md:text-lg">
          Point Syntropic at a domain taxonomy. Three judges — a{" "}
          <span className="text-generator">generator</span>, a{" "}
          <span className="text-prefilter">prefilter</span> and a{" "}
          <span className="text-scorer">scorer</span> — generate, screen, rate and dedupe every
          example into a clean JSONL. Bring your own keys.
        </p>

        <div className="mt-9 flex flex-wrap items-center gap-3">
          <a
            data-hero-cta
            href="#console"
            className="t-fast group rounded-full bg-generator px-6 py-3 text-sm font-semibold text-bg hover:shadow-[0_0_34px_var(--color-generator-soft)]"
          >
            Open the Forge
            <span className="ml-1.5 inline-block transition-transform group-hover:translate-x-1">→</span>
          </a>
          <a
            data-hero-cta
            href="#pipeline"
            className="t-fast rounded-full border border-line px-6 py-3 text-sm font-semibold text-text hover:border-faint hover:bg-raised"
          >
            See how it works
          </a>
        </div>

        <dl className="mt-14 flex flex-wrap gap-x-10 gap-y-6">
          {[
            ["5-dim", "weighted rubric"],
            ["2-layer", "MinHash + cosine dedup"],
            ["any /v1", "OpenAI · Anthropic · Groq …"],
          ].map(([k, v]) => (
            <div data-hero-stat key={k}>
              <dt className="font-display text-2xl font-semibold text-text">{k}</dt>
              <dd className="mt-0.5 text-xs text-muted">{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div
        data-hero-scroll
        className="absolute bottom-6 left-1/2 -translate-x-1/2 opacity-0"
        aria-hidden
      >
        <div className="flex flex-col items-center gap-2">
          <span className="eyebrow">scroll</span>
          <span className="flex h-9 w-5 justify-center rounded-full border border-line pt-1.5">
            <span className="h-1.5 w-1 animate-bounce rounded-full bg-faint" />
          </span>
        </div>
      </div>
    </section>
  );
}
