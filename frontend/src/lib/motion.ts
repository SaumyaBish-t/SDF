import { useEffect } from "react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export const prefersReducedMotion =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Lenis smooth scroll, driven by GSAP's ticker and synced to ScrollTrigger.
 * No-op under prefers-reduced-motion (native scroll stays).
 */
export function useSmoothScroll() {
  useEffect(() => {
    if (prefersReducedMotion) return;

    const lenis = new Lenis({
      duration: 1.1,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      touchMultiplier: 1.4,
    });

    lenis.on("scroll", ScrollTrigger.update);
    const onTick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(onTick);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(onTick);
      lenis.destroy();
    };
  }, []);
}

/**
 * Reveal every [data-reveal] inside `root` as it scrolls into view by toggling
 * the `.is-in` class (CSS owns the transition). Honors reduced motion.
 */
export function useReveal(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const nodes = Array.from(el.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (prefersReducedMotion) {
      nodes.forEach((n) => n.classList.add("is-in"));
      return;
    }
    const triggers = nodes.map((node) => {
      const delay = Number(node.dataset.reveal) || 0;
      node.style.transitionDelay = `${delay}ms`;
      return ScrollTrigger.create({
        trigger: node,
        start: "top 88%",
        once: true,
        onEnter: () => node.classList.add("is-in"),
      });
    });
    ScrollTrigger.refresh();
    return () => triggers.forEach((t) => t.kill());
  }, [root]);
}
