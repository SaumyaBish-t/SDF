export default function Footer() {
  return (
    <footer className="relative overflow-hidden border-t border-line">
      <div className="grid-lines absolute inset-0 opacity-50" aria-hidden />
      <div className="relative mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <div className="flex flex-col gap-12 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="eyebrow mb-4">ready when you are</p>
            <h2 className="display max-w-[12ch] text-4xl font-semibold md:text-6xl">
              Forge your <span className="triad-text">dataset.</span>
            </h2>
            <a
              href="#console"
              className="t-fast mt-8 inline-flex rounded-full bg-generator px-6 py-3 text-sm font-semibold text-bg hover:shadow-[0_0_34px_var(--color-generator-soft)]"
            >
              Open the Forge →
            </a>
          </div>

          <div className="grid grid-cols-2 gap-x-12 gap-y-6 font-mono text-sm">
            <div className="space-y-2.5">
              <p className="eyebrow mb-3">project</p>
              <a href="https://github.com/SaumyaBish-t/SDF" target="_blank" rel="noreferrer" className="block text-muted hover:text-text">GitHub</a>
              <a href="#pipeline" className="block text-muted hover:text-text">Pipeline</a>
              <a href="#rubric" className="block text-muted hover:text-text">Rubric</a>
            </div>
            <div className="space-y-2.5">
              <p className="eyebrow mb-3">stack</p>
              <p className="text-muted">FastAPI · asyncio</p>
              <p className="text-muted">DuckDB · LanceDB</p>
              <p className="text-muted">React · Three.js</p>
            </div>
          </div>
        </div>

        <div className="mt-16 flex flex-col items-center justify-between gap-4 border-t border-faint-line pt-8 text-xs text-faint md:flex-row">
          <div className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rotate-45 rounded-[3px] bg-gradient-to-br from-generator via-prefilter to-scorer" />
            <span className="font-display text-sm font-semibold text-text">Syntropic</span>
          </div>
          <p className="font-mono">MIT · taxonomy-driven dataset forge · BYOK</p>
        </div>
      </div>
    </footer>
  );
}
