"""The independent judge: Claude Sonnet 5.5 with its own prompt, reading the brief and one final pack. It scores all
three arms the same way and never feeds back into a pipeline. Each of its flags was then reviewed one by one (audit/labels.yaml).
"""

import json

from . import llm, pipeline

JUDGE = "sonnet-5.5"
TYPES = ("invented", "contradicted", "offer-without-terms")


def judge(brief: dict, pack) -> dict:
    if not isinstance(pack, dict):
        return {"issues": [], "unparsed": True, "cost_usd": 0.0, "ms": 0}
    user = f"BRIEF\n{pipeline.brief_for_model(brief)}\nAD PACK\n{json.dumps(pack, ensure_ascii=False, indent=1)}"
    res = llm.call(JUDGE, pipeline.prompt("judge"), user, sample=0, purpose="judge", effort=None)
    found = llm.parse_json(res["text"])
    items = found.get("issues") if isinstance(found, dict) else None
    if not isinstance(items, list):
        return {"issues": [], "unparsed": True, "cost_usd": res["cost_usd"], "ms": res["ms"]}
    issues = [
        {"field": str(i.get("field", "")), "text": str(i.get("text", "")), "type": i.get("type"), "why": str(i.get("why", ""))}
        for i in items
        if isinstance(i, dict) and i.get("type") in TYPES
    ]
    return {"issues": issues, "unparsed": False, "cost_usd": res["cost_usd"], "ms": res["ms"]}
