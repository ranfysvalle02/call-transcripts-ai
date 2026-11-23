# Your call summaries are quietly lying to you

### Why free-form LLM call summaries fail in production — and how verbatim-quote extraction makes them auditable.

> A worked example of why "just summarize the call" is riskier than it looks, and six concrete things you can do about it. All code and data are in [call-transcripts-ai](./README.md); the calls are synthetic.
>
> This is a companion to [blackbox-ai](https://github.com/ranfysvalle02/blackbox-ai), a "flight recorder" for coding agents. Same idea, different domain: when the machine won't tell you the truth about why, stop trusting its story and start anchoring on the objective artifacts it leaves behind.

## 1. The seductive summary

You just got off a 40-minute customer call. You paste the transcript into a model and ask for five bullets. Ten seconds later you have a tidy summary, you drop it into the CRM, and you move on.

This feels like a free win. It is not. That summary is now the *system of record* for what the customer said — and it was produced by a process that is **lossy by design** and **impossible to audit after the fact**. Nobody will ever reread the transcript. The bullets are the truth now.

Every expensive, mysterious machine we build eventually gets a flight recorder, because "it seemed fine" is not an answer when something goes wrong. An LLM summarizing your calls is exactly that kind of machine, and by default it flies blind: three weeks later the deal slips, you go back to ask *"wait, what did they actually say about the contract?"* — and all you have is a bullet point that someone paraphrased from a paraphrase. The words evaporated the moment the summary was written.

Let's look at exactly what gets lost.

## 2. Summarization is lossy by definition

A summary's whole job is to throw information away. The problem is *which* information, and the model decides silently, differently each time.

Take one synthetic call from this repo — Northwind Retail, `syn-0001`. In the transcript the customer says, in their own words:

- "Honestly the dashboards are **not** the problem for us" — then the rep guesses "so performance is really your top concern", and the customer pushes back: "**Maybe, but I would not say performance**, it is really about trusting that the numbers are right."
- "The budget we have approved is around **48 thousand** dollars for the year."
- And in the very last turn: "our current contract **auto renews in March** and we cannot sign anything that locks us in for more than a year."

Here is what `compare` actually produced for that call, running **fully locally against Ollama (`llama3`) — no OpenAI, no API key**. The summary is the model's real output; everything below it is the tool's deterministic analysis (`python -m callintel compare --ollama --model llama3 --call-id syn-0001`):

```markdown
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
```

Read it closely — and remember this came out of a small 8B model on a laptop, which makes the point sharper, not weaker:

- **A hard constraint became a concession.** The customer said they "cannot sign anything that locks us in for more than a year." The summary reports they are "**willing to auto-renew their current contract in March**." A red flag got written up as a green light. This is the most dangerous failure mode: the summary is confidently *wrong*, not merely incomplete.
- **The hedge and negation got flattened.** The customer pushed back — "I would not say performance" — yet the summary leads its fourth bullet with "Query performance is a concern." The qualifier survives in spirit, but the emphasis is inverted.
- **A specific number vanished.** "120 store managers" — the entire scope of the deal — is simply gone.
- **The texture is lost.** "every regional manager builds their own reports by hand" flattens into "using spreadsheets to build reports." Close enough to feel faithful, lossy enough that you can no longer tell *who* does *what*.

Notice the invention check came back empty: this model didn't fabricate a number or a name, it *distorted* and *dropped* — the quieter, more common failure. (And yes, coverage is strict on purpose: `$48,000` appears in the summary, yet the 48-thousand fact is still "lost," because coverage wants the customer's *actual words*, not a paraphrase you can't trace back. That strictness is the feature.) The heuristics are signal, not a verdict — the output says so itself — but the direction is unmistakable: the summary reads beautifully, and it is not safe to trust.

## 3. The black box: why you can't just ask it to be better

Beyond lossiness, a raw summary has three properties that make it unauditable:

- **Non-determinism.** Ask twice, get two different summaries. Which one is "the call"? There is no stable answer, so any metric you build on top of summaries (counts of objections, win/loss themes) silently drifts.
- **Silent model and prompt drift.** Your vendor upgrades the model. Someone tweaks the prompt. Yesterday's summaries and today's are no longer comparable, and nothing records that the rules changed.
- **No provenance.** A bullet says "performance is their main concern." Where in the 40 minutes did they say that? You cannot tell. There is no link from the claim back to the evidence, so the claim can never be checked — only trusted.

And here's the part people miss: **you cannot fix this by asking the model to explain itself.** If you ask "why did you say performance?", you get *another* generated paragraph — a plausible, confident story that may have nothing to do with what actually drove the output. The model's self-report is the convenient signal, not the trustworthy one. This is the same lesson [blackbox-ai](https://github.com/ranfysvalle02/blackbox-ai) draws about a coding agent's chain-of-thought: treat a capture as a **decision record, not a confession**.

"The AI said so" — and "the AI said it did so for this reason" — are both just the AI talking.

## 4. Mitigation: box the model in

You cannot make an LLM deterministic or omniscient, and you cannot trust its explanation of itself. But you can box it in so its mistakes are *small, local, and checkable*, and so that the record you keep is anchored on something objective. Here is the recipe this repo implements.

### 4.1 Extract, don't summarize
Ask the model for a list of small, typed facts, not prose. A fact like `{fact_type: objection, category: contract_terms, quote: "..."}` is a tiny, verifiable claim. Prose is an unverifiable blob. (`build_extraction_prompt`, `extraction_schema` in `callintel/core.py`.)

### 4.2 Anchor on the objective artifact — verify every quote mechanically
This is the keystone. Each fact must carry a `quote`, and that quote must be a **verbatim substring** of the utterances we actually showed the model. If it is not, the fact is flagged *ungrounded* and excluded from the counts.

The quote is the objective artifact — the equivalent of a diff or a tool call in agent-land. The *label* on top of it ("this is a contract-terms objection") is the model's stated interpretation and can be wrong; the quote itself either exists in the transcript or it doesn't, and that is a mechanical string check, not a judgment call. A hallucinated quote cannot survive it. (`validate_grounding`.)

### 4.3 Use closed vocabularies
The model must label each fact using a fixed enum (`pricing_cost`, `contract_terms`, `dashboards`, ...). Anything it invents is coerced to the nearest known bucket, or to `other`. Closed vocabularies are what keep "pricing", "price sensitive", and "too expensive" from becoming three different categories. (`DEFAULT_TAXONOMY`, `coerce_enum`.)

### 4.4 Move determinism upstream, and version everything
The LLM runs exactly once per transcript, as an extractor. Every count, ranking, and time window after that is plain Python over the cached facts, so re-running the report gives byte-identical numbers — no model touches the arithmetic (`aggregate_facts`). And because the cache key is `(source, call_id, prompt_version, model)`, with `prompt_version` + model stamped on every stored fact, changing the prompt or the model transparently supersedes the old facts, and you can always tell which rules produced which number.

### 4.5 Generate the narrative last, and keep it on a leash
If you do want prose at the end, generate it *from the already-computed aggregates*, and require it to cite the evidence. The optional `--narrative` restates numbers that were computed deterministically; it is not allowed to introduce a fact that isn't already in the evidence list. (`render_narrative`.)

### 4.6 Keep a human in the loop, and measure the loss
Grounding proves a quote is real; it does not prove the *label* is right. The `audit` command prints a random sample of facts with their quotes so a person can mark each pass/fail — auditability means someone can actually do the audit. And `compare` makes the lossiness visible instead of pretending it isn't there: per call, how many grounded facts a summary dropped, what it appears to have invented, and how little of it is traceable.

## 5. From a black box to a possible explanation

Notice what this buys you. We never opened the black box. We never got the model to truthfully explain itself. We still ran a stochastic model we don't fully understand.

But look at the difference in what we can *say* afterward.

- **Before:** "The customer is willing to auto-renew their current contract in March." Source: a summary. Confidence: total. Checkability: none. If it's wrong — and it is — you'll never know why.
- **After:** "A contract-terms concern was raised on call `syn-0001`, at utterance 11, where the customer said *'our current contract auto renews in March and we cannot sign anything that locks us in for more than a year.'*"

That second statement is not certainty — in this very run the small local model even filed that quote under the wrong category. But it is **auditable**: a human can jump straight to utterance 11, read the sentence, decide in five seconds that it's a *constraint* and not a willingness, and fix the label. The claim is pinned to an objective artifact and a location, so you can reconstruct a *possible explanation* for any number in the report — and defend it, or catch the error. An LLM is a black box and will stay one; strategic facts and verbatim quotes don't make it transparent, they just give you a trail back to the words that were actually said. That is the whole trade: black boxes can't be opened, but strategic facts and quotes buy you auditability, and a possible explanation. Auditability instead of blind trust. A possible explanation instead of a shrug.

## 6. What this does *not* solve

Be honest about the edges:

- **Grounding is not correctness.** A verbatim quote can still be tagged with the wrong category. The mechanical check catches fabrication, not misclassification — hence the human audit.
- **The `compare` heuristics are lexical.** Coverage is a content-word overlap test; invention detection is a digit-sequence and proper-noun presence test. They are intentionally simple so they are themselves auditable, and they lean toward *under*-reporting problems rather than crying wolf. They are signal, not a verdict.
- **Real transcripts are noisy, and strict matching has a recall cost.** These calls are clean text. Real ASR output has odd punctuation, filler words, and inconsistent spelling — and models quietly tidy it up when they quote. A strict `quote in transcript` check (even with the whitespace- and case-normalization used here) will then reject a *valid* quote like "auto-renews" against a transcript that says "auto renews." On real data you trade some strictness for recall: normalize punctuation, or fall back to a fuzzy / near-substring match, and accept that grounding becomes high-precision rather than perfect.
- **Extraction has its own cost.** One LLM call per transcript, a taxonomy to maintain, and a schema to evolve. In exchange you get numbers you can defend. For a throwaway personal note, a plain summary is fine. For anything that feeds a decision, it isn't.

## 7. Try it yourself

All the output above was produced on a laptop with no OpenAI account. The tool talks to the OpenAI-compatible Chat Completions API, so it runs against OpenAI *or* a fully local model via [Ollama](https://ollama.com) — all it needs from the model is a JSON response.

```bash
pip install -r requirements.txt

# Fully local, no API key: just `ollama serve` + `ollama pull llama3`
python -m callintel run     --ollama --model llama3 --show-evidence
python -m callintel compare --ollama --model llama3 --out out/compare.md

# ...or against OpenAI
export OPENAI_API_KEY=sk-...
python -m callintel run --show-evidence

python -m callintel audit --sample 10          # the human-in-the-loop step
python -m callintel selftest                   # offline, proves the checks work
```

Swap in your own transcripts with `--jsonl your_calls.jsonl`. The model still makes mistakes — you saw a laptop-sized one make several — but now every mistake is small, local, and something you can see, trace, and explain.
