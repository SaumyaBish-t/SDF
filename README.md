# Synthetic Data Forge

A production-shaped pipeline for generating curated instruction-tuning data from a taxonomy, with quality gates, deduplication, and per-request BYOK so each user can plug in their own LLM provider.

> **Status:** working end-to-end. 178 tests passing. Verified live against AWS Bedrock (Nova family), NVIDIA NIM, and OpenAI-compatible aggregators.

---

## What it does

You give it a **domain taxonomy** (topics, tones, scenarios) and a **target sample count**. It returns a JSONL of distinct, scored, deduplicated `(instruction, response)` pairs ready for fine-tuning — along with DuckDB metadata and LanceDB embeddings for downstream analysis.

The pipeline is **provider-agnostic**: as long as your three LLM endpoints speak the OpenAI `/chat/completions` shape, they slot in. Mix-and-match across providers per role is fine.

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
   meta-prompt            pass/fail             5-dim rubric
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

Each role is a separate worker pool reading from its inbound `asyncio.Queue` and pushing to the next stage's queue. **Back-pressure is the whole game** — the scorer is the slowest and most expensive stage, so the bounded queues mean the generator throttles itself naturally instead of burning tokens on examples that won't be scored before shutdown.

### Why three roles, not one big "judge"

| Role | Job | What it spends on |
|---|---|---|
| **Generator** | Produce 10 distinct examples per taxonomy node-set | Output tokens — write long, structured JSON |
| **Prefilter** | Drop format / relevance / coherence failures cheap | Input tokens — read the batch, emit tiny verdicts |
| **Scorer** | 5-dim weighted rubric → accept / revise / reject | Capability — needs real reasoning to avoid sycophancy |

Splitting them lets you spend a cheap fast model on prefilter (kills ~30% of garbage before it reaches the scorer), keep the generator at mid-tier, and put your capability budget on the scorer — which is where calibration actually matters.

### Quality gates

- **Prefilter** is binary (pass/fail per example) with conservative defaults — unparseable verdicts mark FAIL, not PASS.
- **Scorer** weights the 5 dimensions: factuality 0.30, response_quality 0.25, instruction_clarity 0.20, domain_relevance 0.15, format_compliance 0.10. Composite ≥ 4.0 → accept, ≥ 3.0 → revise, else reject.
- **Dedup** is two-layer: MinHash LSH for cheap exact-ish dupes, then cosine sim on local `sentence-transformers/all-MiniLM-L6-v2` embeddings for semantic duplicates.
- **Diversity** is tracked per run via the Vendi score on the accepted set, with coverage gaps per taxonomy dimension surfaced through the `coverage` and `diversity` endpoints.

### Crash safety

- **Atomic checkpoints** per accepted batch — `run` records the last node-set index so re-running with `--no-resume=false` continues exactly where the previous attempt died.
- **Per-stage `with_retry`** with exponential backoff. Single-request 60s HTTP timeout so a hung TCP socket fails into a retry instead of blocking a worker forever.
- **Sentinel-based shutdown** — workers drain their inbound queue and forward the sentinel downstream; no orphaned tasks on `target_reached` or `ctrl+c`.

---

## Two ways to run it

### 1. Server-side keys (single-tenant deploy)

The operator fills `.env` with three role bindings. Anyone hitting the API or CLI uses those keys, on the operator's bill.

### 2. BYOK — bring your own keys (multi-tenant deploy)

The caller posts their own three keys in the request body. The server uses them for the run and forgets them when the run ends. Costs go on the caller's bill. Server-side `.env` is the fallback for requests that omit `providers`.

```json
POST /runs
{
  "domain": "customer_support",
  "target": 100,
  "providers": {
    "generator": { "api_key": "sk-...", "model": "gpt-4o-mini",   "base_url": "https://api.openai.com/v1",     "batch_size": 5 },
    "prefilter": { "api_key": "sk-...", "model": "claude-haiku",  "base_url": "https://api.anthropic.com/v1",  "batch_size": 8 },
    "scorer":    { "api_key": "sk-...", "model": "deepseek-r1",   "base_url": "https://api.deepseek.com/v1",   "batch_size": 4 }
  }
}
```

Keys are wrapped in Pydantic `SecretStr` — they never appear in `repr()`, logs, or exception messages. Nothing is persisted to disk.

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

That's it. The first run downloads the sentence-transformers model (~80 MB, cached under `~/.cache/huggingface`). Output lands at `output/run_<timestamp>_<domain>.jsonl`.

### Pick three models

