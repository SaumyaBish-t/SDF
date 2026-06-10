# ⚒️ Synthetic Data Forge

A taxonomy-driven pipeline that produces fine-tuning datasets you can actually train on.

![License](https://img.shields.io/badge/License-MIT-blue) ![Pipeline](https://img.shields.io/badge/Pipeline-asyncio-orange) ![API](https://img.shields.io/badge/API-FastAPI-009688) ![LLM](https://img.shields.io/badge/LLM-Bring%20Your%20Own-success)

Synthetic Data Forge turns a domain taxonomy and a sample target into a curated JSONL of `(instruction, response)` pairs that have been generated, screened, scored on a 5-dimension rubric, and deduped end-to-end. Every accepted example also lands in DuckDB metadata and a LanceDB vector store, so you can audit coverage and run diversity analytics before you spend a GPU-hour on training.

The whole system is **provider-agnostic and per-request BYOK**: each of the three pipeline roles — generator, prefilter, scorer — takes its own `(api_key, model, base_url)`, so you can mix providers per role, swap models at runtime, or expose a frontend that lets each user supply their own keys without ever touching the server's `.env`.

---

## Architecture

```
                  ┌─────────────────────┐
                  │  taxonomy/<domain>  │   topic / tone / depth / ...
                  └──────────┬──────────┘
                             │ seed sampler
                             │ (min-coverage guarantee)
                             ▼
                  ┌─────────────────────┐
                  │      NodeSets       │   sampled scenarios
                  └──────────┬──────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
   Generator              Prefilter             Scorer
   ─────────              ─────────             ──────
   meta-prompt            pass / fail           5-dim rubric
   batched JSON           format · relevance    factuality · clarity ·
   array out              · coherence           quality · relevance ·
                                                format
   role: gen              role: prefilter       role: scorer
   model: ANY             model: ANY            model: ANY
   base_url: ANY          base_url: ANY         base_url: ANY
       │                     │                     │
       │  raw_queue          │  scored_queue       │  accepted_queue
       ▼                     ▼                     ▼
  ┌──────────────────────────────────────────────────────┐
  │  asyncio.Queue fan-out — bounded, back-pressured     │
  └──────────────────────────────────────────────────────┘
                             │
                             ▼
                     ┌──────────────┐
                     │  Dedup       │  MinHash LSH (Jaccard 0.7)
                     │              │  + LanceDB cosine (sentence-transformers)
                     └──────┬───────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  Writer      │  JSONL + DuckDB metadata
                     │              │  + checkpoint per N
                     └──────────────┘
```

### Why three roles, not one big "judge"

| Role | Job | What it spends on |
|---|---|---|
| **Generator** | Produce a batch of distinct examples per taxonomy node-set | Output tokens — long, structured JSON |
| **Prefilter** | Cheaply drop format / relevance / coherence failures | Input tokens — read batch, emit tiny verdicts |
| **Scorer** | 5-dim weighted rubric → accept / revise / reject | Capability — needs real reasoning to avoid sycophancy |

Splitting the work lets you put a cheap fast model on the prefilter (kills roughly a third of garbage before it reaches the scorer), keep the generator at mid-tier, and spend your capability budget where calibration actually matters.

### Quality gates

- **Prefilter** is binary, with conservative defaults — unparseable verdicts mark FAIL, not PASS.
- **Scorer** weights the five dimensions: factuality 0.30, response_quality 0.25, instruction_clarity 0.20, domain_relevance 0.15, format_compliance 0.10. Composite ≥ 4.0 → accept; ≥ 3.0 → revise; else reject.
- **Dedup** is two layers: MinHash LSH for near-exact dupes, then cosine similarity over local `sentence-transformers/all-MiniLM-L6-v2` embeddings for semantic dupes. No embedding API calls.
- **Diversity** is tracked via the Vendi score on the accepted set, with per-taxonomy-dimension coverage gaps surfaced through `coverage` and `diversity` endpoints.

### Crash safety

- Atomic checkpoints per N accepted samples — re-running resumes from the last node-set index.
- Every API call wrapped in exponential-backoff retry with a 60s per-request timeout, so a hung TCP socket fails into a retry instead of stalling a worker.
- Sentinel-based shutdown: workers drain their inbound queue and forward the sentinel downstream when the target is hit, so `ctrl+c` and target-reached paths land in the same orderly teardown.

---

## Two ways to run it

### Server-side keys (single-tenant)

The operator fills `.env` with three role bindings. Anyone hitting the API or CLI uses those keys, on the operator's bill.

### BYOK — bring your own keys (multi-tenant / frontend)

The caller posts their three keys in the request body. The server uses them for that run and forgets them. Costs go on the caller's bill. `.env` is the fallback for requests that omit `providers`.

```json
POST /runs
{
  "domain": "customer_support",
  "target": 100,
  "providers": {
    "generator": { "api_key": "sk-...", "model": "gpt-4o-mini",  "base_url": "https://api.openai.com/v1",    "batch_size": 5 },
    "prefilter": { "api_key": "sk-...", "model": "claude-haiku", "base_url": "https://api.anthropic.com/v1", "batch_size": 8 },
    "scorer":    { "api_key": "sk-...", "model": "deepseek-r1",  "base_url": "https://api.deepseek.com/v1",  "batch_size": 4 }
  }
}
```

Keys are wrapped in Pydantic `SecretStr` — they never appear in `repr()`, logs, or exception messages, and nothing is persisted to disk.

---

## Quick start

```bash
git clone https://github.com/SaumyaBish-t/SDF.git synthetic-data-forge
cd synthetic-data-forge

python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Unix

pip install -r requirements.txt

cp .env.example .env
# edit .env: fill in the three role bindings (api_key + model + base_url each)

python cli.py run --domain customer_support --target 100
```

The first run downloads the local embedding model (~80 MB, cached under `~/.cache/huggingface`). Output lands at `output/run_<timestamp>_<domain>.jsonl`.

### Picking models

The system is provider-agnostic; pick whatever fits your budget. Some sensible defaults:

| Tier | Generator | Prefilter | Scorer |
|---|---|---|---|
| **Cheap** | OpenAI `gpt-4o-mini` | OpenAI `gpt-4o-mini` | Anthropic `claude-3-5-haiku` |
| **Balanced** | DeepSeek V3 | Llama-3.1-8B (Groq) | Claude Haiku 4.5 |
| **High-quality** | Claude Sonnet 4 | `gpt-4o-mini` | Claude Opus 4 |

Cost per 10k-sample run typically lands in the $3–$15 range depending on tier.

---

## API surface

```
POST   /runs                  start a pipeline run (BYOK optional)
GET    /runs                  list jobs in this process
GET    /runs/{job_id}         job status + progress counters (live, checkpoint-fed)
GET    /runs/{job_id}/export  stream the resulting JSONL
GET    /coverage/{domain}     counts + gaps per taxonomy dimension
GET    /diversity/{domain}    Vendi score on the accepted set
GET    /domains               taxonomy domains available for runs
GET    /healthz
```

```bash
uvicorn api.app:app --reload --port 8000
# OpenAPI / Swagger UI at http://localhost:8000/docs
```

## Web console

A WebGL frontend lives in `frontend/` — a 3D particle visualization of the pipeline
(watch examples die at each gate), scroll-driven storytelling of the architecture,
and a functional Forge Console: pick a domain, set a target, optionally paste your
own three keys, ignite, watch live accept/reject counters, download the JSONL.

```bash
# terminal 1 — backend
uvicorn api.app:app --port 8000

# terminal 2 — frontend
cd frontend
npm install
npm run dev          # → http://localhost:5173
```

Stack: React 19 + TypeScript + Vite, React Three Fiber (WebGL), GSAP ScrollTrigger +
Lenis (scroll), Tailwind v4. The 3D scene runs entirely in a vertex shader — the main
thread stays free — and respects `prefers-reduced-motion`. Point it at a deployed
backend with `VITE_API_URL`.

## CLI surface

```bash
python cli.py run --domain <name> --target N [--providers path.json]
python cli.py status --domain <name>
python cli.py list-domains
python cli.py coverage --domain <name> --dimension <dim> [--expected N]
python cli.py diversity --domain <name>
```

Pass `--providers providers.json` (see `providers.json.example`) to override `.env` for a single run — handy for local BYOK testing.

---

## Repo layout

```
.
├── api/                 FastAPI app + routes
├── pipeline/            Stage implementations + orchestrator
│   ├── orchestrator.py  Worker fan-out, queue wiring, run() entry point
│   ├── generator.py     Meta-prompt + JSON-array parsing
│   ├── critic_prefilter.py   Binary verdict critic (batched)
│   ├── critic_scorer.py      5-dim rubric scorer (per-example)
│   ├── deduplicator.py  MinHash LSH + LanceDB cosine
│   ├── writer.py        JSONL emitter + DuckDB metadata
│   ├── checkpoint.py    Atomic per-N-accepted checkpoints
│   ├── diversity.py     Vendi score + coverage gap analytics
│   └── queues.py        Bounded asyncio.Queue factories
├── storage/             DuckDB + LanceDB wrappers (async)
├── taxonomy/            Domain definitions + seed sampler
│   └── domains/<name>.json
├── config.py            Env-driven role bindings + thresholds
├── models.py            Pydantic records + BYOK schemas
├── cli.py               argparse CLI mirroring the API
└── requirements.txt
```

---

## Configuration reference

| Var / Constant | What it controls |
|---|---|
| `SDF_GENERATOR_{API_KEY,MODEL,BASE_URL,BATCH_SIZE}` | Generator role binding |
| `SDF_PREFILTER_{API_KEY,MODEL,BASE_URL,BATCH_SIZE}` | Prefilter role binding |
| `SDF_SCORER_{API_KEY,MODEL,BASE_URL,BATCH_SIZE}` | Scorer role binding |
| `GEN_DEFAULT_BATCH_SIZE` | Examples requested per generator call |
| `GEN_MAX_TOKENS` | Output token ceiling per generator call |
| `RUBRIC_WEIGHTS` | Per-dimension weight in the scorer composite |
| `ACCEPT_THRESHOLD` / `REVISE_THRESHOLD` | Composite cutoffs for verdict |
| `MINHASH_NUM_PERM` / `JACCARD_THRESHOLD` | Dedup layer 1 (MinHash LSH) |
| `COSINE_SIM_THRESHOLD` | Dedup layer 2 (semantic) |
| `EMBED_MODEL` | sentence-transformers model id (local, no network) |

---

## License

MIT.
