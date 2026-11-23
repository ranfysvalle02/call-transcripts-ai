#!/usr/bin/env python3
"""callintel.core -- the source-agnostic pipeline.

The punchline: black boxes can't be opened -- but strategic facts and quotes buy
you auditability, and a possible explanation. This module is the machinery for
that trade.

The contract between a data *source* (synthetic sample calls, a JSONL export
from your call-recording tool, ...) and the pipeline is a list of `Call`
objects. Everything here -- extraction, grounding, the local SQLite fact store,
deterministic aggregation, and reporting -- consumes `Call`/`Fact` and never
touches a specific backend.

Design principle (move determinism upstream, anchor on the objective artifact):
  * The LLM is ONLY a per-call extractor of schema-bound facts, each with a
    verbatim `quote` span (a small, checkable surface).
  * The quote is the OBJECTIVE artifact (it is in the transcript or it is not);
    the label on top of it is the model's STATED interpretation and may be
    wrong. A stored fact is therefore a decision record, not a confession.
  * Facts are cached locally and aggregated with deterministic Python; counts
    are reproducible and every number drills to {source, call_id, quote}, so a
    human can always trace a claim back to the words actually said.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import random
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .llm import DEFAULT_MODEL, LLMClient

LOG = logging.getLogger("call_intel")

# Bump PROMPT_VERSION whenever the extraction prompt/schema/taxonomy changes; it is
# part of the cache key so stale extractions are transparently superseded.
PROMPT_VERSION = "facts-v1"

NA = "n/a"  # sentinel for "field does not apply to this fact"


# --------------------------------------------------------------------------- #
# The source <-> pipeline contract
# --------------------------------------------------------------------------- #
@dataclass
class Utterance:
    """One spoken turn. `id`/`index` let a grounded fact point back to its source."""

    snippet: str
    speaker_type: str = "?"  # "customer" | "rep" | ...
    speaker_name: str = ""
    id: str | None = None
    index: int | None = None


@dataclass
class Call:
    """The canonical call record every adapter must produce."""

    call_id: str
    company_name: str = ""
    account_name: str = ""
    call_date: dt.datetime | None = None
    utterances: list[Utterance] = field(default_factory=list)
    source: str = "unknown"
    mention_count: int | None = None  # adapter decoration (display only)


# --------------------------------------------------------------------------- #
# Controlled vocabularies ("the schema is the contract")
# --------------------------------------------------------------------------- #
# Closed enums keep the deterministic group-by buckets stable across runs/models.
# Everything unknown coerces to "other" rather than inventing a new bucket.
#
# This demo is intentionally generic: the calls are synthetic B2B sales calls for
# a fictional analytics product called "Lumen". Swap these lists (or pass a
# `--taxonomy` JSON file) to fit your own domain; nothing downstream is tied to
# any real company or product.
DEFAULT_TAXONOMY: dict[str, list[str]] = {
    "fact_type": ["interest", "objection", "product_feature", "competitor_mention"],
    "objection_category": [
        "pricing_cost",
        "migration_effort",
        "performance",
        "scalability",
        "security_compliance",
        "skills_familiarity",
        "tooling_integration",
        "support",
        "vendor_lockin",
        "contract_terms",
        "other",
    ],
    "product_feature": [
        "dashboards",
        "alerts",
        "embedded_analytics",
        "data_connectors",
        "sso_scim",
        "audit_logs",
        "api",
        "ai_assistant",
        "other",
    ],
    "competitor": [
        "brightline",
        "kestrel_bi",
        "quanta_insights",
        "spreadsheets",
        "in_house_tooling",
        "other",
    ],
    "interest_theme": [
        "cost_reduction",
        "consolidation",
        "self_serve_reporting",
        "real_time_visibility",
        "compliance_reporting",
        "team_velocity",
        "ai_insights",
        "other",
    ],
}


def load_taxonomy(path: str | None) -> dict[str, list[str]]:
    if not path:
        return DEFAULT_TAXONOMY
    data = json.loads(Path(path).read_text())
    merged = {k: list(v) for k, v in DEFAULT_TAXONOMY.items()}
    for key, values in data.items():
        merged[key] = list(values)
    return merged


def coerce_enum(value: Any, allowed: list[str], default: str = "other") -> str:
    """Map a free-form model value onto the closed vocabulary, deterministically."""
    if value is None:
        return default
    norm = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    if not norm or norm in {"none", "null", "na", "n_a", "unknown"}:
        return default
    if norm in allowed:
        return norm
    # light fuzzy: substring either direction (e.g. "dashboarding" -> "dashboards")
    for term in allowed:
        if term == "other":
            continue
        if norm.startswith(term) or term.startswith(norm) or term in norm or norm in term:
            return term
    return default


# --------------------------------------------------------------------------- #
# Facts + grounding
# --------------------------------------------------------------------------- #
@dataclass
class Fact:
    call_id: str
    company_name: str
    account_name: str
    call_date: str  # ISO date (YYYY-MM-DD) or ""
    fact_type: str
    category: str  # objection_category (NA unless fact_type == objection)
    competitor: str  # NA unless relevant
    product_feature: str  # NA unless relevant
    interest_theme: str  # NA unless relevant
    quote: str
    utterance_id: str | None
    speaker_type: str
    confidence: float
    grounded: bool
    model: str
    prompt_version: str
    extracted_at: str
    source: str = "unknown"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def validate_grounding(quote: str, utterances: list[Utterance]) -> tuple[bool, str | None]:
    """A quote is grounded iff it is a verbatim (whitespace/case-insensitive) substring
    of the utterances we actually showed the model. Returns (grounded, utterance_id)."""
    nq = _norm(quote)
    if len(nq) < 8:  # too short to be a meaningful, auditable span
        return False, None
    # Per-utterance containment resolves which utterance the span came from.
    for u in utterances:
        if nq in _norm(u.snippet):
            uid = u.id
            if uid is None and u.index is not None:
                uid = str(u.index)
            return True, (str(uid) if uid is not None else None)
    # Cross-utterance span: still grounded against the concatenation, no single id.
    joined = _norm(" ".join(u.snippet for u in utterances))
    if nq in joined:
        return True, None
    return False, None


# --------------------------------------------------------------------------- #
# Extraction (LLM-as-extractor)
# --------------------------------------------------------------------------- #
def extraction_schema(taxonomy: dict[str, list[str]]) -> dict[str, Any]:
    """JSON schema for strict structured outputs, built from the active taxonomy."""
    def str_enum(key: str) -> dict[str, Any]:
        return {"type": "string", "enum": [*taxonomy[key], NA]}

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "fact_type": {"type": "string", "enum": taxonomy["fact_type"]},
                        "category": str_enum("objection_category"),
                        "competitor": str_enum("competitor"),
                        "product_feature": str_enum("product_feature"),
                        "interest_theme": str_enum("interest_theme"),
                        "quote": {"type": "string"},
                        "speaker_type": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "fact_type",
                        "category",
                        "competitor",
                        "product_feature",
                        "interest_theme",
                        "quote",
                        "speaker_type",
                        "confidence",
                    ],
                },
            }
        },
        "required": ["facts"],
    }


def build_extraction_prompt(call: Call, taxonomy: dict[str, list[str]]) -> str:
    company = call.company_name or call.account_name or "<unknown company>"
    lines: list[str] = []
    for i, u in enumerate(call.utterances):
        snippet = (u.snippet or "").strip()
        if not snippet:
            continue
        lines.append(f"[u{i} | {u.speaker_type or '?'}] {snippet}")
    transcript = "\n".join(lines)

    def enum_list(key: str) -> str:
        return ", ".join(taxonomy[key])

    return f"""You extract structured sales-intelligence facts from ONE customer call.

