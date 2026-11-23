#!/usr/bin/env python3
"""Regenerate the figures used in blog.md and README.md.

    python3 assets/make_figures.py

Needs only matplotlib. Every number below is copied from real `compare` runs
against a local llama3 (Ollama); LLM output is non-deterministic, so a fresh
run of `compare` will produce different numbers. The figures document these
runs, they do not recompute them:

  * SYN0001 -- `python -m callintel compare --ollama --model llama3 --call-id syn-0001`
               (the output block embedded in blog.md)
  * ALL_CALLS -- `python -m callintel compare --ollama --model llama3`
               (raw output saved next to this script as compare_all_llama3.md)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent

INK = "#1f2328"
MUTED = "#57606a"
LINE = "#8c959f"
PANEL = "#f6f8fa"
RED = "#cf222e"
RED_BG = "#ffebe9"
GREEN = "#1a7f37"
GREEN_BG = "#dafbe1"
BLUE = "#0969da"
BLUE_BG = "#ddf4ff"
AMBER = "#9a6700"
AMBER_BG = "#fff8c5"

plt.rcParams.update({
    "font.family": ["Arial", "DejaVu Sans"],
    "font.size": 12,
    "text.color": INK,
    "axes.edgecolor": LINE,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "savefig.dpi": 200,
})

SYN0001 = {
    "grounded": 7,
    "covered": 4,
    "lost": ["\u201cevery regional manager builds their own reports by hand\u201d  (utt 1)",
             "\u201cabout 120 store managers\u201d  (utt 2)",
             "\u201cbudget ... around 48 thousand dollars\u201d  (utt 3)"],
    "inventions": 0,
    "bullets": 5,
    "bullets_cited": 0,
    "facts_quoted": 7,
}


def _box(ax, x, y, w, h, text, *, fc=PANEL, ec=LINE, color=INK, size=12, weight="normal", ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fc, ec=ec, lw=1.4, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size,
            color=color, weight=weight, linespacing=1.35)


def _arrow(ax, x0, y0, x1, y1, *, color=LINE, ls="-", rad=0.0, lw=1.6):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=16,
                                 color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}"))


def _canvas(w, h, xlim, ylim):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return fig, ax


def _save(fig, name):
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"wrote {path}")


# --------------------------------------------------------------------------- #
# 1. Black-box summary vs auditable pipeline
# --------------------------------------------------------------------------- #
def fig_pipelines():
    fig, ax = _canvas(13, 6.2, (0, 26), (0, 12.4))
    bh = 2.0

    ax.text(0.2, 11.6, "Black-box summary", fontsize=15, weight="bold", color=RED)
    ax.text(5.6, 11.6, "convenient, confident, no trail", fontsize=12, color=MUTED, style="italic")
    y = 8.4
    _box(ax, 0.2, y, 4.2, bh, "Transcript")
    _box(ax, 6.0, y, 4.6, bh, "LLM\n\"summarize this call\"")
    _box(ax, 12.2, y, 5.0, bh, "Five tidy bullets\n(prose)")
    _box(ax, 18.8, y, 6.8, bh, "Which sentence said that?\nNo link back to the words.",
         fc=RED_BG, ec=RED, color=RED)
    for x0, x1 in [(4.4, 6.0), (10.6, 12.2), (17.2, 18.8)]:
        _arrow(ax, x0, y + bh / 2, x1, y + bh / 2)

    ax.plot([0.2, 25.6], [7.2, 7.2], color="#d0d7de", lw=1)

    ax.text(0.2, 6.3, "Auditable pipeline", fontsize=15, weight="bold", color=GREEN)
    ax.text(5.9, 6.3, "the model only extracts; everything after it is checkable",
            fontsize=12, color=MUTED, style="italic")
    y = 3.1
    _box(ax, 0.2, y, 4.2, bh, "Transcript")
    _box(ax, 5.4, y, 4.6, bh, "LLM extracts\ntyped facts + quote")
    _box(ax, 11.0, y, 4.4, bh, "Verbatim quote\ncheck (substring)", fc=BLUE_BG, ec=BLUE)
    _box(ax, 16.4, y, 4.2, bh, "Deterministic\ncounts (Python)")
    _box(ax, 21.6, y, 4.0, bh, "Report", fc=GREEN_BG, ec=GREEN, color=GREEN, weight="bold")
    for x0, x1 in [(4.4, 5.4), (10.0, 11.0), (15.4, 16.4), (20.6, 21.6)]:
        _arrow(ax, x0, y + bh / 2, x1, y + bh / 2)

    ax.text(13.2, 2.45, "fails \u2192 flagged ungrounded,\nexcluded from counts", ha="center",
            va="top", fontsize=10.5, color=MUTED)
    _arrow(ax, 23.6, y, 2.3, y, color=GREEN, rad=-0.18, lw=1.8)
    ax.text(12.9, 0.05, "every number drills down to {call_id, utterance_id, quote}",
            ha="center", va="bottom", fontsize=12.5, color=GREEN, weight="bold")
    _save(fig, "fig1_blackbox_vs_auditable.png")


# --------------------------------------------------------------------------- #
# 2. syn-0001: a constraint became a concession
# --------------------------------------------------------------------------- #
def _rich_lines(ax, x, y, lines, *, size=13.5, step=0.95):
    """Draw lines made of (text, bg) segments; bg=None means plain text."""
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    for i, segs in enumerate(lines):
        cx = x
        for text, bg in segs:
            kw = {}
            if bg:
                kw["bbox"] = dict(boxstyle="square,pad=0.12", fc=bg[0], ec="none")
            t = ax.text(cx, y - i * step, text, fontsize=size, va="baseline",
                        color=bg[1] if bg else INK, weight="bold" if bg else "normal", **kw)
            bb = t.get_window_extent(renderer)
            (x0, _), (x1, _) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y0)])
            cx += x1 - x0


def fig_concession():
    fig, ax = _canvas(13, 5.6, (0, 26), (0, 11.2))
    red, green = (RED_BG, RED), (GREEN_BG, GREEN)

    ax.add_patch(FancyBboxPatch((0.2, 0.6), 11.4, 8.6, boxstyle="round,pad=0.02,rounding_size=0.2",
                                fc="white", ec=RED, lw=1.6))
    ax.text(0.2, 10.2, "What the customer said", fontsize=15, weight="bold")
    ax.text(0.2, 9.5, "syn-0001, utterance 11 (verbatim)", fontsize=11.5, color=MUTED)
    _rich_lines(ax, 0.8, 8.0, [
        [("\u201cOne more thing, our current contract", None)],
        [("auto renews in March and ", None)],
        [("we cannot sign anything that locks", red)],
        [("us in for more than a year.", red), ("\u201d", None)],
    ])
    ax.text(0.8, 1.3, "RED FLAG: a hard contract constraint", fontsize=12.5, color=RED, weight="bold")

    _arrow(ax, 11.9, 5.0, 14.0, 5.0, color=INK, lw=2.2)
    ax.text(12.95, 5.6, "summarized", ha="center", fontsize=11, color=MUTED)

    ax.add_patch(FancyBboxPatch((14.3, 0.6), 11.5, 8.6, boxstyle="round,pad=0.02,rounding_size=0.2",
                                fc="white", ec=GREEN, lw=1.6))
    ax.text(14.3, 10.2, "What the summary said", fontsize=15, weight="bold")
    ax.text(14.3, 9.5, "llama3 free-form summary, bullet 5", fontsize=11.5, color=MUTED)
    _rich_lines(ax, 14.9, 8.0, [
        [("\u201cThe customer is interested in moving", None)],
        [("forward if the solution can handle their", None)],
        [("point of sale systems and ", None)],
        [("is willing to auto-renew their", green)],
        [("current contract in March", green), (", but only", None)],
        [("if the new solution does not lock them", None)],
        [("in for more than a year.\u201d", None)],
    ])
    ax.text(14.9, 1.3, "GREEN LIGHT: reads as a concession", fontsize=12.5, color=GREEN, weight="bold")
    _save(fig, "fig2_constraint_became_concession.png")


# --------------------------------------------------------------------------- #
# 3. syn-0001 compare scorecard
# --------------------------------------------------------------------------- #
def fig_scorecard():
    d = SYN0001
    fig = plt.figure(figsize=(13, 5.0))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1], wspace=0.42)

    ax = fig.add_subplot(gs[0])
    ax.set_xlim(0, 7.6)
    ax.set_ylim(-3.5, 2.4)
    ax.axis("off")
    ax.set_title(f"{d['grounded']} grounded facts: does the summary cover them?",
                 loc="left", fontsize=14, weight="bold", pad=10)
    for i in range(d["grounded"]):
        covered = i < d["covered"]
        ax.add_patch(FancyBboxPatch((i * 1.05 + 0.1, 0.3), 0.85, 0.85,
                                    boxstyle="round,pad=0.0,rounding_size=0.1",
                                    fc=BLUE_BG if covered else RED_BG,
                                    ec=BLUE if covered else RED, lw=1.5))
        ax.text(i * 1.05 + 0.525, 0.725, "\u2713" if covered else "\u2717", ha="center",
                va="center", fontsize=16, color=BLUE if covered else RED, weight="bold")
    ax.text(0.1, 1.6, f"covered: {d['covered']}", fontsize=12.5, color=BLUE, weight="bold")
    ax.text(d["covered"] * 1.05 + 0.1, 1.6, f"lost: {len(d['lost'])}", fontsize=12.5,
            color=RED, weight="bold")
    ax.text(0.1, -0.35, "What was lost:", fontsize=12, color=MUTED)
    for j, label in enumerate(d["lost"]):
        ax.text(0.1, -0.95 - j * 0.55, label, fontsize=11.5, color=RED, va="center")
    ax.text(0.1, -2.55, f"Invention check: {d['inventions']} detected.\nThe failure is "
            "distortion and omission, not fabrication.", fontsize=11, color=MUTED, style="italic",
            va="top", linespacing=1.4)

    ax2 = fig.add_subplot(gs[1])
    labels = ["Summary bullets\nthat cite a source", "Grounded facts linked\nto an exact quote"]
    have = [d["bullets_cited"], d["facts_quoted"]]
    total = [d["bullets"], d["grounded"]]
    pct = [h / t * 100 for h, t in zip(have, total)]
    ypos = [1, 0]
    ax2.barh(ypos, [100, 100], color="#eaeef2", height=0.5)
    ax2.barh(ypos, pct, color=[RED, GREEN], height=0.5)
    for yy, h, t, p, c in zip(ypos, have, total, pct, [RED, GREEN]):
        ax2.text(max(p, 0) + 2 if p < 80 else p - 2, yy, f"{h} of {t}",
                 ha="left" if p < 80 else "right", va="center", fontsize=14, weight="bold",
                 color=c if p < 80 else "white")
    ax2.set_yticks(ypos, labels, fontsize=12, color=INK)
    ax2.set_xlim(0, 100)
    ax2.set_xticks([0, 50, 100], ["0%", "50%", "100%"])
    ax2.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        ax2.spines[s].set_visible(False)
    ax2.set_title("Traceability", loc="left", fontsize=14, weight="bold", pad=10)
    _save(fig, "fig3_compare_scorecard_syn0001.png")


# --------------------------------------------------------------------------- #
# 4. Anatomy of a decision record (a real stored fact)
# --------------------------------------------------------------------------- #
def fig_decision_record():
    fig, ax = _canvas(13, 5.4, (0, 26), (0, 10.8))
    rows = [
        ("label", "fact_type: interest\ntheme:     self_serve_reporting",
         "MODEL'S INTERPRETATION", "Can be wrong (it is, here). A human\nfixes it to a contract-terms objection.",
         AMBER_BG, AMBER),
        ("quote", "\u201cOne more thing, our current contract auto\n"
                  "renews in March and we cannot sign anything\n"
                  "that locks us in for more than a year.\u201d",
         "OBJECTIVE ARTIFACT", "Verbatim substring of the transcript:\nchecked mechanically, grounded = true.",
         BLUE_BG, BLUE),
        ("provenance", "call_id: syn-0001    utterance_id: 11",
         "WHERE TO LOOK", "Jump straight to the sentence\nand decide in seconds.",
         GREEN_BG, GREEN),
        ("version", "model: llama3    prompt_version: facts-v1",
         "WHICH RULES", "Change the prompt or model and old\nfacts are superseded, not mixed in.",
         PANEL, MUTED),
    ]
    ax.text(0.2, 10.2, "One extracted fact is a decision record, not a confession",
            fontsize=15, weight="bold")
    h, gap, top = 2.0, 0.35, 9.3
    for i, (key, val, tag, note, bg, fg) in enumerate(rows):
        y = top - (i + 1) * h - i * gap
        ax.add_patch(FancyBboxPatch((0.2, y), 15.0, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    fc=bg, ec=fg, lw=1.4))
        ax.text(0.6, y + h / 2, key, fontsize=11.5, color=fg, weight="bold", va="center")
        ax.text(3.6, y + h / 2, val, fontsize=11, va="center", family="monospace",
                linespacing=1.35)
        _arrow(ax, 15.4, y + h / 2, 16.4, y + h / 2, color=fg)
        ax.text(16.7, y + h / 2 + 0.45, tag, fontsize=11.5, color=fg, weight="bold", va="center")
        ax.text(16.7, y + h / 2 - 0.35, note, fontsize=10.5, color=MUTED, va="center",
                linespacing=1.3)
    _save(fig, "fig4_decision_record.png")


# --------------------------------------------------------------------------- #
# 5. All seven calls: grounded facts covered vs lost
# --------------------------------------------------------------------------- #
# (company, call_id, grounded, covered) from compare_all_llama3.md
ALL_CALLS: list[tuple[str, str, int, int]] = [
    ("Northwind Retail", "syn-0001", 7, 4),
    ("Cobalt Health", "syn-0002", 9, 4),
    ("Meridian Logistics", "syn-0003", 6, 5),
    ("Apex Fintech", "syn-0004", 8, 6),
    ("Granite Manufacturing", "syn-0005", 6, 2),
    ("Harbor Media", "syn-0006", 6, 2),
    ("Vertex Education", "syn-0007", 9, 7),
]


def fig_all_calls():
    if not ALL_CALLS:
        return
    fig, ax = plt.subplots(figsize=(12, 5.2))
    rows = list(reversed(ALL_CALLS))
    names = [f"{c}  ({cid})" for c, cid, _, _ in rows]
    covered = [cov for _, _, _, cov in rows]
    lost = [g - cov for _, _, g, cov in rows]
    y = range(len(rows))
    ax.barh(y, covered, color=BLUE, height=0.6, label="covered by the summary")
    ax.barh(y, lost, left=covered, color=RED, height=0.6, label="lost (grounded, not in summary)")
    for yy, c, n_lost in zip(y, covered, lost):
        if c:
            ax.text(c / 2, yy, str(c), ha="center", va="center", color="white", weight="bold")
        if n_lost:
            ax.text(c + n_lost / 2, yy, str(n_lost), ha="center", va="center", color="white",
                    weight="bold")
    ax.set_yticks(list(y), names, fontsize=11.5, color=INK)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("grounded, quote-backed facts per call")
    ax.xaxis.get_major_locator().set_params(integer=True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    tg, tc = sum(r[2] for r in ALL_CALLS), sum(r[3] for r in ALL_CALLS)
    ax.set_title(f"Across all {len(ALL_CALLS)} calls, the summaries dropped {tg - tc} of {tg} "
                 "grounded facts", loc="left", fontsize=14, weight="bold", pad=12)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.24), ncol=2, frameon=False)
    _save(fig, "fig5_coverage_all_calls.png")


if __name__ == "__main__":
    fig_pipelines()
    fig_concession()
    fig_scorecard()
    fig_decision_record()
    fig_all_calls()
