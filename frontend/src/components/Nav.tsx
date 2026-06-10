const LINKS = [
  { href: "#pipeline", label: "Pipeline" },
  { href: "#gates", label: "Quality gates" },
  { href: "#byok", label: "BYOK" },
  { href: "#console", label: "Console" },
];

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden>
      <path
        d="M16 7 L25 22 L7 22 Z"
        fill="none"
        stroke="#272A30"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="7" r="3" fill="#10B981" />
      <circle cx="25" cy="22" r="3" fill="#0EA5E9" />
      <circle cx="7" cy="22" r="3" fill="#F43F5E" />
      <circle cx="16" cy="17.5" r="2.2" fill="#F59E0B" />
    </svg>
  );
}

export default function Nav() {
  return (
    <header className="glass fixed inset-x-0 top-0 z-50 border-b border-line">
      <nav className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
        <a href="#top" className="flex items-center gap-2.5 font-display text-[17px] font-semibold tracking-tight">
          <Mark />
          <span>Syntropic</span>
        </a>

        <div className="hidden items-center gap-7 text-sm text-muted md:flex">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} className="t-fast hover:text-text">
              {l.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <a
            href="https://github.com/SaumyaBish-t/SDF"
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub repository"
            className="t-fast text-muted hover:text-text"
          >
            <svg viewBox="0 0 16 16" className="h-5 w-5" fill="currentColor" aria-hidden>
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
            </svg>
          </a>
          <a
            href="#console"
            className="t-fast rounded-[4px] bg-generator px-3.5 py-1.5 text-sm font-semibold text-bg hover:shadow-[0_0_20px_rgba(16,185,129,0.35)]"
          >
            Start a run
          </a>
        </div>
      </nav>
    </header>
  );
}
