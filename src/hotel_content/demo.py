"""A terminal walk-through for the demo video: one hotel's one-shot draft, what the checks caught, the repaired pack,
then the results table. Reads results/ only; no model calls."""

import json
import time

from . import checks, experiment

HOTEL, MODEL, SAMPLE = "lantern", "haiku-4.5", 0


def _say(line: str = "", pause: float = 0.0) -> None:
    print(line, flush=True)
    if pause:
        time.sleep(pause)


def main(pause: float = 0.5, hotel: str = HOTEL, model: str = MODEL, sample: int = SAMPLE) -> None:
    rows = [json.loads(line) for line in (experiment.RESULTS / "packs.jsonl").read_text().splitlines()]
    pick = {r["arm"]: r for r in rows if (r["hotel"], r["model"], r["sample"]) == (hotel, model, sample)}
    brief = checks.load_briefs()[hotel]
    _say(f"BRIEF  {brief['name']}, {brief['town']} (made-up hotel)", pause)
    _say(f"  offer: {brief['offer']['text']}, {', '.join(brief['offer']['conditions'])}")
    _say(f"  does not have: {', '.join(brief['not_available'])}", pause)
    _say()
    one = pick["oneshot"]
    _say(f"ONE-SHOT draft ({model})", pause)
    for issue in one["rule_issues"]:
        _say(f"  rule problem  [{issue['rule']}] {issue['field']}: {issue['detail'][:90]}", pause / 2)
    for issue in one["audited_issues"]:
        _say(f"  judge+review  [{issue['type']}] {issue['field']}: {issue['text'][:70]}", pause / 2)
    if one["clean"]:
        _say("  clean", pause)
    full = pick["full"]
    _say()
    _say(f"PIPELINE (checks, LLM fact check, {full['rounds']} repair round(s))", pause)
    for issue in full["rule_issues"] + full["audited_issues"]:
        _say(f"  still wrong   {issue.get('field')}: {issue.get('detail') or issue.get('text')}"[:110], pause / 2)
    _say("  clean" if full["clean"] else "  flagged for review" if full["flagged_for_review"] else "  shipped with a problem")
    m = full["pack"].get("meta_ad", {}) if isinstance(full["pack"], dict) else {}
    _say(f"  meta ad: {m.get('primary_text', '')}", pause)
    _say()
    _say("RESULTS  (8 made-up hotels x 2 samples per model; judge flags reviewed one by one)", pause)
    summary = json.loads((experiment.RESULTS / "summary.json").read_text())
    _say(f"  {'model':<11}{'setup':<9}{'clean':>7}{'claims':>8}{'unflagged bad':>15}{'$/pack':>9}{'s/pack':>8}")
    for r in summary["table"]:
        _say(
            f"  {r['model']:<11}{r['arm']:<9}{r['clean_packs']:>4}/{r['packs']:<2}{r['unsupported_claims']:>8}"
            f"{r['shipped_dirty']:>15}{r['cost_per_pack_usd']:>9.3f}{r['seconds_per_pack']:>8.0f}",
            pause / 2,
        )
