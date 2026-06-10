export default function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-5 py-10 text-sm text-muted md:flex-row">
        <p className="font-mono text-xs">
          synthetic-data-forge · MIT · generate → screen → score → dedupe → train
        </p>
        <div className="flex items-center gap-6">
          <a
            href="https://github.com/SaumyaBish-t/SDF"
            target="_blank"
            rel="noreferrer"
            className="transition-colors hover:text-text"
          >
            GitHub
          </a>
          <a href="#console" className="transition-colors hover:text-text">
            Console
          </a>
          <a href="#top" className="transition-colors hover:text-text">
            Back to top
          </a>
        </div>
      </div>
    </footer>
  );
}
