# Synthetic Data Forge

## Project purpose
Pipeline that generates high-quality synthetic fine-tuning datasets
using a generator–critic loop. Input: task spec + domain.
Output: HuggingFace-compatible JSONL with full metadata.

## Tech stack — DO NOT change these without asking
- Python 3.11+
- LanceDB — vector storage + semantic dedup (no FAISS, no MongoDB)
- DuckDB — metadata analytics + coverage queries (no Postgres)
- asyncio + asyncio.Queue — pipeline orchestration (no Redis, no Celery)
- openai Python SDK — all NIM calls (base_url swap)
- datasketch — MinHash LSH deduplication
- vendi-score — diversity metric
- FastAPI — REST API layer
- No Redis. No MongoDB. No Docker required to run locally.

## API key configuration
Keys stored in .env, loaded via python-dotenv.
NEVER hardcode keys. NEVER print keys in logs.
Key roles (import from config.py, never reassign):
  KEY_1 = generator     → deepseek-ai/deepseek-v4-flash,    batch=10
  KEY_2 = generator     → z-ai/glm4.7,                      batch=10
  KEY_3 = pre_filter    → nvidia/nemotron-3-nano-30b-a3b,   batch=3
  KEY_4 = pre_filter    → mistralai/mistral-small-4-119b-2603, batch=3
  KEY_5 = full_scorer   → deepseek-ai/deepseek-r1-0528,     batch=1
NIM base_url: https://integrate.api.nvidia.com/v1

## Quality thresholds (import from config.py)
ACCEPT_THRESHOLD = 3.5
REVISE_RANGE = (3.0, 3.4)
REJECT_BELOW = 3.0
SIMILARITY_REJECT = 0.92   ← cosine similarity ceiling for dedup
MINHASH_THRESHOLD = 0.7    ← Jaccard similarity for MinHash dedup

## Pipeline flow
taxonomy_builder → seed_sampler → generator (async batch)
→ Queue1(raw) → pre_filter workers (Keys 3+4, async)
→ Queue2(scored) → full_scorer (Key 5)
→ Queue3(accepted) → deduplicator → DuckDB+LanceDB writer
→ checkpoint every 100 examples → JSONL output

## Checkpoint behavior
Save to checkpoints/run_{timestamp}.json every 100 accepted examples.
Fields: accepted_count, last_node_idx, vendi_score, timestamp.
On startup: check for latest checkpoint, resume from it if found.

## Code style
- Type hints on all function signatures
- Async functions for all API calls (never sync)
- Every API call wrapped in try/except with exponential backoff
- Max retries: 3. Backoff: 2^attempt seconds.
- Log to logs/ not stdout (use Python logging module)
- All thresholds and model strings imported from config.py
- No magic numbers anywhere in pipeline code

## DO NOT change without explicit instruction
- The 5-key role assignment
- DuckDB + LanceDB as the storage stack
- asyncio.Queue as the pipeline glue
- The checkpoint interval (100 examples)
- The quality threshold values

## Repo
https://github.com/SaumyaBish-t/SDF
