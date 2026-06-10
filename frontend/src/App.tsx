import { useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";

import Nav from "./components/Nav";
import Hero from "./components/Hero";
import Pipeline from "./components/Pipeline";
import Gates from "./components/Gates";
import Byok from "./components/Byok";
import Console from "./components/Console";
import Footer from "./components/Footer";
import { prefersReducedMotion } from "./lib/scrollState";

gsap.registerPlugin(ScrollTrigger);

export default function App() {
  useEffect(() => {
    if (prefersReducedMotion) return;

    // Lenis drives scrolling; GSAP's ticker drives Lenis. One rAF loop total.
    const lenis = new Lenis({ duration: 1.1, anchors: true });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(tick);
      lenis.destroy();
    };
  }, []);

  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Pipeline />
        <Gates />
        <Byok />
        <Console />
      </main>
      <Footer />
    </>
  );
}
