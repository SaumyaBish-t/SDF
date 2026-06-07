# Synthetic Data Forge — Full Technical Specification

> Living reference document. Read before building any pipeline module.
> Last updated: June 2026

---

## 1. Problem Statement

Every team fine-tuning an LLM needs thousands of high-quality domain-specific
instruction–response pairs. Collecting real data is slow, expensive, and legally
constrained. Naive synthetic generation (just prompting an LLM) produces:
- Low diversity (model collapses to narrow distribution)
- No quality control (bad examples pollute the dataset)
- No coverage guarantee (edge cases never generated)

Synthetic Data Forge solves all three with a structured pipeline.

---

## 2. Target Users

| User | Pain | How SDF helps |
|---|---|---|
| AI startups building domain chatbots | Need 10K+ examples, can't use real data | Generate plausible domain data at $0 cost |
| MLOps teams patching model failures | Need targeted data for specific failure modes | Coverage-steering generates exactly the missing cases |
| RAG pipeline engineers | Need (query, document) pairs pre-launch | Synthetic queries that mirror real user behavior |
| ML researchers | Need preference datasets for RLHF/DPO | Auto-generates chosen/rejected pairs |
| Indian vernacular AI teams | Indic instruction data is scarce | Sarvam-M + GLM-4.7 for Hindi/Tamil/Bengali at scale |

---

## 3. Core Architecture

### Pipeline flow

```
Task Spec (domain + schema + N)
    ↓
Taxonomy Builder → taxonomy/{domain}.json
    ↓
Seed Sampler → N node-sets (one per example)
    ↓
Generator LLMs (async batch=10)
    ↓ raw_queue (asyncio.Queue)
Pre-filter Critics (Nemotron-nano + Mistral Small, batch=3)
    ↓ prefiltered_queue
Full Scorer (DeepSeek R1-0528, batch=1)
    ↓ accepted_queue / revise_queue / rejected
Deduplicator (MinHash LSH + LanceDB cosine)
    ↓
Storage Writer (DuckDB metadata + LanceDB vectors)
    ↓
Coverage Checker → if gaps: loop back to Seed Sampler
    ↓
JSONL Output + HuggingFace push
```

### Queue topology

```
raw_queue        → between generator and pre-filter
prefiltered_queue → between pre-filter and full scorer
accepted_queue   → between scorer and deduplicator/writer
revise_queue     → marginal examples (3.0-3.4) for revision
```

### Worker assignment (5 API keys)

```
Key 1 → deepseek-ai/deepseek-v4-flash     generator,    batch=10
Key 2 → z-ai/glm4.7                       generator,    batch=10
Key 3 → nvidia/nemotron-3-nano-30b-a3b    pre-filter,   batch=3
Key 4 → mistralai/mistral-small-4-119b-2603 pre-filter, batch=3
Key 5 → deepseek-ai/deepseek-r1-0528      full scorer,  batch=1
```

### Throughput estimates

| Config | Raw/hr | Accepted/hr | 10K dataset |
|---|---|---|---|
| 2 gen keys batch=10, Key 5 bottleneck | 72,000 | ~40/min | ~4 hrs |
| Simple domain (no R1, all GLM) | 72,000 | ~120/min | ~1.5 hrs |

---

## 4. Taxonomy Builder

### Purpose
Builds a hierarchical tree of task dimensions. Guarantees that generation
covers the task distribution intentionally, not accidentally.

### Structure

```json
{
  "topic": ["billing_dispute", "account_access", "product_defect"],
  "tone": ["polite", "frustrated", "confused", "urgent"],
  "complexity": ["simple_lookup", "multi_step", "edge_case"],
  "language": ["english", "hinglish", "formal_hindi"],
  "channel": ["chat", "email", "whatsapp"]
}
```

### Seed Sampler
- Draws N unique node-sets (cartesian product sampling without full enumeration)
- Guarantees minimum coverage: every leaf node appears at least min_coverage=3 times
- Returns list of dicts, shuffled

### Meta-prompt template

```
Generate exactly {BATCH_SIZE} distinct training examples for {domain}
matching this scenario: {node_set}.
Return ONLY a valid JSON array. No markdown, no explanation, no code fences.
[{"instruction": "...", "response": "..."}, ...]
Requirements:
- Each example meaningfully different from the others
- Vary phrasing, complexity, scenario within the node
- No repeated sentence starters
```

---

## 5. Generator Node

### Primary model: DeepSeek V4 Flash
- 284B MoE, 1M context, 14.34M NIM calls
- Use for: bulk generation (Key 1)
- Temperature: 0.9 for diversity
- JSON compliance: high but validate every response

### Secondary model: GLM-4.7
- Best free NIM endpoint for structured JSON output
- Use for: secondary generation (Key 2) + pre-filter (Keys 3-4 share model)
- Temperature: 0.85

