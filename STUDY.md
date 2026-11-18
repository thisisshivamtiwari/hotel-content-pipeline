# STUDY: hotel-content-pipeline

Notes to study before talking about this project. Numbers are from [results/summary.json](results/summary.json).

## 1. The problem in one paragraph

Hotels use AI to write ads and posts. The risk isn't bad prose. It's wrong details: an offer without its conditions,
an amenity the hotel doesn't have, a "from" price shown as a flat price, "24/7" when reception closes at 11pm. They
mislead guests and can break advertising rules. The question here: is a careful prompt enough, and what does it cost
to check and repair the output?

## 2. Design choices and why

| Choice | Why | Alternative not taken |
|---|---|---|
| Made-up briefs with a "not available" list and a footage list | Gives the checks something concrete to test against; no real hotel data | Scrape real hotel sites (licensing, privacy, and no ground truth) |
| One shared first draft for all three setups | Paired comparison: differences come from checking and repair, not from sampling luck | Separate drafts per setup (needs many more samples) |
| Deterministic rules first | Cheap, exact, explainable; they catch limits, numbers, banned amenities, offer terms | LLM-only checking (costlier, less predictable) |
| Offer rule at ad-unit level, not per text | A 30-character Google headline can't hold conditions; the unit's descriptions can | Per-text rule (would fail every short headline) |
| Repair prompt lists exact problems; max 2 rounds; then flag for review | Bounded cost; a person sees what the machine couldn't fix | Loop until clean (unbounded cost, can oscillate) |
| Independent judge with its own prompt, plus a review of every flag | The pipeline's own checker can't also be the grader | Trust the checker's verdict |
| Cassettes keyed by request hash | CI is free, deterministic and needs no key; any prompt change forces a re-record | Mock the model in CI (tests nothing real) |
| Renders with labelled slots, no generated images | A render can't show what the hotel doesn't have; an editor drops in real footage | Image generation (new failure mode, out of scope) |
| `--effort low` for pipeline calls | Content copy doesn't need long reasoning; Sonnet went from minutes to ~23 s | Default effort (slower, costlier) |

## 3. Results to remember

- Sonnet 5.5 one-shot: 14/16 clean; + rule checks and one repair: 16/16 for +$0.003 a pack ($0.037, 24 s).
- Haiku 4.5 one-shot: 2/16 clean, 21 rule problems (15 offers without conditions), 41 unsupported claims, $0.10 and
  137 s a pack. The full pipeline: 5/16 clean, 24 claims (−1.06 per pack, 95% interval −1.88 to −0.31), $0.33 and
  467 s a pack, and 7 packs still shipped with an unflagged problem.
- Haiku ignored `--effort low`: 10k–32k output tokens per draft. The cheaper-per-token model was 22x dearer per clean pack.
- The judge flagged 109 statements; review kept 98 and overruled 11 (e.g. "from £599" on a fixed price, a missing
  "subject to availability").
- Whole recorded run: 202 calls, $8.25 at list prices, about 25 minutes with 8 workers.

## 4. Failure modes seen

1. **Offer without its conditions** was the most common rule failure (15 of Haiku's 21), despite an explicit rule
   in the prompt. Models compress "20% off 2+ nights Sun–Thu, book by 31 Jan" into "20% off".
2. **Stretching a true fact**: "27-inch desks" from "a desk and a 27-inch monitor"; "on the beach" from "beach 300
   metres away"; "every bed has a curtain" when only dorm beds do. Rules can't see these; the LLM check and the judge can.
3. **Dropping "from"**: "Suites £189" when the brief says "from £189 for 2 adults and 2 children".
4. **Turning a deadline into a stay window**: "through January 31" for "book by 31 January".
5. **Repair that breaks something else**: in one Haiku pack (Ferrow, sample 1) the repair rightly changed "Dine on our
   terrace" to "Visit our restaurant and terrace bar", which pushed the voiceover to 235 characters (limit 220). After
   2 rounds it was flagged for review, not shipped. Repairs need the same checks again and a round limit.
6. **Over-strict judging**: 11 of 109 judge flags were overruled. A judge needs a review step or a calibration set.
7. **The cheap model thinks hard**: Haiku's long thinking made it slower and costlier than Sonnet at low effort.

## 5. Ten likely interview questions

1. **Why not just write a better prompt?**
   The prompt already had every rule. Sonnet followed it 14 times in 16, Haiku twice. Prompts set intent; checks
   enforce it. Rule checks cost Sonnet $0.003 a pack and closed the gap.

2. **How do you know the judge is right?**
   I don't assume it. Every one of its 109 flags was reviewed against the brief and 11 were overruled, with reasons in
   audit/labels.yaml. Its weak spot is that it's the same model as one writer; the next step is a judge from another
   model family and a human sample.

3. **Why is the comparison paired?**
   All three setups start from the same draft, so a difference is caused by checking and repair, not by a luckier
   sample. The intervals are paired bootstraps over hotel x sample.

4. **What does the deterministic layer catch, and what can't it catch?**
   Limits, counts, numbers not in the brief, not-available amenities (with negation handling), superlatives, offers
   without conditions, non-existent footage. It can't catch a true fact that has been stretched ("on the beach"),
   which needs the brief's meaning.

5. **Why did the LLM fact check not help Sonnet?**
   Sonnet's drafts had no unsupported claims to find; the only problems were offer terms, which the rules already
   caught. It flagged one clean pack for review. For Sonnet it's cost without benefit; for Haiku it was the only thing
   that cut claims.

6. **How does CI work without an API key?**
   Each call is recorded with a hash of model, system prompt, user prompt, sample and effort. CI replays them,
   rebuilds summary.json, fails if it differs from the committed file, then applies gate rules (no pipeline setup
   worse than one-shot; recommended setup ships no unflagged problem).

7. **What would you put in production?**
   Sonnet-class model at low effort, rule checks, up to 2 repairs, then flag for review. Add the LLM check only for
   high-risk units or weaker models. Log every flag and every human override to tune the rules.

8. **How would you scale this to hundreds of hotels?**
   Briefs become structured data with versioning (facts change). Run per hotel per campaign in a queue with
   per-call caching. Track clean rate, flags and cost per hotel over time, and alert when a model or prompt change
   moves them.

9. **How do you handle images and video?**
   Here, renders use labelled slots so nothing false can appear. With generated media you'd need a vision check
   against the not-available list and the footage list, plus human approval before anything publishes.

10. **What surprised you?**
    The cost result: Haiku 4.5 ignored `--effort low`, thought for 10k–32k tokens per draft, and ended up slower and
    22x more expensive per clean pack than Sonnet 5.5. Price per token is not price per usable output.
