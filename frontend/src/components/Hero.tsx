import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "../lib/scrollState";

gsap.registerPlugin(ScrollTrigger);

const JUDGES = [
  { id: "generator", title: "GENERATOR", sub: "creation", color: "var(--color-generator)" },
  { id: "prefilter", title: "PREFILTER", sub: "logic · binary", color: "var(--color-prefilter)" },
  { id: "scorer", title: "SCORER", sub: "authority · judgment", color: "var(--color-scorer)" },
];

/** One hooded judge silhouette. Reused three times in the fallback scene. */
function Judge({ color }: { color: string }) {
  return (
    <g>
      {/* aura */}
      <ellipse cx="0" cy="-20" rx="120" ry="150" fill={color} opacity="0.16" filter="url(#blur-xl)" />
      <ellipse cx="0" cy="-30" rx="70" ry="100" fill={color} opacity="0.22" filter="url(#blur-lg)" />
      {/* robe */}
      <path
        d="M -55 130 C -50 40 -44 -10 -38 -40 C -34 -68 -28 -88 -20 -97 C -12 -107 -6 -112 0 -112 C 6 -112 12 -107 20 -97 C 28 -88 34 -68 38 -40 C 44 -10 50 40 55 130 Z"
        fill="#0b0d11"
        stroke={color}
        strokeOpacity="0.35"
        strokeWidth="1"
      />
      {/* hood void */}
      <ellipse cx="0" cy="-76" rx="14" ry="19" fill="#000000" />
      <ellipse cx="0" cy="-76" rx="14" ry="19" fill={color} opacity="0.12" />
      {/* chest sigil line */}
      <path d="M -16 -28 L 0 -14 L 16 -28" fill="none" stroke={color} strokeOpacity="0.5" strokeWidth="1" />
      {/* floor ring */}
      <ellipse cx="0" cy="132" rx="64" ry="10" fill="none" stroke={color} strokeOpacity="0.45" strokeWidth="1" />
      <ellipse cx="0" cy="132" rx="64" ry="10" fill={color} opacity="0.08" />
    </g>
  );
}

/** Coded backdrop used until /hero.jpg is dropped into frontend/public/. */
function JudgesFallback() {
  return (
    <svg
      viewBox="0 0 1600 900"
      preserveAspectRatio="xMidYMid slice"
      className="absolute inset-0 h-full w-full"
      aria-hidden
    >
      <defs>
        <filter id="blur-xl" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="46" />
        </filter>
        <filter id="blur-lg" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="22" />
        </filter>
        <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#101216" />
          <stop offset="0.62" stopColor="#0b0d10" />
          <stop offset="1" stopColor="#090a0c" />
        </linearGradient>
        <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0e1013" />
          <stop offset="1" stopColor="#090a0c" />
        </linearGradient>
      </defs>

      {/* wall + floor */}
      <rect width="1600" height="620" fill="url(#wall)" />
      <rect y="620" width="1600" height="280" fill="url(#floor)" />
      <line x1="0" y1="620" x2="1600" y2="620" stroke="#272a30" strokeWidth="1" />

      {/* wall panel seams */}
      {[200, 467, 734, 1001, 1268, 1450].map((x) => (
        <line key={x} x1={x} y1="0" x2={x} y2="620" stroke="#1a1d22" strokeWidth="1" />
      ))}

      {/* circuit traces */}
      <g stroke="#22262c" strokeWidth="1" fill="none">
        <path d="M 80 90 H 300 V 160 H 420" />
        <path d="M 1520 120 H 1320 V 220 H 1180" />
        <path d="M 60 480 H 220 V 380" />
        <path d="M 1540 460 H 1390 V 540" />
        <circle cx="420" cy="160" r="3" />
        <circle cx="1180" cy="220" r="3" />
        <circle cx="220" cy="380" r="3" />
        <circle cx="1390" cy="540" r="3" />
      </g>

      {/* the three judges */}
      <g transform="translate(400 470) scale(1.55)">
        <Judge color="#10B981" />
      </g>
      <g transform="translate(800 450) scale(1.75)">
        <Judge color="#0EA5E9" />
      </g>
      <g transform="translate(1200 470) scale(1.55)">
        <Judge color="#F43F5E" />
      </g>

      {/* floating instruction-pair crystal before the center judge */}
      <g transform="translate(800 560)">
        <polygon
          points="0,-46 40,-23 40,23 0,46 -40,23 -40,-23"
          fill="#0EA5E9"
          opacity="0.1"
        />
        <polygon
          points="0,-46 40,-23 40,23 0,46 -40,23 -40,-23"
          fill="none"
          stroke="#F59E0B"
          strokeOpacity="0.8"
          strokeWidth="1.2"
        />
        <line x1="0" y1="-46" x2="0" y2="46" stroke="#F59E0B" strokeOpacity="0.35" strokeWidth="1" />
        <line x1="-40" y1="-23" x2="40" y2="23" stroke="#F59E0B" strokeOpacity="0.25" strokeWidth="1" />
        <line x1="40" y1="-23" x2="-40" y2="23" stroke="#F59E0B" strokeOpacity="0.25" strokeWidth="1" />
      </g>
    </svg>
  );
}