### Async implementation pattern

```python
import asyncio
from itertools import cycle

GEN_KEYS = [KEY_1, KEY_2]
gen_cycle = cycle(GEN_KEYS)
gen_sem = asyncio.Semaphore(2)  # max concurrent gen calls

async def generate_batch(meta_prompt: str) -> list[dict]:
    async with gen_sem:
        client = AsyncOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=next(gen_cycle)
        )
        for attempt in range(3):
            try:
                r = await client.chat.completions.create(
                    model=GEN_MODEL_1,
                    messages=[{"role": "user", "content": meta_prompt}],
                    temperature=0.9,
                    max_tokens=4096
                )
                return parse_json_array(r.choices[0].message.content)
            except Exception as e:
                if "429" in str(e):
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
```

### JSON array parser (handles partial arrays)

```python
import json, re

def parse_json_array(text: str) -> list[dict]:
    # strip markdown fences if present
    text = re.sub(r'```json|```', '', text).strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        # recover partial array
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
        return []
```

---

## 6. Critic Node

### Double-critic pattern (anti-sycophancy)
Two independent critics with different model families prevent sycophancy.
Generator family (DeepSeek) never evaluates its own outputs at the full-score level.

```
Candidate → Pre-filter A (Nemotron-nano, fast, binary pass/fail)
          → Pre-filter B (Mistral Small, judgment on borderline)
          → Full scorer  (DeepSeek R1, 1-5 rubric scoring)
```

### Pre-filter rubric (Keys 3 and 4)

```
For each example in this batch, check ONLY:
1. Format: is instruction non-empty? is response non-empty?
2. Relevance: is this clearly about {domain}?
3. Coherence: does the response address the instruction?
Score each 0 (fail) or 1 (pass).
Return ONLY valid JSON: [{"id": 0, "pass": true}, ...]
```

### Full scorer rubric (Key 5 — DeepSeek R1)

```
Score this training example 1-5 on each dimension.
Return ONLY valid JSON:
{"factuality": N, "instruction_clarity": N, 
 "response_quality": N, "domain_relevance": N, 
 "format_compliance": N}

REJECT (score ≤ 2) if:
- Response contains detectable factual errors
- Instruction is ambiguous or multi-interpretable
- Response doesn't answer the instruction
- Example is too similar to common internet patterns
- Format deviates from target schema

Score 5 only if: novel phrasing, correct, complete,
domain-authentic, would genuinely improve model performance.
```

### Composite score formula

```python
WEIGHTS = {
    "factuality": 0.30,
    "instruction_clarity": 0.20,
    "response_quality": 0.25,
    "domain_relevance": 0.15,
    "format_compliance": 0.10
}

def composite_score(scores: dict) -> float:
    return sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
```

### Decision thresholds

```python
ACCEPT_THRESHOLD = 3.5   # composite >= 3.5 → accepted_queue
REVISE_MIN = 3.0         # 3.0 <= composite < 3.5 → revise_queue
REJECT_BELOW = 3.0       # composite < 3.0 → discard

# Expected yield: ~65% of pre-filtered examples accepted
# ~15% marginal (revise), ~20% hard rejected
```

---

## 7. Diversity Enforcement

### Vendi Score (primary diversity metric)
- Formula: VS(X;k) = exp(−Σᵢ λ̄ᵢ log λ̄ᵢ) where λ̄ᵢ = eigenvalues(K/n)
- K is cosine similarity matrix of all accepted example embeddings
- Track VS after every 100 accepted examples
- If VS delta < 0.05 between batches: raise generation temperature by 0.05
- If VS drops > 15% between SPIN iterations: inject examples from different model

```python
from vendi_score import vendi_score as compute_vs
import numpy as np

def track_diversity(embeddings: np.ndarray) -> float:
    # embeddings shape: (n_examples, embedding_dim)
    similarity_matrix = np.dot(embeddings, embeddings.T)
    return compute_vs(similarity_matrix)
```

### FAISS-based rejection sampling
Before accepting any example:
1. Compute embedding via nv-embedcode-7b-v1 (free NIM)
2. Query LanceDB for nearest neighbor cosine similarity
3. If similarity > SIMILARITY_REJECT (0.92): reject regardless of quality score

### MinHash LSH (syntactic dedup — Layer 1)

```python
from datasketch import MinHash, MinHashLSH

lsh = MinHashLSH(threshold=0.7, num_perm=128)

def is_syntactic_duplicate(text: str) -> bool:
    m = MinHash(num_perm=128)
    for gram in get_ngrams(text, n=5):
        m.update(gram.encode('utf8'))
    result = lsh.query(m)
    return len(result) > 0

def add_to_lsh(text: str, key: str):
    m = MinHash(num_perm=128)
    for gram in get_ngrams(text, n=5):
        m.update(gram.encode('utf8'))
    lsh.insert(key, m)
```

