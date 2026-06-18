import { useEffect, useState } from "react";
import { useSmoothScroll } from "./lib/motion";
import Loader from "./components/Loader";
import Nav from "./components/Nav";
import Hero from "./components/Hero";
import Marquee from "./components/Marquee";
import Pipeline from "./components/Pipeline";
import Rubric from "./components/Rubric";
import Byok from "./components/Byok";
import Console from "./components/Console";
import Footer from "./components/Footer";

function ScrollProgress() {
  const [p, setP] = useState(0);
  useEffect(() => {
    const onScroll = () => {
      const h = document.documentElement;
      const max = h.scrollHeight - h.clientHeight;
      setP(max > 0 ? h.scrollTop / max : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <div className="fixed inset-x-0 top-0 z-[60] h-0.5 bg-transparent">
      <div
        className="h-full origin-left bg-gradient-to-r from-generator via-prefilter to-scorer"
        style={{ transform: `scaleX(${p})` }}
      />
    </div>
  );
}

export default function App() {
  useSmoothScroll();

  return (
    <div className="noise">
      <Loader />
      <ScrollProgress />
      <Nav />
      <main>
        <Hero />
        <Marquee />
        <Pipeline />
        <Rubric />
        <Byok />
        <Console />
      </main>
      <Footer />
    </div>
  );
}
