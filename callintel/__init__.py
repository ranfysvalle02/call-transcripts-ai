"""callintel -- grounded, auditable intelligence over call transcripts.

The pipeline (extract -> ground -> store -> aggregate -> report) is source-agnostic:
it consumes `Call` objects produced by any `CallSource` adapter (baked-in synthetic
sample calls, a JSONL export from your call-recording tool, ...). See
`callintel.core` for the contract and `callintel.adapters` for the plug-ins.
"""
from __future__ import annotations

from .core import (
    Aggregation,
    Call,
    Fact,
    FactStore,
    Utterance,
    aggregate_and_render,
    aggregate_facts,
    apply_model_default,
    cmd_audit,
    cmd_report,
    cmd_selftest,
    extract_calls,
    llm_args,
    make_client,
    report_args,
)
from .llm import DEFAULT_MODEL, LLMClient

__all__ = [
    "DEFAULT_MODEL",
    "Aggregation",
    "Call",
    "Fact",
    "FactStore",
    "LLMClient",
    "Utterance",
    "aggregate_and_render",
    "aggregate_facts",
    "apply_model_default",
    "cmd_audit",
    "cmd_report",
    "cmd_selftest",
    "extract_calls",
    "llm_args",
    "make_client",
    "report_args",
]
