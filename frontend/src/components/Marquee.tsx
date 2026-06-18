const ITEMS = [
  "asyncio fan-out",
  "MinHash LSH",
  "LanceDB cosine",
  "Vendi diversity",
  "5-dim rubric",
  "DuckDB metadata",
  "atomic checkpoints",
  "SecretStr keys",
  "back-pressured queues",
  "sentence-transformers",
];

export default function Marquee() {
  return (
    <section className="relative border-y border-line/60 bg-bg2/60 py-5" aria-hidden>
      <div className="flex overflow-hidden [mask-image:linear-gradient(to_right,transparent,#000_8%,#000_92%,transparent)]">
        <div className="flex shrink-0 animate-[marquee_38s_linear_infinite] items-center gap-10 pr-10">
          {[...ITEMS, ...ITEMS].map((it, i) => (
            <span key={i} className="flex items-center gap-10 whitespace-nowrap">
              <span className="font-mono text-sm text-muted">{it}</span>
              <span className="h-1 w-1 rounded-full bg-generator/70" />
            </span>
          ))}
        </div>
        <div
          className="flex shrink-0 animate-[marquee_38s_linear_infinite] items-center gap-10 pr-10"
          aria-hidden
        >
          {[...ITEMS, ...ITEMS].map((it, i) => (
            <span key={i} className="flex items-center gap-10 whitespace-nowrap">
              <span className="font-mono text-sm text-muted">{it}</span>
              <span className="h-1 w-1 rounded-full bg-generator/70" />
            </span>
          ))}
        </div>
      </div>
      <style>{`@keyframes marquee{from{transform:translateX(0)}to{transform:translateX(-100%)}}`}</style>
    </section>
  );
}
