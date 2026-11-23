#!/usr/bin/env python3
"""compare -- put a naive LLM summary next to the grounded extraction.

The point: a free-form summary is the model's STATED account of the call, which
you have to trust. A grounded fact anchors on an OBJECTIVE artifact -- a verbatim
quote you can check -- so you get auditability instead of blind trust. This
command makes the gap between the two concrete.

For each call it:

  1. asks the model for a plain free-form summary (no schema, no quotes);
  2. measures LOSS -- grounded, quote-backed facts the summary does not cover;
  3. flags likely INVENTIONS -- numbers and proper names in the summary that
     never appear anywhere in the transcript;
  4. reports TRACEABILITY -- summary bullets cite nothing; every grounded fact
     links back to {call_id, utterance_id, quote}.

The loss and invention checks are deliberately simple, deterministic text
heuristics (documented inline and in the output). They are not meant to be a
perfect NLP judge; they are meant to be auditable themselves and to reliably
surface the classes of error this demo is about.
"""
from __future__ import annotations

import argparse
import logging
import re
from collections import defaultdict
from pathlib import Path

from . import core
from .core import Call, Fact, FactStore
from .llm import LLMClient

LOG = logging.getLogger("call_intel")

# Common words ignored when testing whether a summary "covers" a quote, so that
# coverage is driven by content words (nouns/verbs) rather than filler.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "is", "are", "was",
    "were", "be", "been", "being", "to", "of", "in", "on", "for", "with", "at",
    "by", "from", "up", "about", "into", "over", "after", "we", "our", "us", "i",
    "you", "your", "they", "them", "their", "it", "its", "this", "that", "these",
    "those", "he", "she", "his", "her", "do", "does", "did", "have", "has", "had",
    "not", "no", "yes", "can", "could", "would", "should", "will", "want", "need",
    "really", "just", "very", "too", "much", "more", "most", "some", "any", "all",
    "one", "two", "like", "get", "got", "go", "going", "right", "now",
    "thing", "things", "team", "lot", "day", "week", "time", "today", "honestly",
    "maybe", "there", "here", "what", "which", "who", "how", "when", "where", "as",
    "than", "out", "down", "off", "own", "every", "only", "also", "me",
    "customer", "rep", "call", "said", "say", "says", "well", "okay", "sure",
}

# A run of digits (optionally with separators / $ / %), used to detect numbers
# the summary states that are not present in the transcript.
_NUMBER_RE = re.compile(r"\d[\d,.]*")
# A Title-cased token (possible proper noun) in the summary.
_PROPER_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")


def _content_words(text: str) -> list[str]:
    return [
        w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(w) > 2 and w not in _STOPWORDS
    ]


def quote_covered(quote: str, summary: str, *, threshold: float = 0.5) -> bool:
    """Heuristic: a fact's quote is 'covered' by the summary when at least
    `threshold` of its content words appear anywhere in the summary."""
    words = set(_content_words(quote))
    if not words:
        return True  # nothing to cover
    present = set(_content_words(summary))
    hits = len(words & present)
    return (hits / len(words)) >= threshold


def _digit_cores(text: str) -> set[str]:
    """All digit sequences in `text`, separators stripped (e.g. '48,000' -> '48000')."""
    return {re.sub(r"[,.]", "", m.group(0)).rstrip("0") or m.group(0)
            for m in _NUMBER_RE.finditer(text or "")}


def find_invented_numbers(summary: str, transcript: str) -> list[str]:
    """Numbers stated in the summary whose digit sequence is absent from the transcript."""
    source = _digit_cores(transcript)
    out: list[str] = []
    seen: set[str] = set()
    for m in _NUMBER_RE.finditer(summary or ""):
        raw = m.group(0)
        core_digits = re.sub(r"[,.]", "", raw).rstrip("0") or raw
        if core_digits not in source and raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


