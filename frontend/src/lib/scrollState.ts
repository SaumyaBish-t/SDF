/** Mutable refs shared between GSAP ScrollTrigger (DOM world) and the R3F
 *  scene (render-loop world). Plain module-level objects — no re-renders. */

export const heroScroll = { progress: 0 };

export const pointer = { x: 0, y: 0 };

export const prefersReducedMotion =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;
