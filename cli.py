"""Synthetic Data Forge command-line interface.

Usage:
  python cli.py run --domain customer_support --target 100
  python cli.py status --domain customer_support
  python cli.py list-domains
  python cli.py coverage --domain customer_support --dimension topic --expected 5
  python cli.py diversity --domain customer_support

All subcommands print JSON to stdout so the CLI is pipeable into `jq`,
the FastAPI layer, or test harnesses.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional


# Windows: switch off the default ProactorEventLoop. It races on shutdown
# with long-running HTTPS sockets opened by httpx/openai and surfaces as
# `InvalidStateError: invalid state` during teardown. SelectorEventLoop
# has none of those races for this workload (no subprocess pipes here).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ---------------------------------------------------------------------------
# Output helpers — emit JSON to stdout so the CLI is scriptable.
# ---------------------------------------------------------------------------
def _emit(payload: Any, *, indent: int = 2) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=indent, default=str)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Subcommand handlers (each returns a process exit code)
# ---------------------------------------------------------------------------
async def _cmd_run(args: argparse.Namespace) -> int:
    from pipeline import orchestrator

    summary = await orchestrator.run(
        domain=args.domain,
        target=args.target,
        output_path=Path(args.output) if args.output else None,
        seed=args.seed,
        gen_batch_size=args.gen_batch_size,
        resume=not args.no_resume,
    )
    _emit(summary)
    return 0


async def _cmd_status(args: argparse.Namespace) -> int:
    from pipeline import checkpoint as ck

    payload = await ck.load_latest(domain=args.domain)
    if payload is None:
        _emit({"status": "no_checkpoint", "domain": args.domain})
        return 1
    _emit(payload)
    return 0


def _cmd_list_domains(args: argparse.Namespace) -> int:
    from taxonomy.builder import list_domains

    _emit({"domains": list_domains()})
    return 0


async def _cmd_coverage(args: argparse.Namespace) -> int:
    from pipeline.diversity import coverage_gaps
    from storage.store import Store

    async with Store() as store:
        counts = await store.coverage(domain=args.domain, dimension=args.dimension)
    gaps = coverage_gaps(counts, args.expected) if args.expected else {}
    _emit({
        "domain": args.domain,
        "dimension": args.dimension,
        "counts": counts,
        "gaps": gaps,
    })
    return 0


async def _cmd_diversity(args: argparse.Namespace) -> int:
    from pipeline.diversity import compute_vendi_score
    from storage.store import Store

    async with Store() as store:
        embeddings = await store.all_embeddings(domain=args.domain)
    _emit({
        "domain": args.domain,
        "n_examples": len(embeddings),
        "vendi_score": compute_vendi_score(embeddings),
    })
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdf",
        description="Synthetic Data Forge — generate + curate fine-tuning data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- run -------------------------------------------------------------
    p_run = sub.add_parser("run", help="Run the pipeline until target is reached.")
    p_run.add_argument("--domain", required=True, help="Taxonomy file stem.")
    p_run.add_argument("--target", type=int, required=True, help="Accepted examples to collect.")
    p_run.add_argument("--seed", type=int, default=None, help="Deterministic sampling seed.")
    p_run.add_argument("--output", default=None, help="JSONL output path.")
    p_run.add_argument("--gen-batch-size", type=int, default=None, help="Examples per generator call.")
    p_run.add_argument("--no-resume", action="store_true", help="Ignore prior checkpoints for this domain.")
    p_run.set_defaults(handler=_cmd_run, is_async=True)

    # ---- status ----------------------------------------------------------
    p_status = sub.add_parser("status", help="Show the latest checkpoint for a domain.")
    p_status.add_argument("--domain", default=None, help="Filter by domain (optional).")
    p_status.set_defaults(handler=_cmd_status, is_async=True)

    # ---- list-domains ----------------------------------------------------
    p_ld = sub.add_parser("list-domains", help="List available taxonomy domains.")
    p_ld.set_defaults(handler=_cmd_list_domains, is_async=False)

    # ---- coverage --------------------------------------------------------
    p_cov = sub.add_parser("coverage", help="Coverage counts (and optional gaps) per dimension.")
    p_cov.add_argument("--domain", required=True)
    p_cov.add_argument("--dimension", required=True)
    p_cov.add_argument("--expected", type=int, default=None,
                       help="Expected count per value — populates `gaps`.")
    p_cov.set_defaults(handler=_cmd_coverage, is_async=True)

    # ---- diversity -------------------------------------------------------
    p_div = sub.add_parser("diversity", help="Vendi-score diversity of accepted embeddings.")
    p_div.add_argument("--domain", required=True)
    p_div.set_defaults(handler=_cmd_diversity, is_async=True)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Initialise the sdf logger so pipeline INFOs land on stderr live.
    # Stdout stays reserved for the JSON payload each subcommand emits.
    from utils import setup_logging
    setup_logging(console=args.command == "run")

    handler = args.handler
    if args.is_async:
        return asyncio.run(handler(args))
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
