import { useEffect, useRef } from "react";
import gsap from "gsap";
import { prefersReducedMotion, useReveal } from "../lib/motion";

const DIMS = [
  { label: "factuality", weight: 0.3 },
  { label: "response_quality", weight: 0.25 },
  { label: "instruction_clarity", weight: 0.2 },
  { label: "domain_relevance", weight: 0.15 },
  { label: "format_compliance", weight: 0.1 },
];

const SIZE = 420;
const CX = SIZE / 2;
const CY = SIZE / 2;
const RMAX = 150;
const MAXW = 0.3;

function point(i: number, r: number) {
  const a = -Math.PI / 2 + (i / DIMS.length) * Math.PI * 2;
  return [CX + Math.cos(a) * r, CY + Math.sin(a) * r] as const;
}

export default function Rubric() {
  const ref = useRef<HTMLElement>(null);
  const polyRef = useRef<SVGPolygonElement>(null);
  useReveal(ref);

  const dataPoly = DIMS.map((d, i) => point(i, (d.weight / MAXW) * RMAX).join(",")).join(" ");

  useEffect(() => {
    const poly = polyRef.current;
    if (!poly || prefersReducedMotion) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        poly,
        { scale: 0, transformOrigin: "center", opacity: 0 },
        {
          scale: 1,
          opacity: 1,
          duration: 1.1,
          ease: "elastic.out(1, 0.7)",
          scrollTrigger: { trigger: poly, start: "top 80%", once: true },
        },
      );
      gsap.utils.toArray<HTMLElement>("[data-bar]").forEach((bar) => {
        gsap.fromTo(
          bar,
          { scaleX: 0, transformOrigin: "left" },
          {
            scaleX: 1,
            duration: 1,
            ease: "power3.out",
            scrollTrigger: { trigger: bar, start: "top 90%", once: true },
          },
        );
      });
    }, ref);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={ref} id="rubric" className="relative border-y border-line/60 bg-bg2/40 py-28 md:py-40">
      <div className="mx-auto max-w-7xl px-5 md:px-8">
        <div className="grid items-center gap-14 lg:grid-cols-2">
          {/* radar */}
          <div data-reveal className="order-2 flex justify-center lg:order-1">
            <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full max-w-[560px]" role="img" aria-label="Scorer rubric weights radar">
              {/* rings */}
              {[0.25, 0.5, 0.75, 1].map((f) => (
                <polygon
                  key={f}
                  points={DIMS.map((_, i) => point(i, RMAX * f).join(",")).join(" ")}
                  fill="none"
                  stroke="var(--color-line)"
                  strokeWidth="1"
                />
              ))}
              {/* spokes + labels */}
              {DIMS.map((d, i) => {
                const [x, y] = point(i, RMAX);
                const [lx, ly] = point(i, RMAX + 32);
                return (
                  <g key={d.label}>
                    <line x1={CX} y1={CY} x2={x} y2={y} stroke="var(--color-faint-line)" strokeWidth="1" />
                    <text
                      x={lx}
                      y={ly}
                      fill="var(--color-muted)"
                      fontSize="11"
                      fontFamily="var(--font-mono)"
                      textAnchor={lx > CX + 5 ? "start" : lx < CX - 5 ? "end" : "middle"}
                      dominantBaseline="middle"
                    >
                      {d.label}
                    </text>
                  </g>
                );
              })}
              {/* data polygon */}
              <polygon
                ref={polyRef}
                points={dataPoly}
                fill="url(#triadGrad)"
                stroke="var(--color-generator)"
                strokeWidth="1.5"
              />
              {DIMS.map((d, i) => {
                const [x, y] = point(i, (d.weight / MAXW) * RMAX);
                return <circle key={d.label} cx={x} cy={y} r="4" fill="var(--color-gold)" />;
              })}
              <defs>
                <linearGradient id="triadGrad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="var(--color-generator)" stopOpacity="0.35" />
                  <stop offset="50%" stopColor="var(--color-prefilter)" stopOpacity="0.28" />
                  <stop offset="100%" stopColor="var(--color-scorer)" stopOpacity="0.35" />
                </linearGradient>
              </defs>
            </svg>
          </div>

          {/* copy + weights */}
          <div className="order-1 lg:order-2">
            <div data-reveal>
              <p className="eyebrow mb-4">quality gate</p>
              <h2 className="display fluid-h2">A weighted rubric, not a vibe.</h2>
              <p className="mt-5 max-w-xl text-muted">
                Every survivor is scored on five dimensions. The composite is a weighted sum —
                factuality carries the most, format the least. Accept at{" "}
                <span className="gold-text font-semibold">≥ 4.0</span>, revise at{" "}
                <span className="text-text">≥ 3.0</span>, reject below.
              </p>
            </div>

            <div data-reveal className="mt-10 space-y-5">
              {DIMS.map((d) => (
                <div key={d.label}>
                  <div className="mb-1.5 flex items-baseline justify-between font-mono text-sm">
                    <span className="text-muted">{d.label}</span>
                    <span className="text-gold">{d.weight.toFixed(2)}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-raised">
                    <div
                      data-bar
                      className="h-full rounded-full bg-gradient-to-r from-generator via-prefilter to-scorer"
                      style={{ width: `${(d.weight / MAXW) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
