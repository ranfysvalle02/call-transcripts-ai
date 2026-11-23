"""The drop-in adapter contract: anything that can yield `Call` objects."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core import Call


@runtime_checkable
class CallSource(Protocol):
    """A source of calls for the pipeline.

    `name` is the stable source tag persisted with every fact (used in the cache
    key and the audit trail). `cohort` is a human label for this batch (e.g.
    "synthetic" or a JSONL export name). `fetch()` returns the calls to extract.
    """

    name: str
    cohort: str

    def fetch(self) -> list[Call]: ...
