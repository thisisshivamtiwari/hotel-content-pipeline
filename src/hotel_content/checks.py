"""Deterministic checks on an ad pack: platform limits, numbers not in the brief, amenities the hotel doesn't have,
unverifiable superlatives, offers stated without their conditions, and reel shots that don't exist.

Every check returns plain dicts `{rule, field, detail}` so the repair prompt and the report can use them as they are.
"""

import re
from pathlib import Path

import yaml

BRIEFS = Path(__file__).resolve().parents[2] / "briefs" / "hotels.yaml"

# Platform limits (characters). Google responsive search ads: headlines 30, descriptions 90. Meta: the primary text
# is cut after ~125 characters in most placements, and the headline after ~40.
LIMITS = {
    "google_rsa.headlines": (5, 30),
    "google_rsa.descriptions": (3, 90),
    "meta_ad.primary_text": (1, 125),
    "meta_ad.headline": (1, 40),
    "instagram.caption": (1, 300),
    "image_post.headline": (1, 40),
    "image_post.subline": (1, 70),
    "reel.voiceover": (1, 220),
}
REEL_SCENES, REEL_TEXT, REEL_SECONDS, REEL_TOTAL = 4, 32, (2, 6), (12, 20)
MAX_HASHTAGS = 5
UNITS = ["google_rsa", "meta_ad", "instagram", "reel", "image_post"]

SUPERLATIVES = [
    "best",
    "#1",
    "number one",
    "award-winning",
    "award winning",
    "world-class",
    "world class",
    "finest",
    "unbeatable",
    "guaranteed",
    "cheapest",
    "lowest price",
    "luxury",
    "luxurious",
]
NEGATIONS = re.compile(r"\b(no|not|without|zero|never)\b[\w\s,'-]{0,20}$", re.I)
NUMBER = re.compile(r"£?\d+(?:[.,]\d+)?%?")


def load_briefs(path: Path = BRIEFS) -> dict[str, dict]:
    return {h["id"]: h for h in yaml.safe_load(path.read_text())["hotels"]}


def brief_text(brief: dict) -> str:
    """What the brief says is true, as one lower-case string (the allowed vocabulary for numbers and words). The
    not-available list and the checker's own trigger words are left out: they are not claims."""
    offer = {k: v for k, v in brief["offer"].items() if k in ("text", "conditions")}
    keep = {k: v for k, v in brief.items() if k not in ("not_available", "offer", "brand")}
    return yaml.safe_dump({**keep, "offer": offer}, allow_unicode=True).lower()


def norm(text: str) -> str:
    return text.lower().replace("–", "-").replace("—", "-").replace("’", "'")


def unit_texts(pack: dict) -> dict[str, list[tuple[str, str]]]:
    """(field path, text) pairs for each ad unit. Missing pieces are simply absent (the shape check reports them)."""
    out: dict[str, list[tuple[str, str]]] = {u: [] for u in UNITS}
    g = pack.get("google_rsa") or {}
    out["google_rsa"] += [(f"google_rsa.headlines[{i}]", t) for i, t in enumerate(g.get("headlines") or [])]
    out["google_rsa"] += [(f"google_rsa.descriptions[{i}]", t) for i, t in enumerate(g.get("descriptions") or [])]
    m = pack.get("meta_ad") or {}
    out["meta_ad"] += [(f"meta_ad.{k}", m[k]) for k in ("primary_text", "headline") if k in m]
    ig = pack.get("instagram") or {}
    if "caption" in ig:
        out["instagram"].append(("instagram.caption", ig["caption"]))
    out["instagram"] += [(f"instagram.hashtags[{i}]", t) for i, t in enumerate(ig.get("hashtags") or [])]
    r = pack.get("reel") or {}
    out["reel"] += [
        (f"reel.scenes[{i}].on_screen_text", s.get("on_screen_text", "")) for i, s in enumerate(r.get("scenes") or [])
    ]
    if "voiceover" in r:
        out["reel"].append(("reel.voiceover", r["voiceover"]))
    ip = pack.get("image_post") or {}
    out["image_post"] += [(f"image_post.{k}", ip[k]) for k in ("headline", "subline") if k in ip]
    for unit, pairs in out.items():
        out[unit] = [(f, t if isinstance(t, str) else str(t)) for f, t in pairs]
    return out