### Cluster-aware sampling
Every 200 accepted examples:
1. KMeans cluster accepted pool (k=20 for 1000-example datasets)
2. Identify under-populated clusters (< 5% of target)
3. Bias Seed Sampler toward taxonomy nodes that fill sparse clusters

### Taxonomy fill rate gate
If any leaf node has < min_coverage=3 examples after 80% of generation:
Force-generate examples for that node regardless of VS score.

---

## 8. Storage Layer

### LanceDB (vector storage + semantic dedup)

```python
import lancedb
import numpy as np

LANCE_PATH = "storage/lance_db"
TABLE_NAME = "examples"

SCHEMA = {
    "id": str,
    "instruction": str,
    "response": str,
    "vector": list,           # 1024-dim embedding
    "composite_score": float,
    "taxonomy_node": str,     # JSON string
    "generator_model": str,
    "critic_scores": str,     # JSON string
    "difficulty_level": int,  # 1=simple, 2=medium, 3=hard
    "generation_pass": int,   # 1=first try, 2=after revision
    "domain": str,
    "timestamp": str
}

def get_nearest_similarity(embedding: list) -> float:
    db = lancedb.connect(LANCE_PATH)
    table = db.open_table(TABLE_NAME)
    results = table.search(embedding).limit(1).to_pandas()
    if results.empty:
        return 0.0
    return float(results['_distance'].iloc[0])
```

### DuckDB (metadata analytics)

```python
import duckdb

DB_PATH = "storage/metadata.duckdb"

ANALYTICS_QUERIES = {
    "coverage": """
        SELECT json_extract(taxonomy_node, '$.{dim}') as val,
               COUNT(*) as count
        FROM examples
        WHERE domain = ?
        GROUP BY val
        ORDER BY count
    """,
    "score_distribution": """
        SELECT ROUND(composite_score, 1) as score_bucket,
               COUNT(*) as count
        FROM examples
        WHERE domain = ?
        GROUP BY score_bucket
        ORDER BY score_bucket
    """,
    "hourly_rate": """
        SELECT COUNT(*) as accepted,
               MIN(timestamp) as start_time,
               MAX(timestamp) as end_time
        FROM examples
        WHERE domain = ?
          AND timestamp > datetime('now', '-1 hour')
    """
}
```

### Why DuckDB over MongoDB

| | DuckDB | MongoDB |
|---|---|---|
| Analytical queries | 10-100x faster | Slow aggregations |
| Setup | pip install duckdb | Needs running server |
| HuggingFace compatibility | Native Parquet export | Manual conversion |
| Vector search | Via LanceDB companion | Needs Atlas (paid) |
| Cost | $0 | $0 local, paid cloud |

---

## 9. Output Format Specification

### JSONL schema (one line per example)

```json
{
  "id": "sdf_20260607_001234",
  "instruction": "A frustrated customer asks about billing...",
  "response": "I understand your concern. Let me check...",
  "reasoning_trace": null,
  "metadata": {
    "taxonomy_node": {
      "topic": "billing_dispute",
      "tone": "frustrated",
      "complexity": "multi_step",
      "language": "hinglish",
      "channel": "whatsapp"
    },
    "generator_model": "deepseek-ai/deepseek-v4-flash",
    "critic_scores": {
      "factuality": 4,
      "instruction_clarity": 5,
      "response_quality": 4,
      "domain_relevance": 5,
      "format_compliance": 5
    },
    "composite_score": 4.55,
    "nearest_neighbor_similarity": 0.71,
    "generation_pass": 1,
    "difficulty_level": 2,
    "timestamp": "2026-06-07T14:22:11Z"
  }
}
```

### HuggingFace push

```python
from datasets import Dataset
import json

def push_to_huggingface(jsonl_path: str, repo_id: str):
    with open(jsonl_path) as f:
        data = [json.loads(line) for line in f]
    dataset = Dataset.from_list(data)
    dataset.push_to_hub(repo_id)
```

---

## 10. Checkpoint / Resume System

### Checkpoint schema

```json
{
  "run_id": "run_20260607_230000",
  "domain": "customer_support",
  "target": 10000,
  "accepted_count": 3420,
  "rejected_count": 1840,
  "last_node_idx": 156,
  "vendi_score": 28.4,
  "taxonomy_coverage": {"billing_dispute": 234, "account_access": 189},
  "timestamp": "2026-06-07T23:00:00Z"
}
```

### Resume logic

