#!/usr/bin/env python3
"""Synthetic call source -- realistic, fictional B2B sales calls.

These are hand-written sales calls for a fictional analytics product called
"Lumen". They let the whole pipeline (extract -> ground -> aggregate -> report)
and the `compare` demo run anywhere with only an OPENAI_API_KEY -- no customer
data, nothing real.

Every company, competitor, and number here is invented.

The calls are written on purpose to be *hard to summarize faithfully*. Each one
plants at least one classic summarization trap so the `compare` command has
something to catch:
  * specific numbers (seat counts, budgets, dates) a summary tends to drop or
    round;
  * hedges ("maybe", "not sure") a summary tends to harden into certainty;
  * negations ("security is NOT the blocker") a summary can silently flip;
  * a rep claim the customer never agrees to (misattribution bait);
  * a real objection buried in the final turn.

IMPORTANT: utterances must read like real speech. Grounding requires every
extracted quote to be a VERBATIM substring of a snippet below, so summaries or
paraphrases here would (correctly) be flagged ungrounded.
"""
from __future__ import annotations

import datetime as dt

from ..core import Call, Utterance


def _c(call_id: str, company: str, day: str, turns: list[tuple[str, str]]) -> Call:
    return Call(
        call_id=call_id,
        company_name=company,
        account_name=company,
        call_date=dt.datetime.fromisoformat(day),
        utterances=[
            Utterance(snippet=text, speaker_type=who, speaker_name=who.title(), index=i)
            for i, (who, text) in enumerate(turns)
        ],
        source="synthetic",
    )