export default function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const copyRef = useRef<HTMLDivElement>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  const [hasImage, setHasImage] = useState(true);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section || prefersReducedMotion) return;

    const ctx = gsap.context(() => {
      if (copyRef.current) {
        gsap.fromTo(
          copyRef.current.children,
          { y: 22, opacity: 0 },
          { y: 0, opacity: 1, stagger: 0.07, duration: 0.7, ease: "power2.out", delay: 0.1 },
        );
      }
      if (mediaRef.current) {
        // slow Ken Burns on scroll — functional depth, no DOM particles
        gsap.fromTo(
          mediaRef.current,
          { scale: 1 },
          {
            scale: 1.07,
            ease: "none",
            scrollTrigger: { trigger: section, start: "top top", end: "bottom top", scrub: true },
          },
        );
      }
    }, section);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} id="top" className="relative h-[100svh] overflow-hidden">
      {/* backdrop: real render if present, coded scene otherwise */}
      <div ref={mediaRef} className="absolute inset-0">
        <JudgesFallback />
        {hasImage && (
          <img
            src="/hero.jpg"
            alt=""
            aria-hidden
            onError={() => setHasImage(false)}
            className="absolute inset-0 h-full w-full object-cover"
          />
        )}
      </div>

      {/* legibility gradient */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-bg/55 via-transparent to-bg" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_75%_60%_at_50%_45%,transparent_35%,#090A0C_96%)]" />

      <div className="relative z-10 mx-auto flex h-full max-w-6xl flex-col justify-end px-5 pb-20 md:pb-24">
        <div ref={copyRef}>
          <p className="eyebrow mb-4">syntropic · data pipeline authority</p>

          <h1 className="max-w-3xl font-display text-5xl font-bold leading-[1.02] tracking-tight md:text-7xl">
            Every example faces the three judges.
          </h1>

          <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted md:text-lg">
            Syntropic forges fine-tuning data from a taxonomy — generated, screened, scored
            on a five-dimension rubric, and deduped before it earns a row in your dataset.
            Bring your own keys; any OpenAI-compatible provider drops in.
          </p>

          {/* the triad strip */}
          <div className="mt-7 flex flex-wrap gap-2.5">
            {JUDGES.map((j) => (
              <span
                key={j.id}
                className="t-fast inline-flex items-center gap-2 border border-line bg-surface/80 px-3 py-1.5 font-mono text-[11px] tracking-[0.18em]"
                style={{ borderRadius: 4 }}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: j.color, boxShadow: `0 0 8px ${j.color}` }}
                />
                <span style={{ color: j.color }}>{j.title}</span>
                <span className="hidden text-faint sm:inline">{j.sub}</span>
              </span>
            ))}
          </div>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <a
              href="#console"
              className="t-fast rounded-[4px] bg-generator px-6 py-3 font-semibold text-bg hover:shadow-[0_0_28px_rgba(16,185,129,0.35)]"
            >
              Open the console
            </a>
            <a
              href="#pipeline"
              className="t-fast rounded-[4px] border border-line bg-surface/70 px-6 py-3 font-semibold text-text hover:border-faint"
            >
              See the pipeline
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
