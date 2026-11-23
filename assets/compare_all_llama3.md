# Naive summary vs. grounded extraction

Model: `llama3`  |  calls compared: 7

For each call below: a normal free-form summary, then the grounded facts it dropped, the numbers or names it appears to have invented, and a traceability tally. Loss and invention are deterministic text heuristics (see `callintel/compare.py`); treat them as signal, not a verdict.

---

## Northwind Retail  (`syn-0001`)

### Naive summary (free-form, no grounding)
• Northwind Retail is currently using spreadsheets to build reports, which takes most of a day every week.
• The company has a budget of $48,000 for the year and is looking for a solution that fits within that budget.
• The main pain point is getting clean data into dashboards, as they pull from four different point of sale systems.
• Query performance is a concern, but more importantly, the customer wants to trust that the numbers are accurate.
• The customer is interested in moving forward if the solution can handle their point of sale systems and is willing to auto-renew their current contract in March, but only if the new solution does not lock them in for more than a year.

### What the grounded extraction found
7 grounded, quote-backed facts. The summary covers 4, and misses 3.

#### Lost facts (grounded, but absent from the summary)
- **interest/self_serve_reporting** - (customer) "Right now every regional manager builds their own reports by hand in spreadsheets, and it eats most of a day every single week."  [syn-0001 / utt 1]
- **interest/team_velocity** - (customer) "We have about 120 store managers who would need access to this."  [syn-0001 / utt 2]
- **interest/cost_reduction** - (customer) "The budget we have approved is around 48 thousand dollars for the year, so pricing really matters to us."  [syn-0001 / utt 3]

#### Likely inventions (in the summary, not in the transcript)
- None detected by this heuristic.

#### Traceability
- Summary bullets that cite a source: 0 of 5.
- Grounded facts that link to an exact quote {call_id, utterance_id, quote}: 7 of 7.

## Cobalt Health  (`syn-0002`)

### Naive summary (free-form, no grounding)
• Cobalt Health is a healthcare provider seeking a solution to replace their in-house tool with an auditable report generator.
• The current tool lacks an audit trail, which is a compliance requirement.
• The customer expects any serious vendor to pass security and compliance reviews, but is more concerned about migration and support.
• The customer is interested in Lumen's ability to keep full audit logs on every change and supports single sign-on (SSO) with SCIM provisioning.
• The customer is looking for a seamless migration plan to bring over their three years of historical data and requires same-day support for any compliance report issues.

### What the grounded extraction found
9 grounded, quote-backed facts. The summary covers 4, and misses 5.

#### Lost facts (grounded, but absent from the summary)
- **interest/compliance_reporting** - (customer) "An audit log on every change is exactly what our compliance team keeps asking for."  [syn-0002 / utt 4]
- **interest/compliance_reporting** - (customer) "We would need single sign on through Okta for all 300 clinicians."  [syn-0002 / utt 5]
- **objection/migration_effort** - (customer) "My bigger worry is migration, we have three years of history in the old tool and I am not sure we can move it over."  [syn-0002 / utt 6]
- **product_feature/api** - (rep) "We can bring historical data across through the import API."  [syn-0002 / utt 7]
- **interest/cost_reduction** - (customer) "If you can bring that history over it makes this a much easier internal sell."  [syn-0002 / utt 8]

#### Likely inventions (in the summary, not in the transcript)
- None detected by this heuristic.

#### Traceability
- Summary bullets that cite a source: 0 of 5.
- Grounded facts that link to an exact quote {call_id, utterance_id, quote}: 9 of 9.

## Meridian Logistics  (`syn-0003`)

### Naive summary (free-form, no grounding)
• The customer is seeking real-time visibility into shipments to enable timely reactions to delays.
• Current dashboards only refresh once a night, making it too late to react to delayed shipments.
• Lumen's solution can stream updates and fire alerts the moment a shipment slips its window, which would be a significant improvement.
• The customer's primary concern is speed and scalability, as they move about 2 million shipments a month.
• The customer is interested in Lumen's solution if it can maintain speed at their volume, and is willing to budget for a learning curve for their team.

### What the grounded extraction found
6 grounded, quote-backed facts. The summary covers 5, and misses 1.

#### Lost facts (grounded, but absent from the summary)
- **objection/migration_effort/kestrel_bi** - (customer) "We looked hard at Kestrel BI but the dashboards got painfully slow once we passed a few million rows."  [syn-0003 / utt 4]

#### Likely inventions (in the summary, not in the transcript)
- Proper names not found in the transcript: Current

#### Traceability
- Summary bullets that cite a source: 0 of 5.
- Grounded facts that link to an exact quote {call_id, utterance_id, quote}: 6 of 6.

## Apex Fintech  (`syn-0004`)

### Naive summary (free-form, no grounding)
• Apex Fintech is interested in embedding analytics and AI assistant directly into their customer-facing app, rather than sending users to a separate tool.
• They would use the API to pull Lumen charts into their product and are interested in the AI assistant's ability to answer natural language questions across all data.
• The customer is skeptical of AI answers and wants to see the sources behind each number, which would increase their trust in the assistant.
• The company is a startup with 40 seats currently, but expects to grow quickly, and is price-sensitive but not yet comfortable with budget.
• The customer is concerned about lock-in and wants a clean export path in case they need to leave Apex Fintech's API in the future.

