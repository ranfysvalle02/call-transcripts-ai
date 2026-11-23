#!/usr/bin/env python3
"""JSONL call source -- bring your own transcripts.

Point it at a newline-delimited JSON file where each line is one call. Export
your calls from whatever call-recording tool you use, map them to this shape,
and run the exact same pipeline. Field names are matched leniently.

Minimal per-line shape::

    {"call_id": "abc", "company_name": "Acme", "call_date": "2026-01-15",
     "utterances": [{"speaker_type": "customer", "snippet": "..."}, ...]}
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from ..core import Call, Utterance

_CALL_ID_KEYS = ("call_id", "id", "_id", "callId")
_COMPANY_KEYS = ("company_name", "company", "account_name", "account", "customer")
_DATE_KEYS = ("call_date", "date", "created_at", "start_time", "timestamp")
_UTTS_KEYS = ("utterances", "turns", "transcript", "segments")
_TEXT_KEYS = ("snippet", "text", "content", "utterance", "body")
_SPEAKER_KEYS = ("speaker_type", "speaker", "role", "speaker_name")


def _first(d: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _parse_dt(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):  # epoch seconds
        try:
            return dt.datetime.utcfromtimestamp(float(value))
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).replace("Z", "+00:00")
    for parse in (dt.datetime.fromisoformat,):
        try:
            return parse(s)
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def _to_call(rec: dict[str, Any], idx: int) -> Call:
    raw_utts = _first(rec, _UTTS_KEYS, []) or []
    utterances: list[Utterance] = []
    for i, u in enumerate(raw_utts):
        if isinstance(u, str):
            utterances.append(Utterance(snippet=u, index=i))
            continue
        if not isinstance(u, dict):
            continue
        utterances.append(
            Utterance(
                snippet=str(_first(u, _TEXT_KEYS, "") or ""),
                speaker_type=str(_first(u, _SPEAKER_KEYS, "?") or "?"),
                speaker_name=str(u.get("speaker_name", "") or ""),
                id=(str(u["id"]) if u.get("id") is not None else None),
                index=u.get("index", i),
            )
        )
    return Call(
        call_id=str(_first(rec, _CALL_ID_KEYS, f"jsonl-{idx:05d}")),
        company_name=str(_first(rec, _COMPANY_KEYS, "") or ""),
        account_name=str(_first(rec, ("account_name", "account"), "") or ""),
        call_date=_parse_dt(_first(rec, _DATE_KEYS)),
        utterances=utterances,
        source="jsonl",
    )


class JsonlCallSource:
    """CallSource over a local JSONL file (one call per line)."""

    name = "jsonl"

    def __init__(self, path: str, cohort: str | None = None, limit: int | None = None) -> None:
        self.path = path
        self.cohort = cohort or Path(path).stem
        self.limit = limit

    def fetch(self) -> list[Call]:
        calls: list[Call] = []
        with open(self.path) as fh:
            for i, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    calls.append(_to_call(rec, i))
                if self.limit and len(calls) >= self.limit:
                    break
        return calls
