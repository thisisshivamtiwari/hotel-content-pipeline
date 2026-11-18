"""Run every (model, hotel, sample), judge every final pack, apply the flag review, and summarise.

results/packs.jsonl  one row per (model, hotel, sample, arm): the pack, rule issues, judge issues, cost, time
results/summary.json the tables in the README (generated from packs.jsonl by `summarise`)
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import yaml

from . import checks, judge, llm, pipeline

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
AUDIT = ROOT / "audit" / "labels.yaml"
SAMPLES = 2
BOOT = 10_000


def _one(alias: str, brief: dict, sample: int) -> list[dict]:
    rows = []
    for arm, r in pipeline.run(alias, brief, sample).items():
        j = judge.judge(brief, r["pack"])
        rows.append(
            {
                "model": alias,
                "hotel": brief["id"],
                "sample": sample,
                "arm": arm,
                "pack": r["pack"],
                "rounds": r["rounds"],
                "calls": len(r["log"]),
                "cost_usd": round(sum(c["cost_usd"] for c in r["log"]), 6),
                "seconds": round(sum(c["ms"] for c in r["log"]) / 1000, 2),
                "flagged_for_review": bool(r["last_problems"]) and arm != "oneshot",
                "rule_issues": checks.check_pack(r["pack"], brief),
                "judge_issues": j["issues"],
                "judge_unparsed": j["unparsed"],
                "judge_cost_usd": j["cost_usd"],
            }
        )
    return rows


def run_all(models=tuple(llm.MODELS), hotels=None, workers: int = 4) -> list[dict]:
    briefs = checks.load_briefs()
    jobs = [(m, b, s) for m in models for b in briefs.values() if not hotels or b["id"] in hotels for s in range(SAMPLES)]
    with ThreadPoolExecutor(workers) as ex:
        rows = [row for rs in ex.map(lambda j: _one(*j), jobs) for row in rs]
    return sorted(rows, key=lambda r: (r["model"], r["hotel"], r["sample"], pipeline.ARMS.index(r["arm"])))


def audit_key(row: dict, issue: dict) -> str:
    return f"{row['model']}|{row['hotel']}|{row['sample']}|{row['arm']}|{issue['field']}|{issue['text']}"


def load_audit() -> dict[str, str]:
    """Reviewed verdicts on judge flags: 'real' or 'false-flag'. A judge flag without a verdict counts as real."""
    if not AUDIT.exists():
        return {}
    return {e["key"]: e["verdict"] for e in yaml.safe_load(AUDIT.read_text()) or []}


def apply_audit(rows: list[dict]) -> None:
    verdicts = load_audit()
    for r in rows:
        r["audited_issues"] = [i for i in r["judge_issues"] if verdicts.get(audit_key(r, i), "real") == "real"]
        r["clean"] = not r["rule_issues"] and not r["audited_issues"]


def _paired_ci(a: np.ndarray, b: np.ndarray, seed: int = 7) -> list[float]:
    """95% paired bootstrap interval for mean(b - a) over the same (hotel, sample) items."""
    rng = np.random.default_rng(seed)
    d = b - a
    idx = rng.integers(0, len(d), size=(BOOT, len(d)))
    means = d[idx].mean(axis=1)
    return [round(float(np.percentile(means, 2.5)), 3), round(float(np.percentile(means, 97.5)), 3)]


def summarise(rows: list[dict]) -> dict:
    apply_audit(rows)
    table, deltas = [], []
    for model in sorted({r["model"] for r in rows}):
        by_arm = {}
        for arm in pipeline.ARMS:
            rs = [r for r in rows if r["model"] == model and r["arm"] == arm]
            n = len(rs)
            cost = sum(r["cost_usd"] for r in rs)
            clean = sum(r["clean"] for r in rs)
            rule_counts: dict[str, int] = {}
            for r in rs:
                for i in r["rule_issues"]:
                    rule_counts[i["rule"]] = rule_counts.get(i["rule"], 0) + 1
            row = {
                "model": model,
                "arm": arm,
                "packs": n,
                "clean_packs": clean,
                "rule_clean_packs": sum(not r["rule_issues"] for r in rs),
                "rule_issues": sum(len(r["rule_issues"]) for r in rs),
                "rule_issues_by_type": dict(sorted(rule_counts.items())),
                "judge_flags": sum(len(r["judge_issues"]) for r in rs),
                "unsupported_claims": sum(len(r["audited_issues"]) for r in rs),
                "flagged_for_review": sum(r["flagged_for_review"] for r in rs),
                "flagged_but_clean": sum(r["flagged_for_review"] and r["clean"] for r in rs),
                "shipped_dirty": sum(not r["flagged_for_review"] and not r["clean"] for r in rs),
                "calls_per_pack": round(sum(r["calls"] for r in rs) / n, 2),
                "cost_per_pack_usd": round(cost / n, 4),
                "seconds_per_pack": round(sum(r["seconds"] for r in rs) / n, 1),
                "cost_per_clean_pack_usd": round(cost / clean, 4) if clean else None,
            }
            by_arm[arm] = rs
            table.append(row)
        for arm in ("rules", "full"):
            key = lambda r: (r["hotel"], r["sample"])  # noqa: E731
            base = {key(r): r for r in by_arm["oneshot"]}
            pairs = [(base[key(r)], r) for r in by_arm[arm] if key(r) in base]
            a_clean = np.array([p[0]["clean"] for p in pairs], float)
            b_clean = np.array([p[1]["clean"] for p in pairs], float)
            a_claims = np.array([len(p[0]["audited_issues"]) for p in pairs], float)
            b_claims = np.array([len(p[1]["audited_issues"]) for p in pairs], float)
            deltas.append(
                {
                    "model": model,
                    "arm": arm,
                    "vs": "oneshot",
                    "clean_rate_delta": round(float((b_clean - a_clean).mean()), 3),
                    "clean_rate_ci95": _paired_ci(a_clean, b_clean),
                    "claims_per_pack_delta": round(float((b_claims - a_claims).mean()), 3),
                    "claims_per_pack_ci95": _paired_ci(a_claims, b_claims),
                }
            )
    return {
        "table": table,
        "paired": deltas,
        "hotels": len({r["hotel"] for r in rows}),
        "samples_per_hotel": SAMPLES,
        "judge_unparsed": sum(r["judge_unparsed"] for r in rows),
        "judge_cost_usd": round(sum(r["judge_cost_usd"] for r in rows), 4),
    }


def write(rows: list[dict]) -> dict:
    RESULTS.mkdir(exist_ok=True)
    summary = summarise(rows)
    with (RESULTS / "packs.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    return summary