def _get(pack: dict, path: str):
    node = pack
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def check_shape(pack: dict, brief: dict) -> list[dict]:
    issues = []
    for path, (count, limit) in LIMITS.items():
        value = _get(pack, path)
        items = value if isinstance(value, list) else ([value] if value is not None else [])
        if len(items) != count or not all(isinstance(t, str) and t.strip() for t in items):
            issues.append({"rule": "shape", "field": path, "detail": f"needs {count} non-empty text(s), got {len(items)}"})
        for i, t in enumerate(items):
            if isinstance(t, str) and len(t) > limit:
                field = f"{path}[{i}]" if isinstance(value, list) else path
                issues.append({"rule": "length", "field": field, "detail": f"{len(t)} characters, limit {limit}: {t!r}"})
    heads = _get(pack, "google_rsa.headlines") or []
    if len({norm(h) for h in heads if isinstance(h, str)}) < len(heads):
        issues.append({"rule": "shape", "field": "google_rsa.headlines", "detail": "duplicate headlines"})
    tags = _get(pack, "instagram.hashtags")
    if not isinstance(tags, list) or not 1 <= len(tags) <= MAX_HASHTAGS:
        issues.append({"rule": "shape", "field": "instagram.hashtags", "detail": f"needs 1-{MAX_HASHTAGS} hashtags"})
    else:
        for i, t in enumerate(tags):
            if not isinstance(t, str) or not re.fullmatch(r"#\w+", t):
                issues.append({"rule": "shape", "field": f"instagram.hashtags[{i}]", "detail": f"not a single #word: {t!r}"})
    caption = _get(pack, "instagram.caption")
    if isinstance(caption, str) and "#" in caption:
        issues.append({"rule": "shape", "field": "instagram.caption", "detail": "hashtags belong in the hashtags list"})
    scenes = _get(pack, "reel.scenes")
    if not isinstance(scenes, list) or len(scenes) != REEL_SCENES:
        issues.append({"rule": "shape", "field": "reel.scenes", "detail": f"needs {REEL_SCENES} scenes"})
        scenes = scenes if isinstance(scenes, list) else []
    total = 0.0
    for i, s in enumerate(scenes):
        f = f"reel.scenes[{i}]"
        if not isinstance(s, dict):
            issues.append({"rule": "shape", "field": f, "detail": "scene must be an object"})
            continue
        if s.get("shot") not in brief["footage"]:
            issues.append({"rule": "footage", "field": f + ".shot", "detail": f"{s.get('shot')!r} is not in the footage list"})
        text = s.get("on_screen_text")
        if not isinstance(text, str) or not text.strip():
            issues.append({"rule": "shape", "field": f + ".on_screen_text", "detail": "missing"})
        elif len(text) > REEL_TEXT:
            issues.append(
                {"rule": "length", "field": f + ".on_screen_text", "detail": f"{len(text)} characters, limit {REEL_TEXT}"}
            )
        sec = s.get("seconds")
        if not isinstance(sec, int | float) or not REEL_SECONDS[0] <= sec <= REEL_SECONDS[1]:
            issues.append(
                {"rule": "shape", "field": f + ".seconds", "detail": f"needs {REEL_SECONDS[0]}-{REEL_SECONDS[1]} seconds"}
            )
        else:
            total += sec
    if scenes and not REEL_TOTAL[0] <= total <= REEL_TOTAL[1]:
        issues.append(
            {"rule": "shape", "field": "reel.scenes", "detail": f"total {total:g}s, needs {REEL_TOTAL[0]}-{REEL_TOTAL[1]}s"}
        )
    return issues


def check_grounding(pack: dict, brief: dict) -> list[dict]:
    """Rule-based claim checks against the brief. These catch the specific, costly mistakes; the LLM check and the
    judge look for the rest (made-up facts phrased without numbers or banned words)."""
    issues = []
    allowed = brief_text(brief)
    allowed_numbers = {n.lstrip("£").rstrip("%").replace(",", "") for n in NUMBER.findall(allowed)}
    offer = brief["offer"]
    for unit, pairs in unit_texts(pack).items():
        unit_has_offer = False
        unit_text = " ".join(norm(t) for _, t in pairs)
        for field, text in pairs:
            t = norm(text)
            for n in NUMBER.findall(t):
                if n.lstrip("£").rstrip("%").replace(",", "") not in allowed_numbers:
                    issues.append({"rule": "number", "field": field, "detail": f"{n!r} is not in the brief: {text!r}"})
            for term in brief["not_available"]:
                for m in re.finditer(rf"(?<![\w-]){re.escape(norm(term))}(?![\w-])", t):
                    if not NEGATIONS.search(t[: m.start()]):
                        issues.append(
                            {
                                "rule": "unavailable",
                                "field": field,
                                "detail": f"mentions {term!r}, which the hotel doesn't have: {text!r}",
                            }
                        )
            for word in SUPERLATIVES:
                if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", t) and word not in allowed:
                    issues.append({"rule": "superlative", "field": field, "detail": f"unverifiable {word!r}: {text!r}"})
            if any(trig in t for trig in offer["trigger"]):
                unit_has_offer = True
        if unit_has_offer:
            for group in offer["required"]:
                if not any(alt in unit_text for alt in group):
                    issues.append({"rule": "offer-terms", "field": unit, "detail": f"states the offer but not {group[0]!r}"})
    return issues


def check_pack(pack: dict, brief: dict) -> list[dict]:
    if not isinstance(pack, dict):
        return [{"rule": "shape", "field": "pack", "detail": "not a JSON object"}]
    return check_shape(pack, brief) + check_grounding(pack, brief)
