import { Suspense, lazy, useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { heroScroll, pointer, prefersReducedMotion } from "../lib/scrollState";

const HeroScene = lazy(() => import("./HeroScene"));

gsap.registerPlugin(ScrollTrigger);

export default function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const copyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

    const onMove = (e: PointerEvent) => {
      pointer.x = (e.clientX / window.innerWidth - 0.5) * 2;
      pointer.y = (e.clientY / window.innerHeight - 0.5) * 2;
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    const ctx = gsap.context(() => {
      // feed hero scroll progress to the 3D rig
      ScrollTrigger.create({
        trigger: section,
        start: "top top",
        end: "bottom top",
        onUpdate: (self) => {
          heroScroll.progress = self.progress;
        },
      });

      if (!prefersReducedMotion && copyRef.current) {
        // entrance
        gsap.fromTo(
          copyRef.current.children,
          { y: 28, opacity: 0 },
          { y: 0, opacity: 1, stagger: 0.09, duration: 0.9, ease: "power3.out", delay: 0.15 },
        );
        // parallax away on scroll
        gsap.to(copyRef.current, {
          y: -90,
          opacity: 0.15,
          ease: "none",
          scrollTrigger: { trigger: section, start: "top top", end: "75% top", scrub: true },
        });
      }
    }, section);

    return () => {
      window.removeEventListener("pointermove", onMove);
      ctx.revert();
    };
  }, []);

  return (
    <section ref={sectionRef} id="top" className="relative h-[100svh] overflow-hidden">
      {/* 3D pipeline visual */}
      <Suspense fallback={<div className="absolute inset-0 grid-bg" />}>
        <HeroScene />
      </Suspense>

      {/* vignette so text stays readable over the scene */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_55%_at_50%_46%,transparent_20%,#07090D_92%)]" />

      <div className="relative z-10 mx-auto flex h-full max-w-6xl flex-col items-center justify-center px-5 text-center">
        <div ref={copyRef}>
          <p className="mb-5 inline-block rounded-full border border-line bg-surface/60 px-4 py-1.5 font-mono text-xs tracking-wider text-muted">
            generate <span className="text-ember">→</span> screen{" "}
            <span className="text-prefilter">→</span> score{" "}
            <span className="text-scorer">→</span> dedupe{" "}
            <span className="text-accept">→</span> train
          </p>

          <h1 className="mx-auto max-w-4xl text-5xl font-extrabold leading-[1.05] tracking-tight md:text-7xl">
            Fine-tuning data, <span className="gradient-text ember-glow">forged</span> not
            scraped.
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted md:text-lg">
            A taxonomy-driven pipeline that generates, critiques, scores and dedupes
            instruction data — every example fights for its place in your dataset.
            Bring your own keys; any OpenAI-compatible provider drops in.
          </p>

          <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
            <a
              href="#console"
              className="rounded-lg bg-ember px-6 py-3 font-semibold text-bg transition-all hover:bg-ember-hot hover:shadow-[0_0_36px_rgba(251,146,60,0.4)]"
            >
              Open the console
            </a>
            <a
              href="#pipeline"
              className="rounded-lg border border-line bg-surface/70 px-6 py-3 font-semibold text-text transition-colors hover:border-faint"
            >
              See how it works
            </a>
          </div>
        </div>
      </div>

      {/* scroll hint */}
      <div className="absolute bottom-7 left-1/2 z-10 -translate-x-1/2 text-faint">
        <svg viewBox="0 0 24 24" className="h-6 w-6 animate-bounce" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M12 5v14m0 0-6-6m6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </section>
  );
}