### What the grounded extraction found
8 grounded, quote-backed facts. The summary covers 6, and misses 2.

#### Lost facts (grounded, but absent from the summary)
- **interest/ai_assistant/ai_insights** - (customer) "We are also really interested in the AI assistant, letting our ops team ask questions in plain English."  [syn-0004 / utt 2]
- **interest/other/cost_reduction** - (customer) "Pricing wise we are a startup, we have maybe 40 seats today but we expect to grow fast."  [syn-0004 / utt 6]

#### Likely inventions (in the summary, not in the transcript)
- None detected by this heuristic.

#### Traceability
- Summary bullets that cite a source: 0 of 5.
- Grounded facts that link to an exact quote {call_id, utterance_id, quote}: 8 of 8.

## Granite Manufacturing  (`syn-0005`)

### Naive summary (free-form, no grounding)
• The customer is currently using separate tools for finance, operations, and reporting, and is looking to consolidate down to one platform.
• The customer's primary value proposition is the ability for Lumen to connect to their ERP and finance system.
• The customer runs an older on-premise ERP system, and is unsure if Lumen supports it out of the box.
• The customer has approximately 85 report consumers spread across their plants.
• The customer is not under pressure to make a decision, as their current Brightline contract does not renew until September of next year.

### What the grounded extraction found
6 grounded, quote-backed facts. The summary covers 2, and misses 4.

#### Lost facts (grounded, but absent from the summary)
- **objection/migration_effort/brightline/consolidation** - (customer) "We are paying for three different tools and I really want to consolidate down to one."  [syn-0005 / utt 1]
- **interest/consolidation** - (customer) "We are paying for three different tools and I really want to consolidate down to one."  [syn-0005 / utt 1]
- **interest/consolidation** - (customer) "Consolidating the spreadsheets is the real priority."  [syn-0005 / utt 7]
- **product_feature/api** - (rep) "Lumen ships native connectors for most of the major ERPs."  [syn-0005 / utt 3]

#### Likely inventions (in the summary, not in the transcript)
- None detected by this heuristic.

#### Traceability
- Summary bullets that cite a source: 0 of 5.
- Grounded facts that link to an exact quote {call_id, utterance_id, quote}: 6 of 6.

## Harbor Media  (`syn-0006`)

### Naive summary (free-form, no grounding)
• The customer is frustrated with the unpredictable cost increases and slow custom dashboard development on Quanta Insights.
• The customer wants their analysts to be able to build their own dashboards without relying on the professional services team.
• The rep highlighted Lumen's self-serve capabilities, allowing analysts to build dashboards in minutes.
• The customer is interested in Lumen, but has concerns about support and reliability, citing a previous negative experience with Quanta.
• The customer is not committing to a specific timeline for a decision, but is considering Lumen as a potential solution.

### What the grounded extraction found
6 grounded, quote-backed facts. The summary covers 2, and misses 4.

#### Lost facts (grounded, but absent from the summary)
- **objection/pricing_cost/quanta_insights** - (customer) "the cost keeps climbing every renewal, it is completely unpredictable."  [syn-0006 / utt 0]
- **interest/cost_reduction** - (customer) "If my team can move that fast on their own it genuinely changes how we operate."  [syn-0006 / utt 4]
- **interest/team_velocity** - (customer) "If my team can move that fast on their own it genuinely changes how we operate."  [syn-0006 / utt 4]
- **objection/support/quanta_insights** - (customer) "Honestly my single biggest fear is support, when Quanta went down we waited days, and I cannot put us through that again."  [syn-0006 / utt 9]

#### Likely inventions (in the summary, not in the transcript)
- None detected by this heuristic.

#### Traceability
- Summary bullets that cite a source: 0 of 5.
- Grounded facts that link to an exact quote {call_id, utterance_id, quote}: 6 of 6.

## Vertex Education  (`syn-0007`)

### Naive summary (free-form, no grounding)
• The customer is a university system that needs to accurately report enrollment numbers to the state every term.
• Currently, they are using a messy system of spreadsheets emailed around, which is not reliable.
• The customer requires role-based access control, specifically row-level access by department, which is a hard requirement.
• The customer has 15 colleges and approximately 500 staff members who touch reporting, and security review will take time but is not a dealbreaker.
• The customer's timeline is the real constraint, as procurement adds about three months to the process, and they may need to put the project out to bid, which could bring Brightline back into the mix.

### What the grounded extraction found
9 grounded, quote-backed facts. The summary covers 7, and misses 2.

#### Lost facts (grounded, but absent from the summary)
- **objection/migration_effort** - (customer) "Today it is a mess of spreadsheets emailed around and nobody can tell which version is actually final."  [syn-0007 / utt 1]
- **product_feature/sso_scim** - (rep) "Lumen supports SSO, SCIM provisioning, and row level access controls out of the box."  [syn-0007 / utt 3]

#### Likely inventions (in the summary, not in the transcript)
- Proper names not found in the transcript: Currently

#### Traceability
- Summary bullets that cite a source: 0 of 5.
- Grounded facts that link to an exact quote {call_id, utterance_id, quote}: 9 of 9.

---

_Black boxes can't be opened -- but strategic facts and quotes buy you auditability, and a possible explanation._