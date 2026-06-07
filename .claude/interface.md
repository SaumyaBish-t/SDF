# Module Interface Contracts

> Updated at end of every Cowork session.
> Read this file at the start of every session alongside CLAUDE.md.
> Never delete entries — mark deprecated ones with [DEPRECATED].

---

## config.py
Last updated: Session 1
Purpose: Single source of truth for all constants.
Import pattern: `from config import KEY_1, ACCEPT_THRESHOLD, GEN_MODEL_1`
Never import directly from .env anywhere except config.py.

---

## utils.py
Last updated: Session 2
Purpose: Cross-cutting helpers — exponential-backoff retry + file logging.
Public API:
  - `setup_logging() -> logging.Logger`
      Returns the "sdf" logger. Idempotent. Configures a RotatingFileHandler
      writing to `config.LOG_FILE` (10MB × 5 backups, UTF-8). Sets
      `propagate=False` so nothing leaks to stdout.
  - `with_retry(fn, *args, _op_name: str | None = None, **kwargs) -> T`
      Async retry wrapper. Up to `config.MAX_RETRIES` attempts, sleeps
      `config.BACKOFF_BASE_SECONDS ** attempt` between tries. Logs every
      failure to logger `sdf.retry` (warning per retry, error on final).
      Re-raises the last exception when all attempts fail.
Import pattern:
  `from utils import with_retry, setup_logging`
Side effects: creates `logs/` directory if absent; writes to `logs/pipeline.log`.
Logger names used by pipeline code: child loggers under "sdf.*"
  (e.g. "sdf.generator", "sdf.critic.prefilter").

---

## pipeline/queues.py
Last updated: Session 3
Purpose: Typed, bounded asyncio.Queue factories for the three pipeline boundaries.
Public API:
  - `make_raw_queue() -> asyncio.Queue[RawExample]`        (maxsize=QUEUE_RAW_MAXSIZE)
  - `make_scored_queue() -> asyncio.Queue[ScoredExample]`  (maxsize=QUEUE_SCORED_MAXSIZE)
  - `make_accepted_queue() -> asyncio.Queue[JudgedExample]` (maxsize=QUEUE_ACCEPTED_MAXSIZE)
Queue schema (item types):
  - raw_queue       : RawExample      (generator → pre_filter)
  - scored_queue    : ScoredExample   (pre_filter → full_scorer)
  - accepted_queue  : JudgedExample   (full_scorer → deduplicator/writer)
Backpressure: bounded queues block on `put()` when full — slow downstream
  throttles upstream automatically. Sizes come from config; do not pass
  literals here.
Side effects: none.

---