The system is provider-agnostic; pick whatever fits your budget. Some sensible defaults:

| Tier | Generator | Prefilter | Scorer |
|---|---|---|---|
| **Cheap** | OpenAI `gpt-4o-mini` | OpenAI `gpt-4o-mini` | Anthropic `claude-3-5-haiku` |
| **Balanced** | DeepSeek-V3 | Llama-3.1-8B (Groq) | Claude Haiku 4.5 |
| **High-quality** | Claude 4 Sonnet | gpt-4o-mini | Claude Opus 4 |

Cost per 10k-sample run typically lands $3–$15 depending on tier.

---

## API surface

```
POST   /runs                 start a pipeline run (BYOK optional)
GET    /runs                 list jobs in this process
GET    /runs/{job_id}        job status + progress counters
GET    /runs/{job_id}/export stream the resulting JSONL
GET    /coverage/{domain}    counts + gaps per taxonomy dimension
GET    /diversity/{domain}   Vendi-score on the accepted set
GET    /healthz
```

```bash
uvicorn api.app:app --reload --port 8000
# OpenAPI/Swagger at http://localhost:8000/docs
```

## CLI surface

```bash
python cli.py run --domain <name> --target N [--providers path.json]
python cli.py status --domain <name>
python cli.py list-domains
python cli.py coverage --domain <name> --dimension <dim> [--expected N]
python cli.py diversity --domain <name>
```

Pass `--providers providers.json` (see `providers.json.example`) to override the `.env` keys for one run — useful for local BYOK testing.

---

## Repo layout

```
.
├── api/                 FastAPI app + routes (POST /runs, GET /coverage, ...)
│   ├── app.py
│   └── routes.py
├── pipeline/            Stage implementations + orchestrator
│   ├── orchestrator.py  Worker fan-out, queue wiring, run() entry point
│   ├── generator.py     Meta-prompt + JSON-array parsing + key rotation
│   ├── critic_prefilter.py   Binary verdict critic (batched)
│   ├── critic_scorer.py      5-dim rubric scorer (per-example)
│   ├── deduplicator.py  MinHash LSH + LanceDB cosine
│   ├── writer.py        JSONL emitter + DuckDB metadata
│   ├── checkpoint.py    Atomic per-N-accepted checkpoints
│   ├── diversity.py     Vendi score + coverage gap analytics
│   └── queues.py        Bounded asyncio.Queue factories
├── storage/             DuckDB + LanceDB wrappers, async
│   └── store.py
├── taxonomy/            Domain definitions + seed sampler
│   ├── builder.py
│   ├── seed_sampler.py
│   └── domains/<name>.json
├── tests/               178 tests — pytest + pytest-asyncio
├── config.py            Env-driven role bindings + thresholds
├── models.py            Pydantic records flowing through queues + BYOK schemas
├── cli.py               argparse CLI mirroring the API
├── utils.py             with_retry, setup_logging, response helpers
└── requirements.txt
```

---

## Configuration reference

All knobs live in `config.py` or `.env`. Highlights:

| Var / Constant | What it controls |
|---|---|
| `SDF_GENERATOR_{API_KEY,MODEL,BASE_URL,BATCH_SIZE}` | Generator role binding |
| `SDF_PREFILTER_{API_KEY,MODEL,BASE_URL,BATCH_SIZE}` | Prefilter role binding |
| `SDF_SCORER_{API_KEY,MODEL,BASE_URL,BATCH_SIZE}` | Scorer role binding |
| `GEN_DEFAULT_BATCH_SIZE` | Examples requested per generator call (default 10) |
| `GEN_MAX_TOKENS` | Output token ceiling per generator call (default 4096) |
| `RUBRIC_WEIGHTS` | Per-dimension weight in scorer composite |
| `ACCEPT_THRESHOLD` / `REVISE_THRESHOLD` | Composite cutoffs for verdict |
| `MINHASH_NUM_PERM` / `JACCARD_THRESHOLD` | Dedup layer 1 (MinHash LSH) |
| `COSINE_SIM_THRESHOLD` | Dedup layer 2 (semantic) |
| `EMBED_MODEL` | sentence-transformers model id (local, no network calls) |

---

## Testing

```bash
python -m pytest tests/ -q
```

178 tests cover: parsing, retries, JSON tolerance, queue back-pressure, worker shutdown, prefilter validation, scorer rubric weighting, dedup thresholds, writer atomicity, checkpoint resume, API contract, coverage analytics, and Vendi-score computation.

Tests never make real API calls — `_make_client` is monkeypatched per test.

---

## License

MIT.
