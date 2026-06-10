"""Pipeline orchestrator — wires every stage through three asyncio.Queues.

Stages, in order:
  taxonomy → seed_sampler → generator workers
    → raw_queue (RawExample)
  → prefilter workers (batched drain)
    → scored_queue (ScoredExample, only passers)
  → scorer workers
    → accepted_queue (JudgedExample, verdict='accept')
  → dedup+writer worker
    → Store (DuckDB+LanceDB) + JSONL writer + checkpoint

Shutdown contract:
  * `target` accepted examples triggers `_stop_event`. Generator workers
    stop pulling new node_sets; in-flight items drain through the queues.
  * Each stage propagates a `_SENTINEL` after its upstream finishes, so
    downstream consumers know when to exit.
  * `run(...)` always saves a final checkpoint before returning.

Resume:
  * On startup we call `checkpoint.load_latest(domain)`. If found, we seed
    `accepted_count`, skip node_sets up through `last_node_idx`, and emit
    new accepts to a fresh JSONL file `output/{run_id}.jsonl`.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config
from models import JudgedExample, NodeSet, RawExample, ScoredExample
from pipeline import checkpoint as ck
from pipeline.critic_prefilter import prefilter_batch, round_robin_prefilter_keys
from pipeline.diversity import compute_vendi_score
from pipeline.critic_scorer import full_score
from pipeline.deduplicator import Deduplicator
from pipeline.generator import generate_batch, round_robin_keys
from pipeline.queues import (
    make_accepted_queue,
    make_raw_queue,
    make_scored_queue,
)
from pipeline.writer import write_jsonl
from storage.store import Store
from taxonomy.builder import load_taxonomy
from taxonomy.seed_sampler import sample_node_sets


_log = logging.getLogger("sdf.orchestrator")

# Sentinel pushed through each queue to signal end-of-stream to consumers.
# A plain object() is cheap, identity-comparable, and can never collide with
# a real Pydantic record.
_SENTINEL: object = object()


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------
@dataclass
class _RunState:
    """Shared counters / event flags across all worker tasks."""

    run_id: str
    domain: str
    target: int
    output_path: Path
    accepted_count: int = 0
    rejected_count: int = 0
    last_node_idx: int = -1
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# ---------------------------------------------------------------------------
# Node-set iterator (shared across generator workers)
# ---------------------------------------------------------------------------
class _NodeSetCursor:
    """Thread-safe-ish cursor over the sampled NodeSets.

    Generator workers race for the next index; the cursor hands out indices
    atomically and reports the highest dispatched index for checkpointing.
    """

    def __init__(self, node_sets: list[NodeSet], start_idx: int = 0):
        self._node_sets = node_sets
        self._next = start_idx
        self._lock = asyncio.Lock()

    async def next(self) -> Optional[tuple[int, NodeSet]]:
        async with self._lock:
            if self._next >= len(self._node_sets):
                return None
            idx = self._next
            self._next += 1
            return idx, self._node_sets[idx]


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------
async def _generator_worker(
    name: str,
    key: config.KeyRole,
    cursor: _NodeSetCursor,
    raw_queue: asyncio.Queue,
    state: _RunState,
    batch_size: int,
) -> None:
    """Pull node_sets and push RawExamples to raw_queue until stop_event or exhaustion."""
    while not state.stop_event.is_set():
        nxt = await cursor.next()
        if nxt is None:
            _log.info("generator[%s] exhausted node_sets", name)
            return
        idx, node_set = nxt
        try:
            examples = await generate_batch(node_set, key=key, batch_size=batch_size)
        except Exception:  # noqa: BLE001 — log + skip; never kill the loop
            _log.exception("generator[%s] failed for node_id=%s", name, node_set.node_id)
            continue
        for ex in examples:
            if state.stop_event.is_set():
                return
            await raw_queue.put(ex)
        async with state.lock:
            if idx > state.last_node_idx:
                state.last_node_idx = idx


async def _prefilter_worker(
    name: str,
    raw_queue: asyncio.Queue,
    scored_queue: asyncio.Queue,
    state: _RunState,
    domain: str,
    batch_size: int = 3,
    keys_iter=None,
) -> None:
    """Drain raw_queue into batches and pass survivors to scored_queue.

    A worker pulls one item (blocking) then opportunistically drains up to
    `batch_size`-1 more without blocking, so it sends a true batch to the
    critic rather than one-at-a-time.

    `keys_iter` is an infinite iterator over prefilter KeyRoles (round-robin).
    Defaults to the server-side pool; BYOK callers pass their own.
    """
    keys = keys_iter if keys_iter is not None else round_robin_prefilter_keys()
    while True:
        first = await raw_queue.get()
        if first is _SENTINEL:
            raw_queue.task_done()
            await scored_queue.put(_SENTINEL)
            _log.info("prefilter[%s] received sentinel — exiting", name)
            return

        # Target reached — drain raw_queue without spending prefilter API
        # budget. The downstream scorer + writer also discard on stop_event,
        # so this just keeps the worker alive to absorb sentinels.
        if state.stop_event.is_set():
            raw_queue.task_done()
            async with state.lock:
                state.rejected_count += 1
            continue

        batch: list[RawExample] = [first]
        saw_sentinel = False
        while len(batch) < batch_size:
            try:
                item = raw_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is _SENTINEL:
                # Put it back so the next iteration's blocking get sees it
                # and triggers the orderly shutdown above.
                raw_queue.task_done()
                saw_sentinel = True
                break
            batch.append(item)

        try:
            key = next(keys)
            try:
                scored = await prefilter_batch(batch, domain=domain, key=key)
            except Exception:  # noqa: BLE001
                _log.exception(
                    "prefilter[%s] batch failed (size=%d) — rejecting all",
                    name, len(batch),
                )
                async with state.lock:
                    state.rejected_count += len(batch)
            else:
                passed = 0
                for s in scored:
                    if s.prefilter_score >= config.PREFILTER_PASS_SCORE:
                        await scored_queue.put(s)
                        passed += 1
                    else:
                        async with state.lock:
                            state.rejected_count += 1
                _log.debug("prefilter[%s] batch=%d passed=%d", name, len(batch), passed)
        finally:
            for _ in batch:
                raw_queue.task_done()
            if saw_sentinel:
                await raw_queue.put(_SENTINEL)


async def _scorer_worker(
    name: str,
    scored_queue: asyncio.Queue,
    accepted_queue: asyncio.Queue,
    state: _RunState,
    domain: str,
    scorer_key: Optional[config.KeyRole] = None,
) -> None:
    """Full scorer — accept/revise/reject. Only 'accept' moves on."""
    while True:
        item = await scored_queue.get()
        try:
            if item is _SENTINEL:
                await accepted_queue.put(_SENTINEL)
                _log.info("scorer[%s] received sentinel — exiting", name)
                return

            # Target reached — drain without spending API budget.
            if state.stop_event.is_set():
                async with state.lock:
                    state.rejected_count += 1
                continue

            scored: ScoredExample = item
            try:
                judged: JudgedExample = await full_score(
                    scored, domain=domain, key=scorer_key,
                )
            except Exception:  # noqa: BLE001
                _log.exception(
                    "scorer[%s] failed for example_id=%s — counting as reject",
                    name, scored.raw.example_id,
                )
                async with state.lock:
                    state.rejected_count += 1
                continue

            if judged.verdict == "accept":
                await accepted_queue.put(judged)
            else:
                async with state.lock:
                    state.rejected_count += 1
        finally:
            scored_queue.task_done()


async def _dedup_writer_worker(
    accepted_queue: asyncio.Queue,
    dedup: Deduplicator,
    store: Store,
    state: _RunState,
    n_scorer_workers: int,
    nodes_by_id: dict[str, NodeSet],
) -> None:
    """Single consumer — dedup, persist, write JSONL, checkpoint, stop on target.

    Must be single-threaded because MinHashLSH is not thread-safe.
    """
    sentinels_seen = 0
    while True:
        item = await accepted_queue.get()
        try:
            if item is _SENTINEL:
                sentinels_seen += 1
                if sentinels_seen >= n_scorer_workers:
                    _log.info("dedup/writer drained all upstream sentinels — exiting")
                    return
                continue

            # Once target is reached, discard anything still in flight
            # rather than embed + persist + write JSONL for examples we
            # don't need. Saves API calls + disk during the shutdown
            # drain (we used to overshoot by 10+ during the wind-down).
            if state.stop_event.is_set():
                async with state.lock:
                    state.rejected_count += 1
                continue

            judged: JudgedExample = item

            try:
                accepted = await dedup.check(judged)
            except Exception:  # noqa: BLE001
                _log.exception(
                    "dedup failed for example_id=%s — counting as reject",
                    judged.scored.raw.example_id,
                )
                async with state.lock:
                    state.rejected_count += 1
                continue

            if accepted is None:
                # MinHash or cosine duplicate — already counted in dedup stats.
                async with state.lock:
                    state.rejected_count += 1
                continue

            # Compose taxonomy_node from the original NodeSet via node_id lookup
            # is unnecessary — we already have it from the scored example chain.
            # The NodeSet dimensions aren't carried through, so we derive a
            # minimal dict from what we have. PROJECT_SPEC writer schema only
            # requires {"domain": ...}; downstream tooling can join on node_id.
            raw = judged.scored.raw
            # Hydrate the taxonomy_node from the NodeSet lookup table built
            # at orchestrator startup. Without this the dimension values
            # (topic, tone, language, ...) never reach DuckDB and the
            # `coverage(domain, dimension)` query returns empty.
            node_set = nodes_by_id.get(raw.node_id)
            taxonomy_node = {"domain": state.domain, "node_id": raw.node_id}
            if node_set is not None:
                taxonomy_node.update(node_set.dimensions)

            try:
                await store.write(accepted, taxonomy_node=taxonomy_node)
                await write_jsonl(
                    accepted, state.output_path, taxonomy_node=taxonomy_node,
                )
                # Register for future MinHash dedup *after* persistence so
                # commit order is explicit.
                dedup.register(
                    raw.example_id,
                    f"{raw.prompt}\n{raw.completion}",
                )
            except Exception:  # noqa: BLE001
                _log.exception(
                    "store/writer failed for example_id=%s — counting as reject",
                    raw.example_id,
                )
                async with state.lock:
                    state.rejected_count += 1
                continue

            async with state.lock:
                state.accepted_count += 1
                count = state.accepted_count
                last_idx = state.last_node_idx

            _log.info(
                "ACCEPTED %d/%d example_id=%s score=%.3f",
                count, state.target, raw.example_id, judged.full_score,
            )

            if count % config.CHECKPOINT_INTERVAL == 0:
                await _save_checkpoint(state, count, last_idx, store=store)

            if count >= state.target and not state.stop_event.is_set():
                # Set-and-log exactly once. Without the guard, every accept
                # past the threshold re-fires the log line and re-sets the
                # already-set event.
                _log.info("target %d reached — signalling shutdown", state.target)
                state.stop_event.set()
        finally:
            accepted_queue.task_done()


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------
async def _heartbeat(
    state: _RunState,
    raw_queue: asyncio.Queue,
    scored_queue: asyncio.Queue,
    accepted_queue: asyncio.Queue,
    interval_s: float = 30.0,
) -> None:
    """Every interval, log queue depths + counters so the user can see
    which stage is the bottleneck instead of staring at a silent terminal.

    Exits cleanly when `stop_event` is set.
    """
    while not state.stop_event.is_set():
        try:
            await asyncio.wait_for(state.stop_event.wait(), timeout=interval_s)
            return  # stop_event fired during the wait
        except asyncio.TimeoutError:
            pass
        async with state.lock:
            accepted = state.accepted_count
            rejected = state.rejected_count
            last_idx = state.last_node_idx
        _log.info(
            "heartbeat: accepted=%d/%d rejected=%d last_node_idx=%d "
            "queues[raw=%d scored=%d accepted=%d]",
            accepted, state.target, rejected, last_idx,
            raw_queue.qsize(), scored_queue.qsize(), accepted_queue.qsize(),
        )


async def _save_checkpoint(
    state: _RunState,
    accepted: int,
    last_idx: int,
    *,
    store: Optional[Store] = None,
) -> None:
    vendi_score: Optional[float] = None
    if store is not None:
        try:
            embeddings = await store.all_embeddings(domain=state.domain)
            vendi_score = compute_vendi_score(embeddings)
        except Exception:  # noqa: BLE001 — diagnostics, never block a checkpoint
            _log.exception("vendi-score computation failed (accepted=%d)", accepted)

    try:
        await ck.save_checkpoint(
            run_id=state.run_id,
            domain=state.domain,
            accepted_count=accepted,
            last_node_idx=last_idx,
            target=state.target,
            rejected_count=state.rejected_count,
            vendi_score=vendi_score,
        )
    except Exception:  # noqa: BLE001 — never fail the run on a checkpoint hiccup
        _log.exception("checkpoint save failed (accepted=%d)", accepted)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
async def run(
    domain: str,
    target: int,
    *,
    output_path: Optional[Path] = None,
    seed: Optional[int] = None,
    min_coverage: int = 3,
    gen_batch_size: Optional[int] = None,
    n_scorer_workers: int = 2,
    n_prefilter_workers: int = 2,
    resume: bool = True,
    providers=None,
) -> dict:
    """Run the pipeline until `target` accepts are written or node_sets exhaust.

    Args:
        domain: taxonomy file stem under taxonomy/domains/.
        target: number of accepted examples to collect.
        output_path: JSONL output. Default `output/{run_id}.jsonl`.
        seed: pass-through to the seed sampler for deterministic node_set order.
        min_coverage: per-dimension coverage minimum (sampler).
        gen_batch_size: examples per generator call.
        n_scorer_workers: full scorer concurrency (default 2 lets one wait on
            IO while another is in-flight).
        n_prefilter_workers: one per pre-filter key is a reasonable default.
        resume: if True and a checkpoint exists for `domain`, resume from it.
        providers: optional `models.ProviderConfig` (BYOK). When given,
            the run uses the caller's three keys instead of the server-side
            `config.GENERATOR_KEYS / PRE_FILTER_KEYS / FULL_SCORER_KEY`.

    Returns: summary dict {run_id, accepted, rejected, last_node_idx, output_path}.
    """
    # ---- per-run key pool resolution (BYOK overrides server defaults) ----
    if providers is not None:
        byok_gen, byok_pre, byok_scr = config.keyroles_from_provider_config(providers)
        gen_pool: tuple[config.KeyRole, ...] = (byok_gen,)
        pre_pool: tuple[config.KeyRole, ...] = (byok_pre,)
        scorer_key: Optional[config.KeyRole] = byok_scr
    else:
        # Server defaults required for non-BYOK runs — fail fast with a
        # clear message rather than 401-ing inside a worker.
        config.validate_runtime_keys()
        gen_pool = config.GENERATOR_KEYS
        pre_pool = config.PRE_FILTER_KEYS
        scorer_key = None  # full_score() will fall back to FULL_SCORER_KEY
    # ---- node_set planning ------------------------------------------------
    taxonomy = load_taxonomy(domain)
    # Oversample 3× target — most batches lose items to dedup/rejection. The
    # final node_set count is just an upper bound; the run halts on `target`.
    n_node_sets = max(target * 3, target + 1)
    node_sets = sample_node_sets(
        taxonomy=taxonomy,
        domain=domain,
        n=n_node_sets,
        min_coverage=min_coverage,
        seed=seed,
    )

    # ---- resume from checkpoint ------------------------------------------
    resume_payload: Optional[dict] = None
    if resume:
        resume_payload = await ck.load_latest(domain=domain)

    if resume_payload:
        run_id = resume_payload["run_id"]
        start_idx = int(resume_payload.get("last_node_idx", -1)) + 1
        initial_accepted = int(resume_payload.get("accepted_count", 0))
        initial_rejected = int(resume_payload.get("rejected_count", 0))
        _log.info(
            "resuming run_id=%s from node_idx=%d (accepted=%d)",
            run_id, start_idx, initial_accepted,
        )
    else:
        run_id = ck.make_run_id(domain)
        start_idx = 0
        initial_accepted = 0
        initial_rejected = 0
        _log.info(
            "starting run_id=%s domain=%s target=%d node_sets=%d "
            "(workers: gen=%d prefilter=%d scorer=%d dedup=1) byok=%s",
            run_id, domain, target, len(node_sets),
            len(gen_pool), n_prefilter_workers, n_scorer_workers,
            providers is not None,
        )

    if output_path is None:
        output_path = config.OUTPUT_DIR / f"{run_id}.jsonl"

    state = _RunState(
        run_id=run_id,
        domain=domain,
        target=target,
        output_path=output_path,
        accepted_count=initial_accepted,
        rejected_count=initial_rejected,
        last_node_idx=start_idx - 1,
    )

    if state.accepted_count >= target:
        _log.info("already at target on resume — nothing to do")
        return _summary(state)

    # ---- queues & shared deps --------------------------------------------
    raw_queue = make_raw_queue()
    scored_queue = make_scored_queue()
    accepted_queue = make_accepted_queue()

    cursor = _NodeSetCursor(node_sets, start_idx=start_idx)

    async with Store() as store:
        dedup = Deduplicator(store=store)

        # ---- launch workers ------------------------------------------------
        # Round-robin iterators built from the resolved per-run pools (BYOK
        # or server defaults). itertools.cycle is fine here — pools are tiny.
        from itertools import cycle as _cycle
        gen_keys_iter = _cycle(gen_pool)
        pre_keys_iter = _cycle(pre_pool)

        gen_tasks = [
            asyncio.create_task(
                _generator_worker(
                    name=f"gen{i}",
                    key=next(gen_keys_iter),
                    cursor=cursor,
                    raw_queue=raw_queue,
                    state=state,
                    batch_size=gen_batch_size or config.GEN_DEFAULT_BATCH_SIZE,
                ),
                name=f"sdf.generator.{i}",
            )
            for i in range(len(gen_pool))
        ]

        pre_tasks = [
            asyncio.create_task(
                _prefilter_worker(
                    name=f"pre{i}",
                    raw_queue=raw_queue,
                    scored_queue=scored_queue,
                    state=state,
                    domain=domain,
                    keys_iter=pre_keys_iter,
                ),
                name=f"sdf.prefilter.{i}",
            )
            for i in range(n_prefilter_workers)
        ]

        scorer_tasks = [
            asyncio.create_task(
                _scorer_worker(
                    name=f"scr{i}",
                    scored_queue=scored_queue,
                    accepted_queue=accepted_queue,
                    state=state,
                    domain=domain,
                    scorer_key=scorer_key,
                ),
                name=f"sdf.scorer.{i}",
            )
            for i in range(n_scorer_workers)
        ]

        # Lookup so the dedup/writer can hydrate the persisted taxonomy_node
        # with the NodeSet's actual dimension values (topic, tone, ...).
        nodes_by_id = {ns.node_id: ns for ns in node_sets}

        heartbeat_task = asyncio.create_task(
            _heartbeat(state, raw_queue, scored_queue, accepted_queue),
            name="sdf.heartbeat",
        )

        writer_task = asyncio.create_task(
            _dedup_writer_worker(
                accepted_queue=accepted_queue,
                dedup=dedup,
                store=store,
                state=state,
                n_scorer_workers=n_scorer_workers,
                nodes_by_id=nodes_by_id,
            ),
            name="sdf.dedup_writer",
        )

        # ---- orchestrate shutdown -----------------------------------------
        # Wait for generators to finish (either stop_event or node_sets out).
        await asyncio.gather(*gen_tasks, return_exceptions=True)
        # Inject one sentinel per prefilter worker so each exits cleanly.
        for _ in pre_tasks:
            await raw_queue.put(_SENTINEL)
        await asyncio.gather(*pre_tasks, return_exceptions=True)
        # prefilter workers each emit one sentinel into scored_queue, but we
        # need one per scorer worker. Top up.
        for _ in range(max(0, n_scorer_workers - len(pre_tasks))):
            await scored_queue.put(_SENTINEL)
        await asyncio.gather(*scorer_tasks, return_exceptions=True)
        # Each scorer emits one sentinel; writer counts them. Just await.
        await writer_task
        # stop_event was set when target hit (or run ended) — heartbeat will
        # observe it next tick and exit on its own; ensure it's awaited so we
        # don't leak a pending task.
        state.stop_event.set()
        await heartbeat_task

        # ---- final checkpoint ---------------------------------------------
        await _save_checkpoint(
            state, state.accepted_count, state.last_node_idx, store=store,
        )

    _log.info(
        "run complete: accepted=%d rejected=%d (minhash=%d cosine=%d) output=%s",
        state.accepted_count, state.rejected_count,
        dedup.minhash_rejects, dedup.cosine_rejects, output_path,
    )
    return _summary(state)


def _summary(state: _RunState) -> dict:
    return {
        "run_id": state.run_id,
        "domain": state.domain,
        "target": state.target,
        "accepted": state.accepted_count,
        "rejected": state.rejected_count,
        "last_node_idx": state.last_node_idx,
        "output_path": str(state.output_path),
    }
