"""Call-source adapters: turn some backend into a list of `callintel.core.Call`."""
from __future__ import annotations

from .base import CallSource
from .jsonl import JsonlCallSource
from .synthetic import SyntheticCallSource

__all__ = ["CallSource", "JsonlCallSource", "SyntheticCallSource"]