Company: {company}

Return a JSON object: {{"facts": [ ... ]}}. Each fact describes one concrete thing
the CUSTOMER expressed. Use ONLY these closed vocabularies (pick the closest; use
"other" if none fit, and "{NA}" for fields that do not apply to the fact):
- fact_type: {enum_list("fact_type")}
- category (objection_category, only for fact_type=objection): {enum_list("objection_category")}
- competitor: {enum_list("competitor")}
- product_feature: {enum_list("product_feature")}
- interest_theme: {enum_list("interest_theme")}

Rules:
- `quote` MUST be copied VERBATIM from a snippet below (a short phrase, <= 240 chars).
  Do not paraphrase, fix grammar, or merge across snippets. If you cannot quote it
  verbatim, do not emit the fact.
- `speaker_type` is the speaker of the quoted snippet (customer / rep).
- `confidence` in [0,1].
- Prefer facts grounded in CUSTOMER speech. Do not invent companies, features, or numbers.
- If the call contains no substantive facts, return {{"facts": []}}.

CALL SNIPPETS (quote only from these):
{transcript}
"""


def _parse_facts_json(text: str) -> list[dict[str, Any]]:
    """Tolerantly parse the model's JSON (handles code fences and bare arrays)."""
    if not text:
        return []
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).rsplit("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = data.get("facts", [])
    return [f for f in data if isinstance(f, dict)] if isinstance(data, list) else []


def extract_facts_for_call(
    client: LLMClient, call: Call, taxonomy: dict[str, list[str]]
) -> list[Fact]:
    """LLM-extract -> coerce to taxonomy -> validate grounding. One LLM call per call."""
    if not call.utterances:
        return []
    prompt = build_extraction_prompt(call, taxonomy)
    out = client.complete(prompt, schema=extraction_schema(taxonomy))

    raw_facts = _parse_facts_json(out["text"])
    call_date = _fmt_date(call.call_date)
    now = _now_iso()

    facts: list[Fact] = []
    for rf in raw_facts:
        quote = str(rf.get("quote", "")).strip()
        if not quote:
            continue
        fact_type = coerce_enum(rf.get("fact_type"), taxonomy["fact_type"], default="interest")
        grounded, uid = validate_grounding(quote, call.utterances)
        try:
            confidence = float(rf.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        facts.append(
            Fact(
                call_id=call.call_id,
                company_name=call.company_name or "",
                account_name=call.account_name or "",
                call_date=call_date,
                fact_type=fact_type,
                category=coerce_enum(rf.get("category"), taxonomy["objection_category"], NA)
                if fact_type == "objection"
                else NA,
                competitor=coerce_enum(rf.get("competitor"), taxonomy["competitor"], NA),
                product_feature=coerce_enum(rf.get("product_feature"), taxonomy["product_feature"], NA),
                interest_theme=coerce_enum(rf.get("interest_theme"), taxonomy["interest_theme"], NA),
                quote=quote[:240],
                utterance_id=uid,
                speaker_type=str(rf.get("speaker_type") or "?"),
                confidence=max(0.0, min(1.0, confidence)),
                grounded=grounded,
                model=client.model,
                prompt_version=PROMPT_VERSION,
                extracted_at=now,
                source=call.source,
            )
        )
    return facts


# --------------------------------------------------------------------------- #
# Local fact store (SQLite + JSONL export) -- no writes to any source backend
# --------------------------------------------------------------------------- #
class FactStore:
    """Cache key is (source, call_id, prompt_version, model) so facts from
    different adapters (synthetic/jsonl) never collide."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS extractions (
                source TEXT, call_id TEXT, prompt_version TEXT, model TEXT,
                extracted_at TEXT, cohort TEXT, n_facts INTEGER,
                PRIMARY KEY (source, call_id, prompt_version, model)
            );
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT, cohort TEXT,
                call_id TEXT, company_name TEXT, account_name TEXT, call_date TEXT,
                fact_type TEXT, category TEXT, competitor TEXT, product_feature TEXT,
                interest_theme TEXT, quote TEXT, utterance_id TEXT, speaker_type TEXT,
                confidence REAL, grounded INTEGER, model TEXT, prompt_version TEXT,
                extracted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(source, call_id, prompt_version, model);
            CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type);
            """
        )
        self.conn.commit()

    def is_cached(self, source: str, call_id: str, prompt_version: str, model: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM extractions WHERE source=? AND call_id=? AND prompt_version=? AND model=?",
            (source, call_id, prompt_version, model),
        )
        return cur.fetchone() is not None

    def replace_call(
        self, call_id: str, facts: list[Fact], *, cohort: str, source: str, model: str
    ) -> None:
        """Atomically replace all facts for (source, call_id, prompt_version, model)."""
        self.conn.execute(
            "DELETE FROM facts WHERE source=? AND call_id=? AND prompt_version=? AND model=?",
            (source, call_id, PROMPT_VERSION, model),
        )
        self.conn.executemany(
            """INSERT INTO facts
               (source, cohort, call_id, company_name, account_name, call_date, fact_type,
                category, competitor, product_feature, interest_theme, quote, utterance_id,
                speaker_type, confidence, grounded, model, prompt_version, extracted_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    source, cohort, f.call_id, f.company_name, f.account_name, f.call_date,
                    f.fact_type, f.category, f.competitor, f.product_feature, f.interest_theme,
                    f.quote, f.utterance_id, f.speaker_type, f.confidence, int(f.grounded),
                    f.model, f.prompt_version, f.extracted_at,
                )
                for f in facts
            ],
        )
        self.conn.execute(
            """INSERT OR REPLACE INTO extractions
               (source, call_id, prompt_version, model, extracted_at, cohort, n_facts)
               VALUES (?,?,?,?,?,?,?)""",
            (source, call_id, PROMPT_VERSION, model, _now_iso(), cohort, len(facts)),
        )
        self.conn.commit()

    def load_facts(
        self, *, model: str | None = None, cohort: str | None = None, source: str | None = None
    ) -> list[Fact]:
        sql = "SELECT * FROM facts WHERE prompt_version=?"
        params: list[Any] = [PROMPT_VERSION]
        if model:
            sql += " AND model=?"
            params.append(model)
        if cohort:
            sql += " AND cohort=?"
            params.append(cohort)
        if source:
            sql += " AND source=?"
            params.append(source)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_fact(r) for r in rows]

    @staticmethod
    def _row_to_fact(r: sqlite3.Row) -> Fact:
        return Fact(
            call_id=r["call_id"], company_name=r["company_name"], account_name=r["account_name"],
            call_date=r["call_date"], fact_type=r["fact_type"], category=r["category"],
            competitor=r["competitor"], product_feature=r["product_feature"],
            interest_theme=r["interest_theme"], quote=r["quote"], utterance_id=r["utterance_id"],
            speaker_type=r["speaker_type"], confidence=r["confidence"], grounded=bool(r["grounded"]),
            model=r["model"], prompt_version=r["prompt_version"], extracted_at=r["extracted_at"],
            source=r["source"],
        )

    def export_jsonl(
        self, path: str, *, model: str | None = None, cohort: str | None = None,
        source: str | None = None,
    ) -> int:
        facts = self.load_facts(model=model, cohort=cohort, source=source)
        with open(path, "w") as fh:
            for f in facts:
                fh.write(json.dumps(asdict(f), default=str) + "\n")
        return len(facts)

    def close(self) -> None:
        self.conn.close()


# --------------------------------------------------------------------------- #
# Deterministic aggregation (plain-Python $match / $group over cached facts)
# --------------------------------------------------------------------------- #
@dataclass
class Bucket:
    key: str
    mentions: int
    companies: set[str] = field(default_factory=set)
    evidence: list[tuple[str, str, str]] = field(default_factory=list)  # (company, call_id, quote)


@dataclass
class Aggregation:
    label: str | None
    n_calls: int
    n_facts_total: int
    n_facts_grounded: int
    date_min: str
    date_max: str
    as_of: str
    window_days: int
    interests: list[Bucket]
    features: list[Bucket]
    objections_windowed: list[Bucket]  # question 2: last N days
    competitors: list[Bucket]


def _count_dimension(facts: list[Fact], attr: str, *, skip: set[str]) -> list[Bucket]:
    buckets: dict[str, Bucket] = {}
    for f in facts:
        key = getattr(f, attr)
        if not key or key in skip:
            continue
        b = buckets.setdefault(key, Bucket(key=key, mentions=0))
        b.mentions += 1
        b.companies.add(f.company_name or f.call_id)
        if len(b.evidence) < 25:
            b.evidence.append((f.company_name or "?", f.call_id, f.quote))
    return sorted(buckets.values(), key=lambda b: (-b.mentions, -len(b.companies), b.key))


def aggregate_facts(
    facts: list[Fact], label: str | None, *, as_of: dt.date | None, window_days: int
) -> Aggregation:
    grounded = [f for f in facts if f.grounded]
    call_ids = {f.call_id for f in facts}
    dates = sorted(d for d in (f.call_date for f in grounded) if d)
    date_min, date_max = (dates[0], dates[-1]) if dates else (NA, NA)

    if as_of is None:
        as_of = _parse_date(date_max) or dt.date.today()
    cutoff = as_of - dt.timedelta(days=window_days)

    def in_window(f: Fact) -> bool:
        d = _parse_date(f.call_date)
        return d is not None and cutoff <= d <= as_of

    objections = [f for f in grounded if f.fact_type == "objection"]
    objections_win = [f for f in objections if in_window(f)] or objections  # fall back to all-time

    skip = {NA, "", "other"}
    return Aggregation(
        label=label,
        n_calls=len(call_ids),
        n_facts_total=len(facts),
        n_facts_grounded=len(grounded),
        date_min=date_min,
        date_max=date_max,
        as_of=as_of.isoformat(),
        window_days=window_days,
        interests=_count_dimension(grounded, "interest_theme", skip=skip),
        features=_count_dimension(grounded, "product_feature", skip=skip),
        objections_windowed=_count_dimension(objections_win, "category", skip={NA, ""}),
        competitors=_count_dimension(grounded, "competitor", skip=skip),
    )


# --------------------------------------------------------------------------- #
# Rendering: deterministic report (+ optional grounded narrative)
# --------------------------------------------------------------------------- #
def _render_buckets(buckets: list[Bucket], show_evidence: bool, top: int = 8) -> list[str]:
    out: list[str] = []
    if not buckets:
        out.append("- _(no grounded evidence)_")
        return out
    for b in buckets[:top]:
        out.append(f"- **{b.key}** - {b.mentions} mentions across {len(b.companies)} companies")
        if show_evidence:
            for company, call_id, quote in b.evidence[:3]:
                out.append(f'    - {company} ({call_id}): "{quote}"')
    return out


def render_report(agg: Aggregation, *, show_evidence: bool) -> str:
    pct = (100.0 * agg.n_facts_grounded / agg.n_facts_total) if agg.n_facts_total else 0.0
    flagged = agg.n_facts_total - agg.n_facts_grounded
    lines = [
        "# Customer Intelligence Report (grounded + deterministic)",
        "",
        f"Cohort: `{agg.label or 'all'}`  |  calls: {agg.n_calls}  |  "
        f"facts: {agg.n_facts_total} total, {agg.n_facts_grounded} grounded "
        f"({pct:.0f}%), {flagged} flagged (quote not verbatim-found)",
        f"Data span: {agg.date_min} -> {agg.date_max}  |  as_of: {agg.as_of}  |  "
        f"recent window: last {agg.window_days} days",
        "",
        "## 1. What companies like these want from the product",
        "_Interest themes (all-time):_",
        *_render_buckets(agg.interests, show_evidence),
        "",
        "_Product features they bring up:_",
        *_render_buckets(agg.features, show_evidence),
        "",
        f"## 2. Top complaints & objections (last {agg.window_days} days up to {agg.as_of})",
        *_render_buckets(agg.objections_windowed, show_evidence),
        "",
        "## 3. Competitors / incumbents referenced",
        *_render_buckets(agg.competitors, show_evidence),
        "",
        "---",
        "_Every count above is a deterministic group-by over locally cached, quote-grounded "
        "facts; re-running yields identical numbers. Use `audit` or `--show-evidence` to drill "
        "down to the exact {company, call_id, quote} rows._",
    ]
    return "\n".join(lines)


def render_narrative(client: LLMClient, agg: Aggregation, report_md: str) -> str:
    """Optional: LLM restates the ALREADY-computed aggregates, citing evidence only."""
    evidence_lines: list[str] = []
    for label, buckets in (
        ("INTEREST", agg.interests),
        ("FEATURE", agg.features),
        ("OBJECTION", agg.objections_windowed),
        ("COMPETITOR", agg.competitors),
    ):
        for b in buckets[:6]:
            for company, call_id, quote in b.evidence[:2]:
                evidence_lines.append(f'{label}/{b.key} | {company} ({call_id}): "{quote}"')
    prompt = (
        "You are summarizing an ALREADY-COMPUTED, deterministic aggregation. Do NOT invent "
        "or re-rank anything. Write 3 short paragraphs (interests, complaints, features). "
        "Every sentence must cite at least one (company, call_id) from the evidence list. "
        "Do not use any fact not present below.\n\n"
        f"DETERMINISTIC REPORT:\n{report_md}\n\nEVIDENCE (the only citable facts):\n"
        + "\n".join(evidence_lines)
    )
    return client.complete(prompt)["text"]


# --------------------------------------------------------------------------- #
# Small shared helpers
# --------------------------------------------------------------------------- #
def _fmt_date(value: Any) -> str:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    s = str(value or "")
    return s[:10]


def _parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _effective_base_url(args: argparse.Namespace) -> str | None:
    """Where to send requests: an explicit base URL, LLM_BASE_URL, or the Ollama
    default when --ollama is set. None means OpenAI's public API."""
    base = getattr(args, "base_url", None) or os.getenv("LLM_BASE_URL")
    if not base and getattr(args, "ollama", False):
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    return base


def apply_model_default(args: argparse.Namespace) -> None:
    """Resolve the effective model once, in-place, so every command agrees on the
    string the fact store is keyed by. Explicit --model wins; then a model env
    var; then a sensible local default (llama3.1) when targeting a local server;
    else the OpenAI default."""
    if getattr(args, "model", None):
        return
    env_model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("OLLAMA_MODEL")
    local = bool(_effective_base_url(args)) or getattr(args, "ollama", False)
    args.model = env_model or ("llama3.1" if local else DEFAULT_MODEL)


def make_client(args: argparse.Namespace) -> LLMClient | None:
    """Build an LLMClient from args/env. Returns None (with a logged error) only
    when targeting OpenAI with no OPENAI_API_KEY. Local servers (e.g. Ollama)
    need no real key -- all the pipeline wants from the model is JSON."""
    apply_model_default(args)
    base_url = _effective_base_url(args)
    key = os.getenv("OPENAI_API_KEY")
    local = bool(base_url)
    if local:
        key = key or "local"  # the SDK needs a non-empty string; local servers ignore it
    elif not key:
        LOG.error(
            "OPENAI_API_KEY is not set. Add it to a .env file (see .env.example), "
            "or run a local model with --ollama (or --base-url / LLM_BASE_URL)."
        )
        return None
    LOG.info(
        "LLM | endpoint %s | model %s | key %s | concurrency %d",
        base_url or "https://api.openai.com/v1 (OpenAI)",
        args.model,
        "local" if local else f"...{key[-4:]}",
        getattr(args, "concurrency", 1),
    )
    return LLMClient(key, args.model, base_url=base_url)


# --------------------------------------------------------------------------- #
# Extraction driver (bounded concurrency + cache + per-call isolation)
# --------------------------------------------------------------------------- #
def run_extraction(
    calls: list[Call],
    store: FactStore,
    client: LLMClient,
    taxonomy: dict[str, list[str]],
    *,
    cohort: str,
    source: str,
    concurrency: int,
    refresh: bool,
) -> tuple[int, int, int]:
    """Extract facts for each call (skipping cached), persisting as they finish.
    Returns (n_extracted_calls, n_cached_calls, n_facts)."""
    todo = [
        c for c in calls
        if refresh or not store.is_cached(source, c.call_id, PROMPT_VERSION, client.model)
    ]
    cached = len(calls) - len(todo)
    if cached:
        LOG.info("%d/%d calls already cached (source=%s prompt=%s model=%s); skipping.",
                 cached, len(calls), source, PROMPT_VERSION, client.model)
    if not todo:
        return 0, cached, 0

    n_facts = 0
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        future_to_call = {pool.submit(extract_facts_for_call, client, c, taxonomy): c for c in todo}
        for fut in as_completed(future_to_call):
            call = future_to_call[fut]
            try:
                facts = fut.result()
            except Exception as exc:  # noqa: BLE001 - isolate one bad call from the batch
                LOG.warning("Extraction failed for call %s (%s): %s",
                            call.call_id, call.company_name, exc)
                continue
            store.replace_call(call.call_id, facts, cohort=cohort, source=source, model=client.model)
            n_facts += len(facts)
            done += 1
            if done % 5 == 0 or done == len(todo):
                LOG.info("Extracted %d/%d calls (%d facts so far)...", done, len(todo), n_facts)
    return done, cached, n_facts


def extract_calls(
    calls: list[Call], args: argparse.Namespace, *, cohort: str, source: str, client: LLMClient
) -> tuple[int, int, int]:
    """Shared extract-and-persist used by the run/extract/compare commands."""
    taxonomy = load_taxonomy(args.taxonomy)
    store = FactStore(args.store)
    try:
        done, cached, n_facts = run_extraction(
            calls, store, client, taxonomy,
            cohort=cohort, source=source, concurrency=args.concurrency, refresh=args.refresh,
        )
        jsonl = str(Path(args.store).with_suffix(".jsonl"))
        store.export_jsonl(jsonl, model=client.model, cohort=cohort, source=source)
        LOG.info("Extraction done: %d new, %d cached, %d facts. JSONL: %s",
                 done, cached, n_facts, jsonl)
    finally:
        store.close()
    return done, cached, n_facts


# --------------------------------------------------------------------------- #
# Shared commands (source-agnostic): report, audit, selftest
# --------------------------------------------------------------------------- #
def aggregate_and_render(
    args: argparse.Namespace, narrative_client: LLMClient | None, *,
    cohort: str | None = None, source: str | None = None,
) -> int:
    store = FactStore(args.store)
    try:
        facts = store.load_facts(model=args.model, cohort=cohort, source=source)
    finally:
        store.close()
    if not facts:
        LOG.error("No facts in store (model=%s, cohort=%s, source=%s). Run extract/run first.",
                  args.model, cohort, source)
        return 1
    as_of = _parse_date(args.as_of) if getattr(args, "as_of", None) else None
    agg = aggregate_facts(facts, cohort or source, as_of=as_of, window_days=args.window_days)
    if args.json:
        payload = asdict(agg)
        for dim in ("interests", "features", "objections_windowed", "competitors"):
            payload[dim] = [
                {"key": b.key, "mentions": b.mentions, "companies": sorted(b.companies),
                 "evidence": b.evidence}
                for b in getattr(agg, dim)
            ]
        print(json.dumps(payload, default=str, indent=2))
        return 0
    report = render_report(agg, show_evidence=args.show_evidence)
    print(report)
    if getattr(args, "narrative", False):
        if not narrative_client:
            LOG.warning("Skipping --narrative: no model configured (missing key / endpoint).")
        else:
            print("\n" + "=" * 78 +
                  "\nGROUNDED NARRATIVE (restates aggregates, cites evidence)\n" + "=" * 78 + "\n")
            try:
                print(render_narrative(narrative_client, agg, report))
            except Exception as exc:  # noqa: BLE001
                LOG.error("Narrative failed: %s", exc)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    narrative_client = make_client(args) if getattr(args, "narrative", False) else None
    return aggregate_and_render(
        args, narrative_client,
        cohort=getattr(args, "cohort", None), source=getattr(args, "source", None),
    )


def cmd_audit(args: argparse.Namespace) -> int:
    store = FactStore(args.store)
    try:
        facts = store.load_facts(model=args.model, source=getattr(args, "source", None))
    finally:
        store.close()
    if not facts:
        LOG.error("No facts to audit. Run extract/run first.")
        return 1
    total = len(facts)
    grounded = sum(1 for f in facts if f.grounded)
    sample = random.sample(facts, min(args.sample, total))
    print(f"# Fact audit sheet  ({total} facts, {grounded} grounded = "
          f"{100.0 * grounded / total:.0f}%, sampling {len(sample)})\n")
    print("Mark each row pass/fail: does the quote support the extracted fact?\n")
    for i, f in enumerate(sample, 1):
        flag = "OK " if f.grounded else "UNGROUNDED"
        tag = "/".join(x for x in (f.fact_type, f.category, f.competitor, f.product_feature,
                                   f.interest_theme) if x and x != NA)
        print(f"[{i:>2}] [{flag}] conf={f.confidence:.2f}  {f.company_name} "
              f"({f.source}:{f.call_id})  utt={f.utterance_id}")
        print(f"     {tag}")
        print(f'     ({f.speaker_type}) "{f.quote}"')
        print("     review: [ ] pass  [ ] fail\n")
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    """Offline checks -- no network, no API key required."""
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    tax = DEFAULT_TAXONOMY
    # 1. taxonomy coercion
    check("coerce 'Kestrel BI' -> kestrel_bi",
          coerce_enum("Kestrel BI", tax["competitor"]) == "kestrel_bi")
    check("coerce 'Pricing' -> pricing_cost",
          coerce_enum("pricing", tax["objection_category"]) == "pricing_cost")
    check("coerce unknown -> other", coerce_enum("quantum_blockchain", tax["competitor"]) == "other")
    check("coerce None/'n/a' -> other", coerce_enum(None, tax["product_feature"]) == "other")

    # 2. grounding (against typed Utterance objects)
    utts = [Utterance(snippet="We are comparing it against Kestrel BI from the cost perspective.",
                      id="u-1", index=0)]
    ok1, uid1 = validate_grounding("comparing it against Kestrel BI", utts)
    ok2, _ = validate_grounding("we evaluated Brightline pricing", utts)
    check("grounding: verbatim substring -> grounded + utterance id", ok1 and uid1 == "u-1")
    check("grounding: hallucinated quote -> not grounded", not ok2)

    # 3. JSON parse tolerance (code fences + object wrapper)
    parsed = _parse_facts_json('```json\n{"facts":[{"quote":"x","fact_type":"objection"}]}\n```')
    check("parse fenced JSON object -> 1 fact", len(parsed) == 1 and parsed[0]["quote"] == "x")

    # 4. deterministic aggregation
    def mk(**kw: Any) -> Fact:
        return Fact(
            call_id=kw.get("call_id", "c1"), company_name=kw.get("company", "Acme"),
            account_name="", call_date=kw.get("date", "2024-02-01"),
            fact_type=kw.get("fact_type", "objection"), category=kw.get("category", NA),
            competitor=kw.get("competitor", NA), product_feature=kw.get("feature", NA),
            interest_theme=kw.get("interest", NA), quote=kw.get("quote", "some grounded quote"),
            utterance_id="u1", speaker_type="customer", confidence=0.9,
            grounded=kw.get("grounded", True), model="m", prompt_version=PROMPT_VERSION,
            extracted_at=_now_iso(), source="selftest",
        )

    facts = [
        mk(fact_type="objection", category="pricing_cost", company="Acme", date="2024-02-10"),
        mk(fact_type="objection", category="pricing_cost", company="Beta", date="2024-02-11"),
        mk(fact_type="objection", category="migration_effort", company="Acme", date="2024-02-12"),
        mk(fact_type="product_feature", feature="dashboards", company="Beta"),
        mk(fact_type="objection", category="pricing_cost", company="Z", date="2019-01-01"),  # old
        mk(grounded=False, category="performance"),  # excluded (ungrounded)
    ]
    agg = aggregate_facts(facts, "all", as_of=dt.date(2024, 2, 28), window_days=90)
    top_obj = agg.objections_windowed[0]
    check("aggregate: top windowed objection is pricing_cost x2 (old one excluded by window)",
          top_obj.key == "pricing_cost" and top_obj.mentions == 2)
    check("aggregate: ungrounded fact excluded", agg.n_facts_grounded == 5 and agg.n_facts_total == 6)
    check("aggregate: feature dashboards present", any(b.key == "dashboards" for b in agg.features))

    # 5. report renders
    rep = render_report(agg, show_evidence=True)
    check("report mentions groundedness + sections", "grounded" in rep and "## 2." in rep)

    # 6. compare heuristics (loss + invention detection)
    from .compare import selftest_checks  # local import avoids an import cycle
    for name, cond in selftest_checks():
        check(name, cond)

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
    return 0 if not failures else 1


# --------------------------------------------------------------------------- #
# Shared argparse fragments
# --------------------------------------------------------------------------- #
def llm_args(store_default: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--model", default=None,
                   help="Model name. Default: gpt-4o-mini (OpenAI) or llama3.1 (local). "
                        "Also honors LLM_MODEL / OPENAI_MODEL / OLLAMA_MODEL.")
    p.add_argument("--ollama", action="store_true",
                   help="Target a local Ollama server (http://localhost:11434/v1); no key needed.")
    p.add_argument("--base-url", default=None,
                   help="Any OpenAI-compatible base URL (else OpenAI, or LLM_BASE_URL).")
    p.add_argument("--concurrency", type=int, default=6)
    p.add_argument("--taxonomy", default=None, help="Path to a JSON taxonomy override")
    p.add_argument("--refresh", action="store_true", help="Ignore cache; re-extract all calls")
    p.add_argument("--store", default=store_default)
    return p


def report_args() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--window-days", type=int, default=90)
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD anchor for the recent window")
    p.add_argument("--show-evidence", action="store_true")
    p.add_argument("--narrative", action="store_true", help="Add a grounded LLM narrative")
    p.add_argument("--json", action="store_true")
    p.add_argument("--cohort", default=None, help="Filter facts by cohort label")
    p.add_argument("--source", default=None, help="Filter facts by source (synthetic/jsonl)")
    return p