def find_invented_names(summary: str, transcript: str, *, known: set[str] | None = None) -> list[str]:
    """Title-cased tokens in the summary whose lowercase form never appears in the
    transcript (so sentence-initial 'Maybe', 'Dashboards', etc. are not flagged)."""
    source_words = set(re.findall(r"[a-z0-9]+", (transcript or "").lower()))
    known = known or set()
    out: list[str] = []
    seen: set[str] = set()
    for m in _PROPER_RE.finditer(summary or ""):
        token = m.group(1)
        low = token.lower()
        if low in source_words or low in known or low in _STOPWORDS or low in seen:
            continue
        seen.add(low)
        out.append(token)
    return out


def _transcript_text(call: Call) -> str:
    return "\n".join(f"[{u.speaker_type}] {u.snippet}" for u in call.utterances)


def _naive_summary_prompt(call: Call) -> str:
    company = call.company_name or call.account_name or "the customer"
    return (
        "You are an assistant that writes quick call summaries for a busy sales "
        "executive. Summarize the following sales call with " + company + " in 5 "
        "concise bullet points. Write it the way these summaries normally look: "
        "no quotes, no citations, just the bullets.\n\n"
        "CALL TRANSCRIPT:\n" + _transcript_text(call)
    )


_BULLET_RE = re.compile(r"^\s*([-*\u2022]|\d+[.)])\s+")


def strip_preamble(summary: str) -> str:
    """Drop any lead-in a model prepends before the actual bullets (e.g.
    'Here is a summary ... in 5 bullet points:'), so the analysis sees only the
    summary itself and does not, say, flag the '5' in the preamble as a number."""
    lines = summary.splitlines()
    for i, ln in enumerate(lines):
        if _BULLET_RE.match(ln):
            return "\n".join(lines[i:]).strip()
    return (summary or "").strip()


def _summary_bullets(summary: str) -> list[str]:
    lines = [ln.strip(" \t-*\u2022") for ln in (summary or "").splitlines()]
    return [ln for ln in lines if ln]


# --------------------------------------------------------------------------- #
# Per-call comparison + rendering
# --------------------------------------------------------------------------- #
def compare_call(client: LLMClient, call: Call, facts: list[Fact]) -> dict:
    summary = strip_preamble(client.complete(_naive_summary_prompt(call))["text"])
    transcript = _transcript_text(call)
    grounded = [f for f in facts if f.grounded]

    lost = [f for f in grounded if not quote_covered(f.quote, summary)]
    invented_numbers = find_invented_numbers(summary, transcript)
    invented_names = find_invented_names(
        summary, transcript,
        known={w for w in re.findall(r"[a-z0-9]+", (call.company_name or "").lower())} | {"lumen"},
    )
    return {
        "call": call,
        "summary": summary,
        "bullets": _summary_bullets(summary),
        "grounded": grounded,
        "lost": lost,
        "invented_numbers": invented_numbers,
        "invented_names": invented_names,
    }


def render_comparison(result: dict) -> str:
    call: Call = result["call"]
    grounded: list[Fact] = result["grounded"]
    lost: list[Fact] = result["lost"]
    bullets: list[str] = result["bullets"]
    covered = len(grounded) - len(lost)
    company = call.company_name or call.account_name or call.call_id

    out: list[str] = [
        f"## {company}  (`{call.call_id}`)",
        "",
        "### Naive summary (free-form, no grounding)",
        result["summary"].strip() or "_(empty)_",
        "",
        "### What the grounded extraction found",
        f"{len(grounded)} grounded, quote-backed facts. "
        f"The summary covers {covered}, and misses {len(lost)}.",
        "",
    ]

    if lost:
        out.append("#### Lost facts (grounded, but absent from the summary)")
        for f in lost:
            tag = "/".join(x for x in (f.fact_type, f.category, f.competitor,
                                       f.product_feature, f.interest_theme)
                           if x and x != core.NA)
            out.append(f'- **{tag}** - ({f.speaker_type}) "{f.quote}"  '
                       f'[{call.call_id} / utt {f.utterance_id}]')
        out.append("")
    else:
        out.append("#### Lost facts: none by this heuristic.\n")

    inv_n = result["invented_numbers"]
    inv_name = result["invented_names"]
    out.append("#### Likely inventions (in the summary, not in the transcript)")
    if inv_n or inv_name:
        if inv_n:
            out.append(f"- Numbers not found in the transcript: {', '.join(inv_n)}")
        if inv_name:
            out.append(f"- Proper names not found in the transcript: {', '.join(inv_name)}")
    else:
        out.append("- None detected by this heuristic.")
    out.append("")

    out.append("#### Traceability")
    out.append(f"- Summary bullets that cite a source: 0 of {len(bullets)}.")
    out.append(f"- Grounded facts that link to an exact quote "
               f"{{call_id, utterance_id, quote}}: {len(grounded)} of {len(grounded)}.")
    out.append("")
    return "\n".join(out)