```python
import json
from pathlib import Path

def load_checkpoint(checkpoint_dir: str, domain: str) -> dict | None:
    checkpoints = sorted(
        Path(checkpoint_dir).glob(f"*{domain}*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    if checkpoints:
        with open(checkpoints[0]) as f:
            return json.load(f)
    return None
```

---

## 11. Modern Optimizations (Research-backed)

### 1. SPIN — Self-play loop (Chen et al. NeurIPS 2024)
After base dataset, fine-tune small model on accepted examples.
Use fine-tuned model as secondary generator — outputs represent
"just beyond current model capability." Repeat 3 iterations.

### 2. Curriculum difficulty scheduling
Batch 1: complexity=simple, Batch 2: complexity=medium, Batch 3: hard+edge.
Prevents early training instability. Complexity is a first-class taxonomy dimension.

### 3. Multi-model generation ensemble
DeepSeek V4 Flash (50%) + GLM-4.7 (50%) = higher Vendi Score
than single model. Different stylistic priors → more diverse output.

### 4. RAG-augmented generation (SimRAG, arXiv 2410.17952)
For factual domains: retrieve reference documents first,
generate examples grounded in retrieved facts.
Use nv-embedcode-7b-v1 for retrieval index.

### 5. Reasoning trace injection
Use DeepSeek R1-0528 as generator (not just critic) for CoT datasets.
Produces instruction → reasoning → answer triples.
More valuable for training reasoning models than plain pairs.

### 6. Two-stage critic throughput optimization
Nemotron-nano pre-filter rejects ~40% of candidates cheaply.
R1 only sees 60% of candidates → effectively 67% more R1 capacity.
Biggest single throughput lever after batching.

---

## 12. Architecture Additions (Future)

### Addition 1 — Drift detector
Wasserstein distance between dataset versions v1 and v2.
Alert if distribution shift exceeds threshold in any taxonomy dimension.

### Addition 2 — Preference pair generation (DPO/RLHF)
For each accepted example, generate 2-3 alternative responses.
Critic ranks them: top=chosen, bottom=rejected.
Outputs (instruction, chosen, rejected) triples for DPO training.

### Addition 3 — Model collapse early warning
Monitor VS at each SPIN iteration.
If VS drops > 15%: inject fresh examples from different model family.

### Addition 4 — Execution-based validation (code datasets)
Run generated code in sandboxed subprocess.
Capture stdout/stderr as ground truth for critic score.
LLM critic score overridden by execution result.

### Addition 5 — Auto dataset card generator
README.md auto-generated from run metadata:
taxonomy structure, score distributions, Vendi Score,
models used, domain, known gaps.
Makes every pushed dataset a citable research artifact.

---

## 13. Research Foundation

| Design decision | Paper | Key finding |
|---|---|---|
| Taxonomy-guided generation | Reasoning-Driven SDG (OpenReview 2026) | Node-sets guarantee distribution coverage |
| Constitutional AI critic | Bai et al. 2022 (Anthropic) | RLAIF achieves RLHF-level alignment |
| Vendi Score diversity | Friedman & Dieng 2023 (TMLR) | Shannon entropy of kernel eigenvalues |
| Quality-weighted Vendi | arXiv 2405.02449 (2024) | Joint diversity + quality optimization |
| SPIN self-play | Chen et al. 2024 (NeurIPS) | Progressive capability improvement |
| MinHash deduplication | FineWeb-Edu (HuggingFace 2025) | 5-gram, 128 hash functions, 0.7 threshold |
| RAG-grounded generation | SimRAG (arXiv 2410.17952) | Near-real-data performance on domain QA |
| Curriculum difficulty | Curriculum-RLAIF (arXiv 2505.20075) | Difficulty-ordered data outperforms random |

---

## 14. Full Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Generation | DeepSeek V4 Flash + GLM-4.7 | Fast, free NIM, JSON-reliable |
| Pre-filter | Nemotron-nano + Mistral Small 4 | Speed + judgment, different failure modes |
| Full scorer | DeepSeek R1-0528 | Reasoning-based quality eval |
| Embedding | nv-embedcode-7b-v1 (NIM free) | Semantic similarity for dedup |
| Vector store | LanceDB | Embedded, no server, Arrow native |
| Metadata store | DuckDB | Embedded OLAP, 100x faster than Postgres for analytics |
| Dedup (syntactic) | datasketch MinHash LSH | O(1) lookup, scales to 1M+ |
| Diversity metric | vendi-score Python package | Reference-free, quality-weighted |
| Pipeline glue | asyncio.Queue | No Redis needed at this scale |
| API layer | FastAPI | /status, /start, /export endpoints |
| Output | HuggingFace datasets library | One-line Hub push |
| Code sandbox | Python subprocess | Safe execution for code datasets |

---

*End of specification. Update this file when architecture decisions change.*
