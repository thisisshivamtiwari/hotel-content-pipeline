"""Three ways to turn a brief into an ad pack, sharing the same first draft so the comparison is paired:

- `oneshot`: one call with the full spec and rules in the prompt (the baseline most teams start with);
- `rules`: the draft, then deterministic checks (checks.py) and up to 2 repair calls that list the exact problems;
- `full`: as `rules`, plus an LLM fact check against the brief before each repair decision.

The judge (judge.py) scores the final packs; it is never part of a pipeline.
"""

import json
from pathlib import Path

import yaml

from . import checks, llm

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
ARMS = ["oneshot", "rules", "full"]
MAX_REPAIRS = 2


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.txt").read_text().strip()


def brief_for_model(brief: dict) -> str:
    """The brief as the marketer sees it. The checker's internal trigger words and brand colours stay out."""
    offer = {k: brief["offer"][k] for k in ("text", "conditions")}
    shown = {k: v for k, v in brief.items() if k not in ("id", "brand", "offer")}
    return yaml.safe_dump({**shown, "offer": offer}, allow_unicode=True, sort_keys=False)


def _call(alias: str, name: str, user: str, sample: int, purpose: str, log: list) -> str:
    res = llm.call(alias, prompt(name), user, sample=sample, purpose=purpose)
    log.append({"purpose": purpose, "cost_usd": res["cost_usd"], "ms": res["ms"]})
    return res["text"]


def draft(alias: str, brief: dict, sample: int, log: list) -> dict | None:
    text = _call(alias, "generate", f"BRIEF\n{brief_for_model(brief)}", sample, "generate", log)
    return llm.parse_json(text)


def llm_check(alias: str, brief: dict, pack, sample: int, log: list, rnd: int) -> list[dict]:
    user = f"BRIEF\n{brief_for_model(brief)}\nAD PACK\n{json.dumps(pack, ensure_ascii=False, indent=1)}"
    found = llm.parse_json(_call(alias, "check", user, sample, f"check-{rnd}", log))
    if not isinstance(found, list):
        return [{"rule": "checker-unparsed", "field": "pack", "detail": "the checker's reply was not a JSON list"}]
    return [
        {"rule": "llm-check", "field": str(i.get("field", "")), "detail": f"{i.get('claim', '')!r}: {i.get('why', '')}"}
        for i in found
        if isinstance(i, dict)
    ]


def repair(alias: str, brief: dict, pack, problems: list[dict], sample: int, log: list, rnd: int, arm: str) -> dict | None:
    listed = "\n".join(f"- [{p['rule']}] {p['field']}: {p['detail']}" for p in problems)
    user = f"BRIEF\n{brief_for_model(brief)}\nCURRENT PACK\n{json.dumps(pack, ensure_ascii=False, indent=1)}\nPROBLEMS\n{listed}"
    return llm.parse_json(_call(alias, "repair", user, sample, f"repair-{arm}-{rnd}", log))


def run(alias: str, brief: dict, sample: int) -> dict[str, dict]:
    """All three arms for one (model, hotel, sample). Returns {arm: {pack, log, rounds, last_problems}}."""
    base_log: list = []
    first = draft(alias, brief, sample, base_log)
    out = {"oneshot": {"pack": first, "log": base_log, "rounds": 0, "last_problems": []}}
    for arm in ("rules", "full"):
        log, pack, rounds = list(base_log), first, 0
        while True:
            problems = checks.check_pack(pack, brief)
            if arm == "full":
                problems += llm_check(alias, brief, pack, sample, log, rounds)
            if not problems or rounds == MAX_REPAIRS:
                break
            fixed = repair(alias, brief, pack, problems, sample, log, rounds, arm)
            rounds += 1
            pack = fixed if fixed is not None else pack
        out[arm] = {"pack": pack, "log": log, "rounds": rounds, "last_problems": problems}
    return out