def _header(n_calls: int, model: str) -> str:
    return "\n".join([
        "# Naive summary vs. grounded extraction",
        "",
        f"Model: `{model}`  |  calls compared: {n_calls}",
        "",
        "For each call below: a normal free-form summary, then the grounded facts "
        "it dropped, the numbers or names it appears to have invented, and a "
        "traceability tally. Loss and invention are deterministic text heuristics "
        "(see `callintel/compare.py`); treat them as signal, not a verdict.",
        "",
        "---",
        "",
    ])


_PUNCHLINE = ("_Black boxes can't be opened -- but strategic facts and quotes buy you "
              "auditability, and a possible explanation._")


def cmd_compare(args: argparse.Namespace) -> int:
    from .cli import source_from_args  # local import to avoid a cycle

    client = core.make_client(args)
    if not client:
        return 2
    source = source_from_args(args)
    calls = source.fetch()
    if args.call_id:
        calls = [c for c in calls if c.call_id == args.call_id]
        if not calls:
            LOG.error("No call with id %r in source %s.", args.call_id, source.name)
            return 1
    if args.limit:
        calls = calls[: args.limit]

    # Make sure the grounded facts exist (respects the cache) before comparing.
    core.extract_calls(calls, args, cohort=source.cohort, source=source.name, client=client)

    store = FactStore(args.store)
    try:
        all_facts = store.load_facts(model=client.model, cohort=source.cohort, source=source.name)
    finally:
        store.close()
    by_call: dict[str, list[Fact]] = defaultdict(list)
    for f in all_facts:
        by_call[f.call_id].append(f)

    blocks = [_header(len(calls), client.model)]
    for call in calls:
        LOG.info("Comparing %s (%s)...", call.call_id, call.company_name)
        result = compare_call(client, call, by_call.get(call.call_id, []))
        blocks.append(render_comparison(result))
    blocks.append("---\n\n" + _PUNCHLINE)

    report = "\n".join(blocks)
    print(report)
    if getattr(args, "out", None):
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report)
        LOG.info("Wrote comparison to %s", args.out)
    return 0


# --------------------------------------------------------------------------- #
# Offline self-checks (wired into `callintel selftest`)
# --------------------------------------------------------------------------- #
def selftest_checks() -> list[tuple[str, bool]]:
    transcript = ("[customer] We have about 120 managers and a 48 thousand dollar budget.\n"
                  "[customer] Honestly the dashboards are not the problem for us.")
    results: list[tuple[str, bool]] = []

    covered = quote_covered("the dashboards are not the problem", transcript)
    results.append(("compare: content-word coverage detects a present quote", covered))

    missed = quote_covered("our renewal auto renews in March and locks us in", transcript)
    results.append(("compare: coverage flags an absent quote as lost", not missed))

    nums = find_invented_numbers("They have 500 users and a 48 thousand budget.", transcript)
    results.append(("compare: invented number 500 flagged, 48 not flagged",
                    "500" in nums and "48" not in nums))

    names = find_invented_names("Evaluating Salesforce. Dashboards are a priority.",
                                transcript, known={"lumen"})
    results.append(("compare: invented name Salesforce flagged, Dashboards not",
                    "Salesforce" in names and "Dashboards" not in names))

    stripped = strip_preamble("Here is a summary in 5 concise bullet points:\n"
                              "- first point\n- second point")
    results.append(("compare: model preamble stripped before analysis",
                    stripped.startswith("- first") and "5 concise" not in stripped))
    return results
