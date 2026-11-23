#!/usr/bin/env python3
"""callintel command-line interface.

Punchline: black boxes can't be opened -- but strategic facts and quotes buy you
auditability, and a possible explanation.

Run it as a module::

    python -m callintel run --show-evidence
    python -m callintel run --ollama --model llama3.1   # fully local, no OpenAI key
    python -m callintel compare --out out/compare.md
    python -m callintel audit --sample 10
    python -m callintel selftest            # offline, no network, no API key

All commands work over the baked-in synthetic calls by default, or over your own
transcripts with `--jsonl path.jsonl`. Point it at OpenAI (OPENAI_API_KEY) or any
OpenAI-compatible server such as Ollama (`--ollama` / `--base-url`). Config is
auto-loaded from the nearest .env; see .env.example.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from dotenv import find_dotenv, load_dotenv

from . import compare as compare_mod
from . import core
from .adapters.jsonl import JsonlCallSource
from .adapters.synthetic import SyntheticCallSource

LOG = logging.getLogger("call_intel")

DEFAULT_STORE_PATH = str(Path("out") / "call_facts.sqlite")
COMMANDS = {"run", "extract", "report", "audit", "compare", "selftest"}


def source_from_args(args: argparse.Namespace):
    """Pick the call source: a JSONL export if given, else the synthetic samples."""
    if getattr(args, "jsonl", None):
        return JsonlCallSource(args.jsonl, cohort=getattr(args, "cohort", None),
                               limit=getattr(args, "limit", None))
    return SyntheticCallSource(cohort=(getattr(args, "cohort", None) or "synthetic"),
                               limit=getattr(args, "limit", None))


def cmd_run(args: argparse.Namespace) -> int:
    client = core.make_client(args)
    if not client:
        return 2
    source = source_from_args(args)
    calls = source.fetch()
    if not calls:
        LOG.info("No calls from source %s.", source.name)
        return 0
    LOG.info("Source: %s | cohort: %s | %d calls", source.name, source.cohort, len(calls))
    core.extract_calls(calls, args, cohort=source.cohort, source=source.name, client=client)
    return core.aggregate_and_render(
        args, client if args.narrative else None, cohort=source.cohort, source=source.name
    )


def cmd_extract(args: argparse.Namespace) -> int:
    client = core.make_client(args)
    if not client:
        return 2
    source = source_from_args(args)
    calls = source.fetch()
    if not calls:
        LOG.info("No calls from source %s.", source.name)
        return 0
    core.extract_calls(calls, args, cohort=source.cohort, source=source.name, client=client)
    return 0


def _add_source_args(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    p.add_argument("--jsonl", default=None, help="Path to a JSONL export (else baked-in samples)")
    p.add_argument("--limit", type=int, default=None, help="Cap the number of calls")
    return p


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="callintel",
        description="Grounded, auditable summarization over call transcripts (synthetic or JSONL).",
        epilog="Black boxes can't be opened -- but strategic facts and quotes buy you "
               "auditability, and a possible explanation. Runs on OpenAI or local Ollama.",
    )
    sub = parser.add_subparsers(dest="command")
    llm = core.llm_args(DEFAULT_STORE_PATH)
    rep = core.report_args()

    def src_parent() -> argparse.ArgumentParser:
        return _add_source_args(argparse.ArgumentParser(add_help=False))

    p_run = sub.add_parser("run", parents=[src_parent(), llm, rep], help="extract -> report")
    p_run.set_defaults(func=cmd_run)

    p_ext = sub.add_parser("extract", parents=[src_parent(), llm], help="extract + cache facts")
    p_ext.add_argument("--cohort", default=None, help="Human label for this batch of calls")
    p_ext.set_defaults(func=cmd_extract)

    p_report = sub.add_parser("report", parents=[llm, rep], help="aggregate the local store")
    p_report.set_defaults(func=core.cmd_report)

    p_audit = sub.add_parser("audit", parents=[llm], help="human-in-the-loop review sheet")
    p_audit.add_argument("--sample", type=int, default=15)
    p_audit.add_argument("--source", default=None)
    p_audit.set_defaults(func=core.cmd_audit)

    p_cmp = sub.add_parser("compare", parents=[src_parent(), llm],
                           help="naive summary vs grounded extraction (loss/inventions/trace)")
    p_cmp.add_argument("--cohort", default=None, help="Human label for this batch of calls")
    p_cmp.add_argument("--call-id", default=None, help="Compare a single call by id")
    p_cmp.add_argument("--out", default=None, help="Also write the comparison markdown here")
    p_cmp.set_defaults(func=compare_mod.cmd_compare)

    p_self = sub.add_parser("selftest", help="offline checks, no network")
    p_self.set_defaults(func=core.cmd_selftest)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    load_dotenv(find_dotenv(usecwd=True))

    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] in ("-h", "--help"):
        build_parser().parse_args(raw)
        return 0
    if not raw or raw[0] not in COMMANDS:  # default to `run`
        raw = ["run"] + raw

    args = build_parser().parse_args(raw)
    core.apply_model_default(args)  # resolve the effective model once, for every command
    if getattr(args, "store", None):  # make sure out/ exists before SQLite opens it
        Path(args.store).parent.mkdir(parents=True, exist_ok=True)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
