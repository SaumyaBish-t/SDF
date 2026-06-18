import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { prefersReducedMotion } from "../lib/motion";

export default function Loader() {
  const ref = useRef<HTMLDivElement>(null);
  const [gone, setGone] = useState(prefersReducedMotion);

  useEffect(() => {
    if (prefersReducedMotion) return;
    const el = ref.current;
    if (!el) return;
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ onComplete: () => setGone(true) });
      tl.to("[data-count]", {
        innerText: 100,
        duration: 1.3,
        snap: { innerText: 1 },
        ease: "power2.inOut",
        onUpdate() {
          const t = this.targets()[0] as HTMLElement;
          t.textContent = String(Math.round(Number(t.textContent) || 0)).padStart(3, "0");
        },
      })
        .to("[data-bar-fill]", { scaleX: 1, duration: 1.3, ease: "power2.inOut" }, 0)
        .to("[data-loader-inner]", { yPercent: -40, opacity: 0, duration: 0.6, ease: "power3.in" }, "+=0.15")
        .to(el, { yPercent: -100, duration: 0.8, ease: "expo.inOut" }, "-=0.2");
    }, el);
    return () => ctx.revert();
  }, []);

  if (gone) return null;

  return (
    <div ref={ref} className="fixed inset-0 z-[100] flex items-center justify-center bg-bg">
      <div data-loader-inner className="flex w-full max-w-md flex-col items-center gap-6 px-6">
        <div className="flex items-center gap-3">
          <span className="h-3.5 w-3.5 rotate-45 rounded-[3px] bg-gradient-to-br from-generator via-prefilter to-scorer" />
          <span className="font-display text-xl font-semibold tracking-tight">Syntropic</span>
        </div>
        <div className="h-px w-full overflow-hidden bg-line">
          <div data-bar-fill className="h-full origin-left scale-x-0 bg-gradient-to-r from-generator via-prefilter to-scorer" />
        </div>
        <p className="font-mono text-xs text-faint">
          forging <span data-count className="text-muted">000</span> / 100
        </p>
      </div>
    </div>
  );
}