# Dates are recent so the default 90-day objection window lands on them.
SAMPLE_CALLS: list[Call] = [
    _c(
        "syn-0001", "Northwind Retail", "2026-11-05",
        [
            ("rep", "Thanks for making the time. What is pushing you to look at something new right now?"),
            ("customer", "Right now every regional manager builds their own reports by hand in spreadsheets, and it eats most of a day every single week."),
            ("customer", "We have about 120 store managers who would need access to this."),
            ("customer", "The budget we have approved is around 48 thousand dollars for the year, so pricing really matters to us."),
            ("rep", "Lumen can give every one of those managers a self serve dashboard so they stop rebuilding spreadsheets by hand."),
            ("customer", "Honestly the dashboards are not the problem for us, the problem is getting clean data into them in the first place."),
            ("customer", "We pull from four different point of sale systems and stitching all of that together is painful."),
            ("rep", "So it sounds like query performance is really your top concern here."),
            ("customer", "Maybe, but I would not say performance, it is really about trusting that the numbers are right."),
            ("customer", "If your connectors can handle our point of sale systems then we would be interested in moving forward."),
            ("rep", "Great, I can line up a technical follow up with our solutions team."),
            ("customer", "One more thing, our current contract auto renews in March and we cannot sign anything that locks us in for more than a year."),
        ],
    ),
    _c(
        "syn-0002", "Cobalt Health", "2026-10-28",
        [
            ("customer", "We are a healthcare provider, so every report we generate has to be auditable for compliance."),
            ("customer", "Right now we have an in house tool a couple of engineers built, and it has no audit trail at all."),
            ("customer", "Security and compliance review is going to be involved, but honestly security is not the blocker, we expect any serious vendor to pass that."),
            ("rep", "Understood. Lumen keeps full audit logs on every change, and supports SSO with SCIM provisioning."),
            ("customer", "An audit log on every change is exactly what our compliance team keeps asking for."),
            ("customer", "We would need single sign on through Okta for all 300 clinicians."),
            ("customer", "My bigger worry is migration, we have three years of history in the old tool and I am not sure we can move it over."),
            ("rep", "We can bring historical data across through the import API."),
            ("customer", "If you can bring that history over it makes this a much easier internal sell."),
            ("rep", "I will put together a migration plan for your three years of data."),
            ("customer", "The one thing that could kill this is slow support, when a compliance report is wrong we need an answer the same day."),
        ],
    ),
    _c(
        "syn-0003", "Meridian Logistics", "2026-11-12",
        [
            ("customer", "We need real time visibility into shipments, right now our Kestrel BI dashboards only refresh once a night."),
            ("customer", "By the time we see a delayed shipment it is already too late for the team to react."),
            ("rep", "Lumen can stream updates and fire an alert the moment a shipment slips its window."),
            ("customer", "Alerts the moment something slips would be huge for our operations team."),
            ("customer", "We looked hard at Kestrel BI but the dashboards got painfully slow once we passed a few million rows."),
            ("customer", "We move about 2 million shipments a month, so scale is not theoretical for us."),
            ("rep", "So price is really the main thing you are weighing here."),
            ("customer", "No, price is secondary, speed at our volume is the thing that actually matters."),
            ("customer", "If Lumen stays fast at that volume then we are very interested."),
            ("rep", "I am confident we hold up at that scale, I will get you a benchmark."),
            ("customer", "I should flag that my team only knows Kestrel today, so there is a learning curve we will have to budget for."),
        ],
    ),
    _c(
        "syn-0004", "Apex Fintech", "2026-09-30",
        [
            ("customer", "We want to embed analytics directly inside our customer facing app, not send people off to a separate tool."),
            ("customer", "Our developers would use your API to pull Lumen charts straight into our product."),
            ("customer", "We are also really interested in the AI assistant, letting our ops team ask questions in plain English."),
            ("rep", "The AI assistant can answer natural language questions across all of your data."),
            ("customer", "That said, I am a little skeptical of AI answers, I would want to see exactly where each number came from."),
            ("customer", "If the assistant can show its sources then we would trust it a lot more."),
            ("customer", "Pricing wise we are a startup, we have maybe 40 seats today but we expect to grow fast."),
            ("rep", "So you are comfortable on budget then."),
            ("customer", "I would not say comfortable, I said we are price sensitive right now but growing quickly."),
            ("customer", "The thing I keep coming back to is lock in, if we build on your API I need a clean export path in case we ever leave."),
        ],
    ),
    _c(
        "syn-0005", "Granite Manufacturing", "2026-11-18",
        [
            ("customer", "We have Brightline for finance, spreadsheets for operations, and none of it talks to each other."),
            ("customer", "We are paying for three different tools and I really want to consolidate down to one."),
            ("customer", "If Lumen can connect to our ERP and our finance system, that is the whole value for us."),
            ("rep", "Lumen ships native connectors for most of the major ERPs."),
            ("customer", "We run an older on premise ERP though, and I am not sure you support it out of the box."),
            ("customer", "We have roughly 85 report consumers spread across the plants."),
            ("rep", "So the goal is really to rip out Brightline and replace it."),
            ("customer", "Replacing Brightline would be nice but it is not required, consolidating the spreadsheets is the real priority."),
            ("rep", "Got it, I will scope a connector for your on premise ERP."),
            ("customer", "Our renewal with Brightline is not until next September, so there is no rush and I will not be pushed on timeline."),
        ],
    ),
    _c(
        "syn-0006", "Harbor Media", "2026-10-15",
        [
            ("customer", "We are on Quanta Insights today and the cost keeps climbing every renewal, it is completely unpredictable."),
            ("customer", "Every custom dashboard has to go through their professional services team and it is painfully slow."),
            ("customer", "I want my analysts to build their own dashboards without filing a ticket and waiting a week."),
            ("rep", "Lumen is fully self serve, your analysts build their own dashboards in minutes."),
            ("customer", "If my team can move that fast on their own it genuinely changes how we operate."),
            ("customer", "We have 60 analysts who would be in the tool every day."),
            ("customer", "I will say I have been burned before, Quanta promised self serve too and it really was not."),
            ("rep", "So you will be making the final decision by the end of this quarter."),
            ("customer", "I never said end of quarter, we are still early and I am not committing to a date yet."),
            ("customer", "Honestly my single biggest fear is support, when Quanta went down we waited days, and I cannot put us through that again."),
        ],
    ),
    _c(
        "syn-0007", "Vertex Education", "2026-11-20",
        [
            ("customer", "We are a university system and we report enrollment numbers to the state every term, so it has to be exactly right."),
            ("customer", "Today it is a mess of spreadsheets emailed around and nobody can tell which version is actually final."),
            ("customer", "We need role based access so a department head only ever sees their own college."),
            ("rep", "Lumen supports SSO, SCIM provisioning, and row level access controls out of the box."),
            ("customer", "Row level access by department is a hard requirement for us, not a nice to have."),
            ("customer", "We have 15 colleges and about 500 staff who touch reporting in some way."),
            ("customer", "Security review will take time but it is not a dealbreaker, we go through this with every vendor."),
            ("rep", "So budget approval is really the last step for you."),
            ("customer", "Not quite, the budget is approved but procurement adds about three months, so timeline is the real constraint."),
            ("customer", "One concern, we are a public institution so we may have to put this out to bid, which could bring Brightline back into the mix."),
        ],
    ),
]


class SyntheticCallSource:
    """CallSource with baked-in, realistic fictional sample calls. Needs no network."""

    name = "synthetic"

    def __init__(self, cohort: str = "synthetic", limit: int | None = None) -> None:
        self.cohort = cohort
        self.limit = limit

    def fetch(self) -> list[Call]:
        calls = list(SAMPLE_CALLS)
        if self.limit:
            calls = calls[: self.limit]
        return calls
