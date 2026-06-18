import { useEffect, useState } from "react";

const LINKS = [
  { href: "#pipeline", label: "Pipeline" },
  { href: "#rubric", label: "Rubric" },
  { href: "#byok", label: "BYOK" },
  { href: "#console", label: "Console" },
];

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`t-fast fixed inset-x-0 top-0 z-50 ${
        scrolled ? "glass border-b border-line/70" : "border-b border-transparent"
      }`}
    >
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3.5 md:px-8">
        <a href="#top" className="group flex items-center gap-2.5" aria-label="Syntropic home">
          <span className="relative flex h-7 w-7 items-center justify-center">
            <span className="absolute inset-0 rounded-[7px] bg-generator/20 blur-[6px]" />
            <span className="relative h-3 w-3 rotate-45 rounded-[3px] bg-gradient-to-br from-generator via-prefilter to-scorer" />
          </span>
          <span className="font-display text-[1.05rem] font-semibold tracking-tight">
            Syntropic
          </span>
        </a>

        <div className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="t-fast rounded-full px-3.5 py-1.5 text-sm text-muted hover:bg-raised hover:text-text"
            >
              {l.label}
            </a>
          ))}
          <a
            href="#console"
            className="t-fast ml-2 rounded-full bg-text px-4 py-1.5 text-sm font-semibold text-bg hover:bg-generator hover:shadow-[0_0_24px_var(--color-generator-soft)]"
          >
            Open the Forge
          </a>
        </div>

        <button
          onClick={() => setOpen((v) => !v)}
          className="t-fast flex h-9 w-9 items-center justify-center rounded-full border border-line text-text md:hidden"
          aria-label="Toggle menu"
          aria-expanded={open}
        >
          <span className="text-lg leading-none">{open ? "×" : "≡"}</span>
        </button>
      </nav>

      {open && (
        <div className="glass border-t border-line/60 md:hidden">
          <div className="flex flex-col px-5 py-3">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="t-fast border-b border-faint-line py-3 text-sm text-muted hover:text-text"
              >
                {l.label}
              </a>
            ))}
            <a
              href="#console"
              onClick={() => setOpen(false)}
              className="mt-3 rounded-full bg-text px-4 py-2.5 text-center text-sm font-semibold text-bg"
            >
              Open the Forge
            </a>
          </div>
        </div>
      )}
    </header>
  );
}
